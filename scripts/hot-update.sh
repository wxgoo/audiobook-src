#!/bin/sh
# ============================================================
# hot-update.sh —— 用仓库当前工作区热更「正在运行的容器」
#                  （前端 dist + 后端 Python，不重建镜像）
#
# 用法（在仓库根目录，即 /volume1/docker/audiobook）：
#   sh scripts/hot-update.sh                 # 覆盖 dist + webserver，语法预检，重启 tornado
#   sh scripts/hot-update.sh --no-restart    # 只覆盖文件，不动进程（纯前端改动可用）
#   sh scripts/hot-update.sh --no-backup     # 跳过备份（默认会把旧文件打包留底）
#   CONTAINER=别的容器名 sh scripts/hot-update.sh
#
# 适用 / 不适用
# ------------
# 适用：只改了 app/src（前端，且已 `cd app && bash build.sh` 出过 dist）、
#       或只改了 webserver/ 下的 .py。
# 不适用（老老实实 docker compose up -d --build）：
#       Dockerfile / requirements / 系统包 / conf(nginx、supervisor) / myreader-dist。
#
# 为什么能热更
# ------------
# 前端是静态文件，nginx 直接读 /var/www/mybooks/app/dist，换掉文件即刻生效；
# 后端是纯 Python，被覆盖后只需重启 tornado 进程（docker restart 太重，nginx 不用动）。
#
# 注意：热更改的是容器可写层，`docker compose up -d --build` 重建后会回到镜像里的版本，
# 所以热更只是「先上线」，源码该提交还是要提交、镜像该重建还是要重建。
# ============================================================
set -e

RESTART="1"
BACKUP="1"
for a in "$@"; do
    case "$a" in
        --no-restart) RESTART="0" ;;
        --no-backup) BACKUP="0" ;;
        --restart) RESTART="1" ;;
        -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
        *) echo "!! 未知参数: $a"; exit 1 ;;
    esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONTAINER="${CONTAINER:-audiobook-mybooks-1}"
BASE="${BASE:-$(dirname "$ROOT")}"
BK_ROOT="$BASE/audiobook-hotfix-backup"
APP_DIR_IN_CONTAINER="/var/www/mybooks/app"
CODE_DIR_IN_CONTAINER="/var/www/mybooks"

echo "============================================================"
echo " audiobook 热更新（dist + Python）"
echo "   仓库   : $ROOT"
echo "   容器   : $CONTAINER"
echo "   重启   : $([ "$RESTART" = "1" ] && echo 是（tornado） || echo 否（只覆盖文件）)"
echo "   备份   : $([ "$BACKUP" = "1" ] && echo 是 || echo 否)"
echo "============================================================"

# ---------- 前置检查 ----------
command -v docker >/dev/null 2>&1 || { echo "!! 找不到 docker 命令"; exit 1; }
docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -q true \
    || { echo "!! 容器 $CONTAINER 没在运行（改 CONTAINER 环境变量指定正确名字）"; exit 1; }
[ -f "$ROOT/app/dist/index.html" ] || { echo "!! 缺 app/dist/index.html —— 先在 app/ 下跑 bash build.sh"; exit 1; }
[ -d "$ROOT/webserver" ] || { echo "!! 缺 webserver/ 目录"; exit 1; }

# 前端产物落后于源码时提醒（dist 不是从当前 src 构建的，热更上去等于白更）
if [ -d "$ROOT/app/src" ]; then
    newest_src=$(find "$ROOT/app/src" -type f -newer "$ROOT/app/dist/index.html" 2>/dev/null | head -1)
    [ -n "$newest_src" ] && echo "   !! 提醒：app/src 里有文件比 dist 新（如 $newest_src），先 bash app/build.sh 再热更"
fi

# ---------- 备份 ----------
if [ "$BACKUP" = "1" ]; then
    mkdir -p "$BK_ROOT"
    TS=$(date +%Y%m%d-%H%M%S)
    BK="$BK_ROOT/hot-update-$TS.tar.gz"
    echo "==> [1/5] 备份容器内现有 webserver + dist"
    docker exec "$CONTAINER" tar c -C "$CODE_DIR_IN_CONTAINER" webserver app/dist 2>/dev/null | gzip -1 > "$BK"
    echo "    已存: $BK ($(du -h "$BK" | cut -f1))"
else
    echo "==> [1/5] 跳过备份（--no-backup）"
fi

# ---------- 覆盖前端 ----------
echo "==> [2/5] 覆盖前端 dist"
# 用 tar 管道而不是 docker cp：容器里 dist/avatar、dist/logo 是指向 /data 的软链，
# docker cp 的合并语义撞类型冲突会直接失败（MEMORY.md ②）。
tar c -C "$ROOT/app" dist | docker exec -i "$CONTAINER" tar x -C "$APP_DIR_IN_CONTAINER"
echo "    完成"

# ---------- 覆盖后端 ----------
echo "==> [3/5] 覆盖后端 webserver/（排除 __pycache__ 与 version.py）"
# version.py 由 Dockerfile 在构建时注入 GIT_VERSION，热更不该用工作区版本盖掉它
tar c -C "$ROOT" --exclude=__pycache__ --exclude='*.pyc' --exclude=version.py webserver \
    | docker exec -i "$CONTAINER" tar x -C "$CODE_DIR_IN_CONTAINER"
echo "    完成"

# 属主修正：tar 以 root 解包，进程是 gosu 降权后的 mybooks 在跑
docker exec "$CONTAINER" chown -R mybooks:mybooks \
    "$CODE_DIR_IN_CONTAINER/webserver" "$APP_DIR_IN_CONTAINER/dist" 2>/dev/null || true

# ---------- 语法预检 ----------
echo "==> [4/5] 语法预检（compileall）"
if docker exec "$CONTAINER" python3 -m compileall -q "$CODE_DIR_IN_CONTAINER/webserver" >/tmp/hot-update-compile.log 2>&1; then
    echo "    通过"
else
    echo "  !! Python 语法错误，未重启。详情："
    sed 's/^/     /' /tmp/hot-update-compile.log | tail -20
    echo "  回滚：见上面备份路径，解回容器即可"
    exit 1
fi

# ---------- 重启 ----------
if [ "$RESTART" = "1" ]; then
    echo "==> [5/5] 重启 tornado（nginx 不动，静态文件已生效）"
    docker exec "$CONTAINER" supervisorctl restart tornado 2>&1 | sed 's/^/    /' || {
        echo "  !! supervisorctl 重启失败，退化为整容器重启"
        docker restart "$CONTAINER" >/dev/null
    }
else
    echo "==> [5/5] 跳过重启（--no-restart）"
fi

echo "------------------------------------------------------------"
echo " 验证："
echo "   首页引用的 chunk（应为当前构建的 hash）："
echo "     curl -s http://localhost:9800/ | grep -oE '_nuxt/[a-z0-9]+\\.(js|css)' | sort -u"
echo "   容器内 dist 是否为新产物："
echo "     docker exec $CONTAINER ls $APP_DIR_IN_CONTAINER/dist/_nuxt/ | head"
echo "   浏览器最后一步：Ctrl+Shift+R 强制刷新"
echo "------------------------------------------------------------"
echo " 回滚（如需要）："
echo "   docker exec -i $CONTAINER tar xz -C $CODE_DIR_IN_CONTAINER < $BK_ROOT/hot-update-<时间戳>.tar.gz"
echo "   docker exec $CONTAINER supervisorctl restart tornado"
