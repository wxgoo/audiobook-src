#!/bin/sh
# ============================================================
# sync-hotfix.sh —— 部署前把「在线热更新」固化进宿主机源码目录
#
# 背景：/admin/version 的一键热更新改的是容器可写层里的
#   /var/www/mybooks/webserver/ 与 /var/www/mybooks/update/manifest.json，
# 宿主机 /volume1/docker/audiobook/ 仍是旧包。docker compose down && up -d
# 会用原镜像重建容器，热更新就丢了（页面会提示「在线更新尚未固化」）。
#
# 热更新时后端已把变更文件写到持久化卷 $DATA/update-sync/current/。
# 本脚本在构建镜像之前，把这些文件合并进刚解压好的源码目录，再用同一份
# manifest 覆盖 $SRC/update/manifest.json —— 这样新镜像天然带着热更新内容，
# 包内基线与数据卷记录一致，不会倒退。
#
# 只在「数据卷修订 > 包内修订」时才动作；纯前端/镜像级更新不会进同步区。
# 用法（一般由 deploy.sh / upgrade.sh 自动调用）：
#   SRC=/volume1/docker/audiobook DATA=/volume1/docker/audiobook-data sh scripts/sync-hotfix.sh
# ============================================================
set -e

SELF_DIR=$(cd "$(dirname "$0")" && pwd)
SRC="${SRC:-$(cd "$SELF_DIR/.." && pwd)}"
DATA="${DATA:-/volume1/docker/audiobook-data}"
SYNC="$DATA/update-sync/current"

[ -f "$SYNC/manifest.json" ] || {
    echo "    无待固化的在线热更新（$SYNC 不存在）"
    exit 0
}
[ -f "$SRC/update/manifest.json" ] || {
    echo "    !! 源码目录缺 update/manifest.json，跳过固化（/admin/version 会一直提示有新版本）"
    exit 0
}

rev_of() {
    # 首个无 r 版本起 revision 形如 4.7.0-build.05，抽 build 号做数值比较。
    grep -m1 '"revision"' "$1" 2>/dev/null | \
        sed -n 's/.*-build\.\([0-9][0-9]*\).*/\1/p' | tr -d '\r'
}
SYNC_N=$(rev_of "$SYNC/manifest.json")
PKG_N=$(rev_of "$SRC/update/manifest.json")

if [ -z "$SYNC_N" ] || [ -z "$PKG_N" ]; then
    echo "    !! 读不出 build 号（数据卷 ${SYNC_N:-?}，包内 ${PKG_N:-?}），跳过固化"
    exit 0
fi
if [ "$SYNC_N" -le "$PKG_N" ]; then
    echo "    包内已是 build.$PKG_N（数据卷 build.$SYNC_N），无需固化"
    exit 0
fi

echo "==> 固化在线热更新 r$SYNC_N（包内 r$PKG_N）"
count=0
if [ -f "$SYNC/server.py" ]; then
    cp -f "$SYNC/server.py" "$SRC/server.py"
    count=$((count + 1))
fi
if [ -d "$SYNC/webserver" ]; then
    (cd "$SYNC/webserver" && find . -type f -name '*.py' -print) | while IFS= read -r rel; do
        rel=${rel#./}
        dst="$SRC/webserver/$rel"
        mkdir -p "$(dirname "$dst")"
        cp -f "$SYNC/webserver/$rel" "$dst"
    done
    count=$((count + $(find "$SYNC/webserver" -type f -name '*.py' | wc -l)))
fi
cp -f "$SYNC/manifest.json" "$SRC/update/manifest.json"
echo "    已合并 $count 个后端文件 + 发布清单；接下来构建的镜像会带上它们"
echo "    同步区保留在 $SYNC，确认稳定后可自行删除"
