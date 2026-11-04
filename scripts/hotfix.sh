#!/bin/sh
# ============================================================
# hotfix.sh —— 只改 Python 时，不重建镜像也能上线
#
# 用法（在 /volume1/docker 下）：
#   sh audiobook/scripts/hotfix.sh audiobook-deploy-4.6.0-14.tar.gz
#   sh audiobook/scripts/hotfix.sh <包> --restart    # 顺便重启容器
#
# 为什么需要它
# ------------
# upgrade.sh 走的是「全新解压 + docker compose build + up -d」，全量构建在
# NAS 上要十几分钟。但绝大多数修复（比如 4.6.0-14 的 db.cache）只改了
# webserver/ 下的 .py——这部分在 Dockerfile 里就是 `COPY webserver/`，
# 纯 Python，不参与编译。
#
# 真正需要重建的只有三类：
#   1. app/ 前端源码有改动（要 npm run build-spa）
#   2. myreader-dist/ 产物有改动（要重新导出 Next standalone）
#   3. Dockerfile / requirements / 系统包有改动
# 这三类之外，直接替换容器里 /var/www/mybooks/webserver/ 就够了。
#
# 本脚本做的事：
#   1. 从包里取出 webserver/（和 tools/），解到宿主机临时目录
#   2. docker cp 进容器，覆盖同名文件
#   3. 语法预检：容器内 python -m compileall，编译不过就不重启
#   4. 备份被覆盖的旧目录（可回滚）
#   5. 按需重启（--restart）
#
# 不做什么：不动数据、不动前端产物、不动 nginx/supervisor 配置。
# 需要那些改动的版本，老老实实跑 upgrade.sh。
# ============================================================
set -e

PKG="$1"
RESTART="0"
for a in "$@"; do
    [ "$a" = "--restart" ] && RESTART="1"
done

BASE="${BASE:-/volume1/docker}"
SRC="$BASE/audiobook"
CONTAINER="${CONTAINER:-audiobook-mybooks-1}"
BK_ROOT="$BASE/audiobook-hotfix-backup"

if [ -z "$PKG" ]; then
    echo "用法: sh scripts/hotfix.sh /path/to/audiobook-deploy-vX.Y.Z.tar.gz [--restart]"
    exit 1
fi
[ -f "$PKG" ] || { echo "!! 找不到压缩包: $PKG"; exit 1; }
case "$PKG" in
    /*) ;;
    *) PKG="$(cd "$(dirname "$PKG")" && pwd)/$(basename "$PKG")" ;;
esac

echo "============================================================"
echo " audiobook 热更新（仅 Python）"
echo "   包     : $PKG"
echo "   容器   : $CONTAINER"
echo "   重启   : $([ "$RESTART" = "1" ] && echo 是 || echo 否（只覆盖文件）)"
echo "============================================================"

# ---------- 0. 容器必须在跑 ----------
if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || echo false)" != "true" ]; then
    echo "!! 容器 $CONTAINER 没在运行，请先 docker compose up -d"
    exit 1
fi

# ---------- 1. 判断这个包到底改了哪部分 ----------
echo "==> [1/5] 检查包内容"
TOP=$(tar -tzf "$PKG" 2>/dev/null | head -1 | sed 's#/.*##')
STRIP=0
if tar -tzf "$PKG" 2>/dev/null | head -1 | grep -q '/'; then
    STRIP=1
    echo "    检测到外层目录：$TOP（解压时 strip 1 层）"
fi

HAS_WEBSERVER=$(tar -tzf "$PKG" 2>/dev/null | grep -c "webserver/base/audio_dir.py\|webserver/services/audios_import.py" || true)
if [ "$HAS_WEBSERVER" = "0" ]; then
    echo "    !! 包里没有预期的 webserver 文件，先确认是不是打错了包"
    exit 1
fi
echo "    OK：包内 webserver/ 结构正常"

# ---------- 2. 解到临时目录（只取需要的部分） ----------
echo "==> [2/5] 解出 webserver/ 与 tools/"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
if [ "$STRIP" = "1" ]; then
    tar -xzf "$PKG" -C "$TMP" --strip-components=1 \
        "$TOP/webserver" "$TOP/tools" "$TOP/server.py" 2>/dev/null || \
    tar -xzf "$PKG" -C "$TMP" --strip-components=1
else
    tar -xzf "$PKG" -C "$TMP" webserver tools server.py 2>/dev/null || \
    tar -xzf "$PKG" -C "$TMP"
fi
[ -d "$TMP/webserver" ] || { echo "!! 解压后没有 webserver/"; exit 1; }
# 清掉可能混进来的字节码缓存，避免新旧 .pyc 打架
find "$TMP" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "$TMP" -name '*.pyc' -delete 2>/dev/null || true
echo "    webserver: $(find "$TMP/webserver" -name '*.py' | wc -l) 个 .py 文件"

# ---------- 3. 备份容器里的旧代码 ----------
echo "==> [3/5] 备份容器内旧代码"
BK="$BK_ROOT/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BK"
docker cp "$CONTAINER:/var/www/mybooks/webserver" "$BK/webserver" >/dev/null 2>&1 || {
    echo "    !! 备份失败，为安全起见中止"
    exit 1
}
echo "    已备份到: $BK/webserver"
echo "    回滚命令: docker cp $BK/webserver/. $CONTAINER:/var/www/mybooks/webserver/"

# ---------- 4. 覆盖 ----------
echo "==> [4/5] 覆盖容器内代码"
# 用 /tmp 中转再 mv，避免 docker cp 到运行中的目录时出现「半新半旧」
docker cp "$TMP/webserver" "$CONTAINER:/tmp/webserver.new" >/dev/null
docker exec "$CONTAINER" sh -c '
set -e
rm -rf /var/www/mybooks/webserver.old
mv /var/www/mybooks/webserver /var/www/mybooks/webserver.old
mv /tmp/webserver.new /var/www/mybooks/webserver
chown -R mybooks:mybooks /var/www/mybooks/webserver
'
if [ -f "$TMP/server.py" ]; then
    docker cp "$TMP/server.py" "$CONTAINER:/var/www/mybooks/server.py" >/dev/null
    echo "    server.py 已更新"
fi
if [ -d "$TMP/tools" ]; then
    docker cp "$TMP/tools" "$CONTAINER:/tmp/tools.new" >/dev/null
    docker exec "$CONTAINER" sh -c '
    rm -rf /var/www/mybooks/tools.old
    mv /var/www/mybooks/tools /var/www/mybooks/tools.old 2>/dev/null || true
    mv /tmp/tools.new /var/www/mybooks/tools
    chown -R mybooks:mybooks /var/www/mybooks/tools
    '
    echo "    tools/ 已更新"
fi

# ---------- 5. 语法预检 ----------
echo "==> [5/5] 容器内语法预检"
if docker exec "$CONTAINER" python3 -m compileall -q /var/www/mybooks/webserver >/tmp/compile.log 2>&1; then
    echo "    ✅ 全部 .py 编译通过"
else
    echo "    ❌ 有文件编译失败，已自动回滚："
    docker exec "$CONTAINER" sh -c '
    rm -rf /var/www/mybooks/webserver
    mv /var/www/mybooks/webserver.old /var/www/mybooks/webserver
    ' 2>/dev/null || true
    tail -20 /tmp/compile.log 2>/dev/null || true
    echo "    已恢复为旧代码，容器未重启。"
    exit 1
fi

echo
if [ "$RESTART" = "1" ]; then
    echo "==> 重启容器（supervisor 会拉起新代码）"
    docker restart "$CONTAINER" >/dev/null
    echo "    等待服务就绪..."
    i=0
    while [ $i -lt 90 ]; do
        if docker exec "$CONTAINER" test -S /var/run/supervisor.sock 2>/dev/null; then
            ST=$(docker exec "$CONTAINER" supervisorctl status 2>/dev/null || true)
            if [ -n "$ST" ] && ! echo "$ST" | grep -qE 'STARTING'; then
                break
            fi
        fi
        i=$((i + 1)); sleep 2
    done
    echo
    docker exec "$CONTAINER" supervisorctl status 2>&1 | sed 's/^/    /' || true
    echo
    CODE=$(docker exec "$CONTAINER" python3 -c 'import urllib.request as u; print(u.urlopen("http://127.0.0.1/", timeout=10).status)' 2>&1 | tail -1)
    case "$CODE" in
        200) echo "    HTTP 自检: 200 页面正常" ;;
        *)   echo "    HTTP 自检异常: $CODE（看 docker logs --tail 50 $CONTAINER）" ;;
    esac
else
    echo "注意：文件已更新但**没有重启**，当前跑的还是旧内存里的代码。"
    echo "    生效请执行：docker restart $CONTAINER"
    echo "    或重跑本脚本加 --restart"
fi

echo
echo "============================================================"
echo " 热更新完成（未重建镜像，未动数据）"
echo "   备份: $BK/webserver"
echo "   回滚: docker cp $BK/webserver/. $CONTAINER:/var/www/mybooks/webserver/ && docker restart $CONTAINER"
echo "============================================================"
