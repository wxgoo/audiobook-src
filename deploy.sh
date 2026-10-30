#!/bin/sh
# ============================================================
# MyBooks 移植版（audiobook）NAS 一键部署脚本 v4.8.2
#
# 用法（在解压出来的 audiobook 目录的上一级执行）：
#   cd /volume1/docker/audiobook
#   sh deploy.sh            # 默认做：校验 -> 构建 -> 启动 -> 验证
#   sh deploy.sh build-only # 只构建不启动
#
# 前提：NAS 已安装 Docker + Docker Compose（v2：docker compose 子命令）
# ============================================================
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
CONTAINER="${CONTAINER:-audiobook-mybooks-1}"

echo "==> [1/5] 目录与文件校验"
fail=0
for f in Dockerfile docker-compose.yml myreader-dist/app/server.js \
         conf/supervisor/mybooks.conf conf/nginx/mybooks.conf \
         tools/category_backfill.py; do
    if [ ! -e "$f" ]; then
        echo "    缺少关键文件: $f"; fail=1
    fi
done
[ "$fail" = "1" ] && { echo "==> 校验失败，包不完整，停止。"; exit 1; }
echo "    OK：关键文件齐全"

echo "==> [2/5] 符号链接抽查（之前 502 事故的教训：解压压扁链接会导致 MyReader 崩溃）"
# 正确形态：app/node_modules 第一层恰好 3 个链接（next/react/react-dom），
# 大头在 myreader-dist/node_modules/ 根层，全产物合计应为 127 个。
app_links=$(find myreader-dist/app/node_modules -maxdepth 1 -type l 2>/dev/null | wc -l)
all_links=$(find myreader-dist -type l 2>/dev/null | wc -l)
echo "    app/node_modules 首层链接: $app_links（应为 3）；全产物合计: $all_links（应为 127）"
if [ "$app_links" -lt 3 ] || [ "$all_links" -lt 100 ]; then
    echo "    !! 符号链接数量异常，几乎可以确定是被解压工具压扁了。"
    echo "    !! 请删除本目录，改用命令行重新解压："
    echo "    !!   tar -xzf audiobook-deploy-v4.8.2.tar.gz"
    exit 1
fi

echo "==> [3/5] Docker 构建镜像"
if [ "$1" = "build-only" ]; then
    docker compose build
    echo "==> 完成（build-only，未启动）。启动请执行: docker compose up -d"
    exit 0
fi
docker compose build

echo "==> [4/5] 启动容器"
docker compose up -d

echo "==> [5/5] 启动验证（等 20 秒让 supervisord 拉起各进程）"
sleep 20
echo "    supervisor 状态："
docker exec -it "$CONTAINER" supervisorctl status || true
echo
echo "    myreader 日志末尾（应看到 Next.js Ready，无 SyntaxError）："
docker exec -it "$CONTAINER" tail -5 /data/log/myreader.log 2>/dev/null || true
echo
echo "==> 部署完成。浏览器打开 http://<NAS_IP>:9800 验证；"
echo "    阅读链路测试: http://<NAS_IP>:9800/read/1?format=epub"
echo "    读者组分类回填: docker exec -it $CONTAINER python3 /var/www/mybooks/tools/category_backfill.py"
