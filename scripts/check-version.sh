#!/bin/sh
# ============================================================
# check-version.sh —— 运行期版本全链路自检
#
# 页脚底部显示的版本串，链路是：
#   docker-compose.yml 的 GIT_VERSION
#     -> docker build --build-arg（或 Dockerfile 默认 ARG）
#     -> 镜像内 webserver/version.py 的 VERSION
#     -> GET /api/user/info 的 sys.version
#     -> 前端 AppFooter 读 store.sys.version
#
# 这串跟 app/dist 无关：dist 换了、版本号没换，页脚就还是旧号。
# 所以 deploy.sh / upgrade.sh 构建后、启动后各跑一次本脚本，不一致直接退出。
#
# 用法（在 audiobook 目录或 scripts/ 下都行）：
#   sh scripts/check-version.sh            全链路（镜像 + 容器 + 接口）
#   sh scripts/check-version.sh --image    只看镜像（构建完、还没起容器时用）
#
# 退出码：0 一致；1 有环节不一致；2 环境/文件缺失
# 输出里 xxx_version= 这些行是纯 ASCII 原值，便于窄终端下核对。
# ============================================================

set -u

DIR="$(cd "$(dirname "$0")" && pwd)"
if [ ! -f "$DIR/Dockerfile" ]; then
    DIR="$(cd "$DIR/.." && pwd)"
fi
if [ ! -f "$DIR/webserver/version.py" ]; then
    echo "!! 找不到 webserver/version.py（当前目录: $DIR）"
    exit 2
fi
cd "$DIR" || exit 2

IMAGE="${IMAGE:-mybooks-local:latest}"
CONTAINER="${CONTAINER:-audiobook-mybooks-1}"
MODE="${1:-all}"

# 注意：version.py 若是 CRLF 行尾，上面这条 sed 只替换到收尾引号，
# 行尾那个 \r 会留在输出里（终端看不见，但会让下面所有比较全部失败）。
# 所以统一 tr -d '\r' 洗一遍。
PKG_VER=$(sed -n 's/^VERSION[[:space:]]*=[[:space:]]*"\(.*\)"/\1/p' webserver/version.py | head -1 | tr -d '\r')
if [ -z "$PKG_VER" ]; then
    echo "!! 读不出 webserver/version.py 的 VERSION"
    exit 2
fi

fail=0
echo "pkg_version=$PKG_VER"

# 顺带报一下 compose 里的值：它只影响「手工 docker compose build」，
# 本包的两个脚本都用 --build-arg 显式传参，不依赖它。
COMPOSE_VER=$(sed -n 's/^[[:space:]]*GIT_VERSION:[[:space:]]*"\{0,1\}\([^"]*\)"\{0,1\}[[:space:]]*$/\1/p' docker-compose.yml 2>/dev/null | head -1 | tr -d '\r')
[ -n "$COMPOSE_VER" ] && echo "compose_version=${COMPOSE_VER}（仅手工 compose build 时生效）"

# ---------- 镜像内版本 ----------
IMG_VER=""
if docker image inspect "$IMAGE" >/dev/null 2>&1; then
    IMG_VER=$(docker run --rm "$IMAGE" sh -c \
        'cd /var/www/mybooks && python3 -c "import webserver.version as v;print(v.VERSION)"' 2>/dev/null | tail -1 | tr -d '\r')
    echo "image_version=${IMG_VER:-<unreadable>}"
    if [ "$IMG_VER" != "$PKG_VER" ]; then
        echo "!! 镜像内版本与包内不一致 —— 构建参数没进去（旧 GIT_VERSION / 复用了旧缓存层）"
        fail=1
    fi
else
    echo "!! 镜像不存在: $IMAGE"
    fail=1
fi

if [ "$MODE" = "--image" ]; then
    [ "$fail" = 0 ] && echo "OK: image version = $PKG_VER"
    exit $fail
fi

# ---------- 容器内版本 ----------
if docker inspect "$CONTAINER" >/dev/null 2>&1; then
    RUN_VER=$(docker exec "$CONTAINER" sh -c \
        'cd /var/www/mybooks && python3 -c "import webserver.version as v;print(v.VERSION)"' 2>/dev/null | tail -1 | tr -d '\r')
    echo "container_version=${RUN_VER:-<unreadable>}"
    if [ "$RUN_VER" != "$PKG_VER" ]; then
        echo "!! 容器内版本不一致 —— 容器跑的可能还是旧镜像"
        echo "   修: docker compose up -d --force-recreate --no-build"
        fail=1
    fi

    # ---------- 接口返回值（页脚真正显示的那个） ----------
    API_VER=$(docker exec "$CONTAINER" python3 -c 'import json,urllib.request as u
try:
    print(json.load(u.urlopen("http://127.0.0.1/api/user/info", timeout=10)).get("sys", {}).get("version", ""))
except Exception:
    print("")' 2>/dev/null | tail -1 | tr -d '\r')
    echo "api_version=${API_VER:-<unavailable>}"
    if [ -n "$API_VER" ] && [ "$API_VER" != "$PKG_VER" ]; then
        echo "!! 接口返回的版本不一致 —— 浏览器页脚显示的就是这个值"
        fail=1
    fi
else
    echo "container_version=<not running: $CONTAINER>"
fi

if [ "$fail" = 0 ]; then
    echo "OK: version chain = $PKG_VER"
else
    echo "FAIL: 上面带 !! 的行就是断点"
fi
exit $fail
