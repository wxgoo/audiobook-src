#!/bin/sh
# ============================================================
# check-deployed-version.sh
# 定位「部署后页脚版本还是旧的」是哪一环没换。
#
# 页脚版本串的链路（dist 不参与）：
#   docker-compose.yml 的 GIT_VERSION
#     -> docker build --build-arg（或 Dockerfile 默认 ARG）
#     -> 镜像内 webserver/version.py 的 VERSION
#     -> GET /api/user/info 的 sys.version
#     -> AppFooter 读 store.sys.version
#
# 用法（NAS 上，audiobook 目录内或同级）：
#   sh check-deployed-version.sh          只诊断
#   sh check-deployed-version.sh --fix    诊断后改 compose + 重建 + 重启
#
# 说明：输出里的 raw 行都是纯 ASCII 原值，中文只作解释，
#      避免宽字符在窄终端里折行错位导致看不清。
# ============================================================

set -u

FIX=0
[ "${1:-}" = "--fix" ] && FIX=1

SRC=""
for d in . .. ./audiobook /volume1/docker/audiobook; do
    if [ -f "$d/docker-compose.yml" ] && [ -f "$d/webserver/version.py" ]; then
        SRC="$d"
        break
    fi
done
if [ -z "$SRC" ]; then
    echo "!! 找不到源码目录（需同时有 docker-compose.yml 和 webserver/version.py）"
    exit 2
fi
cd "$SRC" || exit 2

echo "SRC=$(pwd)"
echo

FAIL=0
bad()  { echo "  [X]  $*"; FAIL=$((FAIL + 1)); }
good() { echo "  [OK] $*"; }
warn() { echo "  [!]  $*"; }

# ---------- 1. 期望版本 ----------
echo "[1/6] 期望版本（源码 webserver/version.py）"
SRC_VER=$(sed -n 's/^VERSION[[:space:]]*=[[:space:]]*"\(.*\)"/\1/p' webserver/version.py | head -1 | tr -d '\r')
[ -n "$SRC_VER" ] || { bad "读不出 VERSION"; SRC_VER="unknown"; }
echo "  raw: VERSION = \"$SRC_VER\""
echo

# ---------- 2. compose 构建参数 ----------
echo "[2/6] compose 的构建参数"
RAW_COMPOSE=$(grep -n '^[[:space:]]*GIT_VERSION:' docker-compose.yml 2>/dev/null | head -1)
[ -n "$RAW_COMPOSE" ] || RAW_COMPOSE="(none)"
echo "  raw: $RAW_COMPOSE"
COMPOSE_VER=$(printf '%s\n' "$RAW_COMPOSE" | sed -n 's/^[0-9]*:[[:space:]]*GIT_VERSION:[[:space:]]*"\{0,1\}\([^"]*\)"\{0,1\}[[:space:]]*$/\1/p' | tr -d '\r')
if [ -z "$COMPOSE_VER" ] || [ "$COMPOSE_VER" = "(none)" ]; then
    warn "compose 没有 GIT_VERSION，构建回退到 Dockerfile 默认 ARG"
elif [ "$COMPOSE_VER" != "$SRC_VER" ]; then
    bad "compose=$COMPOSE_VER 与期望 $SRC_VER 不同"
    echo "      用 compose 构建会把旧值写进镜像"
    echo "      修: sh $0 --fix   （会先改这一行再重建）"
else
    good "compose=$COMPOSE_VER"
fi
echo

# ---------- 3. 镜像 ----------
echo "[3/6] 镜像 mybooks-local:latest"
IMG_ID=""
if docker image inspect mybooks-local:latest >/dev/null 2>&1; then
    IMG_ID=$(docker image inspect -f '{{.Id}}' mybooks-local:latest | cut -c1-19)
    IMG_CREATED=$(docker image inspect -f '{{.Created}}' mybooks-local:latest)
    echo "  raw: id=$IMG_ID"
    echo "  raw: created=$IMG_CREATED"
else
    bad "本机没有 mybooks-local:latest"
fi
echo

# ---------- 4. 谁在服务 9800 ----------
echo "[4/6] 9800 端口上的容器"
PORT="${PORT:-9800}"
CNAME=$(docker ps --filter "publish=$PORT" --format '{{.Names}}' 2>/dev/null | head -1)
[ -n "$CNAME" ] || CNAME=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -i mybooks | head -1)
if [ -z "$CNAME" ]; then
    bad "没有运行中的容器"
else
    CIMAGE=$(docker inspect -f '{{.Image}}' "$CNAME" 2>/dev/null | cut -c1-19)
    CWORKDIR=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$CNAME" 2>/dev/null)
    echo "  raw: name=$CNAME"
    echo "  raw: image=$CIMAGE"
    echo "  raw: from=${CWORKDIR:-(not compose)}"
    if [ -n "$IMG_ID" ] && [ "$CIMAGE" != "$IMG_ID" ]; then
        bad "容器镜像 != mybooks-local:latest"
        echo "      修: docker compose up -d --force-recreate --no-build"
    elif [ -n "$IMG_ID" ]; then
        good "容器用的就是当前镜像"
    fi
    if [ -n "$CWORKDIR" ] && [ "$(cd "$CWORKDIR" 2>/dev/null && pwd)" != "$(pwd)" ]; then
        warn "容器来自别的目录: $CWORKDIR"
    fi
fi
echo

# ---------- 5. 容器内真实版本 ----------
echo "[5/6] 容器内 webserver/version.py（决定性）"
RUN_VER=""
if [ -n "$CNAME" ]; then
    RUN_VER=$(docker exec "$CNAME" sh -c 'cd /var/www/mybooks && python3 -c "import webserver.version as v; print(v.VERSION)"' 2>/dev/null | tail -1)
fi
if [ -n "$RUN_VER" ]; then
    echo "  raw: container VERSION = $RUN_VER"
    if [ "$RUN_VER" != "$SRC_VER" ]; then
        bad "镜像内版本是旧的（构建时写入的）"
    else
        good "镜像内版本正确"
    fi
else
    warn "docker exec 取不到版本"
    echo "      手工: docker exec $CNAME sh -c 'cd /var/www/mybooks && grep ^VERSION webserver/version.py'"
fi
echo

# ---------- 6. 接口 ----------
echo "[6/6] 接口 /api/user/info 的 sys.version"
API_VER=$(curl -s --max-time 8 "http://127.0.0.1:$PORT/api/user/info" 2>/dev/null | tr ',' '\n' | sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)
if [ -z "$API_VER" ]; then
    warn "取不到（端口不对或需登录）"
    echo "      手工: curl -s http://127.0.0.1:$PORT/api/user/info | head -c 300"
elif [ "$API_VER" != "$SRC_VER" ]; then
    bad "接口返回 $API_VER（页脚显示的就是它）"
else
    good "接口返回 $API_VER"
fi
echo

echo "================ SUMMARY ================"
if [ "$FAIL" -eq 0 ]; then
    echo "后端链路已是 $SRC_VER。页脚仍旧则："
    echo "  1) 浏览器强刷 Ctrl+Shift+R 或关标签重开"
    echo "  2) 确认访问的就是这个容器（8080 是官方版）"
    echo "  3) 反代若缓存 /api/，清一次"
else
    echo "不一致 $FAIL 处。整体修法："
    echo
    echo "  cd $(pwd)"
    echo "  sh $0 --fix"
    echo
    echo "或手工三步："
    echo "  sed -i 's/^\\([[:space:]]*GIT_VERSION:\\).*/\\1 \"$SRC_VER\"/' docker-compose.yml"
    echo "  DOCKER_BUILDKIT=0 docker build --no-cache --build-arg GIT_VERSION=$SRC_VER -t mybooks-local:latest ."
    echo "  docker compose up -d --force-recreate --no-build"
    echo
    echo "构建完先验一行再启动："
    echo "  docker run --rm mybooks-local:latest sh -c 'cd /var/www/mybooks && python3 -c \"import webserver.version as v;print(v.VERSION)\"'"
fi
echo "========================================="

# ---------- 自动修复 ----------
if [ "$FIX" = "1" ]; then
    echo
    echo "==> --fix: 对齐 compose 的 GIT_VERSION"
    if [ "$COMPOSE_VER" != "$SRC_VER" ]; then
        cp docker-compose.yml "docker-compose.yml.bak-$(date +%Y%m%d-%H%M%S)"
        sed -i "s/^\([[:space:]]*GIT_VERSION:[[:space:]]*\).*/\1\"$SRC_VER\"/" docker-compose.yml
        echo "  raw: $(grep -n '^[[:space:]]*GIT_VERSION:' docker-compose.yml | head -1)"
    fi
    echo "==> 重建镜像（--no-cache，显式 build-arg）"
    DOCKER_BUILDKIT=0 docker build --no-cache --build-arg "GIT_VERSION=$SRC_VER" -t mybooks-local:latest . || {
        echo "!! 构建失败，旧容器仍在跑，站点不受影响"
        exit 1
    }
    echo "==> 校验镜像内版本"
    NEW_VER=$(docker run --rm mybooks-local:latest sh -c 'cd /var/www/mybooks && python3 -c "import webserver.version as v;print(v.VERSION)"' 2>/dev/null | tail -1)
    echo "  raw: image VERSION = ${NEW_VER:-(读取失败)}"
    if [ "$NEW_VER" != "$SRC_VER" ]; then
        echo "!! 镜像内版本仍不是 $SRC_VER，已中止，未替换容器"
        exit 1
    fi
    echo "==> 重建容器"
    docker compose up -d --force-recreate --no-build || exit 1
    echo "==> 完成，复查：sh $0"
fi
