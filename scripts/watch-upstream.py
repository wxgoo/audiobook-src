#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
watch-upstream.py —— 盯上游 PoxenStudio/mybooks 的改动，告诉你「哪些跟我们有关」。

为什么需要它：
    我们这份代码是上游 4.6.0 的定制超集。上游一天十几个提交，多数与我们无关
    （dependabot 升依赖、别人家的 UI 微调）。真正要处理的是两类：
      1. 改了「我们也改过」的文件 —— 升级时会冲突，得先知道
      2. 修了「我们也遇到」的 bug —— 可以直接抄过来

用法：
    python3 scripts/watch-upstream.py                 # 看 develop 最近 30 个提交
    python3 scripts/watch-upstream.py --limit 100     # 看更多
    python3 scripts/watch-upstream.py --baseline      # 记录当前位置为基线
    python3 scripts/watch-upstream.py --since-baseline  # 只看基线之后的

基线存在 docs/upstream-baseline.json，提交进仓库，换机器也能接着盯。

依赖：只要 git + python3 标准库。需要能访问 github.com（走 git，不走 API，
      避开 60 次/小时的未认证限流）。
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

UPSTREAM = "https://github.com/PoxenStudio/mybooks.git"
BRANCH = "develop"

# 我们改过的上游文件（相对仓库根）。这些文件一旦上游动了，升级必然冲突。
# 来源：docs/移植改动清单.md，改了那边记得同步这边。
TOUCHED = [
    "webserver/handlers/static_files.py",
    "webserver/handlers/admin.py",
    "webserver/handlers/book.py",
    "webserver/handlers/meta.py",
    "webserver/handlers/audio.py",
    "webserver/handlers/podcast.py",
    "webserver/handlers/base.py",
    "webserver/main.py",
    "webserver/webdav/dav_provider.py",
    "webserver/services/autofill.py",
    "webserver/services/ai_fillinfo.py",
    "webserver/base/meta_helper.py",
    "webserver/podcast/podcast_provider.py",
    "app/src/components/AppHeader.vue",
    "app/src/components/BookCards.vue",
    "app/src/components/AudioListDialog.vue",
    "app/src/components/ReadingTimeBackfillDialog.vue",
    "app/src/pages/admin/settings.vue",
    "app/src/pages/admin/imports.vue",
    "app/src/pages/book/_bookid.vue",
    "app/src/pages/login.vue",
    "app/src/pages/tag.vue",
]

# 我们的核心目录：这里的任何改动都值得看一眼
WATCH_DIRS = [
    "webserver/",
    "app/src/",
]

BASELINE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs", "upstream-baseline.json",
)


def run(cmd, cwd=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit("命令失败: %s\n%s" % (" ".join(cmd), r.stderr.strip()))
    return r.stdout


def ensure_repo(cache_dir, offline=False):
    """浅克隆上游（只看最近 300 个提交，够判断了）。已存在就 fetch。

    offline=True 时不联网，直接用本地缓存 —— 网络不通（国内直连 github 经常断）
    时仍然能看上次拉到的内容，只是看不到增量。
    """
    if not os.path.isdir(os.path.join(cache_dir, ".git")):
        if offline:
            sys.exit("缓存不存在且指定了 --offline：%s" % cache_dir)
        run(["git", "clone", "--depth", "300", "--filter=blob:none",
             "--no-checkout", "-b", BRANCH, UPSTREAM, cache_dir])
    elif not offline:
        run(["git", "fetch", "--depth", "300", "origin", BRANCH], cwd=cache_dir)
    # FETCH_HEAD 只有刚 fetch 过才存在；离线或克隆后没 fetch 过就退回远端分支引号。
    # 注意 rev-parse 找不到时退出码非 0、stdout 为空，这里两个条件都要判。
    rev = ""
    r = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "FETCH_HEAD"],
                       cwd=cache_dir, capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        rev = r.stdout.strip()
    if not rev:
        rev = run(["git", "rev-parse", "origin/%s" % BRANCH], cwd=cache_dir).strip()
    if not rev:
        sys.exit("拿不到上游提交号，检查 %s 是不是一个正常的 git 仓库" % cache_dir)
    return rev


def load_baseline():
    try:
        with open(BASELINE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return None


def save_baseline(rev, date):
    os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
    with open(BASELINE, "w", encoding="utf-8") as f:
        json.dump({"branch": BRANCH, "commit": rev, "date": date}, f,
                  ensure_ascii=False, indent=2)
        f.write("\n")


def resolve_ref(cache, ref):
    """把 tag 名解析成 commit。本地没有该 tag 时提示怎么拉。"""
    r = subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref + "^{commit}"],
                       cwd=cache, capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        sys.exit("找不到 %s。本地没有这个 tag 时先拉一下：\n"
                 "  git -C %s fetch --tags --depth 200" % (ref, cache))
    return r.stdout.strip()


def show_between(cache, spec, offline):
    """看两个 tag/提交之间的改动，如 v4.6.0..v4.6.1。"""
    if ".." not in spec:
        sys.exit("--between 要写成 A..B，例如 --between v4.6.0..v4.6.1")
    a, b = spec.split("..", 1)
    if not os.path.isdir(os.path.join(cache, ".git")):
        if offline:
            sys.exit("缓存不存在且指定了 --offline：%s" % cache)
        run(["git", "clone", "--depth", "200", "--filter=blob:none",
             "--no-checkout", UPSTREAM, cache])
    resolve_ref(cache, a)
    resolve_ref(cache, b)
    rng = "%s..%s" % (a, b)
    n = int(run(["git", "rev-list", "--count", rng], cwd=cache).strip() or 0)
    if n == 0:
        print("%s 与 %s 之间没有提交（可能历史太浅，试试 git -C %s fetch --unshallow）"
              % (a, b, cache))
        return 0
    print("范围：%s（%d 个提交）\n" % (rng, n))
    return report(cache, rng, n, header=None)


def show_tags(cache, offline):
    """列出上游 tag，新的在上。用来判断「上游发新版了吗」。"""
    if not os.path.isdir(os.path.join(cache, ".git")):
        if offline:
            sys.exit("缓存不存在且指定了 --offline：%s" % cache)
        run(["git", "clone", "--depth", "1", "--filter=blob:none",
             "--no-checkout", UPSTREAM, cache])
    out = run(["git", "tag", "--sort=-creatordate",
               "--format=%(refname:lstrip=2)\t%(creatordate:short)\t%(objectname:short)"],
              cwd=cache, check=False)
    if not out.strip():
        print("本地没有 tag。先联网跑一次（去掉 --offline）把 tag 拉下来：")
        print("  git -C %s fetch --tags" % cache)
        return 0
    print("上游 tag（新的在上）：")
    for line in out.strip().split("\n")[:20]:
        parts = line.split("\t")
        if len(parts) >= 3:
            print("  %-12s %s  %s" % (parts[0], parts[1], parts[2]))
    print()
    print("看某个区间的改动：--between 旧tag..新tag")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30, help="看最近多少个提交")
    ap.add_argument("--baseline", action="store_true", help="把当前 HEAD 记为基线")
    ap.add_argument("--since-baseline", action="store_true", help="只看基线之后")
    ap.add_argument("--cache", default=os.path.join(tempfile.gettempdir(), "mybooks-upstream-cache"))
    ap.add_argument("--offline", action="store_true", help="不联网，只看本地缓存")
    ap.add_argument("--tags", action="store_true",
                    help="列出上游所有 tag（看有没有发新版）")
    ap.add_argument("--between", metavar="A..B",
                    help="看两个 tag/提交之间的改动，如 --between v4.6.0..v4.6.1")
    args = ap.parse_args()

    cache = args.cache

    # --tags / --between 都不需要解析分支 HEAD —— 只拿 tag 克隆的仓库里没有
    # origin/develop，早在这里返回，别让后面的 rev-parse 把命令打断。
    if args.tags:
        return show_tags(cache, args.offline)
    if args.between:
        return show_between(cache, args.between, args.offline)

    rev = ensure_repo(cache, offline=args.offline)
    head_date = run(["git", "log", "-1", "--format=%ci", rev], cwd=cache).strip()
    short = rev[:7]

    base = load_baseline()

    if args.baseline:
        save_baseline(rev, head_date)
        print("已把基线记到 %s" % rev)
        print("  docs/upstream-baseline.json → %s (%s)" % (short, head_date))
        return 0

    if args.since_baseline:
        if not base:
            sys.exit("还没有基线，先跑一次 --baseline")
        rng = "%s..%s" % (base["commit"], rev)
        n = int(run(["git", "rev-list", "--count", rng], cwd=cache).strip() or 0)
        if n == 0:
            print("基线 %s 之后没有新提交（当前 %s, %s）" % (base["commit"][:7], short, head_date))
            return 0
        args.limit = max(n, 1)
    else:
        rng = rev

    if not base:
        print("上游 %s/%s 当前 %s (%s)" % ("PoxenStudio/mybooks", BRANCH, short, head_date))
        print("检查范围：最近 %d 个提交\n" % args.limit)
    rc = report(cache, rng, args.limit, header=None)
    if not base:
        print("提示：用 --baseline 把当前位置记下来，之后 --since-baseline 只看增量。")
    return rc


def report(cache, rng, limit, header=None):
    """按「跟我们有没有关系」把 rng 范围内的提交分三档打印出来。"""
    fmt = "%H%x1f%h%x1f%ci%x1f%s"
    log = run(["git", "log", rng, "--max-count=%d" % limit, "--format=" + fmt], cwd=cache)
    commits = []
    for line in log.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) >= 4:
            commits.append({"sha": parts[0], "short": parts[1],
                            "date": parts[2], "subject": parts[3]})

    if not commits:
        print("没有提交")
        return 0

    # 一次性拿到这批提交改了哪些文件
    out = run(["git", "log", rng, "--max-count=%d" % limit,
               "--name-only", "--format=@@%H"], cwd=cache)
    files_by_commit = {}
    cur = None
    for line in out.split("\n"):
        line = line.strip()
        if line.startswith("@@"):
            cur = line[2:]
            files_by_commit[cur] = []
        elif line and cur:
            files_by_commit[cur].append(line)

    touched_set = set(TOUCHED)

    conflicts, related, other = [], [], []
    for c in commits:
        files = files_by_commit.get(c["sha"], [])
        hit_touched = [f for f in files if f in touched_set]
        hit_dir = [f for f in files if any(f.startswith(d) for d in WATCH_DIRS)]
        c["files"] = files
        if hit_touched:
            c["hit"] = hit_touched
            conflicts.append(c)
        elif hit_dir:
            related.append(c)
        else:
            other.append(c)

    def show(title, items, note, show_files=False, maxfiles=6):
        print("=" * 68)
        print("%s：%d 个" % (title, len(items)))
        print("  %s" % note)
        print("=" * 68)
        for c in items:
            print("  %s  %s  %s" % (c["short"], c["date"][:10], c["subject"][:70]))
            if show_files:
                fs = c.get("hit") or [f for f in c["files"] if any(f.startswith(d) for d in WATCH_DIRS)]
                for f in fs[:maxfiles]:
                    print("        └─ %s" % f)
                if len(fs) > maxfiles:
                    print("        └─ …另有 %d 个" % (len(fs) - maxfiles))
        print()

    show("⚠ 改了我们也改过的文件（升级必冲突）", conflicts,
         "这些文件上游一动，我们下次 merge 就要手工处理。优先看。", show_files=True)
    show("● 碰了我们关心的目录", related,
         "webserver/ 或 app/src/ 下有改动，可能有我们需要的修复。", show_files=True)
    print("○ 其余 %d 个提交（依赖升级、文档、其他目录）—— 一般可忽略" % len(other))

    return 0


if __name__ == "__main__":
    sys.exit(main())
