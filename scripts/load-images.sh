#!/bin/sh
# ---------------------------------------------------------------------------
# 从 images/ 导入离线镜像（deploy.sh 会自动调，一般不用手工执行）
#
# 用法：
#   sh scripts/load-images.sh              # 导入 <包根>/images/ 下所有 tar / tar.gz
#   sh scripts/load-images.sh /path/images # 指定目录
#
# 幂等：重复执行只是重新铺一遍同名标签，不会删任何东西。
# ---------------------------------------------------------------------------
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$DIR/../Dockerfile" ]; then
    ROOT="$(cd "$DIR/.." && pwd)"
else
    ROOT="$DIR"
fi
IDIR="${1:-$ROOT/images}"
BASE_REF="${BASE_REF:-docker.1ms.run/poxenstudio/mybooks_base:latest}"

command -v docker >/dev/null 2>&1 || { echo "!! 找不到 docker"; exit 1; }

say() { printf '%s\n' "$*"; }

if [ ! -d "$IDIR" ]; then
    say "!! 目录不存在: $IDIR"
    say "   先把 export-images.sh 生成的 images/ 拷到包根目录"
    exit 1
fi

# 先数一遍，空目录早点报错
n=0
for f in "$IDIR"/*.tar.gz "$IDIR"/*.tar; do
    [ -f "$f" ] || continue
    n=$((n + 1))
done
if [ "$n" = "0" ]; then
    say "!! $IDIR 里没有 .tar / .tar.gz"
    exit 1
fi

# 校验放在 load 之前：1.6GB 的包传到一半被截断，直接 load 会报一堆看不懂的
# tar 错误，甚至只导入一半层；先核 sha256，坏了就停，别污染本地镜像库。
if [ -f "$IDIR/SHA256SUMS" ] && command -v sha256sum >/dev/null 2>&1; then
    say "==> 先校验 SHA256SUMS（可能需要几分钟，1.6GB+）"
    ( cd "$IDIR" && sha256sum -c SHA256SUMS 2>&1 | sed 's/^/    /' ) || {
        say "!! 校验不通过 —— 文件在传输中被截断或损坏，重新拷一次再导"
        exit 1
    }
else
    say "! 没有 SHA256SUMS，跳过校验（建议用 export-images.sh 生成的那份）"
fi

for f in "$IDIR"/*.tar.gz "$IDIR"/*.tar; do
    [ -f "$f" ] || continue
    say "==> 导入 $(basename "$f")  ($(ls -lh "$f" | awk '{print $5}'))"
    docker load -i "$f"
done

say ""
say "==> 本地镜像现状"
docker images --format '{{.Repository}}:{{.Tag}}  {{.Size}}' 2>/dev/null | grep -i -E 'mybooks' | sed 's/^/    /' || true
say ""
if docker image inspect "$BASE_REF" >/dev/null 2>&1; then
    say "OK：$BASE_REF 就绪"
else
    say "! 没有 $BASE_REF 这个标签"
    say "  离线包可能是别的 tag，补一个即可："
    say "    docker tag <上表里的 mybooks_base 标签> $BASE_REF"
fi
