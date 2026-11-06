#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本锁检查（防版本回退 / 防被交付标签覆盖）。

背景：本 fork 自本版起把运行期版本统一为 `4.6.0-20`，语义是
「上游 mybooks 已发布 tag 4.6.0 + 第 20 次本地发布」。旧的 4.8.x 号段已封存，
与 4.6.0-20 是纯号段重置，不对应任何版本先后关系（详见 README 对照表）。

本检查把这条约定变成显式断言：任何一处被回退（写回 4.8.x / 写回不带后缀的
4.6.0）、被交付标签顶掉、或被构建参数写成空串，都会直接失败。

注意：`4.6.0-20` 在 semver 里是 **预发布后缀（prerelease）**，排序低于 `4.6.0`。
本程序不发布 npm 包、package.json 无 `engines` 校验，因此该排序差异无实际影响；
但不要拿它去做版本大小比较。

用法：
    python3 scripts/check-version-lock.py [--root <仓库或发布包根目录>]

退出码：0 全部通过；1 有断言失败。
"""

import argparse
import re
import sys
from pathlib import Path

VERSION_LOCK = "4.6.0-20"      # 运行期版本（webserver/version.py / docker-compose / Makefile）
PKG_VERSION_LOCK = "4.6.0-20"  # 前端包版本（app/package.json / package-lock.json），须与运行期一致

WHY = ("这是防版本回退 / 防被交付标签覆盖的保护，不是普通测试失败。"
       "运行期版本已统一为 4.6.0-20（上游已发布 tag 4.6.0 + 第 20 次本地发布），"
       "旧 4.8.x 号段已封存，不得写回；也不得写成不带 -20 的 4.6.0。")

SEMVER_NOTE = ("4.6.0-20 是 semver 预发布后缀，排序低于 4.6.0；"
               "本程序不发布 npm、package.json 无 engines 校验，故无实际影响。")


def read(root: Path, rel: str) -> str:
    p = root / rel
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return p.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser(description="版本锁检查")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent),
                    help="仓库或发布包根目录（默认脚本上级目录）")
    args = ap.parse_args()
    root = Path(args.root).resolve()

    failures = []

    def ok(name, detail):
        print("[OK]   %-22s %s" % (name, detail))

    def bad(name, detail, fix):
        print("[FAIL] %-22s %s" % (name, detail))
        print("       %s" % WHY)
        print("       补救：%s" % fix)
        failures.append(name)

    # 1) webserver/version.py
    try:
        src = read(root, "webserver/version.py")
        m = re.search(r'^VERSION\s*=\s*"([^"]*)"', src, re.M)
        if not m:
            bad("version.py", "找不到 VERSION = \"...\" 定义",
                "恢复为 VERSION = \"%s\"（见 scripts/check-version-lock.py 的 VERSION_LOCK）" % VERSION_LOCK)
        elif m.group(1) != VERSION_LOCK:
            bad("version.py", "VERSION=%r，应为 %r" % (m.group(1), VERSION_LOCK),
                "改回 VERSION = \"%s\"；若确需升级运行期版本（如上游正式发布 4.6.1），"
                "必须同时更新本脚本、docker-compose.yml、Makefile 与 README 对照表" % VERSION_LOCK)
        else:
            ok("version.py", 'VERSION = "%s"' % VERSION_LOCK)
    except FileNotFoundError as e:
        bad("version.py", "文件缺失 %s" % e, "从仓库恢复 webserver/version.py")

    # 2) docker-compose.yml 的 GIT_VERSION
    try:
        comp = read(root, "docker-compose.yml")
        hits = re.findall(r'^[ \t]*GIT_VERSION:\s*"?([^"\n]*)"?[ \t]*$', comp, re.M)
        if not hits:
            bad("docker-compose.yml", "没有 GIT_VERSION 构建参数（Dockerfile 会把 version.py 写成空串）",
                "在 build.args 下加 GIT_VERSION: \"%s\"" % VERSION_LOCK)
        elif len(hits) > 1:
            bad("docker-compose.yml", "GIT_VERSION 出现 %d 次，口径不唯一" % len(hits),
                "只保留一处 GIT_VERSION: \"%s\"" % VERSION_LOCK)
        elif hits[0].strip() == "":
            bad("docker-compose.yml", "GIT_VERSION 为空（会把运行期版本顶成空串）",
                "填 GIT_VERSION: \"%s\"" % VERSION_LOCK)
        elif hits[0].strip() != VERSION_LOCK:
            bad("docker-compose.yml", "GIT_VERSION=%r，应为 %r" % (hits[0].strip(), VERSION_LOCK),
                "改回 GIT_VERSION: \"%s\"；分支名、旧 4.8.x、裸 4.6.0 都不要写进构建参数" % VERSION_LOCK)
        else:
            ok("docker-compose.yml", 'GIT_VERSION = "%s"' % VERSION_LOCK)
    except FileNotFoundError as e:
        bad("docker-compose.yml", "文件缺失 %s" % e, "从仓库恢复 docker-compose.yml")

    # 3) Dockerfile 空值守卫
    try:
        df = read(root, "Dockerfile")
        flat = re.sub(r"\\\s*\n", " ", df)          # 把续行拉平，便于跨行匹配
        guard = re.search(
            r'if\s*\[\s*-z\s+"\$\{GIT_VERSION:-\}"\s*\]\s*;\s*then'
            r'.{0,240}?exit\s+1', flat, re.S)
        has_arg = re.search(r'^ARG\s+GIT_VERSION\s*=\s*"([^"]*)"', df, re.M)
        if not guard:
            bad("Dockerfile", "缺少「GIT_VERSION 为空则构建失败」的守卫",
                "在写 webserver/version.py 之前加：if [ -z \"${GIT_VERSION:-}\" ]; then "
                "echo \"ERROR: 版本锁…\" >&2; exit 1; fi")
        elif not has_arg:
            bad("Dockerfile", "缺少 GIT_VERSION 的 ARG 声明", "补 ARG GIT_VERSION=\"%s\"" % VERSION_LOCK)
        elif has_arg.group(1) != VERSION_LOCK:
            bad("Dockerfile", "ARG GIT_VERSION 默认值=%r，应为 %r（裸 docker build 会写错版本）"
                % (has_arg.group(1), VERSION_LOCK),
                "改回 ARG GIT_VERSION=\"%s\"；该默认值必须与运行期版本锁一致" % VERSION_LOCK)
        else:
            ok("Dockerfile", 'ARG 默认值 %s；空值守卫存在（空 GIT_VERSION 会让构建失败，而不是写入空串）'
               % VERSION_LOCK)
    except FileNotFoundError as e:
        bad("Dockerfile", "文件缺失 %s" % e, "从仓库恢复 Dockerfile")

    # 4) app/package.json
    try:
        pkg = read(root, "app/package.json")
        m = re.search(r'"version"\s*:\s*"([^"]*)"', pkg)
        if not m:
            bad("app/package.json", "找不到 version 字段", "恢复 \"version\": \"%s\"" % PKG_VERSION_LOCK)
        elif m.group(1) != PKG_VERSION_LOCK:
            bad("app/package.json", "version=%r，应为 %r" % (m.group(1), PKG_VERSION_LOCK),
                "改回 \"version\": \"%s\"（须与运行期版本一致；%s）"
                % (PKG_VERSION_LOCK, SEMVER_NOTE))
        else:
            ok("app/package.json", '"version": "%s"' % PKG_VERSION_LOCK)
    except FileNotFoundError as e:
        bad("app/package.json", "文件缺失 %s" % e, "从仓库恢复 app/package.json")

    # 5) Makefile 的 VER 覆盖
    try:
        mk = read(root, "Makefile")
        has_lock = re.search(r'^VERSION_LOCK\s*:?=\s*%s' % re.escape(VERSION_LOCK), mk, re.M)
        has_guard = ("ifneq ($(strip $(VER)),$(VERSION_LOCK))" in mk and "$(error" in mk)
        if not has_lock:
            bad("Makefile", "没有 VERSION_LOCK 常量", "加 VERSION_LOCK := %s" % VERSION_LOCK)
        elif not has_guard:
            bad("Makefile", "VER 不匹配时没有报错退出（会把分支名/交付标签写进镜像）",
                "加：ifneq ($(strip $(VER)),$(VERSION_LOCK)) 与 $(error ...) 守卫")
        else:
            ok("Makefile", "VER 不匹配即报错（默认 VER=%s）" % VERSION_LOCK)
    except FileNotFoundError as e:
        bad("Makefile", "文件缺失 %s" % e, "从仓库恢复 Makefile")

    # 6) package-lock 顶层版本（与 package.json 对齐）
    try:
        lock = read(root, "app/package-lock.json")
        m = re.search(r'"name"\s*:\s*"mybooks"\s*,\s*"version"\s*:\s*"([^"]*)"', lock, re.S)
        if not m:
            bad("package-lock.json", "找不到顶层 version", "恢复顶层 \"version\": \"%s\"" % PKG_VERSION_LOCK)
        elif m.group(1) != PKG_VERSION_LOCK:
            bad("package-lock.json", "顶层 version=%r，应为 %r" % (m.group(1), PKG_VERSION_LOCK),
                "改回 \"version\": \"%s\"（与 package.json 对齐）" % PKG_VERSION_LOCK)
        else:
            ok("package-lock.json", '顶层 version = "%s"' % PKG_VERSION_LOCK)
    except FileNotFoundError as e:
        bad("package-lock.json", "文件缺失 %s" % e, "从仓库恢复 app/package-lock.json")

    print()
    if failures:
        print("❌ 版本锁检查失败：%d 项" % len(failures))
        print("   %s" % WHY)
        return 1
    print("✅ 版本锁检查通过：运行期版本 %s 未被回退或被交付标签覆盖" % VERSION_LOCK)
    print("   注意：%s" % SEMVER_NOTE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
