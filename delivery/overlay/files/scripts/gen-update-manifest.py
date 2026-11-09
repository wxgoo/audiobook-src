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
  blocking  前端 / 镜像配置 / myreader / tools / scripts 等 —— 必须重新 deploy 或 upgrade
  docs      *.md、docs/**、delivery/overlay/files/docs/** —— 只影响说明，不触发更新操作

只要存在 blocking 改动，requires_dist 就为 true，页面只给重新部署指引，不提供在线更新按钮。
hotfix.files 里的 sha256 取自工作区当前文件，在线更新时会逐个复核，防篡改/防下载不全。
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
# 文档类：改动不需要用户执行任何操作（但仍会体现在 changed 里，方便核对）。
DOCS_PREFIX = ("docs/", "document/", "delivery/overlay/files/docs/",
               "delivery/overlay/files/document/", "delivery/overlay/files/CHANGELOG.md")
DOCS_EXACT = {"CHANGELOG.md", "README.md", "INSTALL_GUIDE.md", "SECURITY.md"}


def git(*args):
    return subprocess.check_output(["git", "-C", ROOT] + list(args)).decode("utf-8", "replace")


def changed_files(base_commit):
    """工作区相对 base_commit 的全部变更（含尚未提交的改动）。"""
    out = {}
    # 已提交的变更
    for line in git("diff", "--name-status", base_commit, "HEAD").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            out[parts[-1]] = parts[0][0]
    # 未提交 / 未跟踪的改动（生成清单时通常正是这一批）
    for line in git("status", "--porcelain", "-z").replace("\x00", "\n").splitlines():
        if len(line) < 4:
            continue
        code, path = line[:2], line[3:]
        out[path] = "D" if "D" in code else "A"
    return out


def classify(path):
    if path in DOCS_EXACT or path.endswith(".md") or path.startswith(DOCS_PREFIX):
        return "docs"
    if path in HOTFIX_EXACT:
        return "hotfix"
    if path.startswith(HOTFIX_PREFIX) and path.endswith(".py") and "/__pycache__/" not in path:
        return "hotfix"
    return "blocking"


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


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
    hotfix, blocking, docs = [], [], []
    for path, status in sorted(changes.items()):
        if path.startswith("update/") and path.endswith("manifest.json"):
            continue  # 清单本身不参与分类
        kind = classify(path)
        (hotfix if kind == "hotfix" else blocking if kind == "blocking" else docs).append(
            {"path": path, "status": status}
        )

    files = []
    for item in hotfix:
        rel = item["path"]
        full = os.path.join(ROOT, rel)
        if item["status"] == "D" or not os.path.isfile(full):
            # 删除文件不能靠「下载」完成，交给重新部署
            blocking.append(dict(item, reason="deleted"))
            continue
        files.append({
            "path": rel,
            "sha256": sha256_of(full),
            "bytes": os.path.getsize(full),
        })

    requires_dist = bool(blocking)
    manifest = {
        "schema": 1,
        "revision": args.revision,
        "base_revision": args.base_revision,
        "version": "4.6.0-build.27",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "summary": args.summary or "功能与修复更新",
        "notes": args.notes,
        "requires_dist": requires_dist,
        "hotfixable": (not requires_dist) and bool(files),
        "reason": (
            "本次改动包含前端产物或镜像级文件，在线替换无法生效，请重新执行 deploy.sh / upgrade.sh"
            if requires_dist else
            "仅后端 Python 代码变更，可在线替换并重启服务，无需重建镜像"
            if files else
            "仅文档或无需运行态变更的内容"
        ),
        "files": files,
        "changed": {
            "hotfix": [i["path"] for i in hotfix],
            "blocking": [i["path"] for i in blocking],
            "docs": [i["path"] for i in docs],
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
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("已生成", args.out)
    print("  revision      :", args.revision, "(base:", args.base_revision + ")")
    print("  requires_dist :", requires_dist, " hotfixable:", manifest["hotfixable"])
    print("  hotfix files  :", len(files), " blocking:", len(blocking), " docs:", len(docs))
    for i in blocking[:8]:
        print("    ! ", i["path"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
