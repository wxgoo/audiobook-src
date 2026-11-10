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
DOCS_EXACT = {"CHANGELOG.md", "README.md", "INSTALL_GUIDE.md", "SECURITY.md",
              # §维护者侧工具§（build.27-r12）：只在出清单的开发机/git 上跑，
              # NAS 运行态不执行——它的改动不阻塞在线热更，随下次整包部署落地。
              "scripts/gen-update-manifest.py"}


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
    # §tests/ 不进部署包§（pack.sh 有意排除，见 docs/部署包说明.md「包内容裁剪」）：
    # 测试改动既不能通过在线热更投递（apply 只收 server.py + webserver/**/*.py），
    # 也不存在于部署目录里——按 docs 同口径归档，不能让一个测试文件的改动把
    # 整次纯后端修订顶成「必须重新部署」（build.27-r12 现场教训）。
    if path == "tests" or path.startswith("tests/"):
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
    # 显式 LF：Windows 上默认 newline=None 会写成 CRLF，虽然 JSON 仍能解析，
    # 但部署包与 Gitee raw 上的同一份清单会逐字节不一致，核对时容易误判。
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
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
