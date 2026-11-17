#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本锁检查（防版本回退 / 防被交付标签覆盖）。

背景：本 fork 的运行期版本统一为「上游 mybooks 已发布 tag + 第 N 次本地构建」，
形式是 `<上游 tag>-build.<N>`（例：`4.7.0-build.05`）。**基线段跟随上游 tag 走**：
上游正式发 tag 且我们按主题合入后，整体改号，构建号在新基线上**从 1 重新起算**
（`4.7.0-build.05` → `4.7.0-build.05`）。

旧的 `4.8.x` 号段已封存，与当前基线是纯号段重置，不对应任何版本先后关系
（详见 README 对照表）。

本检查把这条约定变成显式断言：
- **基线段不得回退**（不得从 `4.7.0` 写回 `4.6.0` / `4.8.x` / 裸 tag）；
- **构建号不得回退**（同一基线内 `build.N` 只能递增；换基线时允许重置为 1）；
- 不得被交付标签顶掉、不得被构建参数写成空串。

注意：`4.7.0-build.05` 在 semver 里是 **预发布标记（prerelease）**，整串排序低于 `4.7.0`。
本程序不发布 npm 包、package.json 无 `engines` 校验，因此该排序差异无实际影响；
同一上游基线的本地构建之间用 `build.N` 区分，版本检测不能只靠 `>` 比较，须比较 `build.N` 段。

用法：
    python3 scripts/check-version-lock.py [--root <仓库或发布包根目录>]
    python3 scripts/check-version-lock.py --set 4.7.0-build.05   # 一条命令改全部载体

退出码：0 全部通过；1 有断言失败。

--set 的意义：版本载体有八处（version.py / compose / Dockerfile / package.json /
package-lock / Makefile / 本脚本常量 / tests 字面量），手工逐处改必然漏。
--set 统一改写后立即复检——新增载体时必须同步维护 CARRIERS 表。
CHANGELOG 的版本条目是人工写的（内容随版本走），--set 不碰，打包前由
pack.sh 从其首条版本标题取号——忘写会在打包时暴露。
"""

import argparse
import re
import sys
from pathlib import Path

VERSION_LOCK = "4.7.0-build.05"      # 运行期版本（webserver/version.py / docker-compose / Makefile）
PKG_VERSION_LOCK = "4.7.0-build.05"  # 前端包版本（app/package.json / package-lock.json），须与运行期一致

# 基线段 = 上游已发布 tag；构建号段 = 该基线上的第几次本地构建。
# 两者分开，才能在「上游发新 tag → 整体改号 → 构建号重置」时做正确的回退判定。
UPSTREAM_BASE = VERSION_LOCK.split("-build.")[0]      # 例：4.7.0
BUILD_NO = VERSION_LOCK.rsplit("-build.", 1)[-1]      # 例：01
# 已封存的上游号段：4.8.x 是本 fork 早前的号段，与当前基线无先后关系，禁止写回
SEALED_BASES = ("4.8.0", "4.8.1", "4.8.2", "4.8.3")
# 允许的基线段集合：当前基线 + 它的前序基线（跟上游前的旧基线）
KNOWN_BASES = ("4.6.0", "4.7.0")


def _version_parts(ver):
    """拆成 (基线段, 构建号)。解析不出来返回 (None, None)。"""
    m = re.fullmatch(r"([0-9]+\.[0-9]+\.[0-9]+)-build\.(\d{1,3})", ver or "")
    if not m:
        return None, None
    return m.group(1), int(m.group(2))

def _rollback_reason(ver):
    """判断 ver 相对当前锁是不是「回退」。返回原因字符串，OK 时返回 None。

    判定分两段：
    - **基线段**：必须等于当前基线（或在已知集合里且不低于当前基线）；
      落到 SEALED_BASES（4.8.x）或裸 tag 一律算回退。
    - **构建号段**：同一基线内只能递增；换基线（基线变新）时构建号可重置为 1。
    """
    base, build_no = _version_parts(ver)
    if base is None:
        return "不是 <tag>-build.<N> 形式（裸 tag / v4.8.x / 空串都不接受）"
    if base in SEALED_BASES:
        return "%s 是已封存号段，不得写回" % base
    if base not in KNOWN_BASES:
        return "基线段 %s 不在已知集合 %s 里" % (base, "、".join(KNOWN_BASES))
    cur_base, cur_build = _version_parts(VERSION_LOCK)
    if base == cur_base and build_no < cur_build:
        return "同一基线内构建号回退（当前 %d，写的 %d）" % (cur_build, build_no)
    if base != cur_base and base in KNOWN_BASES:
        # 换基线：只允许往更新的基线走
        if base < cur_base:
            return "基线段回退（当前 %s，写的 %s）" % (cur_base, base)
    return None


def _why():
    """从 VERSION_LOCK 派生，--set 后同一进程内自动一致，无需手工同步。"""
    return ("这是防版本回退 / 防被交付标签覆盖的保护，不是普通测试失败。"
            "运行期版本已统一为 %s（上游已发布 tag %s + 第 %s 次本地构建），"
            "基线段不得回退到旧 tag（%s 已封存），构建号在同一基线内只能递增。"
            % (VERSION_LOCK, UPSTREAM_BASE, BUILD_NO, "、".join(SEALED_BASES)))


def _semver_note():
    return ("%s 是 semver 预发布标记，整串排序低于 %s；"
            "本程序不发布 npm、package.json 无 engines 校验，故无实际影响。"
            "同一上游基线的本地构建之间用 build.N 区分：版本检测不能只靠 > 比较，须比较 build.N 段。"
            % (VERSION_LOCK, UPSTREAM_BASE))


def read(root: Path, rel: str) -> str:
    p = root / rel
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return p.read_text(encoding="utf-8", errors="replace")


# §单一权威改版§ 载体清单：rel -> 预期出现次数（None = 不限，全量替换）。
# 新增版本载体时必须在这里登记——--set 就是为此而存在，漏登记的载体
# 会立即被下面的检查断言抓出来（这正是防线的工作方式：改版工具与检查器互为镜像）。
CARRIERS = {
    "webserver/version.py": 2,          # VERSION 行 + 文件尾注释
    "docker-compose.yml": 2,            # GIT_VERSION + 注释示例
    ".env.example": 1,                   # IMAGE_TAG（交付给别人的镜像标签）
    "Dockerfile": 1,                    # ARG GIT_VERSION 默认值
    "app/package.json": 1,
    "app/package-lock.json": 2,         # 顶层 version 两处
    "Makefile": 2,                      # VERSION_LOCK + 头部注释
    "README.md": None,                  # 升级规则说明里的示例
    "scripts/check-version-lock.py": None,  # 本脚本常量 + 文案
    "tests/test_version_lock.py": None,     # 用例字面量
}


def set_version(root: Path, new_ver: str) -> None:
    """把全部载体统一改写为 new_ver。

    接受 `<上游 tag>-build.<N>` 形式，其中基线段必须在 KNOWN_BASES 里
    （4.6.0 / 4.7.0）、且不得落在 SEALED_BASES（4.8.x 已封存）。
    换基线时构建号可以重置为 1（这是「新基线上的第一次本地构建」）。
    """
    base, build_no = _version_parts(new_ver)
    if base is None:
        raise SystemExit("!! 只接受 <上游 tag>-build.<N> 形式（裸 tag、空串、v4.8.x 都不接受）")
    if base in SEALED_BASES:
        raise SystemExit("!! %s 是已封存号段，不得写回" % base)
    if base not in KNOWN_BASES:
        raise SystemExit("!! 基线段 %s 不在已知集合 %s 里（新增上游基线时先改 KNOWN_BASES）"
                         % (base, "、".join(KNOWN_BASES)))
    # 旧值取「各载体文件里实际写的那个版本」，不是本脚本的常量：
    # 脚本常量已随 --set 改过一遍，若拿它当基准就会误判「已是新版本」而跳过改写，
    # 结果文件里还留着旧号（本次就踩到了）。
    old = VERSION_LOCK
    for rel in sorted(CARRIERS.keys()):
        p = root / rel
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8")
        found = re.findall(r"[0-9]+\.[0-9]+\.[0-9]+-build\.\d{1,3}(?:-r\d{1,3})?", text)
        if found:
            old = found[0]
            break
    if old == new_ver:
        print("== 已是 %s，无需改写" % new_ver)
        return
    old_n = old.rsplit(".", 1)[-1]
    new_n = new_ver.rsplit("-build.", 1)[-1]

    for rel, expected in sorted(CARRIERS.items()):
        p = root / rel
        if not p.is_file():
            print("  !! 载体缺失，跳过: %s" % rel)
            continue
        text = p.read_text(encoding="utf-8")
        n = text.count(old)
        if n == 0:
            print("  !! %s 里没有 %s（该文件可能已手工改过，请核对）" % (rel, old))
            continue
        if expected is not None and n != expected:
            print("  !! %s 出现 %d 次（预期 %d），拒绝盲改——请人工核对后用 "
                  "--set 前先手工对齐" % (rel, n, expected))
            continue
        new_text = text.replace(old, new_ver)
        # 「第 N 次本地构建」文案到处都有（Makefile 注释/校验器/报告），
        # 统一跟着 build.N 走——Makefile 注释里躺过一个「第 20 次」就是教训
        new_text = re.sub(r"第 \d+ 次本地构建", "第 %s 次本地构建" % new_n, new_text)
        # 必须显式 newline="\n"：Path.write_text 在 Windows 上按 os.linesep 换行，
        # 会把 version.py 写成 CRLF —— 而 shell 侧 sed 取值只替换到收尾引号，
        # 行尾 \r 会残留在变量里，导致 check-version.sh 五个值看着一样却全线 FAIL
        # （build.25 现场的真凶）。这里统一成 LF，从源头断掉。
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_text)
        print("  已改写 %-32s（%d 处）" % (rel, n))
    print("== CHANGELOG 的版本条目请人工补写（内容随版本走，--set 不代劳；"
          "pack.sh 从其首条版本标题取号）")


def main() -> int:
    ap = argparse.ArgumentParser(description="版本锁检查")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent),
                    help="仓库或发布包根目录（默认脚本上级目录）")
    ap.add_argument("--set", metavar="NEW_VER", default=None,
                    help="把全部版本载体统一改写为 NEW_VER（<上游 tag>-build.<N>），改完立即复检")
    args = ap.parse_args()
    root = Path(args.root).resolve()

    if args.set:
        set_version(root, args.set)
        # WHY/SEMVER_NOTE 已函数化（从 VERSION_LOCK 派生），刷新全局常量即可
        global VERSION_LOCK, PKG_VERSION_LOCK, UPSTREAM_BASE, BUILD_NO
        VERSION_LOCK = PKG_VERSION_LOCK = args.set
        # 派生常量必须跟着刷新：否则 --set 同进程复检时 .env.example 仍拿旧
        # BUILD_NO 比对，明明已改成新 build 号却报「不一致」的误导性 FAIL。
        # （文件顶部的常量定义已由 set_version 一并改写，下次进程启动自然正确。）
        UPSTREAM_BASE = VERSION_LOCK.split("-build.")[0]
        BUILD_NO = VERSION_LOCK.rsplit("-build.", 1)[-1]

    failures = []

    def ok(name, detail):
        print("[OK]   %-22s %s" % (name, detail))

    def bad(name, detail, fix):
        print("[FAIL] %-22s %s" % (name, detail))
        print("       %s" % _why())
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
            why = _rollback_reason(m.group(1))
            detail = "VERSION=%r，应为 %r" % (m.group(1), VERSION_LOCK)
            if why:
                detail += "；且是回退：%s" % why
            bad("version.py", detail,
                "改回 VERSION = \"%s\"；若确需升级运行期版本（如上游正式发布新 tag），"
                "用 python3 scripts/check-version-lock.py --set <新版本> 一条命令改全部载体" % VERSION_LOCK)
        else:
            ok("version.py", 'VERSION = "%s"' % VERSION_LOCK)
    except FileNotFoundError as e:
        bad("version.py", "文件缺失 %s" % e, "从仓库恢复 webserver/version.py")

    # 2) docker-compose.yml 的版本口径
    #    两种部署形态都要支持：
    #    a) 本地构建形态（有 build 段）：GIT_VERSION 必须与运行期版本一致，
    #       否则 Dockerfile 会把 version.py 写成空串或错值。
    #    b) 纯镜像形态（只有 image:，与上游一致）：版本由**镜像内**的 version.py 决定，
    #       compose 不参与注入。此时要求 image 指向一个带版本号的成品镜像 tag，
    #       并检查该 tag 里的构建号段与运行期版本一致（首个无 r 版本 build.05 起不再带 -rN）。
    try:
        comp = read(root, "docker-compose.yml")
        has_build = re.search(r'^[ \t]*build\s*:', comp, re.M) is not None
        hits = re.findall(r'^[ \t]*GIT_VERSION:\s*"?([^"\n]*)"?[ \t]*$', comp, re.M)
        if has_build:
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
        else:
            # 纯镜像形态：检查 image 行带版本号，且构建号段与运行期版本对得上
            imgs = re.findall(r'^[ \t]*image\s*:\s*"?([^"\n]+)"?[ \t]*$', comp, re.M)
            if not imgs:
                bad("docker-compose.yml", "既没有 build 段也没有 image 行，无法确定用哪个镜像",
                    "写 image: ghcr.io/wxgoo/audiobooks:<版本号>")
            else:
                tag = imgs[0].strip()
                # 允许 ${IMAGE_TAG:-默认tag} 这种带默认值的写法：取花括号里的默认值
                m = re.search(r'\$\{IMAGE_TAG:-([^}]+)\}', tag)
                if m:
                    tag = m.group(1).strip()
                # 镜像 tag 形如 4.6.0-build.27-r41：构建号段必须与运行期版本一致
                mb = re.search(r'build\.(\d+)', tag)
                if not mb:
                    bad("docker-compose.yml", "镜像 tag %r 里没有构建号，无法校验版本口径" % tag,
                        "写成 ghcr.io/wxgoo/audiobooks:%s" % VERSION_LOCK)
                elif mb.group(1) != VERSION_LOCK.rsplit("build.", 1)[-1]:
                    bad("docker-compose.yml", "镜像 tag %r 的构建号与运行期版本 %r 不一致" % (tag, VERSION_LOCK),
                        "换成本版镜像 tag（构建号 %s）" % VERSION_LOCK.rsplit("build.", 1)[-1])
                else:
                    ok("docker-compose.yml", "image = %s（构建号与运行期版本一致）" % tag)
    except FileNotFoundError as e:
        bad("docker-compose.yml", "文件缺失 %s" % e, "从仓库恢复 docker-compose.yml")

    # 2b) .env.example 的 IMAGE_TAG：交付给别人的镜像标签，构建号须与运行期一致
    #     （它是「第几号交付」，即 <tag>-build.<N>；只校验构建号段）
    try:
        env = read(root, ".env.example")
        m2 = re.search(r'^IMAGE_TAG=\s*([^\s]+)', env, re.M)
        if not m2:
            bad(".env.example", "找不到 IMAGE_TAG",
                "写 IMAGE_TAG=ghcr.io/wxgoo/audiobooks:%s" % VERSION_LOCK)
        else:
            tag = m2.group(1).strip()
            mb = re.search(r'build\.(\d+)', tag)
            if not mb:
                bad(".env.example", "镜像 tag %r 里没有构建号" % tag,
                    "写成 ghcr.io/wxgoo/audiobooks:%s" % VERSION_LOCK)
            elif mb.group(1) != BUILD_NO:
                bad(".env.example", "镜像 tag %r 的构建号与运行期版本 %r 不一致" % (tag, VERSION_LOCK),
                    "换成本版镜像 tag（构建号 %s）" % BUILD_NO)
            else:
                ok(".env.example", "IMAGE_TAG = %s" % tag)
    except FileNotFoundError as e:
        bad(".env.example", "文件缺失 %s" % e, "从仓库恢复 .env.example")

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
                % (PKG_VERSION_LOCK, _semver_note()))
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
        print("   %s" % _why())
        return 1
    print("✅ 版本锁检查通过：运行期版本 %s 未被回退或被交付标签覆盖" % VERSION_LOCK)
    print("   注意：%s" % _semver_note())
    return 0


if __name__ == "__main__":
    sys.exit(main())
