#!/bin/sh
# ============================================================
# install-from-tar.sh —— 解压部署包后的全新安装入口（不需要 git、不需要 clone）
#
# 适用：从 audiobook-deploy-<版本>.tar.gz 解压出来的目录。
#   老 NAS / 不想构建 → 请用镜像离线包（pack-image.sh 产物），不用本脚本。
#
# 用法（在解压出来的 audiobook 目录里）：
#   tar -xzf audiobook-deploy-4.6.0-build.27-r38.tar.gz
#   cd audiobook
#   DATA_DIR=/你的/数据目录 PUID=$(id -u) PGID=$(id -g) sh scripts/install-from-tar.sh
#
#   CHECK_ONLY=1 sh scripts/install-from-tar.sh   # 只校验 + 生成 .env，不构建不启动
#
# 环境变量（透传给 install-fresh.sh，都会写进 .env）：
#   DATA_DIR      数据目录，默认 /volume1/docker/audiobook-data
#   PUID / PGID   数据目录所有者的 uid/gid，默认 1026 / 100
#   HTTP_PORT / HTTPS_PORT  默认 9800 / 8443
#   TZ            默认 Asia/Shanghai
#
# 本脚本是**薄封装**：真正的校验/配置/部署逻辑只有一份，在 install-fresh.sh。
#   install-fresh.sh     = 统一入口（git clone 仓库 与 tar 解压包都支持）
#   install-from-tar.sh  = 只做「tar 包模式」的来源判定，然后转发
# 这样避免两份脚本各自维护一套逻辑、以后改一处忘另一处（r36/r38 的教训）。
#
# 前置：Docker + Docker Compose v2 + Linux 命令行解压（保住 myreader 的软链）。
# ============================================================
set -eu

SELF_DIR=$(cd "$(dirname "$0")" && pwd)
# 脚本可能在 <包根>/scripts/ 下，也可能被直接放在包根，两种位置都认
if [ -f "$SELF_DIR/../Dockerfile" ]; then
    ROOT=$(cd "$SELF_DIR/.." && pwd)
elif [ -f "$SELF_DIR/Dockerfile" ]; then
    ROOT="$SELF_DIR"
else
    echo "!! 请在解压出来的 audiobook 目录里运行（找不到 Dockerfile）"; exit 1
fi
cd "$ROOT"

[ -f scripts/install-fresh.sh ] || {
    echo "!! 包内缺 scripts/install-fresh.sh（统一安装逻辑），包不完整"; exit 1; }

if [ -d .git ]; then
    echo "!! 检测到 .git —— 这是 git clone 出来的仓库，请直接用 sh scripts/install-fresh.sh"
    exit 1
fi

echo "==> tar 解压包模式（无 .git，不需要 git），转交统一安装逻辑"
echo "    老 NAS 若报 layer does not exist，请改用镜像离线包（零构建）。"
exec sh "$ROOT/scripts/install-fresh.sh" "$@"
