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

# 没指定容器名时自动探测：新栈容器名 mybooks，兼容旧名 audiobook
if [ -z "$CONTAINER" ]; then
    CONTAINER=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -x 'mybooks' | head -1)
    [ -z "$CONTAINER" ] && CONTAINER=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -x 'audiobook' | head -1)
    [ -z "$CONTAINER" ] && CONTAINER=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -iE 'audiobook|mybooks' | head -1)
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
    echo "    ✘ 没找到 mybooks / audiobook 运行中容器"
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
# 进程全名是 组名:进程名，即 mybooks:myreader。
# 只写 myreader 会得到 "ERROR (no such process)"，是假警报——只要 [3] 里
# 9100 在监听，就说明进程活着。
docker exec "$CONTAINER" supervisorctl status 2>/dev/null \
    | grep -E 'myreader' | sed 's/^/    /'
docker exec "$CONTAINER" sh -c '
    s=$(supervisorctl status mybooks:myreader 2>/dev/null)
    case "$s" in
        *RUNNING*) echo "    ✔ 运行中" ;;
        *BACKOFF*|*FATAL*) echo "    ✘ 起不来：$s" ;;
        "") echo "    ! 取不到状态" ;;
        *) echo "    $s" ;;
    esac'

line
echo "[3] 9100 端口有没有在听"
# 精简镜像里 ss / netstat 常常都没有，直接读 /proc/net/tcp 最可靠。
# 9100 = 0x238C；80 = 0x0050；8000 = 0x1F40。
# 第 4 列是状态，0A = LISTEN。
docker exec "$CONTAINER" sh -c '
listen() {
    hex=$1
    awk -v h=":"$hex "\$0 ~ h && \$4 == \"0A\" {found=1} END{exit !found}" \
        /proc/net/tcp /proc/net/tcp6 2>/dev/null
}
listen 238C && echo "LISTEN_9100" || echo "NO_9100"
listen 0050 && echo "LISTEN_80"   || echo "NO_80"
listen 1F40 && echo "LISTEN_8000" || echo "NO_8000"
' 2>/dev/null | while read -r r; do
    case "$r" in
        LISTEN_9100) echo "    ✔ 9100 在监听（myreader）" ;;
        NO_9100)     echo "    ✘ 9100 未监听 → nginx 转发 /readerx 必然 502" ;;
        LISTEN_80)   echo "    ✔ 80 在监听（nginx）" ;;
        NO_80)       echo "    ✘ 80 未监听（nginx 没起来）" ;;
        LISTEN_8000) echo "    ✔ 8000 在监听（tornado）" ;;
        NO_8000)     echo "    ✘ 8000 未监听（后端没起来）" ;;
    esac
done

line
echo "[4] myreader 日志最后 25 行（关键）"
# 日志是追加写入的，历史报错会留在文件里。这里只取「最后一次启动之后」的部分：
# 找到最后一个 Next.js 启动标记，从那里往后打，才是当前这次的真实状况。
docker exec "$CONTAINER" sh -c '
F=/data/log/myreader.log
[ -f "$F" ] || F=$(ls /var/log/supervisor/myreader*.log 2>/dev/null | head -1)
[ -f "$F" ] || { echo "（找不到 myreader 日志）"; exit 0; }
n=$(grep -n "Next.js" "$F" 2>/dev/null | tail -1 | cut -d: -f1)
if [ -n "$n" ] && [ "$n" -gt 1 ]; then
    echo "（以下为最后一次启动之后的内容；之前的历史报错已省略）"
    tail -n +"$n" "$F" | head -25
else
    tail -25 "$F"
fi
' 2>&1 | sed 's/^/    /'

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
# 优先 curl，没有就退回 wget，两个都没有就只报端口层面结论
c1=$(docker exec "$CONTAINER" sh -c '
  if command -v curl >/dev/null 2>&1; then
      curl -s -o /dev/null -w "%{http_code}" --max-time 8 http://127.0.0.1:9100/
  elif command -v wget >/dev/null 2>&1; then
      wget -q -O /dev/null -T 8 http://127.0.0.1:9100/ && echo 200 || echo "非200"
  else
      echo "无curl/wget"
  fi' 2>/dev/null)
c2=$(docker exec "$CONTAINER" sh -c '
  if command -v curl >/dev/null 2>&1; then
      curl -s -o /dev/null -w "%{http_code}" --max-time 8 http://127.0.0.1/readerx/
  elif command -v wget >/dev/null 2>&1; then
      wget -q -O /dev/null -T 8 http://127.0.0.1/readerx/ && echo 200 || echo "非200"
  else
      echo "无curl/wget"
  fi' 2>/dev/null)
echo "    9100 根路径      → HTTP ${c1:-（无响应）}"
echo "    /readerx/ 经 nginx → HTTP ${c2:-（无响应）}"

line
echo "【怎么读结果】"
echo "  先看 [3]：9100 在监听 = 服务活着，其余大多是假象"
echo "      · [2] 报 no such process  → 进程全名是 mybooks:myreader，已修"
echo "      · [4] 里老的 Cannot find module → 追加日志的历史残留，看最后一段即可"
echo ""
echo "  9100 未监听 + 日志最后一段是 Cannot find module 'next'"
echo "      → node_modules 缺失。要么从旧机器/备份取回，要么重新构建产物。"
echo ""
echo "  9100 在听但 /readerx 502"
echo "      → nginx 侧问题，看 conf/nginx/mybooks.conf 的 upstream。"
echo ""
echo "  /readerx 返回 301/308"
echo "      → 正常。尾斜杠重定向，浏览器会自动跟随。"
echo ""
echo "  都正常但书页空白"
echo "      → 前端问题。F12 看 Console 报错和 Network 里失败的 /api/mybooks/* 请求。"
line
