#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""新版本检测与在线热更新服务（Gitee 发布清单驱动）。

设计要点
--------
* 唯一发布源：Gitee 仓库 `wxgoo/audiobook-src` 的 `update/manifest.json`。
  公开仓库，用 raw 直链读取，不需要 token / 不需要容器里装 git。
* 版本口径：`revision`（形如 4.6.0-build.27-r7），不是 `VERSION`。
  VERSION 固定 4.6.0-build.27，本地修订靠 -rN 区分，避免"改了代码却检测不到"。
* 更新分级：
    - manifest.requires_dist = true → 前端产物/镜像级文件有变，只提示重新 deploy/upgrade；
    - 否则 → 按 manifest.files 从 Gitee 下载，逐个 sha256 校验，备份、替换、重启进程。
* 安全边界：只允许 `server.py` 与 `webserver/**/*.py`；所有 .py 先过 compile()；
  旧文件备份到持久化 /data；失败即回滚；提供 Web 一键回滚与宿主机回滚命令。
* 生效方式：Python 是解释型，代码在镜像的可写层里替换后，进程退出
  （supervisor autorestart=true 会拉起）即加载新代码，与既有 AdminRestartServer 一致。
  注意 docker compose down && up -d（换 IMAGE_TAG 重建）会丢弃可写层，所以另有
  /data/update-sync 保存最新清单，供宿主机侧脚本在换镜像时固化热更，避免版本倒退。
"""
import hashlib
import json
import logging
import os
import shutil
import tempfile
import threading
import time
import traceback
from urllib.parse import quote

import requests

from webserver.version import VERSION

OWNER = "wxgoo"
REPO = "audiobook-src"
BRANCH = "master"
MANIFEST_PATH = "update/manifest.json"
GITEE_RAW = "https://gitee.com/{o}/{r}/raw/{b}/{p}"
GITEE_COMMITS = "https://gitee.com/api/v5/repos/{o}/{r}/commits?per_page=5"

def _detect_code_root():
    """从本文件位置往上找项目根（含 server.py + webserver/），不写死层级。

    r7 曾写死"往上三级"，在容器里指到 /var/www 而不是 /var/www/mybooks：
    包内 update/manifest.json 读不到 → 本地修订被兜底成 -r0 → 把自己装的
    那一版误报成「发现新版本」；在线热更新也会把 Python 文件写到 /var/www/
    而不是项目目录。改为按目录特征探测，层级调整也不会再错。
    """
    cur = os.path.abspath(os.path.dirname(__file__))
    for _ in range(6):
        if (os.path.isfile(os.path.join(cur, "server.py"))
                and os.path.isdir(os.path.join(cur, "webserver"))):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    # 兜底：webserver/services/ 往上两级即项目根
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


# /var/www/mybooks（项目根，不再是写死的三级上溯）
CODE_ROOT = _detect_code_root()
LOCAL_MANIFEST = os.path.join(CODE_ROOT, "update", "manifest.json")
DATA_ROOT = "/data"
BACKUP_ROOT = os.path.join(DATA_ROOT, "update-backup")
SYNC_ROOT = os.path.join(DATA_ROOT, "update-sync", "current")
STATE_FILE = os.path.join(DATA_ROOT, "update-state.json")

HOTFIX_EXACT = {"server.py"}
HOTFIX_PREFIX = ("webserver/",)
# 前端产物：静态文件，nginx 直接读 /var/www/mybooks/app/dist，换文件即生效（客户端强刷）。
# 只认这些后缀，避免清单里被塞进可执行脚本/配置；python 代码仍然只走 webserver/ 白名单。
DIST_PREFIX = "app/dist/"
DIST_SUFFIX = (".js", ".css", ".html", ".json", ".map", ".txt",
               ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico",
               ".woff", ".woff2", ".ttf", ".eot")
MANIFEST_TTL = 300  # 秒，页面重复打开不必每次打 Gitee
_lock = threading.Lock()
_cache = {"manifest": None, "ts": 0.0, "error": ""}
_session = requests.Session()
_session.headers.update({"User-Agent": "MyBooks-VersionCheck/1.0"})


def _raw_url(path):
    return GITEE_RAW.format(o=OWNER, r=REPO, b=BRANCH,
                            p=quote(path.lstrip("/"), safe="/"))


class RawFetchError(Exception):
    """Gitee raw 下载失败。带状态码，便于把 451 和其他失败区分开。"""

    def __init__(self, code, body=""):
        self.code = code
        self.body = (body or "").strip()[:120]
        msg = "HTTP %s" % code if code else "网络异常"
        if code == 451:
            msg += "（Gitee 判定该文件含违规内容，拒绝分发）"
        elif self.body and code in (403, 404):
            msg += "（%s）" % self.body
        super().__init__(msg)


def _get(url, timeout=20, tries=3):
    """Gitee raw 偶发 5xx / 408 / 429，重试有意义；4xx 是确定性拒绝，
    重试只是把 30 秒拖成 90 秒（451 尤其：内容审核拦了，试一百次也一样）。"""
    last = None
    for i in range(tries):
        try:
            r = _session.get(url, timeout=timeout, allow_redirects=True)
            if r.status_code == 200 and r.content:
                return r.content
            last = RawFetchError(r.status_code, r.text)
            if 400 <= r.status_code < 500 and r.status_code not in (408, 429):
                raise last
        except RawFetchError:
            raise
        except Exception as e:  # noqa: BLE001 - 网络异常统一重试
            last = e
        if i < tries - 1:
            time.sleep(0.8 * (i + 1))
    raise last


def read_local_manifest():
    """包内基线。读不到 / 不含 revision 时返回空 dict，调用方必须显式处理，
    绝不能悄悄把当前修订当成 -r0 再去比对远端（r7 现场就是这样把自己误报成新版本）。
    """
    try:
        with open(LOCAL_MANIFEST, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("revision"):
            return data
        logging.warning("[VERSION] 包内发布清单缺少 revision: %s", LOCAL_MANIFEST)
    except Exception as e:  # noqa: BLE001 - 文件不存在/损坏都按"基线不可用"处理
        logging.warning("[VERSION] 读取包内发布清单失败 %s: %s", LOCAL_MANIFEST, e)
    return {}


def read_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"current_revision": "", "history": []}


def write_state(state):
    os.makedirs(DATA_ROOT, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


def fetch_manifest(force=False, ttl=MANIFEST_TTL):
    """读取远端发布清单；失败不抛异常，返回 (manifest, error)。"""
    now = time.time()
    if not force and _cache["manifest"] and now - _cache["ts"] < ttl:
        return _cache["manifest"], ""
    try:
        raw = _get(_raw_url(MANIFEST_PATH), timeout=20)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict) or not data.get("revision"):
            raise ValueError("manifest 缺少 revision")
        _cache.update(manifest=data, ts=now, error="")
        return data, ""
    except Exception as e:  # noqa: BLE001
        err = "%s: %s" % (type(e).__name__, e)
        logging.warning("[VERSION] 拉取发布清单失败: %s", err)
        _cache["ts"] = now - ttl + 30  # 30 秒后允许再试，别把失败缓存满 5 分钟
        return _cache["manifest"], err


def fetch_latest_commits():
    try:
        raw = _get(GITEE_COMMITS.format(o=OWNER, r=REPO), timeout=15, tries=2)
        rows = json.loads(raw.decode("utf-8"))
        return [{
            "sha": (x.get("sha") or "")[:10],
            "message": ((x.get("commit") or {}).get("message") or "").strip().split("\n")[0],
            "date": ((x.get("commit") or {}).get("author") or {}).get("date", "")[:10],
        } for x in rows[:5]]
    except Exception:
        return []


def _rev_num(rev):
    """4.6.0-build.27-r7 → 7；无 -r 后缀返回 0。"""
    try:
        tail = str(rev).rsplit("-r", 1)
        return int(tail[1]) if len(tail) == 2 else 0
    except (ValueError, IndexError):
        return 0


def is_allowed(path):
    p = (path or "").lstrip("/")
    if "\\" in p or p.startswith("..") or "/../" in p or p.startswith("/"):
        return False
    if p in HOTFIX_EXACT or (p.startswith(HOTFIX_PREFIX) and p.endswith(".py")):
        return True
    # 前端产物：只允许 app/dist/ 下的静态文件（后缀白名单），其它一律拒绝
    return p.startswith(DIST_PREFIX) and p.endswith(DIST_SUFFIX)


def list_backups():
    try:
        names = sorted(os.listdir(BACKUP_ROOT), reverse=True)
    except Exception:
        return []
    out = []
    for n in names[:8]:
        meta = os.path.join(BACKUP_ROOT, n, "meta.json")
        if os.path.isfile(meta):
            try:
                with open(meta, "r", encoding="utf-8") as f:
                    d = json.load(f)
                out.append({"id": n, "from": d.get("from_revision", ""),
                            "to": d.get("to_revision", ""), "date": d.get("date", ""),
                            "files": len(d.get("files", []))})
            except Exception:
                pass
    return out


def status(force=False):
    """页面主接口：当前版本 / 最新版本 / 更新方式与可执行动作。"""
    local = read_local_manifest()
    state = read_state()
    baseline_ok = bool(local.get("revision"))
    cur = local.get("revision") or (VERSION + "-r0")
    remote, err = fetch_manifest(force=force)
    latest = remote or {}
    # 基线不可信时一律不报「有新版本」：宁可页面显示"基线缺失"告警，也不能把
    # 自己刚部署的那一版当成待更新版本，误导管理员反复重新部署。
    # 远端比本地旧（例如分支回滚 / 误发了老清单）时同样不提示。
    has = bool(baseline_ok and latest and latest.get("revision")
               and latest["revision"] != cur
               and _rev_num(latest["revision"]) >= _rev_num(cur))

    mode = "none"
    dist_files = latest.get("dist_files") or []
    dist_deleted = latest.get("dist_deleted") or []
    py_files = latest.get("files") or []
    # 前端产物能否随这次在线更新一起替换：清单显式标了 dist_hotfixable，
    # 且确实带了文件（新增/修改）或删除项。老清单没这个字段 → 一律按需重新部署处理。
    dist_ok = bool(latest.get("dist_hotfixable")) and bool(dist_files or dist_deleted)
    if has:
        if latest.get("requires_dist") and not dist_ok:
            mode = "redeploy"
        elif not (py_files or dist_files or dist_deleted):
            mode = "docs_only"
        elif latest.get("base_revision") and latest["base_revision"] != cur:
            mode = "redeploy"  # 跨版本，增量补丁不能直接用
        elif not latest.get("hotfixable"):
            mode = "redeploy"
        else:
            mode = "hotfix"

    state_rev = state.get("current_revision", "")
    need_persist = bool(state_rev and state_rev != cur and _rev_num(state_rev) > _rev_num(cur))
    return {
        "err": "ok",
        "version": VERSION,
        "current": {
            "revision": cur,
            "date": local.get("date", ""),
            "summary": local.get("summary", ""),
            "requires_dist": local.get("requires_dist", False),
        },
        "latest": {
            "revision": latest.get("revision", ""),
            "date": latest.get("date", ""),
            "summary": latest.get("summary", ""),
            "notes": latest.get("notes", []),
            "reason": latest.get("reason", ""),
            "base_revision": latest.get("base_revision", ""),
            "requires_dist": latest.get("requires_dist", False),
            "changed": latest.get("changed", {}),
            "files": [{"path": f.get("path"), "bytes": f.get("bytes")}
                      for f in latest.get("files", [])],
            "dist_files": [{"path": f.get("path"), "bytes": f.get("bytes")}
                           for f in dist_files],
            "dist_deleted": dist_deleted,
            "dist_hotfixable": dist_ok,
            "dist_bytes": sum(int(f.get("bytes") or 0) for f in dist_files),
            "deploy_commands": latest.get("deploy_commands", []),
        } if latest else None,
        "has_update": has,
        "mode": mode,
        "can_apply": mode == "hotfix",
        # 基线自检：包内 update/manifest.json 是否读到了有效 revision
        "baseline_ok": baseline_ok,
        "baseline_path": LOCAL_MANIFEST,
        "baseline_code_root": CODE_ROOT,
        "baseline_error": "" if baseline_ok else (
            "包内发布清单缺失或不含 revision，本地修订不可信；"
            "请确认镜像里包含 update/manifest.json（%s）" % LOCAL_MANIFEST
        ),
        "check_error": err,
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "commits": fetch_latest_commits() if force else [],
        "backups": list_backups(),
        "need_persist": need_persist,
        "persist_revision": state_rev if need_persist else "",
        "auto_check": None,  # handler 层从 CONF 注入
    }


def _backup(files, from_rev, to_rev):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(BACKUP_ROOT, stamp + "-" + to_rev.replace("/", "_"))
    os.makedirs(dest, exist_ok=True)
    saved = []
    created = []
    for rel in files:
        src = os.path.join(CODE_ROOT, rel)
        if os.path.isfile(src):
            dst = os.path.join(dest, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            saved.append(rel)
        else:
            # 本次新增的文件：回滚时要删掉，否则会留下「半新半旧」的代码树
            created.append(rel)
    with open(os.path.join(dest, "meta.json"), "w", encoding="utf-8") as f:
        json.dump({"from_revision": from_rev, "to_revision": to_rev,
                   "date": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "files": saved, "created": created}, f, ensure_ascii=False, indent=2)
    return dest


def _download_failure(path, err):
    """把下载异常翻译成管理员照着能做的提示。

    451 是**发布侧**问题：Gitee 的内容审核拦了仓库里某个文件（源码里的敏感词组、
    或者是被误判的正文），重试、换网络、等一会儿都无用，只能由发布者改掉那个文件；
    本机这边只能整包部署绕过。历史上 r18 就栽在这里 —— 某个文件里的示例文本
    含敏感词被判 451，在线更新下到第二个文件就断了。
    """
    code = getattr(err, "code", 0)
    if code == 451:
        return ("下载被 Gitee 拦截（451，内容审核）：%s\n"
                "这是发布侧的文件内容问题，与本机网络无关，重试无效。\n"
                "可选：① 用部署包整包替换；② 等发布者发一版修正后的清单再更新。"
                % path)
    return "下载失败：%s（%s）" % (path, err)


def apply_update(revision):
    """按发布清单执行在线热更新。返回 dict；restart=True 时由 handler 触发进程重启。"""
    with _lock:
        return _apply_locked(revision)


def _apply_locked(revision):
    remote, err = fetch_manifest(force=True)
    if not remote:
        raise RuntimeError("无法读取 Gitee 发布清单：%s" % err)
    if remote.get("revision") != revision:
        raise RuntimeError("发布清单已变化（%s），请刷新页面重新检测" % remote.get("revision"))
    # 前端产物可随本次更新一起替换（清单标了 dist_hotfixable 才允许）；
    # 其余 blocking（Dockerfile / conf / 依赖 / myreader）仍然只能重新部署。
    dist_ok = bool(remote.get("dist_hotfixable"))
    if (remote.get("requires_dist") and not dist_ok) or not remote.get("hotfixable"):
        raise RuntimeError("本次更新包含镜像级文件，请把 .env 的 IMAGE_TAG 换成新 tag 后重新 docker compose up -d")

    local = read_local_manifest()
    if not local.get("revision"):
        raise RuntimeError("包内发布清单缺失，本地修订不可信，禁止在线替换文件；请重新部署一次")
    cur = local["revision"]
    base = remote.get("base_revision", "")
    if base and base != cur:
        raise RuntimeError("本地修订是 %s，本补丁要求 %s，跨版本请重新部署" % (cur, base))

    entries = list(remote.get("files") or [])
    deleted = []
    if dist_ok:
        entries += list(remote.get("dist_files") or [])
        deleted = list(remote.get("dist_deleted") or [])
    if not entries and not deleted:
        raise RuntimeError("发布清单没有可更新的文件")

    paths = []
    for item in entries:
        p = item.get("path", "")
        if not is_allowed(p):
            raise RuntimeError("发布清单含不允许在线替换的路径：%s" % p)
        if not item.get("sha256") or not item.get("bytes"):
            raise RuntimeError("发布清单缺少校验值：%s" % p)
        paths.append(p)
    for p in deleted:
        if not is_allowed(p):
            raise RuntimeError("发布清单含不允许删除的路径：%s" % p)

    # 1) 全部下载并校验，任何一个失败都不动线上文件
    tmp = tempfile.mkdtemp(prefix="mybooks-update-")
    try:
        payloads = {}
        for item in entries:
            p, expect, size = item["path"], item["sha256"], int(item["bytes"])
            try:
                data = _get(_raw_url(p), timeout=30)
            except Exception as e:  # noqa: BLE001 - 统一转成「哪个文件 + 怎么办」
                raise RuntimeError(_download_failure(p, e))
            if len(data) != size or hashlib.sha256(data).hexdigest() != expect:
                raise RuntimeError("下载内容与发布清单不符（sha256 / 大小）：%s" % p)
            if p.endswith(".py"):
                try:
                    compile(data.decode("utf-8"), p, "exec")
                except (SyntaxError, UnicodeDecodeError) as e:
                    raise RuntimeError("语法检查未通过：%s（%s）" % (p, e))
            payloads[p] = data
            logging.info("[VERSION] 已校验 %s (%d bytes)", p, size)

        # 2) 备份旧文件到持久化卷（含本次要删除的前端文件，回滚时能还原）
        if not os.path.isdir(DATA_ROOT):
            raise RuntimeError("数据卷 /data 不可用，拒绝在线更新")
        backup = _backup(paths + deleted, cur, revision)

        # 3) 原子替换。index.html 放最后：万一中途失败，旧首页仍指向旧 chunk，
        #    不会出现「新首页 + 半套新 chunk」的白屏。
        ordered = sorted(payloads.items(), key=lambda kv: (kv[0].endswith("app/dist/index.html"), kv[0]))
        for p, data in ordered:
            dst = os.path.join(CODE_ROOT, p)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            new = dst + ".update-new"
            with open(new, "wb") as f:
                f.write(data)
            os.replace(new, dst)
        # 本次删除的前端文件（如旧 chunk）：直接删，回滚时按备份还原
        for rel in deleted:
            dst = os.path.join(CODE_ROOT, rel)
            if os.path.isfile(dst):
                try:
                    os.remove(dst)
                except OSError:
                    logging.warning("[VERSION] 删除旧前端文件失败：%s", rel)
        # 清掉旧字节码，避免 .pyc 抢先加载
        for rel in set(os.path.dirname(p) for p in paths if p.endswith(".py")):
            cache = os.path.join(CODE_ROOT, rel, "__pycache__")
            if os.path.isdir(cache):
                shutil.rmtree(cache, ignore_errors=True)

        # 4) 写回本地清单，让页面不再提示"有新版本"
        os.makedirs(os.path.dirname(LOCAL_MANIFEST), exist_ok=True)
        with open(LOCAL_MANIFEST + ".tmp", "w", encoding="utf-8") as f:
            json.dump(remote, f, ensure_ascii=False, indent=2)
        os.replace(LOCAL_MANIFEST + ".tmp", LOCAL_MANIFEST)

        # 5) 同步到 /data 供宿主机侧脚本读取（换镜像重建时会用到）
        try:
            if os.path.isdir(SYNC_ROOT):
                shutil.rmtree(SYNC_ROOT)
            os.makedirs(SYNC_ROOT, exist_ok=True)
            with open(os.path.join(SYNC_ROOT, "manifest.json"), "w", encoding="utf-8") as f:
                json.dump(remote, f, ensure_ascii=False, indent=2)
            for p, data in payloads.items():
                dst = os.path.join(SYNC_ROOT, p)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, "wb") as f:
                    f.write(data)
            for rel in deleted:
                stale = os.path.join(SYNC_ROOT, rel)
                if os.path.isfile(stale):
                    os.remove(stale)
        except Exception:
            logging.warning("[VERSION] 写同步区失败（不影响本次生效）:\n%s", traceback.format_exc())

        state = read_state()
        state["current_revision"] = revision
        state.setdefault("history", []).insert(0, {
            "revision": revision, "date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "files": paths + deleted, "backup": backup,
        })
        state["history"] = state["history"][:10]
        write_state(state)

        _cache.update(manifest=remote, ts=time.time(), error="")
        return {"err": "ok", "revision": revision,
                "files": len(paths) + len(deleted),
                "dist_files": len([p for p in paths if p.startswith(DIST_PREFIX)]),
                "backup": backup, "restart": True,
                "msg": "已更新 %d 个文件，服务正在重启" % (len(paths) + len(deleted))}
    except Exception:
        # 下载/校验阶段失败：线上文件一个都没动
        raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def rollback(backup_id=None):
    """从最近一次（或指定）备份还原文件。"""
    with _lock:
        if not backup_id:
            items = list_backups()
            if not items:
                raise RuntimeError("没有可用的备份")
            backup_id = items[0]["id"]
        if "/" in backup_id or "\\" in backup_id or backup_id.startswith(".."):
            raise RuntimeError("非法备份编号")
        root = os.path.join(BACKUP_ROOT, backup_id)
        meta_path = os.path.join(root, "meta.json")
        if not os.path.isfile(meta_path):
            raise RuntimeError("备份不存在：%s" % backup_id)
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        restored = []
        for rel in meta.get("files", []):
            if not is_allowed(rel):
                continue
            src = os.path.join(root, rel)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(CODE_ROOT, rel))
                restored.append(rel)
        # 本次在线更新新建、旧版本里没有的文件要删掉，不能留半套新代码
        for rel in meta.get("created", []):
            if not is_allowed(rel):
                continue
            dst = os.path.join(CODE_ROOT, rel)
            if os.path.isfile(dst):
                os.remove(dst)
        old_rev = meta.get("from_revision", "")
        local = read_local_manifest()
        local["revision"] = old_rev
        local["summary"] = "已回滚到 %s" % old_rev
        with open(LOCAL_MANIFEST + ".tmp", "w", encoding="utf-8") as f:
            json.dump(local, f, ensure_ascii=False, indent=2)
        os.replace(LOCAL_MANIFEST + ".tmp", LOCAL_MANIFEST)
        state = read_state()
        state["current_revision"] = old_rev
        write_state(state)
        if os.path.isdir(SYNC_ROOT):
            shutil.rmtree(SYNC_ROOT, ignore_errors=True)
        return {"err": "ok", "revision": old_rev, "files": len(restored),
                "restart": True, "msg": "已回滚 %d 个文件，服务正在重启" % len(restored)}
