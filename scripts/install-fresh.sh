#!/bin/sh
# ============================================================
# install-fresh.sh —— 联网全新安装（在 git clone 之后的仓库根目录执行）
#
# 前置：
#   git -c core.symlinks=true clone https://gitee.com/wxgoo/audiobook-src.git audiobook
#   cd audiobook
#
# 用法：
#   DATA_DIR=/你的/数据目录 PUID=$(id -u) PGID=$(id -g) sh scripts/install-fresh.sh
#   CHECK_ONLY=1 sh scripts/install-fresh.sh   # 只校验+生成 .env，不构建不启动
#
# 环境变量（都会写进 .env，docker compose 自动读取；不传用群晖默认值）：
#   DATA_DIR      数据目录，默认 /volume1/docker/audiobook-data
#   PUID / PGID   数据目录所有者的 uid/gid，默认 1026 / 100
#   HTTP_PORT / HTTPS_PORT  默认 9800 / 8443
#   TZ            默认 Asia/Shanghai
#
# 本脚本做的事：
#   1) 前置检查（docker / compose v2 / Linux 软链）
#   2) 校验 app/dist（768）与 myreader-dist 的 119 根软链，打印包内清单基线
#   3) 生成仓库根 .env 并写进 .git/info/exclude（避免误提交）
#   4) 建数据目录
#   5) 调 scripts/deploy.sh 完成构建、指纹校验、启动与进程验证
#
# 退出码：0 成功；1 前置/校验/部署失败
# ============================================================
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

say() { echo ""; echo "==> $*"; }

# ---------- 1. 前置 ----------
say "[1/5] 前置检查"
[ -f Dockerfile ] && [ -f docker-compose.yml ] && [ -f scripts/deploy.sh ] || {
    echo "!! 请在仓库根目录运行（缺 Dockerfile / docker-compose.yml / scripts/deploy.sh）"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "!! 缺 docker"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "!! 缺 docker compose v2（docker compose 子命令）"; exit 1; }
command -v git >/dev/null 2>&1 || { echo "!! 缺 git"; exit 1; }

DATA_DIR="${DATA_DIR:-/volume1/docker/audiobook-data}"
PUID="${PUID:-1026}"
PGID="${PGID:-100}"
HTTP_PORT="${HTTP_PORT:-9800}"
HTTPS_PORT="${HTTPS_PORT:-8443}"
TZ="${TZ:-Asia/Shanghai}"

case "$DATA_DIR" in
    /*) ;;
    *) echo "!! DATA_DIR 必须是绝对路径: $DATA_DIR"; exit 1 ;;
esac
# 源码目录绝不能当数据目录：start.sh 会往 /data 写 books/settings/log，
# deploy.sh 的污染自检也会直接退出（见 docs/部署方式速查.md §2.5）。
case "$DATA_DIR" in
    "$ROOT"|"$ROOT"/*) echo "!! DATA_DIR 不能是源码目录本身或其子目录: $DATA_DIR"; exit 1 ;;
esac

echo "    docker: $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo '?')"
echo "    compose: $(docker compose version 2>/dev/null | head -1)"
echo "    数据目录: $DATA_DIR"
echo "    PUID/PGID: $PUID/$PGID   端口: $HTTP_PORT / $HTTPS_PORT"

# ---------- 2. 产物校验 ----------
say "[2/5] 校验预构建产物"
sh scripts/check-dist.sh || { echo "!! app/dist 不完整，停止安装"; exit 1; }
sh scripts/check-myreader-links.sh --fix || {
    echo "!! MyReader 119 根软链修复失败。多半是 Windows 检出 / 图形解压压扁了链接，"
    echo "   请在 Linux 上重新 clone：git -c core.symlinks=true clone <仓库> audiobook"; exit 1; }

MF_REV=$(sed -n 's/.*"revision"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
             update/manifest.json 2>/dev/null | head -1)
[ -n "$MF_REV" ] || { echo "!! 读不出 update/manifest.json 的 revision"; exit 1; }
printf '%s' "$MF_REV" | grep -qE -- '-r[0-9]+$' || {
    echo "!! 清单 revision='$MF_REV' 不带 -rN，停止安装"; exit 1; }
echo "    发布清单基线: $MF_REV（装完 /admin/version 就是最新，不会误报有新版本）"

# ---------- 3. 生成本地 .env ----------
say "[3/5] 生成本地配置 .env"
if [ -f .env ]; then
    echo "    .env 已存在，沿用（改配置请直接编辑它）"
else
    cat > .env <<EOF
# 由 scripts/install-fresh.sh 生成，本地配置，勿提交。
COMPOSE_PROJECT_NAME=audiobook
DATA_DIR="$DATA_DIR"
HTTP_PORT=$HTTP_PORT
HTTPS_PORT=$HTTPS_PORT
PUID=$PUID
PGID=$PGID
TZ=$TZ
EOF
    echo "    已生成 .env"
fi
# clone 出来的仓库有 .git，把 .env 排除掉，避免以后 git status 一直提示 / 误提交
if [ -d .git/info ]; then
    grep -qxF '.env' .git/info/exclude 2>/dev/null || printf '\n.env\n' >> .git/info/exclude
    echo "    .env 已写入 .git/info/exclude（不会被提交）"
fi

# ---------- 4. 数据目录 ----------
say "[4/5] 准备数据目录"
mkdir -p "$DATA_DIR" || { echo "!! 建不了数据目录: $DATA_DIR（权限/路径问题）"; exit 1; }
echo "    $DATA_DIR 就绪（书库、音频、账号、日志都在这里，不进镜像）"

# 确认 compose 解析出来的确实是这份配置，避免 .env 写法有误却没发现
echo "    compose 解析结果："
docker compose config 2>/dev/null | grep -E 'source:|published:|PUID|PGID' | sed 's/^/      /' || true

if [ "${CHECK_ONLY:-0}" = "1" ]; then
    say "CHECK_ONLY=1：只校验与生成配置，跳过构建/启动"
    echo "    确认无误后重跑不带 CHECK_ONLY 的命令即可安装。"
    exit 0
fi

# ---------- 5. 构建 + 启动 ----------
say "[5/5] 调用 deploy.sh 构建并启动"
echo "    会走「预构建 dist」快路，跳过 npm ci / generate；"
echo "    联网只用于拉取 Docker 基础镜像与 apt / pip 依赖，首次约几分钟。"
DATA="$DATA_DIR" sh scripts/deploy.sh || {
    echo "!! 部署失败，看上面的具体步骤。常见：网络拉不到基础镜像、PUID/PGID 不对、端口被占。"; exit 1; }

say "安装完成"
echo "    HTTP : http://<这台机器IP>:$HTTP_PORT"
echo "    HTTPS: https://<这台机器IP>:$HTTPS_PORT （自签证书，浏览器会告警）"
echo "    首次启动要初始化数据库，1-3 分钟内访问可能 502，看日志: docker logs -f audiobook-mybooks-1"
echo ""
echo "    以后升级：git pull && docker compose up -d --build"
echo "    或小改动走页内热更：/admin/version → 立即更新"
exit 0
