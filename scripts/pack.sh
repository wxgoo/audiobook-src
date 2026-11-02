#!/bin/sh
# ============================================================
# pack.sh —— 从仓库打部署包
#
# 用法（仓库根目录）：
#   sh scripts/pack.sh                 # 用 CHANGELOG 里的当前版本号
#   sh scripts/pack.sh 4.6.0-11        # 指定版本号
#   sh scripts/pack.sh --check xxx.tar.gz   # 只验一个已有包，不打包
#
# 产物：/workspace/audiobook-deploy-<版本>.tar.gz（或在当前目录）
#
# ------------------------------------------------------------
# 为什么不能简单地 tar -czf 一下
#
# 1. 不能用 --transform 改顶层目录名。
#    tar 的 --transform 会连带作用于**符号链接的目标内容**：
#      s,^\.,audiobook,  会把链接里的 "../../../../node_modules/x"
#      改写成 "audiobook./../../../node_modules/x"，127 个链接全废。
#    正确做法是 cd 到父目录、对目录名打包（见下）。
#
# 2. myreader-dist 必须完整。它 2732 条、92M、127 个符号链接，
#    链接目标指向它自己的 node_modules/.pnpm（相对路径）。
#    少一条 .pnpm 里的文件，链接就全断，阅读器启动即 502。
#    打包后必须实际数一遍有效链接（本脚本第 4 步）。
#
# 3. app/node_modules 要带上。Dockerfile 里 `COPY app/ /build/` 依赖它，
#    且 NAS 上 npm ci 极易因网络抖动失败。
# ============================================================
set -eu

SELF_DIR=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$SELF_DIR/.." && pwd)
cd "$ROOT"

# ---------- 只验包模式 ----------
if [ "${1:-}" = "--check" ]; then
    PKG="${2:-}"
    [ -n "$PKG" ] && [ -f "$PKG" ] || { echo "用法: sh scripts/pack.sh --check <包路径>"; exit 2; }
    verify() {
        T=$(mktemp -d)
        trap 'rm -rf "$T"' EXIT
        tar -xzf "$PKG" -C "$T" || { echo "!! 解压失败"; exit 1; }
        D="$T/audiobook"
        [ -d "$D" ] || { echo "!! 包内没有 audiobook/ 顶层目录"; exit 1; }

        fail=0
        for f in Dockerfile docker-compose.yml myreader-dist/app/server.js \
                 conf/supervisor/mybooks.conf conf/nginx/mybooks.conf \
                 scripts/upgrade.sh scripts/deploy.sh tools/category_backfill.py; do
            [ -e "$D/$f" ] || { echo "  !! 缺 $f"; fail=1; }
        done

        valid=0; broken=0
        for l in $(find "$D/myreader-dist" -type l 2>/dev/null); do
            if [ -e "$l" ]; then valid=$((valid + 1)); else broken=$((broken + 1)); fi
        done
        echo "  myreader-dist: $(find "$D/myreader-dist" \( -type f -o -type l \) | wc -l) 条, 有效链接 $valid, 断链 $broken"

        # 断链超过 10 个就是打包方式坏了（正常残留是 8 个，见 deploy.sh 说明）
        if [ "$valid" -lt 100 ]; then
            echo "  !! 有效链接只有 $valid 个（应 ≥100）—— 多半被 --transform 改坏了，或解压压扁了"
            fail=1
        fi
        if [ "$broken" -gt 10 ]; then
            echo "  !! 断链 $broken 个（正常残留 8 个）—— 检查打包方式"
            fail=1
        fi

        for d in books book data audios library upload imports sync cache logs; do
            [ -e "$D/$d" ] && { echo "  !! 源码目录混入数据目录: $d"; fail=1; }
        done

        # 归档与开发侧杂物不该出现在部署包里
        for junk in scripts/archive docs/archive docs/settings-redesign audiobook-src; do
            [ -e "$D/$junk" ] && { echo "  !! 部署包里混入不该下发的内容: $junk"; fail=1; }
        done

        [ "$fail" = "0" ] && echo "  ✅ 校验通过" || { echo "  ❌ 校验失败"; exit 1; }
    }
    echo "==> 校验 $PKG"
    verify
    exit 0
fi

# ---------- 确定版本号 ----------
VER="${1:-}"
if [ -z "$VER" ]; then
    VER=$(grep -m1 -oE '^## [0-9]+\.[0-9]+\.[0-9]+-[0-9]+' CHANGELOG.md | sed 's/^## //')
    [ -n "$VER" ] || { echo "!! 无法从 CHANGELOG.md 取版本号，请手动指定"; exit 2; }
    echo "==> 版本号（取自 CHANGELOG）: $VER"
else
    echo "==> 版本号（手动指定）: $VER"
fi

NAME="audiobook-deploy-$VER"
OUTDIR="${OUTDIR:-/workspace}"
OUT="$OUTDIR/$NAME.tar.gz"

# ---------- 打包前自检 ----------
echo "==> [1/4] 源码目录自检"
# 数据目录必须不存在。注意：sync/ cache/ logs/ 可能只是空壳残留
# （开发时跑过服务留下的），只要没有实际数据就不算污染——打包时会被排除。
for d in books book data audios library upload imports sync cache logs; do
    [ -e "$d" ] || continue
    if [ -z "$(find "$d" -type f 2>/dev/null | head -1)" ]; then
        echo "  - $d/ 是空目录，打包时排除（无实际数据）"
    else
        echo "  !! 仓库里出现带数据的目录 $d（$(du -sh "$d" | cut -f1)），先清掉再打包"; exit 1
    fi
done
echo "  OK：无数据污染"

echo "==> [2/4] MyReader 产物自检"
[ -d myreader-dist/node_modules ] || { echo "  !! 缺 myreader-dist/node_modules（产物不完整，见 .gitignore 例外区）"; exit 1; }
mr_total=$(find myreader-dist \( -type f -o -type l \) | wc -l)
mr_valid=0
for l in $(find myreader-dist -type l); do [ -e "$l" ] && mr_valid=$((mr_valid + 1)); done
echo "  $mr_total 条，有效链接 $mr_valid"
[ "$mr_valid" -ge 100 ] || { echo "  !! 有效链接只有 $mr_valid（应 ≥100），产物坏了"; exit 1; }

# ---------- 打包 ----------
echo "==> [3/4] 打包（cd 到父目录对目录名打包，不用 --transform）"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
# 用硬链接镜像出一份叫 audiobook 的树，避免复制 92M 产物
mkdir -p "$STAGE/audiobook"
for item in $(ls -A); do
    case "$item" in
        # 版本库与开发侧杂物
        .git|.claude|node_modules|cache|sync|books|data|__pycache__|logs) continue ;;
        # 误提交的嵌套仓库条目（历史上 clone 自己的残留），空目录，无内容
        audiobook-src) continue ;;
    esac
    cp -al "$item" "$STAGE/audiobook/$item" 2>/dev/null || cp -a "$item" "$STAGE/audiobook/$item"
done

# 归档目录不进部署包：它们是历史记录（v9 那趟的一次性脚本、旧版操作手册、
# 设计稿截图），NAS 上用不到，只会让包变大、让人分不清哪个脚本该跑。
# 仓库里保留，随时可查。
for junk in scripts/archive docs/archive docs/settings-redesign; do
    [ -e "$STAGE/audiobook/$junk" ] && rm -rf "$STAGE/audiobook/$junk"
done

mkdir -p "$OUTDIR"
( cd "$STAGE" && tar -czf "$OUT" audiobook )
echo "  产物: $OUT"

# ---------- 验包 ----------
echo "==> [4/4] 验包"
sh "$SELF_DIR/pack.sh" --check "$OUT"

ls -lh "$OUT"
echo "md5: $(md5sum "$OUT" | cut -d' ' -f1)"
