#!/bin/sh
# ---------------------------------------------------------------------------
# 诊断/修复 docker build 在 COPY 之后导出镜像失败：
#   failed to export image: failed to create image:
#   failed to get layer sha256:xxx: layer does not exist
#
# 用法（在 docker-compose.yml 所在目录执行）：
#   sh fix-build-layer.sh            # 只诊断，不改动任何东西
#   sh fix-build-layer.sh fix        # 清理 + 重启 docker + 重建 + 校验
#
# 说明：这个报错与业务代码、Dockerfile、dist 无关，是守护进程把某一层写盘
# 失败后该层引用丢失。最常见的三个原因：磁盘/配额满、残留的半成品容器占空间、
# 两个 build 同时在跑互相删中间层。
# ---------------------------------------------------------------------------
set -u

PROJ="${PROJ:-$(pwd)}"
MODE="${1:-diag}"
IMAGE="${IMAGE:-mybooks-local:latest}"
CONTAINER="${CONTAINER:-audiobook-mybooks-1}"

say()  { printf '%s\n' "$*"; }
hr()   { say "------------------------------------------------------------"; }
ok()   { say "[OK]  $*"; }
bad()  { say "[X ]  $*"; }

VER=""
if [ -f "$PROJ/webserver/version.py" ]; then
    VER=$(sed -n 's/^VERSION[[:space:]]*=[[:space:]]*"\(.*\)"/\1/p' "$PROJ/webserver/version.py" | tr -d '\r')
fi

say "==> 项目目录: $PROJ"
say "==> 包内版本: ${VER:-未找到 webserver/version.py}"
say "==> 模式: $MODE"
hr

# ---------- 1. 守护进程与存储驱动 ----------
say "[1/7] Docker 版本与存储驱动"
docker version --format 'client={{.Client.Version}} server={{.Server.Version}}' 2>/dev/null || bad "docker 命令不可用"
ROOTDIR=$(docker info -f '{{.DockerRootDir}}' 2>/dev/null)
DRIVER=$(docker info -f '{{.Driver}}' 2>/dev/null)
say "存储驱动: ${DRIVER:-未知}"
say "数据目录: ${ROOTDIR:-未知}"
if [ "${DRIVER:-}" = "btrfs" ]; then
    say "       （群晖常见；Btrfs 配额或元数据异常时会报 layer does not exist）"
fi
hr

# ---------- 2. 空间 ----------
say "[2/7] 空间检查（关键）"
df -h "${ROOTDIR:-/volume1}" 2>/dev/null | tail -2
say ""
say "-- inode --"
df -i "${ROOTDIR:-/volume1}" 2>/dev/null | tail -2
say ""
say "-- docker 占用 --"
docker system df 2>/dev/null || say "(docker system df 不可用)"
hr

# ---------- 3. 内存与 OOM ----------
say "[3/7] 内存 / 是否被 OOM 杀掉"
free -m 2>/dev/null | head -3
OOM=$(dmesg 2>/dev/null | grep -iE "killed process|out of memory" | tail -5)
if [ -n "$OOM" ]; then
    bad "内核有新近 OOM 记录，构建过程中的进程被强杀会导致层丢失："
    printf '%s\n' "$OOM"
else
    ok "dmesg 无 OOM 记录（或无权读取）"
fi
hr

# ---------- 4. 是否有并发构建 ----------
say "[4/7] 是否有并发/残留的 build 在跑"
CONC=$(ps -ef 2>/dev/null | grep -E "[d]ocker build|[d]ocker-compose.*build|[b]uildkit" | wc -l | tr -d ' ')
say "疑似并发构建进程数: $CONC"
ps -ef 2>/dev/null | grep -E "[d]ocker build|[b]uildx" | head -5
ORPHAN=$(docker ps -a --filter status=created -q 2>/dev/null | wc -l | tr -d ' ')
say "status=created 的半成品容器数: $ORPHAN（每次 build 会留几个，中断后不清理）"
if [ "$ORPHAN" -gt 20 ] 2>/dev/null; then
    bad "残留容器偏多，建议 docker container prune -f"
fi
hr

# ---------- 5. 悬空镜像（构建缓存的挂载点） ----------
say "[5/7] 悬空镜像（历代构建的缓存层就挂在这些层上）"
DANG=$(docker images -f dangling=true -q 2>/dev/null | wc -l | tr -d ' ')
say "dangling 镜像数: $DANG"
docker images -f dangling=true --format '{{.ID}} {{.Size}}' 2>/dev/null | head -5
hr

if [ "$MODE" != "fix" ]; then
    say "诊断结束。确认上面第 2/3/4 项后再执行修复："
    say "  sh $0 fix"
    exit 0
fi

# ---------- 6. 清理 ----------
say "[6/7] 清理残留（只删已停止容器、悬空镜像、未用网络；不动在跑的容器和正常镜像）"
docker container prune -f 2>&1 | tail -2
docker image prune -f 2>&1 | tail -2
docker network prune -f 2>&1 | tail -1
say ""
say "-- 清理后空间 --"
df -h "${ROOTDIR:-/volume1}" 2>/dev/null | tail -1
docker system df 2>/dev/null
hr

say "重启 Docker 守护进程（清掉内存里已失效的层索引）"
if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files 2>/dev/null | grep -q "^docker\.service"; then
    systemctl restart docker 2>&1 | tail -2
elif [ -x /usr/syno/bin/synopkg ]; then
    /usr/syno/bin/synopkg restart Docker 2>&1 | tail -2
elif [ -x /usr/syno/bin/synoservice ]; then
    /usr/syno/bin/synoservice --restart pkgctl-Docker 2>&1 | tail -2
fi
i=0
while [ "$i" -lt 60 ]; do
    if docker info >/dev/null 2>&1; then break; fi
    i=$((i + 1))
    sleep 2
done
if docker info >/dev/null 2>&1; then
    ok "docker 已恢复"
else
    bad "docker 未在 120s 内恢复，请到套件中心确认 Docker/Container Manager 状态"
    exit 1
fi
hr

# ---------- 7. 重建 ----------
say "[7/7] 重建镜像（--no-cache，显式传版本号）"
say "GIT_VERSION=$VER"
if [ -z "$VER" ]; then
    bad "拿不到包内版本，中止"
    exit 1
fi
( cd "$PROJ" && DOCKER_BUILDKIT=1 docker build --no-cache \
    --build-arg GIT_VERSION="$VER" -t "$IMAGE" . ) || {
    bad "构建仍然失败。看是否停在同一步："
    say "  若仍是 layer does not exist：多为 Btrfs 配额/元数据问题，见交付说明第十节"
    say "  若变成 no space left：先清 /volume1 空间（镜像整体约 6-8GB，构建峰值需再多 6GB）"
    exit 1
}
say ""
say "==> 镜像内 index.html 指纹校验（上下文快照复用会在这里现形）"
HOST_SHA=$(sha256sum "$PROJ/app/dist/index.html" 2>/dev/null | awk '{print $1}')
IMG_SHA=$(docker run --rm "$IMAGE" sha256sum /var/www/mybooks/app/dist/index.html 2>/dev/null | awk '{print $1}')
say "  包内  index.html = ${HOST_SHA:-读取失败}"
say "  镜像内 index.html = ${IMG_SHA:-读取失败}"
if [ -n "$HOST_SHA" ] && [ "$HOST_SHA" != "$IMG_SHA" ]; then
    bad "镜像内 index.html 与包内不一致（上下文快照复用的典型症状）"
    say "  处理：docker builder prune -f 后重跑本脚本；仍不行则 DOCKER_BUILDKIT=0 legacy 兜底一轮"
    exit 1
fi
say ""
say "==> 镜像内版本校验"
if [ -f "$PROJ/scripts/check-version.sh" ]; then
    ( cd "$PROJ" && CONTAINER="$CONTAINER" sh scripts/check-version.sh --image ) || exit 1
else
    docker run --rm "$IMAGE" sh -c \
      'cd /var/www/mybooks && python3 -c "import webserver.version as v;print(v.VERSION)"'
fi
say ""
say "==> 版本一致，替换容器"
( cd "$PROJ" && docker compose up -d --force-recreate --no-build ) || \
( cd "$PROJ" && docker-compose up -d --force-recreate --no-build )
say ""
say "==> 全链路校验（页脚显示的就是 container/api 这两个值）"
if [ -f "$PROJ/scripts/check-version.sh" ]; then
    ( cd "$PROJ" && CONTAINER="$CONTAINER" sh scripts/check-version.sh ) || exit 1
fi
say ""
say "完成。浏览器 Ctrl+Shift+R 强刷后页脚应为 $VER"
