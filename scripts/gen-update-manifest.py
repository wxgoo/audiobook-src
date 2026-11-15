#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""生成 Gitee 发布清单 update/manifest.json。

在线「新版本检测」把这份清单当作唯一发布源：容器启动时把包内清单当作本地基线，
页面检测时请求 Gitee raw 上的同一份文件，比对 revision 决定是否提示更新。

用法（在仓库根目录）：

    python3 scripts/gen-update-manifest.py \
        --revision 4.6.0-build.27-r8 \
        --base-revision 4.6.0-build.27-r7 \
        --base-commit <上一版 commit sha> \
        --summary "修了什么"

判定规则（决定「点一下就能更新」还是「必须重新部署」）：

  hotfix    server.py、webserver/**/*.py —— 纯 Python，容器内替换 + 重启进程即生效
  dist      app/dist/** —— 前端产物，可在线替换「本次变化的文件」，但客户端要强刷
  blocking  镜像配置 / myreader / tools / 系统级改动 —— 必须重新 deploy 或 upgrade
  docs      *.md、docs/**、delivery/overlay/files/docs/** —— 只影响说明，不触发更新操作
  ignored   app/dist/ 下但不在消费端 DIST_SUFFIX 白名单里的构建副产物（如 _nuxt/LICENSES）
            —— 绝不写进 dist_files（否则 apply() 会拒绝整份清单），也不算 blocking

dist 变更是否允许在线更新，看规模：文件数与总字节在阈值内（默认 300 个 / 20MB）
则写进 dist_files，页面可一键更新；超过阈值（例如整包重建 757 个文件）或含
非静态资源，仍退回「重新部署」——逐个 raw 下载几百个文件既慢又容易被限流。

⚠️ requires_dist 的语义保持不变（含前端产物即为 true），老版本页面看到 true 仍然
只显示重新部署指引；新版本额外读 dist_hotfixable 才放开在线更新按钮。这样新旧
两种前端都不会出现「只更了 py 没更 dist」的半新半旧状态。
hotfix.files / dist_files 里的 sha256 取自 git blob，在线更新时逐个复核，防篡改/防下载不全。
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "update", "manifest.json")

# 能在线热替换的路径：镜像里 COPY 进来的纯 Python 代码，且容器运行用户有写权限。
HOTFIX_EXACT = {"server.py"}
HOTFIX_PREFIX = ("webserver/",)
# 前端产物：静态文件，nginx 直接读，替换文件即刻生效（客户端强刷即可）。
DIST_PREFIX = "app/dist/"
DIST_SUFFIX = (".js", ".css", ".html", ".json", ".map", ".txt",
               ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico",
               ".woff", ".woff2", ".ttf", ".eot")
# ⚠️ r39 事故（勿恢复）：这里曾用 DIST_EXACT = {"app/dist/_nuxt/LICENSES"} 单方面
# 把无后缀的许可证清单放行进 dist_files，但消费端 version_check.is_allowed() 只认
# DIST_SUFFIX 白名单，apply() 在下载任何文件之前就抛
# 「发布清单含不允许在线替换的路径」，整次在线更新被卡死。
# 结论：app/dist/ 下凡不在消费端白名单里的路径一律「明确忽略」——既不能投递
# （投不了），也不能算 blocking（不该把一次纯前端修订顶成必须重新部署）。
# 这类文件只是构建副产物（webpack 的第三方许可证文本），运行时不加载。
# 在线更新 dist 的规模上限：超过就不走页内更新，退回重新部署。
# Nuxt 每次构建都会重写全部路由 html（buildId 变），一个异步 chunk 改动还会连带重写引用
# 它的 chunk——实测「只改一个设置页」= 210 个文件 / 3.4MB，所以 200 那个值每次都会误伤。
# 现取 300：够覆盖一次小改，仍能拦住整包重建（757 文件 / 71MB）。
DIST_HOTFIX_MAX_FILES = 300
DIST_HOTFIX_MAX_BYTES = 20 * 1024 * 1024
# 文档类：改动不需要用户执行任何操作（但仍会体现在 changed 里，方便核对）。
DOCS_PREFIX = ("docs/", "document/", "delivery/overlay/files/docs/",
               "delivery/overlay/files/document/", "delivery/overlay/files/CHANGELOG.md")
DOCS_EXACT = {"CHANGELOG.md", "README.md", "SECURITY.md",
              # §维护者侧工具§（build.27-r12）：只在出清单的开发机/git 上跑，
              # NAS 运行态不执行——它的改动不阻塞在线热更，随下次整包部署落地。
              "scripts/gen-update-manifest.py"}
# 前端源码：本身不投递，改了必须重建成 dist 才算数（见主流程的 dist 联动校验）。
APP_SRC_PREFIX = ("app/src/", "app/locales/")


def git(*args):
    # core.quotepath=false：否则 git diff 会把中文路径写成 "docs/\345\234..."
    # 这样的八进制转义串，发布清单里就会出现一堆不可读的路径。
    return subprocess.check_output(
        ["git", "-C", ROOT, "-c", "core.quotepath=false"] + list(args)
    ).decode("utf-8", "replace")


def clean_path(p):
    return p.strip().strip('"')


def changed_files(base_commit):
    """工作区相对 base_commit 的全部变更（含尚未提交的改动）。"""
    out = {}
    # 已提交的变更
    for line in git("diff", "--no-renames", "--name-status", base_commit, "HEAD").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            out[clean_path(parts[-1])] = parts[0][0]
    # 未提交 / 未跟踪的改动（生成清单时通常正是这一批）。
    # -z + --no-renames：既不触发 core.quotepath 的八进制转义，也不会多出一行
    # 「旧路径」把已删除的文件误当成新增。
    for line in git("status", "--porcelain", "-z", "--no-renames").replace("\x00", "\n").splitlines():
        if len(line) < 4:
            continue
        code, path = line[:2], clean_path(line[3:])
        out[path] = "D" if "D" in code else "A"
    return out


def classify(path):
    if path in DOCS_EXACT or path.endswith(".md") or path.startswith(DOCS_PREFIX):
        return "docs"
    # §tests/ 不进部署包§（pack.sh 有意排除）：
    # 测试改动既不能通过在线热更投递（apply 只收 server.py + webserver/**/*.py），
    # 也不存在于部署目录里——按 docs 同口径归档，不能让一个测试文件的改动把
    # 整次纯后端修订顶成「必须重新部署」（build.27-r12 现场教训）。
    if path == "tests" or path.startswith("tests/"):
        return "docs"
    # scripts/ 只在开发机与宿主机跑（build 期的 check-myreader-links.sh 是 COPY 到
    # /tmp 用完即弃），容器运行态不读，改动不阻塞在线热更。
    if path.startswith("scripts/"):
        return "docs"
    # 前端源码 / 语言包：不是投递单元，真正的投递物是重建后的 app/dist
    if path.startswith(APP_SRC_PREFIX):
        return "appsrc"
    if path in HOTFIX_EXACT:
        return "hotfix"
    if path.startswith(HOTFIX_PREFIX) and path.endswith(".py") and "/__pycache__/" not in path:
        return "hotfix"
    # 前端产物：只认 app/dist/ 下的静态文件，其它 app/ 源码改动仍是 blocking
    if path.startswith(DIST_PREFIX) and path.endswith(DIST_SUFFIX):
        return "dist"
    # 消费端白名单不认的 dist 路径：绝不能进 dist_files / dist_deleted，
    # 否则旧版本站点的 apply() 会直接拒绝整份清单。明确忽略并计入 changed.ignored。
    if path.startswith(DIST_PREFIX):
        return "ignored"
    return "blocking"


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob_bytes(rel):
    """HEAD 里该路径的字节内容——热更下载（Gitee raw）拿到的就是它。

    §必须按 git blob 算哈希§（build.27-r12 现场教训）：清单若用工作区文件计算，
    Windows 检出是 CRLF、提交进 git / Gitee raw 是 LF（.gitattributes 强制），
    一个换行符之差会让六份文件的 sha256 全部对不上，热更在第一份文件就中止。
    未跟踪的新文件回退到工作区读取（按流程应先提交再出清单）。
    """
    r = subprocess.run(["git", "-C", ROOT, "show", "HEAD:" + rel], capture_output=True)
    if r.returncode == 0:
        return r.stdout
    with open(os.path.join(ROOT, rel), "rb") as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--revision", required=True, help="本次发布修订号，如 4.6.0-build.27-r8")
    ap.add_argument("--base-revision", required=True, help="上一版修订号，在线更新的前置条件")
    ap.add_argument("--base-commit", required=True, help="上一版在 Gitee 上的 commit sha")
    ap.add_argument("--summary", default="", help="一句话更新说明")
    ap.add_argument("--notes", action="append", default=[], help="可重复，逐条详细变更")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    changes = changed_files(args.base_commit)
    hotfix, blocking, docs, dist, appsrc, ignored = [], [], [], [], [], []
    for path, status in sorted(changes.items()):
        if path.startswith("update/") and path.endswith("manifest.json"):
            continue  # 清单本身不参与分类
        kind = classify(path)
        target = {"hotfix": hotfix, "blocking": blocking, "docs": docs,
                  "dist": dist, "appsrc": appsrc, "ignored": ignored}[kind]
        target.append({"path": path, "status": status})

    files = []
    for item in hotfix:
        rel = item["path"]
        full = os.path.join(ROOT, rel)
        if item["status"] == "D" or not os.path.isfile(full):
            # 删除文件不能靠「下载」完成，交给重新部署
            blocking.append(dict(item, reason="deleted"))
            continue
        blob = git_blob_bytes(rel)
        files.append({
            "path": rel,
            "sha256": hashlib.sha256(blob).hexdigest(),
            "bytes": len(blob),
        })
        try:
            disk_sha = sha256_of(full)
            if disk_sha != files[-1]["sha256"]:
                # 换行符/编码漂移提示：不影响清单正确性（清单以 git blob 为准），
                # 但说明工作区与仓库形态不一致，出部署包前留意
                print("  !! 工作区与 git 内容不一致（多为换行差异，清单已按 git 内容计算）：%s" % rel)
        except OSError:
            pass

    # 前端源码改了但没有任何 dist 变更：多半忘了构建，或构建产物没提交。
    # 这种修订不能在线更新（页面按清单投递 dist，源码不在投递范围内）。
    if appsrc and not dist:
        blocking.extend(appsrc)
        print("  ! app/src 或 app/locales 有改动，但 app/dist 无对应变更——"
              "先 `cd app && bash build.sh` 并提交 dist，再重新出清单")

    # 前端产物：新增/修改逐个登记 sha256，删除的单独记（apply 时删除、回滚时还原）
    dist_files, dist_deleted, dist_oversize = [], [], ""
    for item in dist:
        rel = item["path"]
        if item["status"] == "D":
            dist_deleted.append(rel)
            continue
        blob = git_blob_bytes(rel)
        dist_files.append({
            "path": rel,
            "sha256": hashlib.sha256(blob).hexdigest(),
            "bytes": len(blob),
        })
    dist_bytes = sum(f["bytes"] for f in dist_files)
    dist_hotfixable = bool(dist_files or dist_deleted)
    if dist_hotfixable and len(dist_files) > DIST_HOTFIX_MAX_FILES:
        dist_oversize = "前端文件 %d 个，超过在线更新上限 %d 个" % (
            len(dist_files), DIST_HOTFIX_MAX_FILES)
    elif dist_hotfixable and dist_bytes > DIST_HOTFIX_MAX_BYTES:
        dist_oversize = "前端产物 %.1fMB，超过在线更新上限 %.0fMB" % (
            dist_bytes / 1048576.0, DIST_HOTFIX_MAX_BYTES / 1048576.0)
    if dist_oversize:
        # 规模太大（整包重建）：整批退回 blocking，页面只给重新部署指引
        blocking.extend(dist)
        dist_files, dist_deleted = [], []
        dist_hotfixable = False
        print("  ! 前端产物改为必须重新部署：%s" % dist_oversize)

    # requires_dist 保持「含前端产物即 true」的老语义：老版本页面看到 true 只显示
    # 重新部署指引，不会出现「只更 py 没更 dist」的半新半旧；新版本另看 dist_hotfixable。
    requires_dist = bool(blocking) or bool(dist_files or dist_deleted)
    manifest = {
        "schema": 1,
        "revision": args.revision,
        "base_revision": args.base_revision,
        "version": "4.6.0-build.27",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "summary": args.summary or "功能与修复更新",
        "notes": args.notes,
        "requires_dist": requires_dist,
        "hotfixable": (not blocking) and bool(files or dist_files or dist_deleted),
        "dist_hotfixable": dist_hotfixable,
        "dist_files": dist_files,
        "dist_deleted": dist_deleted,
        "reason": (
            "本次改动包含镜像级文件（Dockerfile / conf / 依赖 / 工具链 / 删除的前端文件），"
            "在线替换无法生效，请把 .env 的 IMAGE_TAG 换成新 tag 后重新 docker compose up -d"
            if blocking else
            "包含前端产物与后端 Python 代码，可在线替换并重启服务；完成后请 Ctrl+Shift+R 强制刷新"
            if (dist_files or dist_deleted) and files else
            "仅前端产物变更（后端代码未动），可在线替换；完成后请 Ctrl+Shift+R 强制刷新"
            if dist_files or dist_deleted else
            "仅后端 Python 代码变更，可在线替换并重启服务，无需重建镜像"
            if files else
            "仅文档或无需运行态变更的内容"
        ),
        "files": files,
        "changed": {
            "hotfix": [i["path"] for i in hotfix],
            "dist": [i["path"] for i in dist],
            "appsrc": [i["path"] for i in appsrc],
            "blocking": [i["path"] for i in blocking],
            "docs": [i["path"] for i in docs],
            "ignored": [i["path"] for i in ignored],
        },
        "deploy_commands": [
            "cd /volume1/docker",
            "sha256sum -c audiobook-deploy-%s.tar.gz.sha256" % args.revision,
            "docker compose -f audiobook/docker-compose.yml down 2>/dev/null",
            "mv audiobook audiobook.old-$(date +%m%d-%H%M)",
            "tar -xzf audiobook-deploy-%s.tar.gz" % args.revision,
            "cd /volume1/docker/audiobook && sh scripts/deploy.sh",
        ],
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    # 显式 LF：Windows 上默认 newline=None 会写成 CRLF，虽然 JSON 仍能解析，
    # 但部署包与 Gitee raw 上的同一份清单会逐字节不一致，核对时容易误判。
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("已生成", args.out)
    print("  revision      :", args.revision, "(base:", args.base_revision + ")")
    print("  requires_dist :", requires_dist, " hotfixable:", manifest["hotfixable"],
          " dist_hotfixable:", dist_hotfixable)
    print("  hotfix files  :", len(files), " dist:", len(dist_files),
          "(%.1fMB, %d deleted)" % (dist_bytes / 1048576.0, len(dist_deleted)),
          " blocking:", len(blocking), " docs:", len(docs), " ignored:", len(ignored))
    for i in blocking[:8]:
        print("    ! ", i["path"])
    for i in ignored[:8]:
        print("    - ", i["path"], "(消费端白名单不认，不投递)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
