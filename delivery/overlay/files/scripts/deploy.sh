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
DATA="${DATA:-/volume1/docker/audiobook-data}"

# 包内运行期版本（唯一权威）。构建时显式传给 Dockerfile，构建后再强校验一次。
# 为什么要显式传：docker-compose.yml 的 GIT_VERSION 只服务于「手工 docker compose build」。
# 现场常会保留自己那份 compose（PUID/PGID、路径是本地化的），里面版本号还是上一版，
# 用它构建就会把旧号写进 webserver/version.py，页脚一直显示旧版本 —— 而 dist 是新的，
# 光比对 index.html 的旧门禁根本发现不了。这里以包内 version.py 为准，compose 写错也不影响。
# 另外：version.py 若是 CRLF 行尾，sed 只替换到收尾引号，行尾 \r 会留在变量里，
# 一旦把它当 --build-arg 传下去，镜像里就会多一个看不见的控制符。统一 tr -d '\r'。
PKG_VER=$(sed -n 's/^VERSION[[:space:]]*=[[:space:]]*"\(.*\)"/\1/p' webserver/version.py | head -1 | tr -d '\r')
if [ -z "$PKG_VER" ]; then
    echo "!! 读不出 webserver/version.py 的 VERSION"
    exit 1
fi
echo "==> 包内版本: $PKG_VER"

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
# 2026-11-09 修订：不再用「数有效链接 >=100」这种模糊判据。
# 现场实锤：myreader-dist 经 Windows 检出/上传/图形界面解压后，
# 119 根符号链接会被压扁成「内容=目标路径文本」的普通文件或空目录：
#   - 启动即 Cannot find module（supervisor FATAL），或
#   - Next.js 显示 Ready，但首个 /reader/open 请求就 500。
# 现在以 scripts/myreader-links.manifest 为权威清单逐根校验，
# 缺失/目标不符一律自动重建（--fix），修不好就停止部署。
mr_fail=0
[ -f myreader-dist/app/server.js ] || { echo "    !! 缺 myreader-dist/app/server.js"; mr_fail=1; }
for sub in "node_modules" "app/node_modules" "app/.next/node_modules"; do
    [ -d "myreader-dist/$sub" ] || { echo "    !! 缺 myreader-dist/$sub"; mr_fail=1; }
done
if [ "$mr_fail" = "1" ]; then
    echo "    !! MyReader 产物不完整 —— 部署后 /readerx 会 502，书页打不开。"
    echo "       补救：从旧机器/备份取回完整 myreader-dist 后重试。"
    exit 1
fi

if [ -f scripts/check-myreader-links.sh ] && [ -f scripts/myreader-links.manifest ]; then
    sh scripts/check-myreader-links.sh --fix || {
        echo "    !! MyReader 链接修复失败，停止部署（镜像会带着坏链接）"
        exit 1
    }
else
    echo "    ! 缺 scripts/check-myreader-links.sh 或 myreader-links.manifest，"
    echo "      退回旧的模糊判据（不建议）。请确认部署包完整。"
    valid=0
    for l in $(find myreader-dist -type l 2>/dev/null); do
        [ -e "$l" ] && valid=$((valid + 1))
    done
    if [ "$valid" -lt 100 ]; then
        echo "    !! 有效链接只有 $valid 个（应 >=119）。多半被解压工具压扁了，"
        echo "       请用命令行解压：tar -xzf <包名>.tar.gz"
        exit 1
    fi
fi
echo "    OK：MyReader 产物与 119 根链接均完整"

# 默认图标/二维码：只在目标不存在时补一份（全新部署自动生效；存量站点不动已有文件）
seed_logo_defaults() {
    logo_src="$DIR/app/public/logo"
    logo_dst="$DATA/books/logo"
    [ -d "$logo_src" ] || return 0
    mkdir -p "$logo_dst" 2>/dev/null || return 0
    for f in favicon.ico link_gongzhonghao.jpg; do
        if [ ! -e "$logo_dst/$f" ] && [ -e "$logo_src/$f" ]; then
            cp "$logo_src/$f" "$logo_dst/$f" && chmod 644 "$logo_dst/$f" 2>/dev/null || true
            echo "    + 初始化默认图标: $logo_dst/$f"
        fi
    done
}
seed_logo_defaults

# 「版本与更新」页做过一键在线热更新时，变更文件会留在数据卷 update-sync/current。
# 必须在构建镜像之前把它们合并进源码目录，否则新镜像仍是旧代码、热更新被冲掉。
SRC="$DIR" DATA="$DATA" sh "$DIR/scripts/sync-hotfix.sh" || {
    echo "    !! 固化在线热更新失败，停止部署"
    exit 1
}

echo "==> [3/5] Docker 构建镜像（BuildKit + --no-cache）"
# 2026-11-09 修订：弃用 legacy builder（DOCKER_BUILDKIT=0）。legacy 在 btrfs 上每层一个
# 子卷，多次构建把缓存池攒到千级后层索引失手（layer does not exist 事故根源），且已发
# deprecation 警告。BuildKit 的上下文快照按 (mtime,size) 判重，包内 index.html mtime 固定、
# 体积可能与上一代相同，理论上可能复用旧快照产出坏镜像——所以下方构建后必须做镜像内
# index.html 的 sha256 比对，坏镜像在这里被当场拦下，不会走到起容器那一步。
build_image() {
    # 选路：NAS 若没装独立 buildx 插件，DOCKER_BUILDKIT=1 docker build 会报
    # "buildx component is missing"。compose v2 内嵌 buildx 库，不依赖插件。
    # compose build 的上下文快照判重风险由下方 index.html 指纹比对兜底。
    if docker buildx version >/dev/null 2>&1; then
        DOCKER_BUILDKIT=1 docker build --no-cache --build-arg "GIT_VERSION=$PKG_VER" \
            -t mybooks-local:latest . || return 1
    else
        docker compose build --no-cache --build-arg "GIT_VERSION=$PKG_VER" || return 1
    fi
    host_sha=$(sha256sum app/dist/index.html | awk '{print $1}')
    img_sha=$(docker run --rm mybooks-local:latest sha256sum /var/www/mybooks/app/dist/index.html | awk '{print $1}')
    if [ "$host_sha" != "$img_sha" ]; then
        echo "!! 镜像内 index.html 与包内不一致：$img_sha != $host_sha"
        echo "   （上下文快照复用的典型症状）处理：docker builder prune -f 后重跑本脚本；"
        echo "    仍不行则 DOCKER_BUILDKIT=0 legacy 兜底一轮"
        return 1
    fi
    echo "==> 镜像内 index.html: $img_sha"
    # 版本门禁：镜像内 version.py 必须等于包内版本。
    # 这一条就是「部署完页脚还是旧版本」的拦网 —— 那个值和 dist 无关，只跟构建参数有关。
    CONTAINER="$CONTAINER" sh scripts/check-version.sh --image || {
        echo "!! 版本门禁未通过，停止部署（容器未启动，站点仍是旧版本，不受影响）"
        return 1
    }
}
if [ "$1" = "build-only" ]; then
    build_image || exit 1
    echo "==> 完成（build-only，未启动）。启动请执行: docker compose up -d --force-recreate --no-build"
    exit 0
fi
build_image || exit 1

echo "==> [4/5] 启动容器"
# --no-build 不可省：up 一旦发现镜像缺失就会重新走 compose 的内嵌 BuildKit 路径。
docker compose up -d --force-recreate --no-build

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
echo "==> 版本自检（页脚显示的就是这个值）"
if ! CONTAINER="$CONTAINER" sh scripts/check-version.sh; then
    echo " !! 版本链路不一致，页脚会显示旧版本。"
    echo "    容器内/接口版本与 $PKG_VER 不一致，先看: sh scripts/check-version.sh"
    exit 1
fi
echo
echo "==> 部署完成。浏览器打开 http://<NAS_IP>:9800 验证；"
echo "    阅读链路测试: http://<NAS_IP>:9800/read/1?format=epub"
echo "    读者组分类回填: docker exec -it $CONTAINER python3 /var/www/mybooks/tools/category_backfill.py"
