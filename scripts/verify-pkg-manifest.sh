#!/bin/sh
# ============================================================
# verify-pkg-manifest.sh —— 校验「最终产物」里的发布清单
#
# 为什么存在：
#   r27 / r33 两次事故都是同一个形状——出包链路里有一处「从 Gitee raw 拉清单
#   覆盖包内基线」的历史分工逻辑，raw 有缓存，仓库已是新清单、远端还停在上一版，
#   于是把旧 revision 打进新包。装完 /admin/version 一直误报有新版本、反复要求
#   重新部署。旧断言只查了「仓库工作区那份」和「暂存区那份」，没查最终 .tar.gz，
#   所以事故能一路溜到用户手上。
#
#   本脚本直接对交付物说话：从 tar 包里把 update/manifest.json 解出来，
#   校验 revision、并与权威清单做字节级 sha256 比对。
#
# 用法（仓库根目录或任意目录）：
#   sh scripts/verify-pkg-manifest.sh <包.tar.gz>
#   sh scripts/verify-pkg-manifest.sh <包.tar.gz> --expect-rev 4.7.0-build.05
#   sh scripts/verify-pkg-manifest.sh <包.tar.gz> \
#        --expect-rev 4.7.0-build.05 \
#        --expect-sha256 <sha256(update/manifest.json)>
#   EXPECT_REV=... EXPECT_SHA256=... sh scripts/verify-pkg-manifest.sh <包.tar.gz>
#
#   --quiet        只报错、不打印通过信息
#   --expect-rev   断言包内 revision 必须等于它（出包时传本次版本号）
#   --expect-sha256 断言包内清单整份字节的 sha256 必须等于它（出包时传仓库清单）
#
# 退出码：0 通过；1 校验失败（包有问题）；2 用法/环境错误
#
# 部署机上没有 python3 也能跑：revision 用 sed 提取；有 python3 时额外做 JSON 合法性检查。
# ============================================================
set -u

PKG=""
EXPECT_REV="${EXPECT_REV:-}"
EXPECT_SHA256="${EXPECT_SHA256:-}"
QUIET="${QUIET:-0}"

usage() {
    sed -n 's/^# \{0,1\}//p' "$0" | sed -n '/^用法/,/^退出码/p' | head -20
}

while [ $# -gt 0 ]; do
    case "$1" in
        --expect-rev)    [ $# -ge 2 ] || { echo "!! --expect-rev 缺参数"; exit 2; }
                         EXPECT_REV="$2"; shift 2 ;;
        --expect-sha256) [ $# -ge 2 ] || { echo "!! --expect-sha256 缺参数"; exit 2; }
                         EXPECT_SHA256="$2"; shift 2 ;;
        --quiet)         QUIET=1; shift ;;
        -h|--help)       usage; exit 0 ;;
        -*)              echo "!! 未知参数: $1"; exit 2 ;;
        *)               if [ -z "$PKG" ]; then PKG="$1"; else
                             echo "!! 多余参数: $1"; exit 2; fi
                         shift ;;
    esac
done

[ -n "$PKG" ] || { echo "!! 用法: sh $0 <包.tar.gz> [--expect-rev <revision>] [--expect-sha256 <sha>]"; exit 2; }
[ -f "$PKG" ] || { echo "!! 找不到包: $PKG"; exit 2; }
command -v tar >/dev/null 2>&1 || { echo "!! 缺 tar"; exit 2; }

sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" 2>/dev/null | cut -d' ' -f1
    elif command -v openssl >/dev/null 2>&1; then
        openssl dgst -sha256 "$1" 2>/dev/null | awk '{print $NF}'
    else
        echo ""
    fi
}

T=$(mktemp -d 2>/dev/null) || { echo "!! 无法创建临时目录"; exit 2; }
trap 'rm -rf "$T"' EXIT HUP INT TERM

fail=0
bad() { echo "  !! $1"; fail=1; }

# 成员清单先落盘再用，别用 `tar -tzf | grep -q`：grep 提前退出会让 tar 吃 SIGPIPE，
# 在 pipefail 环境里被误判成「包里没这个文件」。
if ! tar -tzf "$PKG" > "$T/list" 2>/dev/null; then
    echo "!! 无法读取包内成员（不是有效 gzip tar，或传错文件）: $PKG"
    exit 1
fi
[ -s "$T/list" ] || { echo "!! 包内无成员: $PKG"; exit 1; }

# 部署包收在 audiobook/ 下，源码整包以仓库根为包根；两种都认。
MF_PATH=""
for c in "audiobook/update/manifest.json" "update/manifest.json"; do
    if grep -qx "$c" "$T/list"; then MF_PATH="$c"; break; fi
done
if [ -z "$MF_PATH" ]; then
    echo "!! 包内缺 update/manifest.json —— /admin/version 会拿不到本地基线，一直误报有新版本"
    exit 1
fi

if ! tar -xzOf "$PKG" "$MF_PATH" > "$T/manifest.json" 2>/dev/null; then
    echo "!! 无法从包内解出 $MF_PATH"
    exit 1
fi
[ -s "$T/manifest.json" ] || { echo "!! 包内 $MF_PATH 是空文件"; exit 1; }

# JSON 合法性（有 python3 才做；没有时下面的 sed 提取仍能挡住旧 revision）
if command -v python3 >/dev/null 2>&1; then
    if ! python3 -c 'import json,sys; d=json.load(open(sys.argv[1],encoding="utf-8")); sys.exit(0 if isinstance(d,dict) else 1)' \
            "$T/manifest.json" >/dev/null 2>&1; then
        bad "包内清单不是合法 JSON 对象：$MF_PATH"
    fi
fi

json_str() {
    sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$T/manifest.json" | head -1
}
REV=$(json_str revision)
BASE=$(json_str base_revision)
MF_SHA=$(sha256_of "$T/manifest.json")

[ -n "$REV" ]          || bad "包内清单缺 revision 字段"
[ -n "$MF_SHA" ]       || bad "算不出包内清单 sha256（缺 sha256sum / openssl）"
if [ -n "$REV" ]; then
    printf '%s' "$REV" | grep -qE -- '-build\.[0-9]+$' \
        || bad "包内 revision='$REV' 不带 -build.<N> 版本号（多半是清单没更新就出了包）"
fi
if [ -n "$EXPECT_REV" ] && [ -n "$REV" ]; then
    [ "$REV" = "$EXPECT_REV" ] \
        || bad "包内 revision='$REV' != 本次版本 '$EXPECT_REV'（旧清单被打包 / raw 缓存污染）"
fi
if [ -n "$EXPECT_SHA256" ] && [ -n "$MF_SHA" ]; then
    [ "$MF_SHA" = "$EXPECT_SHA256" ] \
        || bad "包内清单 sha256=$MF_SHA != 仓库清单 $EXPECT_SHA256（产物在打包前后被改过）"
fi

if [ "$fail" != "0" ]; then
    echo "  ✗ 包内发布清单校验失败：$PKG"
    exit 1
fi

if [ "$QUIET" != "1" ]; then
    echo "  ✓ 包内清单: $MF_PATH"
    echo "      revision      = $REV"
    echo "      base_revision = ${BASE:-<无>}"
    echo "      sha256        = $MF_SHA"
    if [ -n "$EXPECT_SHA256" ]; then
        echo "      与仓库清单字节一致: 是"
    fi
fi
exit 0
