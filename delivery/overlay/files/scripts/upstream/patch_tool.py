#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""按主题（A/B/C/D）从上游检出生成补丁，并检查上游是否已修。

只用标准库，NAS 容器内可直接跑：

    python3 scripts/upstream/patch_tool.py list
    python3 scripts/upstream/patch_tool.py export A --upstream /tmp/mybooks-4.6.0 --out upstream-patches
    python3 scripts/upstream/patch_tool.py status --upstream /tmp/mybooks-4.6.0

说明
----
- 左侧是上游检出目录，右侧是本仓库工作区；导出的是「本仓库相对上游」的 unified diff，
  可直接 `git apply --check`。
- 主题只声明文件清单，不保证逐条精确拆分；提 PR 时按 docs/上游跟进/*.md 的条目再手工剔除。
- `status` 用少量「修复标记」做启发式判断，命中只代表上游可能出现同类实现，仍需人工确认。
"""

import argparse
import difflib
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TOPICS = {
    "A": {
        "title": "安全与元数据",
        "files": [
            "webserver/handlers/base.py",
            "webserver/handlers/book.py",
            "webserver/services/monitor_service.py",
            "webserver/services/batch_add.py",
            "webserver/services/converter.py",
        ],
        "markers": [
            ("A1 js CORS/堆栈", "webserver/handlers/base.py", "_is_same_site_origin"),
            ("A2 PDF/TXT 作者", "webserver/handlers/book.py", "prefer_filename"),
            ("A5 CSV 封面 SSRF", "webserver/services/batch_add.py", "ipaddress"),
        ],
    },
    "B": {
        "title": "扫描与导入",
        "files": [
            "webserver/services/scan_service.py",
            "webserver/handlers/scan.py",
            "webserver/services/audios_import.py",
            "webserver/services/monitor_service.py",
            "docker/start.sh",
        ],
        "markers": [
            ("B4 do_import 锁泄漏", "webserver/services/scan_service.py", "static_is_importing = True"),
        ],
    },
    "C": {
        "title": "音频与播放",
        "files": [
            "webserver/handlers/audio.py",
            "app/src/pages/audio/_id.vue",
        ],
        "markers": [
            ("C6 AudioFile 响应头", "webserver/handlers/audio.py", "Content-Range"),
        ],
    },
    "D": {
        "title": "功能与权限",
        "files": [
            "webserver/handlers/book.py",
            "webserver/handlers/user.py",
            "webserver/models.py",
            "webserver/services/book_access_service.py",
        ],
        "markers": [
            ("D8 上传权限口径", "webserver/handlers/user.py", "can_upload"),
        ],
    },
}


def _read_lines(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.readlines()


def _rel_path(rel):
    return rel.replace(os.sep, "/")


def cmd_list(_args):
    for key, topic in TOPICS.items():
        print("%s  %s  (%d files)" % (key, topic["title"], len(topic["files"])))
    return 0


def cmd_export(args):
    topic = TOPICS.get(args.topic)
    if not topic:
        print("unknown topic: %s (choose A/B/C/D)" % args.topic)
        return 2
    outdir = args.out or os.path.join(os.getcwd(), "upstream-patches")
    os.makedirs(outdir, exist_ok=True)

    parts = []
    skipped = []
    for rel in topic["files"]:
        up_path = os.path.join(args.upstream, rel)
        fork_path = os.path.join(REPO_ROOT, rel)
        if not os.path.exists(up_path):
            skipped.append("%s (upstream 缺失)" % rel)
            continue
        if not os.path.exists(fork_path):
            skipped.append("%s (本仓库缺失)" % rel)
            continue
        left = _read_lines(up_path)
        right = _read_lines(fork_path)
        if left == right:
            continue
        name = _rel_path(rel)
        parts.append("diff --git a/%s b/%s\n" % (name, name))
        parts.extend(difflib.unified_diff(
            left, right, fromfile="a/" + name, tofile="b/" + name, n=3,
        ))

    if not parts:
        print("没有差异：主题 %s 与上游一致（或文件全部缺失）" % args.topic)
        for item in skipped:
            print("  - %s" % item)
        return 0

    target = os.path.join(outdir, "%s.patch" % args.topic)
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("".join(parts))
    print("已生成 %s（%d 个文件有差异）" % (target, len([p for p in parts if p.startswith("diff --git")])))
    for item in skipped:
        print("  跳过: %s" % item)
    return 0


def cmd_status(args):
    rc = 0
    for key, topic in TOPICS.items():
        print("\n[%s] %s" % (key, topic["title"]))
        for item, rel, marker in topic["markers"]:
            path = os.path.join(args.upstream, rel)
            if not os.path.exists(path):
                print("  ?  %-24s %s（上游无此文件）" % (item, rel))
                continue
            try:
                content = "".join(_read_lines(path))
            except OSError as err:
                print("  !  %-24s 读取失败: %s" % (item, err))
                rc = 1
                continue
            state = "upstream-has-marker（可能已修，人工复核）" if marker in content else "fork-only"
            print("  -  %-24s %s" % (item, state))
    return rc


def main(argv=None):
    parser = argparse.ArgumentParser(description="上游跟进主题补丁工具")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="列出主题与文件清单")

    p_export = sub.add_parser("export", help="生成某个主题的 patch")
    p_export.add_argument("topic", help="A/B/C/D")
    p_export.add_argument("--upstream", required=True, help="上游检出目录")
    p_export.add_argument("--out", default=None, help="输出目录（默认 ./upstream-patches）")

    p_status = sub.add_parser("status", help="检查上游是否已出现修复标记")
    p_status.add_argument("--upstream", required=True, help="上游检出目录")

    args = parser.parse_args(argv)
    if args.command == "list":
        return cmd_list(args)
    if args.command == "export":
        return cmd_export(args)
    if args.command == "status":
        return cmd_status(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
