#!/bin/sh
# ============================================================
# check-remote-manifest.sh —— 发布**后置**检查：远端清单是否已同步
#
# 定位（重要）：这是出包之外的独立步骤，**只读、不写任何本地文件、
# 绝不参与打包**。r27 / r33 事故的根源就是曾经把「拉远端清单」放进
# pack.sh 并让它覆盖产物；现在出包链路零网络请求（见 pack.sh §3b），
# 远端同步状态改成推完清单后单独跑本脚本确认。
#
# 用法（仓库根目录）：
#   sh scripts/check-remote-manifest.sh                 # 期望值取自本地 update/manifest.json
#   sh scripts/check-remote-manifest.sh 4.6.0-build.27-r33
#   TRIES=10 SLEEP=15 sh scripts/check-remote-manifest.sh
#
# 环境变量：
#   MANIFEST_URL  远端 raw 地址
#   TRIES         轮询次数（默认 6）
#   SLEEP         每次间隔秒数（默认 10）
#
# 退出码：0 远端已与本地一致；1 仍不一致（Gitee raw 缓存，等几分钟再试）；2 用法/环境错误
# ============================================================
set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
MF="$ROOT/update/manifest.json"
URL="${MANIFEST_URL:-https://gitee.com/wxgoo/audiobook-src/raw/master/update/manifest.json}"
TRIES="${TRIES:-6}"
SLEEP="${SLEEP:-10}"

[ -f "$MF" ] || { echo "!! 缺本地清单 $MF"; exit 2; }
command -v tar >/dev/null 2>&1 || true
if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
    echo "!! 缺 curl / wget，无法检查远端"; exit 2
fi
if command -v sha256sum >/dev/null 2>&1; then
    SHA_CMD=sha256sum
elif command -v openssl >/dev/null 2>&1; then
    SHA_CMD=openssl
else
    echo "!! 缺 sha256sum / openssl"; exit 2
fi

sha_of() {
    if [ "$SHA_CMD" = sha256sum ]; then sha256sum "$1" | cut -d' ' -f1
    else openssl dgst -sha256 "$1" | awk '{print $NF}'; fi
}
rev_of() {
    sed -n 's/.*"revision"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$1" 2>/dev/null | head -1
}

EXPECT_REV="${1:-$(rev_of "$MF")}"
EXPECT_SHA=$(sha_of "$MF")
[ -n "$EXPECT_REV" ] || { echo "!! 读不出本地清单的 revision"; exit 2; }

T=$(mktemp -d 2>/dev/null) || { echo "!! 无法创建临时目录"; exit 2; }
trap 'rm -rf "$T"' EXIT HUP INT TERM

fetch() {
    rm -f "$T/remote.json"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --max-time 20 "$1" -o "$T/remote.json" 2>/dev/null
    else
        wget -q -T 20 -O "$T/remote.json" "$1" 2>/dev/null
    fi
}

echo "本地清单: revision=$EXPECT_REV  sha256=$EXPECT_SHA"
echo "远端地址: $URL"
echo "轮询: 最多 $TRIES 次，间隔 ${SLEEP}s（Gitee raw 有缓存，刚推完常要等）"
echo

i=1
while [ "$i" -le "$TRIES" ]; do
    # 加时间戳参数尽量绕过 CDN 缓存；raw 若仍返回旧内容，说明缓存未过期，只能等。
    case "$URL" in
        *\?*) U="$URL&t=$(date +%s)$i" ;;
        *)    U="$URL?t=$(date +%s)$i" ;;
    esac
    if fetch "$U" && [ -s "$T/remote.json" ]; then
        R_REV=$(rev_of "$T/remote.json")
        R_SHA=$(sha_of "$T/remote.json")
        echo "[$i/$TRIES] 远端 revision=${R_REV:-<读不出>}  sha256=$R_SHA"
        if [ "$R_REV" = "$EXPECT_REV" ] && [ "$R_SHA" = "$EXPECT_SHA" ]; then
            echo "✓ 远端清单已与本地完全一致（revision + 字节）"
            exit 0
        fi
        if [ "$R_REV" = "$EXPECT_REV" ]; then
            echo "  revision 相同但字节不同：远端可能是旧清单改过字段，仍需等缓存刷新"
        else
            echo "  远端仍停在 $R_REV，等缓存刷新…"
        fi
    else
        echo "[$i/$TRIES] 远端不可读（网络/缓存/非 JSON），重试…"
    fi
    [ "$i" -lt "$TRIES" ] && sleep "$SLEEP"
    i=$((i + 1))
done

echo
echo "!! 轮询结束，远端清单仍未同步到本地 $EXPECT_REV。"
echo "   这不阻塞出包（包内清单取自本地仓库），只影响页内热更能否检测到新版本。"
echo "   等几分钟再跑一次；或到 Gitee 网页直接打开 update/manifest.json 破缓存。"
exit 1
