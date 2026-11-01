#!/bin/sh
# ============================================================
# check-reader.sh —— 诊断 MyReader 阅读器为什么「打开书什么都没有」
#
# 在 NAS 上跑（不需要进容器，能跑 docker 就行）：
#   sh check-reader.sh
#   sh check-reader.sh audiobook          # 自定义容器名
#
# 只读，不改任何东西。
# ============================================================
CONTAINER="${1:-}"

line() { echo "------------------------------------------------------------"; }

# ---- 先确认 docker 能用（NAS 上普通用户常因不在 docker 组而无权限）----
if ! command -v docker >/dev/null 2>&1; then
    echo "!! 找不到 docker 命令。本脚本要在 NAS 上跑。"
    exit 1
fi
err=$(docker ps 2>&1 >/dev/null)
if [ -n "$err" ]; then
    case "$err" in
        *"permission denied"*|*"Permission denied"*)
            echo "!! 当前用户没有 docker 权限（不在 docker 组）"
            echo "   两个办法："
            echo "     a) 在当前目录用 sudo 重跑： sudo sh check-reader.sh"
            echo "     b) 把用户加进 docker 组（要重新登录才生效）："
            echo "          sudo synogroup --add docker \$USER"
            echo "          sudo chown root:docker /var/run/docker.sock"
            exit 1 ;;
        *"Cannot connect"*|*"Is the docker daemon running"*)
            echo "!! docker 服务没在运行"
            echo "   群晖：套件中心 → Docker → 启动；或 SSH 里 sudo synoservice --start pkgctl-Docker"
            exit 1 ;;
        *)
            echo "!! docker ps 报错："
            echo "   $err"
            exit 1 ;;
    esac
fi

# 没指定容器名时自动探测：优先叫 audiobook 的，其次任何带 audiobook 的
if [ -z "$CONTAINER" ]; then
    CONTAINER=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -x 'audiobook' | head -1)
    [ -z "$CONTAINER" ] && CONTAINER=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -i 'audiobook' | head -1)
fi

echo "============================================================"
echo " MyReader 阅读器诊断"
echo " 容器: ${CONTAINER:-（未找到）}"
echo "============================================================"

line
echo "[1] 容器在跑吗"
if ! command -v docker >/dev/null 2>&1; then
    echo "    ✘ 找不到 docker 命令"
    echo "    本脚本要在 NAS 上跑（装了 docker 的机器），不是在你的电脑上跑。"
    exit 1
fi
if [ -z "$CONTAINER" ]; then
    echo "    ✘ 没找到 name 里带 audiobook 的运行中容器"
    echo "    当前在跑的容器："
    docker ps --format '       {{.Names}}' 2>/dev/null
    echo "    如果名字不一样，带上名字重跑："
    echo "       sh check-reader.sh <容器名>"
    exit 1
fi
if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER"; then
    echo "    ✘ 容器 $CONTAINER 没在运行"
    echo "    当前在跑的容器："
    docker ps --format '       {{.Names}}' 2>/dev/null
    exit 1
fi
echo "    ✔ 容器在运行（$CONTAINER）"

line
echo "[2] myreader 进程状态（supervisord）"
docker exec "$CONTAINER" supervisorctl status myreader 2>&1 | sed 's/^/    /'

line
echo "[3] 9100 端口有没有在听"
if docker exec "$CONTAINER" sh -c 'ss -ltn 2>/dev/null | grep -q ":9100"' 2>/dev/null; then
    echo "    ✔ 9100 在监听"
else
    echo "    ✘ 9100 未监听 → nginx 转发 /readerx 必然 502"
fi

line
echo "[4] myreader 日志最后 25 行（关键）"
docker exec "$CONTAINER" sh -c 'tail -25 /data/log/myreader.log 2>/dev/null || tail -25 /var/log/supervisor/myreader*.log 2>/dev/null' 2>&1 | sed 's/^/    /'

line
echo "[5] 产物目录是否完整"
docker exec "$CONTAINER" sh -c '
cd /var/www/myreader 2>/dev/null || { echo "    ✘ /var/www/myreader 不存在"; exit 0; }
printf "    server.js:          "; [ -f app/server.js ] && echo "✔" || echo "✘ 缺失"
printf "    node_modules/:      "; [ -d node_modules ] && echo "✔ $(ls node_modules | wc -l) 项" || echo "✘ 缺失 ← 启动会报 Cannot find module next"
printf "    app/node_modules/:  "; [ -d app/node_modules ] && echo "✔ $(ls app/node_modules | wc -l) 项" || echo "✘ 缺失"
printf "    app/.next/:         "; [ -d app/.next ] && echo "✔" || echo "✘ 缺失"
printf "    app/.next/node_modules/: "; [ -d app/.next/node_modules ] && echo "✔ $(ls app/.next/node_modules | wc -l) 项" || echo "✘ 缺失"
printf "    符号链接总数:       "; find . -type l 2>/dev/null | wc -l
printf "    其中有效链接:       "; c=0; for l in $(find . -type l 2>/dev/null); do [ -e "$l" ] && c=$((c+1)); done; echo "$c"
printf "    文件总数:           "; find . -type f 2>/dev/null | wc -l
' 2>&1
echo "    （node_modules 三个目录是命门；符号链接数只作参考，静态目录常有断链）"

line
echo "[6] 直接试着加载 server.js（最能说明问题）"
docker exec "$CONTAINER" sh -c 'cd /var/www/myreader && timeout 15 node -e "require(\"./app/server.js\")" 2>&1 | head -6' 2>&1 | sed 's/^/    /'

line
echo "[7] 从容器内部访问阅读器"
c1=$(docker exec "$CONTAINER" sh -c 'curl -s -o /dev/null -w "%{http_code}" --max-time 8 http://127.0.0.1:9100/ 2>/dev/null' 2>/dev/null)
c2=$(docker exec "$CONTAINER" sh -c 'curl -s -o /dev/null -w "%{http_code}" --max-time 8 http://127.0.0.1/readerx/ 2>/dev/null' 2>/dev/null)
echo "    9100 根路径      → HTTP ${c1:-（无响应）}"
echo "    /readerx/ 经 nginx → HTTP ${c2:-（无响应）}"

line
echo "【怎么读结果】"
echo "  9100 未监听 + 日志里有 Cannot find module 'next'"
echo "      → node_modules 缺失。要么从旧机器/备份取回，要么重新构建产物。"
echo ""
echo "  9100 在听但 /readerx 502"
echo "      → nginx 侧问题，看 conf/nginx/mybooks.conf 的 upstream。"
echo ""
echo "  都正常但书页空白"
echo "      → 可能是 /api/mybooks/* 取不到数据，看 [4] 日志里的 whoami 报错。"
line
