#!/bin/sh
# ============================================================
# MyBooks 移植版（audiobook）NAS 一键部署脚本
#
# 用法（在解压出来的 audiobook 目录里执行）：
#   cd /volume1/docker/audiobook
#   sh scripts/deploy.sh            # 默认做：校验 -> 构建 -> 启动 -> 验证
#   sh scripts/deploy.sh build-only # 只构建不启动
#
# 前提：NAS 已安装 Docker + Docker Compose（v2：docker compose 子命令）
# ============================================================
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
# 本脚本住在 <包根>/scripts/ 下，真正要操作的是上一级（Dockerfile 所在处）。
# 老包把它放在根目录，所以两种位置都认。
if [ -f "$DIR/Dockerfile" ]; then
    :
elif [ -f "$DIR/../Dockerfile" ]; then
    DIR="$(cd "$DIR/.." && pwd)"
else
    echo "!! 找不到 Dockerfile（已在 $DIR 与上层各找过）"
    echo "   请在解压出来的 audiobook 目录里运行：sh scripts/deploy.sh"
    exit 1
fi
cd "$DIR"
CONTAINER="${CONTAINER:-audiobook-mybooks-1}"

echo "==> [0/5] 源码目录污染自检"
# 布局（自 4.6.0-1 起）数据外置到 /volume1/docker/audiobook-data，
# 源码目录里不应出现 books/ data/ 等运行数据目录。
DIRTY=""
for p in books book data audios library upload imports sync models cache logs log workspace; do
    [ -e "$DIR/$p" ] && DIRTY="$DIRTY $p"
done
if [ -n "$DIRTY" ]; then
    echo "    !! 源码目录里出现了数据类目录:$DIRTY"
    echo "    !! 数据应统一放在 /volume1/docker/audiobook-data/ 下。"
    echo "    !! 若这些是旧布局遗留的数据，请先搬到 audiobook-data 再删除本目录副本；"
    echo "    !! 详见 INSTALL_GUIDE.md “一次性：把数据目录分离出源码目录”。"
    echo "    !! 若确认是误留的空目录，可直接删除后重跑本脚本："
    delfiles=""
    for p in $DIRTY; do delfiles="$delfiles $DIR/$p"; done
    echo "    !!   rm -rf$delfiles"
    exit 1
fi
echo "    OK：源码目录干净"

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

echo "==> [2/5] MyReader 产物完整性（之前 502 事故的教训：产物不全 → 书页空白）"
# 原来这里只数符号链接总数（<100 就报错）。问题：myreader-dist/static/ 里有
# 127 个断链（指向不存在的 f1.js…），正好把总数凑够，检查永远通过；
# 而真正该在的三层 node_modules 一个都没有时，阅读器启动即
# Cannot find module 'next' → 9100 不监听 → /readerx 全 502 → 打开书什么都没有。
#
# 现在改成查真东西：目录在不在、有效链接够不够（断链不计）。
mr_fail=0
[ -f myreader-dist/app/server.js ] || { echo "    !! 缺 myreader-dist/app/server.js"; mr_fail=1; }
for sub in "node_modules" "app/node_modules" "app/.next/node_modules"; do
    [ -d "myreader-dist/$sub" ] || { echo "    !! 缺 myreader-dist/$sub"; mr_fail=1; }
done

valid=0; broken=0
for l in $(find myreader-dist -type l 2>/dev/null); do
    if [ -e "$l" ]; then valid=$((valid + 1)); else broken=$((broken + 1)); fi
done
echo "    有效符号链接: $valid   断链: $broken"

if [ "$mr_fail" = "1" ]; then
    echo "    !! MyReader 产物不完整 —— 部署后 /readerx 会 502，书页打不开。"
    echo "       补救：从旧机器/备份取回完整 myreader-dist 后重试。"
    exit 1
fi
if [ "$valid" -lt 100 ]; then
    echo "    !! 有效链接只有 $valid 个（应 ≥100）。"
    echo "       如果远少于这个数，多半是被解压工具压扁了，请用命令行解压："
    echo "         tar -xzf <包名>.tar.gz"
    exit 1
fi
[ "$broken" -gt 0 ] && echo "    ! 提示：$broken 个断链（多在 myreader-dist/static/），无用残留，不影响运行"

echo "==> [3/5] Docker 构建镜像"
if [ "$1" = "build-only" ]; then
    docker compose build
    echo "==> 完成（build-only，未启动）。启动请执行: docker compose up -d"
    exit 0
fi
docker compose build

echo "==> [4/5] 启动容器"
docker compose up -d

echo "==> [5/5] 启动验证"
# 不能 fixed sleep 就直接 supervisorctl status：容器里 start.sh 要先补目录、
# 跑 --syncdb 和 --update-config，这期间 supervisord 还没起来，
# 会报 "unix:///var/run/supervisor.sock no such file"（不是启动失败）。
echo "    等待容器初始化（syncdb / update-config 可能较慢）..."
i=0
while [ $i -lt 60 ]; do
    [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" = "true" ] && break
    i=$((i + 1)); sleep 2
done
i=0
while [ $i -lt 90 ]; do
    docker exec "$CONTAINER" test -S /var/run/supervisor.sock 2>/dev/null && break
    [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" = "true" ] || break
    i=$((i + 1)); sleep 2
done
if ! docker exec "$CONTAINER" test -S /var/run/supervisor.sock 2>/dev/null; then
    echo " !! supervisord 未启动，容器日志最后 30 行："
    docker logs --tail 30 "$CONTAINER" 2>&1 | sed 's/^/    /'
    exit 1
fi
# 等 program 从 STARTING 变 RUNNING
i=0
while [ $i -lt 60 ]; do
    ST=$(docker exec "$CONTAINER" supervisorctl status 2>/dev/null)
    echo "$ST" | grep -qE 'FATAL|BACKOFF' && break
    if [ -n "$ST" ] && ! echo "$ST" | grep -qE 'STARTING'; then break; fi
    i=$((i + 1)); sleep 2
done
echo "    supervisor 状态（应为 4 个 RUNNING）："
docker exec "$CONTAINER" supervisorctl status 2>&1 | sed 's/^/    /' || true
echo
echo "    myreader 日志末尾（应看到 Next.js Ready，无 SyntaxError）："
docker exec "$CONTAINER" tail -5 /data/log/myreader.log 2>/dev/null | sed 's/^/    /' || true
echo
echo "==> 部署完成。浏览器打开 http://<NAS_IP>:9800 验证；"
echo "    阅读链路测试: http://<NAS_IP>:9800/read/1?format=epub"
echo "    读者组分类回填: docker exec -it $CONTAINER python3 /var/www/mybooks/tools/category_backfill.py"
