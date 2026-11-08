#!/bin/sh
# ---------------------------------------------------------------------------
# 恢复脚本：镜像丢失 + build 导出层失败（layer does not exist）时用
#
# 适用现场：
#   - docker images mybooks-local:latest 报 Unable to find image
#   - docker build 在 COPY app/ 之后报 failed to get layer ...: layer does not exist
#   - 存储驱动 btrfs（群晖），数据目录 /volume1/@docker，悬空层上百个
#   - 出网被拦（registry-1.docker.io 的 x509 报错），不能依赖拉取
#
# 用法（root）：
#   cd <包目录> && sh scripts/recover.sh   # 完整恢复（也可把本文件放包根目录后 sh recover.sh）
#   sh scripts/recover.sh build            # 只到"构建+校验"，不动容器
#   sh scripts/recover.sh check            # 只体检，不改动
#
# 关键顺序（别搞反）：
#   先重启守护进程 → 再用缓存构建（绕开会写坏的那层）
#   → 缓存这条路失败才清理并 --no-cache 全量重来
#   ——先 prune 会把可用的缓存层一起删掉，等于逼自己全量重建。
#
# 安全边界：只用 docker image prune -f（只删无标签悬空层）与
# docker builder prune -af（只删构建缓存），绝不用 -a / --volumes，
# 不碰带标签镜像、不碰数据卷。
# ---------------------------------------------------------------------------
set -u

MODE="${1:-all}"
PROJ="${PROJ:-}"
IMAGE="${IMAGE:-mybooks-local:latest}"
CONTAINER="${CONTAINER:-audiobook-mybooks-1}"

say() { printf '%s\n' "$*"; }
hr()  { say "------------------------------------------------------------"; }

[ "$(id -u)" = "0" ] || { say "请用 root 运行：sudo -i 后再执行"; exit 1; }

# 允许两种跑法：cd 包根目录 && sh recover.sh，或 sh scripts/recover.sh
if [ -z "$PROJ" ]; then
    if [ -f "webserver/version.py" ]; then
        PROJ="$(pwd)"
    else
        PROJ="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)"
    fi
fi
[ -f "$PROJ/webserver/version.py" ] || { say "当前目录不是项目目录（找不到 webserver/version.py）：$PROJ"; exit 1; }
cd "$PROJ" || exit 1

VER=$(sed -n 's/^VERSION[[:space:]]*=[[:space:]]*"\(.*\)"/\1/p' webserver/version.py | tr -d '\r')
say "==> 项目: $PROJ"
say "==> 包内版本: ${VER:-取不到}"
say "==> 模式: $MODE"
hr

restart_docker() {
    # DSM 7.2：没有 synoservice、没有 docker.service，套件叫 ContainerManager（不是 Docker）。
    # 按可用性逐个试，别写死一个名字。
    for pkg in ContainerManager Docker; do
        if [ -x /usr/syno/bin/synopkg ] && /usr/syno/bin/synopkg status "$pkg" >/dev/null 2>&1; then
            say "  重启套件: synopkg restart $pkg"
            /usr/syno/bin/synopkg restart "$pkg" >/dev/null 2>&1
            break
        fi
    done
    if ! docker info >/dev/null 2>&1; then
        if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files 2>/dev/null | grep -q "^docker\.service"; then
            systemctl restart docker >/dev/null 2>&1
        elif [ -x /usr/syno/bin/synoservice ]; then
            /usr/syno/bin/synoservice --restart pkgctl-Docker >/dev/null 2>&1
        fi
    fi
    i=0
    while [ "$i" -lt 90 ]; do
        docker info >/dev/null 2>&1 && { say "  守护进程已恢复"; return 0; }
        i=$((i + 1)); sleep 2
    done
    say "  !! 守护进程 180s 未恢复，去套件中心确认 Container Manager 状态"
    return 1
}

# ---------- 体检 ----------
say "[1] 现状"
say "docker 版本: $(docker version --format '{{.Server.Version}}' 2>/dev/null)"
say "存储驱动: $(docker info -f '{{.Driver}}' 2>/dev/null)   数据目录: $(docker info -f '{{.DockerRootDir}}' 2>/dev/null)"
say ""
docker system df 2>/dev/null
say ""
if docker image inspect "$IMAGE" >/dev/null 2>&1; then
    say "目标镜像 $IMAGE: 存在"
    HAVE_IMAGE=1
else
    say "目标镜像 $IMAGE: **不存在**（需要构建）"
    HAVE_IMAGE=0
fi
say "基础镜像: $(docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | grep mybooks_base | head -1 | sed 's/^$/(未找到)/')"
say ""
say "-- 相关容器 --"
docker ps -a --filter "name=$CONTAINER" --format '  {{.Names}}  {{.Status}}  {{.Image}}' 2>/dev/null || true
say ""
say "-- OOM 痕迹 --"
if dmesg 2>/dev/null | grep -qiE "killed process|out of memory"; then
    dmesg 2>/dev/null | grep -iE "killed process|out of memory" | tail -3
else
    say "  无（或无权读 dmesg）"
fi
hr

if [ "$MODE" = "check" ]; then
    say "体检结束。要恢复执行： sh $0"
    exit 0
fi

if [ "$HAVE_IMAGE" = "1" ]; then
    say "[2] 镜像已存在，跳过构建，直接校验"
else
    say "[1.5] 基础镜像预检（构建只依赖 mybooks_base；node 镜像自 build.28 起不再需要）"
    if [ -f "$PROJ/scripts/base-image.sh" ]; then
        # shellcheck source=scripts/base-image.sh
        . "$PROJ/scripts/base-image.sh"
        ensure_base_image "$PROJ" "$PWD" \
            || say "  !! 基础镜像拿不到 —— 先在别的机器 sh scripts/export-images.sh，把 images/ 拷过来再重跑"
    else
        say "  （包内没有 scripts/base-image.sh，跳过）"
    fi
    hr

    say "[2] 重启 Docker 守护进程（btrfs 下重建层索引，layer does not exist 的主解药）"
    restart_docker || exit 1
    hr

    say "[3] 第一轮构建：不带 --no-cache，复用仍在的缓存层"
    say "    目的：绕开上次写坏的那一层（失败点就在 COPY app/ 那一层）"
    BUILD_OK=0
    DOCKER_BUILDKIT=0 docker build --build-arg GIT_VERSION="$VER" -t "$IMAGE" . && BUILD_OK=1
    [ "$BUILD_OK" = "1" ] && say "  第一轮成功" || say "  第一轮失败"
    hr

    if [ "$BUILD_OK" != "1" ]; then
        say "[4] 第二轮：清掉碎片再全量重建"
        say "    docker image prune -f   （88 个悬空层，约 50GB 可回收）"
        docker image prune -f 2>&1 | tail -2
        say "    docker builder prune -af（BuildKit 缓存 1595 条 3.9GB）"
        docker builder prune -af 2>&1 | tail -2
        say ""
        restart_docker || exit 1
        say ""
        say "    开始全量构建（--no-cache，耗时较久）"
        DOCKER_BUILDKIT=0 docker build --no-cache --build-arg GIT_VERSION="$VER" -t "$IMAGE" . && BUILD_OK=1
        hr
    fi

    if [ "$BUILD_OK" != "1" ]; then
        say "[5] 第三轮：改用 BuildKit（本机有 1595 条 BuildKit 缓存，说明这条路能走）"
        DOCKER_BUILDKIT=1 docker build --build-arg GIT_VERSION="$VER" -t "$IMAGE" . && BUILD_OK=1
        hr
    fi

    if [ "$BUILD_OK" != "1" ]; then
        say "!! 三轮都失败。把下面四行结果发我："
        say "   docker system df"
        say "   docker images -f dangling=true -q | wc -l"
        say "   dmesg | grep -i 'killed process' | tail -3"
        say "   ls -ld /volume1/@docker/btrfs"
        say ""
        say "下一步通常是：换一台机器 docker build 后 docker save / load，"
        say "或把 storage-driver 换成 overlay2（会清空镜像，数据卷不受影响）。"
        exit 1
    fi
fi

# ---------- 版本校验 ----------
say "[6] 校验镜像内版本（页脚显示的就是这个）"
GOT=$(docker run --rm "$IMAGE" sh -c 'cd /var/www/mybooks && python3 -c "import webserver.version as v;print(v.VERSION)"' 2>/dev/null | tr -d '\r')
say "  包内=$VER / 镜像内=$GOT"
if [ "$GOT" != "$VER" ]; then
    say "  !! 不一致，先别起容器。用 --build-arg 显式传版本重来："
    say "     DOCKER_BUILDKIT=0 docker build --no-cache --build-arg GIT_VERSION=$VER -t $IMAGE ."
    exit 1
fi
say "  OK"
hr

if [ "$MODE" = "build" ]; then
    say "构建完成，未动容器。要起容器： sh $0 all"
    exit 0
fi

# ---------- 起容器 ----------
say "[7] 重建容器（镜像已在本地，不会再尝试 pull）"
docker compose up -d --force-recreate --no-build || docker-compose up -d --force-recreate --no-build || {
    say "  !! compose 起容器失败。多半是它仍想 pull（出网被拦）。改用纯 docker："
    say "     docker rm -f $CONTAINER 2>/dev/null"
    say "     docker run -d --name $CONTAINER --restart always -p 9800:80 \\"
    say "       -v /volume1/docker/audiobook-data:/data \\"
    say "       --security-opt seccomp=unconfined $IMAGE"
    exit 1
}
hr

say "[8] 全链路校验"
if [ -f scripts/check-version.sh ]; then
    CONTAINER="$CONTAINER" sh scripts/check-version.sh || exit 1
else
    docker ps --filter "name=$CONTAINER" --format '{{.Names}} {{.Status}}'
    curl -s http://127.0.0.1:9800/api/user/info | grep -o '"version": *"[^"]*"' | head -1
fi
say ""
say "完成。浏览器 Ctrl+Shift+R 强刷，页脚应为 $VER"
