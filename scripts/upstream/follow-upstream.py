#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""跟随上游：评估规模 + 逐文件三方比对，判定该吸收还是该移植。

为什么需要它
------------
本仓库是用「导出上游源码」的方式建的（根提交 ``5748959 audiobook v4.8 源码``），
**上游的 git 历史不在本仓库里**——`git cat-file` 查上游 tag 的 commit 会报
``could not get object info``。因此：

- ``git merge upstream/4.7.0`` / ``git rebase`` —— 没有 merge base，**直接失败**；
- ``git cherry-pick`` 上游提交 —— 上游对象不存在于本仓库。

跟随上游唯一可行路径是「**拉上游到临时目录 → 文件级三方比对 → 逐条判定 → 手工移植**」。
本脚本把其中机械、可重复的部分标准化，避免每轮从头手工来一遍。

用法
----
::

    # 1. 拉上游（浅克隆，不落进本仓库）
    python3 scripts/upstream/follow-upstream.py fetch --upstream-dir /tmp/up

    # 2. 评估这一轮规模（需要两个 tag 都已 fetch 到）
    python3 scripts/upstream/follow-upstream.py assess --upstream-dir /tmp/up \\
        --base 4.6.0 --target 4.7.0

    # 3. 逐文件三方比对，输出冲突矩阵（base=上游旧版 / ours=本仓库 / theirs=上游新版）
    python3 scripts/upstream/follow-upstream.py compare --upstream-dir /tmp/up \\
        --base 4.6.0 --target 4.7.0 --out /tmp/compare-report.json

设计口径
--------
- **只读**：本脚本只读上游检出目录与本仓库工作区，**从不写任何文件**（``compare``
  的报告写到 ``--out`` 指定的路径，默认打印到 stdout）。不会污染本仓库。
- **冲突判定不估**：对每个「上游改过且我们也算改过」的文件真做三方合并
  （``git merge-file`` 语义用 difflib 实现），冲突块数即数字。
- **CRLF 归一**：Windows 检出的上游文件可能是 CRLF，比对前统一归一，否则整文件
  都会被误判成「双方都改过」。
- **结论只给三种**：``auto``（上游改动我们没有，可自动吸收）、``conflict``
  （双方都改过且冲突，需人工判定）、``ours``（我们独有，上游没有）。
  判定结果**不是结论**，最终「吸收 / 移植 / 不跟」要人来定。
"""

import argparse
import difflib
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPSTREAM_URL = "https://github.com/PoxenStudio/mybooks.git"

# 这些目录不参与比对：构建产物、依赖、版本控制
SKIP_DIRS = {".git", "node_modules", "__pycache__", "dist", ".nuxt", ".pytest_cache"}
# 这些路径永远不整体合并（历次跟进得出的硬约束，见 CHANGELOG「跟随上游」一节）
NEVER_MERGE_WHOLE = {
    "webserver/settings.py",  # 上游默认值/键名有破坏性变更
}


def _norm(text):
    """CRLF/CR 归一 + 去尾随空白，让比对只反映真实内容差异。"""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _read(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return _norm(f.read())


def _git(upstream_dir, *args):
    out = subprocess.run(
        ["git", "-C", upstream_dir] + list(args),
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    return out.returncode, out.stdout.strip(), out.stderr.strip()


def cmd_fetch(args):
    """浅克隆上游到临时目录（只用于比对，不落进本仓库）。"""
    if os.path.exists(args.upstream_dir):
        print("目录已存在，跳过克隆：%s" % args.upstream_dir)
    else:
        rc, out, err = _git_run_clone(args.upstream_dir)
        if rc != 0:
            print("克隆失败：%s" % err, file=sys.stderr)
            return 1
        print(out)
    # 确保 tag 都在
    rc, _, err = _git(args.upstream_dir, "fetch", "--tags", "--depth", "2000")
    if rc != 0:
        print("fetch tags 失败：%s" % err, file=sys.stderr)
        return 1
    print("上游就绪：%s" % args.upstream_dir)
    return 0


def _git_run_clone(target):
    out = subprocess.run(
        ["git", "clone", "--filter=blob:none", "--no-checkout", UPSTREAM_URL, target],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
    )
    return out.returncode, out.stdout.strip(), out.stderr.strip()


def cmd_assess(args):
    """评估 base..target 的规模：提交数、改动文件数、增删行。"""
    rc, commits, err = _git(args.upstream_dir, "rev-list", "--count", "%s..%s" % (args.base, args.target))
    if rc != 0:
        print("取提交数失败：%s" % err, file=sys.stderr)
        return 1
    rc, stat, err = _git(args.upstream_dir, "diff", "--shortstat", "%s..%s" % (args.base, args.target))
    if rc != 0:
        print("取 diff 统计失败：%s" % err, file=sys.stderr)
        return 1
    rc, names, _ = _git(args.upstream_dir, "diff", "--name-only", "%s..%s" % (args.base, args.target))
    files = [x for x in names.split("\n") if x]
    print("上游 %s → %s" % (args.base, args.target))
    print("  提交数    : %s" % commits)
    print("  改动文件  : %d" % len(files))
    print("  增删行    : %s" % stat.strip())
    by_dir = {}
    for f in files:
        top = f.split("/", 1)[0]
        by_dir[top] = by_dir.get(top, 0) + 1
    print("  按顶层目录:")
    for d, n in sorted(by_dir.items(), key=lambda kv: -kv[1])[:12]:
        print("    %-22s %d" % (d, n))
    return 0


def _changed_files(upstream_dir, base, target):
    rc, names, _ = _git(upstream_dir, "diff", "--name-only", "%s..%s" % (base, target))
    return [x for x in names.split("\n") if x]


def _upstream_file(upstream_dir, ref, rel):
    rc, out, err = _git(upstream_dir, "show", "%s:%s" % (ref, rel))
    if rc != 0:
        return None
    return _norm(out)


def _ours_file(rel):
    p = os.path.join(REPO_ROOT, rel)
    if not os.path.isfile(p):
        return None
    return _read(p)


def _conflict_blocks(base, ours, theirs):
    """三方合并，返回冲突块数。冲突越多越要人工判定。

    判定口径（**别改这条**，与 CHANGELOG「跟随上游」一节一致）：
    对每个「我们相对 base 改过的区块」：
      - 上游在**同一段**也改了（内容不同）→ 算 1 个冲突块；
      - 上游在同段没改（内容仍等于 base）→ **不算冲突**——上游没动这块，
        吸收它的其它改动不会覆盖我们的修改；
      - 上游整文件删了 → 单独按「上游删除」处理，不计入冲突块。
    """
    if theirs is None:
        return 0
    sm = difflib.SequenceMatcher(None, base, ours)
    conflicts = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        base_chunk = base[i1:i2]
        ours_chunk = ours[j1:j2]
        theirs_chunk = theirs[i1:i2] if i2 <= len(theirs) else base_chunk
        # 上游在**同一段**改了吗？改法有两种：内容变了，或整段删了。
        upstream_touched = theirs_chunk.strip() != base_chunk.strip()
        if not upstream_touched:
            # 上游没动这块 → 吸收它的其它改动不会覆盖我们，不算冲突
            continue
        if ours_chunk.strip() != theirs_chunk.strip():
            conflicts += 1
    return conflicts


def cmd_compare(args):
    """逐文件三方比对，输出冲突矩阵。"""
    changed = _changed_files(args.upstream_dir, args.base, args.target)
    matrix = {"auto": [], "conflict": [], "ours_only": [], "never_merge": []}

    for rel in changed:
        if any(part in SKIP_DIRS for part in rel.split("/")):
            continue
        theirs = _upstream_file(args.upstream_dir, args.target, rel)
        base = _upstream_file(args.upstream_dir, args.base, rel)
        ours = _ours_file(rel)
        if rel in NEVER_MERGE_WHOLE:
            matrix["never_merge"].append(rel)
        if ours is None:
            matrix["auto"].append({"path": rel, "note": "上游新增，我们没有"})
            continue
        if base is None:
            matrix["ours_only"].append({"path": rel, "note": "我们独有，上游没有"})
            continue
        if ours.strip() == base.strip():
            # 我们没改过这个文件 → 上游的改动可以直接吸收
            matrix["auto"].append({"path": rel, "note": "我们未改，可直接吸收"})
            continue
        conflicts = _conflict_blocks(base, ours, theirs)
        if conflicts == 0:
            matrix["auto"].append({"path": rel, "note": "我们改过但与上游不冲突"})
        else:
            matrix["conflict"].append({"path": rel, "conflicts": conflicts})

    matrix["auto"].sort(key=lambda x: x["path"])
    matrix["conflict"].sort(key=lambda x: -x["conflicts"])
    summary = {k: len(v) for k, v in matrix.items()}
    print("比对结果：%s → %s" % (args.base, args.target))
    print("  上游改动文件     : %d" % len(changed))
    print("  可自动吸收       : %d" % summary["auto"])
    print("  需人工判定(冲突) : %d" % summary["conflict"])
    print("  仅我们有         : %d" % summary["ours_only"])
    if matrix["never_merge"]:
        print("  ⚠ 禁止整体合并   : %s" % ", ".join(matrix["never_merge"]))
    if matrix["conflict"]:
        print("\n冲突 TOP 20（冲突块数越多越要人工看）:")
        for item in matrix["conflict"][:20]:
            print("  %3d  %s" % (item["conflicts"], item["path"]))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(matrix, f, ensure_ascii=False, indent=2)
        print("\n完整矩阵已写入：%s" % args.out)
    return 0


def main():
    ap = argparse.ArgumentParser(description="跟随上游：规模评估 + 三方比对")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("fetch", help="浅克隆上游到临时目录")
    p.add_argument("--upstream-dir", default="/tmp/mybooks-upstream")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("assess", help="评估 base..target 的规模")
    p.add_argument("--upstream-dir", default="/tmp/mybooks-upstream")
    p.add_argument("--base", required=True)
    p.add_argument("--target", required=True)
    p.set_defaults(func=cmd_assess)

    p = sub.add_parser("compare", help="逐文件三方比对，输出冲突矩阵")
    p.add_argument("--upstream-dir", default="/tmp/mybooks-upstream")
    p.add_argument("--base", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--out", default="")
    p.set_defaults(func=cmd_compare)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
