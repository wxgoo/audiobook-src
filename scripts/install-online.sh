#!/bin/sh
# ============================================================
# install-online.sh —— 从 Gitee 在线全新安装（不用手工传 153MB 包）
#
# 用途：新 NAS / 普通 Linux，能联网，不想手工拷 153MB 部署包。
#   老 NAS（legacy builder + btrfs，构建报 layer does not exist）请用镜像
#   离线包（pack-image.sh 产物），本脚本最终仍会构建镜像。
#
# 用法（任意目录执行，一行都不用改）：
#   curl -fsSL -o install-online.sh \
#     https://gitee.com/wxgoo/audiobook-src/raw/master/scripts/install-online.sh
#   DATA_DIR=/volume1/docker/audiobook-data PUID=$(id -u) PGID=$(id -g) \
#     sh install-online.sh
#
# 只下载/校验/解压、不安装（先验收包）：
#   DOWNLOAD_ONLY=1 sh install-online.sh
#
# 环境变量：
#   DATA_DIR / PUID / PGID / HTTP_PORT / HTTPS_PORT / TZ / CHECK_ONLY
#                      原样透传给 scripts/install-from-tar.sh（见 install-fresh.sh）
#   ONLINE_BASE_URL    覆盖分片下载地址（内网镜像/本地测试用）
#   ONLINE_WORK_DIR    工作目录，默认 $(pwd)/.online-install
#   ONLINE_FORCE=1     忽略已下载的分片，全部重下
#   DOWNLOAD_ONLY=1    只下包不安装
#
# 设计约束（改动前请先读 tests/test_install_online_contract.py）：
#   1) 这里只负责「取包」；真正的校验/配置/部署只有一份，在 install-fresh.sh，
#      本脚本最后必须转交 install-from-tar.sh，绝不复制安装逻辑。
#   2) Gitee Release 单附件上限 100MB，所以 153MB 包切成 2 片；raw 大文件
#      (>10MB) 匿名 403，所以走 Release 附件直链（匿名 200）。
#   3) 下载链路与出包链路彻底分离：pack.sh / deploy.sh 里零网络请求，
#      本脚本绝不写 update/manifest.json（r27/r33 事故）。
#   4) 合并后必须校验整包 sha256，且分片逐片校验，防传坏 / 防半截合并。
#   5) 钉死 TAG 而不是 master 路径，避免 raw 的 60~300 秒缓存造成版本漂移。
# ============================================================
set -eu

OWNER=wxgoo
REPO=audiobook-src
TAG=dist-4.6.0-build.27-r38
PKG=audiobook-deploy-4.6.0-build.27-r38.tar.gz
PKG_SHA256=4cb89d2b94b2006f5e248cb1ac7a79a08cacf4dffa987483094313efb3fcbe34
PART_PREFIX=$PKG.part
PARTS=2
SUMS=SHA256SUMS-online

BASE_URL=${ONLINE_BASE_URL:-https://gitee.com/$OWNER/$REPO/releases/download/$TAG}
WORK_DIR=${ONLINE_WORK_DIR:-$(pwd)/.online-install}

say() { echo ""; echo "==> $*"; }

sha_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    elif command -v openssl >/dev/null 2>&1; then
        openssl dgst -sha256 "$1" | awk '{print $NF}'
    else
        echo "!! 缺 sha256sum / openssl，无法校验下载内容" >&2
        exit 1
    fi
}

fetch() {
    _url=$1
    _out=$2
    if command -v curl >/dev/null 2>&1; then
        curl -fL --retry 3 --retry-delay 2 --connect-timeout 20 \
             -o "$_out" "$_url" || {
            echo "!! 下载失败: $_url" >&2
            echo "   Gitee raw 有 60~300 秒缓存；刚发布完请等 1 分钟再试。" >&2
            exit 1
        }
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$_out" "$_url" || {
            echo "!! 下载失败: $_url" >&2
            exit 1
        }
    else
        echo "!! 缺 curl / wget，无法在线安装" >&2
        exit 1
    fi
}

say "[0/5] 在线全新安装（Gitee Release 分片）"
echo "    版本: $TAG"
echo "    来源: $BASE_URL"
echo "    工作目录: $WORK_DIR"
echo "    注意: 本路线会构建镜像；老 NAS 报 layer does not exist 请改用镜像离线包。"

mkdir -p "$WORK_DIR" || { echo "!! 建不了工作目录: $WORK_DIR" >&2; exit 1; }
cd "$WORK_DIR"

if [ "${ONLINE_FORCE:-0}" = "1" ]; then
    rm -f "$SUMS" "$PKG" "${PART_PREFIX}"*
fi

say "[1/5] 下载分片校验清单"
fetch "$BASE_URL/$SUMS" "$SUMS"
[ -s "$SUMS" ] || { echo "!! $SUMS 为空" >&2; exit 1; }

say "[2/5] 下载 $PARTS 个分片（每片 <100MB，Gitee 附件上限）"
_i=1
while [ "$_i" -le "$PARTS" ]; do
    _n=$(printf '%02d' "$_i")
    _part="${PART_PREFIX}${_n}"
    if [ -s "$_part" ]; then
        echo "    $_part 已存在，复用（要重下请加 ONLINE_FORCE=1）"
    else
        echo "    -> $_part"
        fetch "$BASE_URL/$_part" "$_part"
    fi
    _i=$((_i + 1))
done

say "[3/5] 逐片校验"
while read -r _want _name; do
    [ -n "$_want" ] && [ -n "$_name" ] || continue
    case "$_name" in "$PART_PREFIX"*) ;; *) continue ;; esac
    [ -f "$_name" ] || { echo "!! 缺分片 $_name" >&2; exit 1; }
    _got=$(sha_of "$_name")
    [ "$_got" = "$_want" ] || {
        echo "!! 分片校验失败: $_name" >&2
        echo "   期望 $_want" >&2
        echo "   实得 $_got" >&2
        echo "   删掉它重跑：rm -f '$WORK_DIR/$_name'" >&2
        exit 1
    }
    echo "    $_name OK"
done < "$SUMS"

say "[4/5] 合并并校验整包"
: > "$PKG"
_i=1
while [ "$_i" -le "$PARTS" ]; do
    _n=$(printf '%02d' "$_i")
    cat "${PART_PREFIX}${_n}" >> "$PKG"
    _i=$((_i + 1))
done
_got=$(sha_of "$PKG")
[ "$_got" = "$PKG_SHA256" ] || {
    echo "!! 整包 sha256 不符，禁止安装" >&2
    echo "   期望 $PKG_SHA256" >&2
    echo "   实得 $_got" >&2
    echo "   分片可能过期或半截；加 ONLINE_FORCE=1 重下。" >&2
    exit 1
}
echo "    $PKG sha256 OK（$PKG_SHA256）"

say "[5/5] 解压并转交统一安装入口"
echo "    必须用命令行 tar 解压，别用 Windows 图形界面 / 网盘在线解压（会压扁软链）"
tar -xzf "$PKG"
[ -d audiobook ] || { echo "!! 解压后没有 audiobook/ 目录" >&2; exit 1; }
cd audiobook

if [ "${DOWNLOAD_ONLY:-0}" = "1" ]; then
    echo "    DOWNLOAD_ONLY=1：只取包，不安装。"
    echo "    源码目录: $WORK_DIR/audiobook"
    echo "    之后手动装: cd '$WORK_DIR/audiobook' && sh scripts/install-from-tar.sh"
    exit 0
fi

[ -f scripts/install-from-tar.sh ] || {
    echo "!! 包内缺 scripts/install-from-tar.sh" >&2; exit 1; }
exec sh scripts/install-from-tar.sh "$@"
