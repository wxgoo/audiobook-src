#!/bin/sh
# ---------------------------------------------------------------------------
# 导出「离线镜像包」：让另一台机器不用联网也能构建/部署
#
# 用法（在有镜像的机器上跑，通常就是当前这台 NAS）：
#   sh scripts/export-images.sh                 # 只导出基础镜像 base（约 1.6~1.8GB 压缩后）
#   sh scripts/export-images.sh --with-app      # 连成品镜像 mybooks-local 一起导出（约 3GB+）
#   sh scripts/export-images.sh /volume1/tmp    # 指定输出目录
#
# 产物：
#   <输出目录>/images/mybooks_base.tar.gz         ← 构建必需（Dockerfile 的 FROM）
#   <输出目录>/images/mybooks-local.tar.gz        ← 仅 --with-app 时；目标机可「零构建」直接起容器
#   <输出目录>/images/SHA256SUMS                  ← 传输后先核对再 docker load
#
# 目标机上把 images/ 整个目录放到包根（与 Dockerfile 同级），然后：
#   sh scripts/deploy.sh        # 会自动 docker load，不联网
# 或手工： sh scripts/load-images.sh
#
# 为什么要 gzip -1：NAS 多是低功耗 CPU，-6/-9 在 4GB 级别的镜像上要多花十几分钟，
# 只省几百 MB。用 -1 换时间更划算。
# ---------------------------------------------------------------------------
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
# 脚本住在 <包根>/scripts/ 下；也允许独立放在别处，此时输出目录由参数/当前目录决定
if [ -f "$DIR/../Dockerfile" ]; then
    ROOT="$(cd "$DIR/.." && pwd)"
elif [ -f "$DIR/Dockerfile" ]; then
    ROOT="$DIR"
else
    ROOT="$(pwd)"
fi

WITH_APP=0
OUT=""
for a in "$@"; do
    case "$a" in
        --with-app|-a) WITH_APP=1 ;;
        -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) OUT="$a" ;;
    esac
done
[ -n "$OUT" ] || OUT="$ROOT/images"
BASE_REF="${BASE_REF:-docker.1ms.run/poxenstudio/mybooks_base:latest}"
APP_REF="${APP_REF:-mybooks-local:latest}"

command -v docker >/dev/null 2>&1 || { echo "!! 找不到 docker"; exit 1; }

say() { printf '%s\n' "$*"; }

say "==> 导出目录: $OUT"
mkdir -p "$OUT"

# 空间预检：docker save 是流式输出，但临时文件在目标盘上，起码头几个 GB 要够
AVAIL_MB=$(df -Pm "$OUT" 2>/dev/null | awk 'NR==2 {print $4}')
if [ -n "$AVAIL_MB" ] && [ "$AVAIL_MB" -lt 6000 ]; then
    say "    ! 可用空间只有 ${AVAIL_MB}MB，导出单个 base 建议留 6GB 以上"
fi

save_one() {
    _img="$1"; _name="$2"; _dst="$OUT/$_name.tar.gz"
    if ! docker image inspect "$_img" >/dev/null 2>&1; then
        say "    !! 本地没有镜像: $_img"
        return 1
    fi
    if [ -f "$_dst" ] && [ -s "$_dst" ]; then
        say "    = 已存在，跳过: $_dst"
        return 0
    fi
    say "    导出 $_img -> $_dst（低功耗机器上大约 5~20 分钟，别中断）"
    # 先写 .part 再改名：中途断了不会留下一个看起来完整的坏包
    if docker save "$_img" | gzip -1 > "$_dst.part"; then
        mv "$_dst.part" "$_dst"
        say "    OK: $(ls -lh "$_dst" | awk '{print $5}')"
    else
        rm -f "$_dst.part"
        say "    !! 导出失败: $_img"
        return 1
    fi
}

say "==> [1/3] 基础镜像（构建必需）"
save_one "$BASE_REF" "mybooks_base"

if [ "$WITH_APP" = "1" ]; then
    say "==> [2/3] 成品镜像（可选，「零构建」部署用）"
    save_one "$APP_REF" "mybooks-local"
else
    say "==> [2/3] 跳过成品镜像（需要时加 --with-app）"
fi

say "==> [3/3] 生成校验和"
( cd "$OUT" && for f in *.tar.gz; do [ -f "$f" ] && sha256sum "$f"; done > SHA256SUMS )
( cd "$OUT" && ls -lh *.tar.gz | awk '{print "    " $9 "  " $5}' )

say ""
say "完成。把 images/ 整个目录拷到目标机的包根目录，然后："
say "    sh scripts/deploy.sh          # 自动 docker load，不联网"
if [ "$WITH_APP" = "1" ]; then
    say "  或零构建直接起容器："
    say "    sh scripts/load-images.sh && docker compose up -d --force-recreate --no-build"
fi
