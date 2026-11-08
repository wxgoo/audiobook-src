#!/bin/sh
# ---------------------------------------------------------------------------
# 重建 mybooks_base（瘦身后的基础镜像）
#
# 为什么需要单独一个脚本：
#   Docker 的层是只读叠加。在成品镜像里 `RUN rm -rf /usr/share/doc` 只会多出一个
#   "白障"层 —— 文件仍然躺在下面的 apt 层里，镜像体积**一点不变**。所以瘦身必须
#   在装包的同一层里做，也就是改 Dockerfile.base 并整块重建 base。
#   build.29 干的就是这件事：剥掉 /usr/share/{doc,info,man}、/usr/share/locale/*、
#   npm 自带的 docs/man。
#
# 什么时候要跑：
#   只有 Dockerfile.base / requirements.txt / calibre 补丁 / 系统包变更时才需要。
#   日常改代码、改前端**不用**重跑本脚本。
#
# 用法（root，或在 docker 组里的用户）：
#   sh scripts/build-base.sh              # 备份旧 base -> 构建 -> 自检 -> 体积对比
#   sh scripts/build-base.sh report       # 只量当前 base 各目录占用，不构建
#   sh scripts/build-base.sh verify       # 只对现有 base 做功能自检
#   sh scripts/build-base.sh build --no-cache
#
# 构建需要联网：apt 走华为云镜像 + deb.nodesource.com，pip 走 aliyun。
# 这是整条链路里唯一需要外网的一步；建好后可以
#   sh scripts/export-images.sh
# 导成离线包发给其它站点，它们就不必再联网。
# ---------------------------------------------------------------------------

set -eu

PROJ="${PROJ:-$(cd "$(dirname "$0")/.." && pwd)}"
REF="${BASE_REF:-docker.1ms.run/poxenstudio/mybooks_base:latest}"
ALT="poxenstudio/mybooks_base:latest"
STAMP=$(date +%Y%m%d)
BACKUP_TAG="docker.1ms.run/poxenstudio/mybooks_base:pre-slim-$STAMP"

MODE=""
NO_CACHE=""

usage() {
    sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
}

for _a in "$@"; do
    case "$_a" in
        build|report|verify) MODE="$_a" ;;
        --no-cache) NO_CACHE="--no-cache" ;;
        -h|--help) usage; exit 0 ;;
        *) echo "未知参数：$_a（用 --help 看用法）" >&2; exit 2 ;;
    esac
done
MODE="${MODE:-build}"

say() { printf '%s\n' "$*"; }
hr()  { say "------------------------------------------------------------"; }

human() {
    awk -v b="$1" 'BEGIN{
        if (b == "")            { print "?"; exit }
        if (b >= 1073741824)    printf "%.2f GB", b / 1073741824;
        else if (b >= 1048576)  printf "%.1f MB", b / 1048576;
        else                    printf "%.0f KB", b / 1024;
    }'
}

img_size() {
    docker image inspect -f '{{.Size}}' "$1" 2>/dev/null || true
}

# 容器内跑一段 sh，量各目录占用（不依赖宿主机的 du 版本）
REPORT_SNIPPET='for d in / /usr/share/doc /usr/share/info /usr/share/man /usr/share/locale /usr/lib/calibre /usr/lib/node_modules /usr/share/fonts /usr/lib/x86_64-linux-gnu; do
  if [ ! -e "$d" ]; then printf "%8s     %s (不存在)\n" "-" "$d"; continue; fi
  printf "%8s MB  %s\n" "$(du -sm "$d" 2>/dev/null | cut -f1)" "$d"
done
printf "%8s     %s\n" "$(find /usr/share/doc -type f 2>/dev/null | wc -l)" "/usr/share/doc 里剩余文件数"'

do_report() {
    _tag="${1:-$REF}"
    if ! docker image inspect "$_tag" >/dev/null 2>&1; then
        say "!! 本地没有这个镜像：$_tag"
        return 1
    fi
    hr
    say "体积明细：$_tag"
    hr
    docker run --rm --entrypoint sh "$_tag" -c "$REPORT_SNIPPET"
    hr
    say "docker images 记录的压缩后体积：$(human "$(img_size "$_tag")")"
    hr
}

# 功能自检：这里失败就说明剥过头了，别拿去替换 base
do_verify() {
    _tag="${1:-$REF}"
    hr
    say "功能自检：$_tag"
    hr
    docker run --rm --entrypoint sh "$_tag" -c '
set -e
printf "%-14s " nginx;    nginx -v 2>&1 || true
printf "%-14s " node;     node -v
printf "%-14s " npm;      npm -v
printf "%-14s " ffmpeg;   ffmpeg -version 2>/dev/null | head -1
printf "%-14s " python3;  python3 -V
printf "%-14s " 时区;     date +%Z
if [ -f /usr/share/locale/locale.alias ]; then printf "%-14s 有\n" locale.alias; else printf "%-14s 缺失（部分程序会告警）\n" locale.alias; fi
if [ -d /usr/lib/locale ]; then printf "%-14s 有\n" "glibc locale"; else printf "%-14s 缺失\n" "glibc locale"; fi
printf "%-14s %s\n" "用户 mybooks" "$(id mybooks 2>/dev/null || echo 缺失)"
printf "%-14s %s\n" "nginx 运行用户" "$(awk "/^user /{print \$2}" /etc/nginx/nginx.conf | tr -d ";")"
echo "--- python 运行时依赖抽查 ---"
python3 -c "import tornado, jinja2, lxml, bs4, mutagen, psutil, apsw, regex; print(\"   ok: tornado/jinja2/lxml/bs4/mutagen/psutil/apsw/regex\")" || echo "   !! 依赖导入失败 —— 先确认 build.28 的 base 里是否本来就缺，别急着怪瘦身"
echo "--- calibre ---"
calibre --version 2>&1 | head -1 || echo "   !! calibre 命令异常"
ebook-convert --version 2>&1 | head -1 || echo "   !! ebook-convert 异常"
'
    hr
}

# 构建上下文只放 Dockerfile.base 需要的那几样（4~5MB），
# 不把整个项目（含 app/dist / myreader-dist，200MB+）塞给 daemon
prepare_context() {
    _ctx="$1"
    cp "$PROJ/Dockerfile.base" "$_ctx/Dockerfile"
    cp "$PROJ/requirements.txt" "$_ctx/"
    cp -R "$PROJ/prebuilt" "$_ctx/prebuilt"
    mkdir -p "$_ctx/calibre/7.6"
    cp -R "$PROJ/calibre/7.6/calibre" "$_ctx/calibre/7.6/calibre"
}

do_build() {
    for _f in Dockerfile.base requirements.txt prebuilt calibre/7.6/calibre; do
        [ -e "$PROJ/$_f" ] || { say "!! 缺少 $_f（当前目录：$PROJ）"; exit 1; }
    done
    docker info >/dev/null 2>&1 || { say "!! docker 不可用（没启动 / 当前用户无权限）"; exit 1; }

    _old=$(img_size "$REF")
    if [ -n "$_old" ]; then
        say "== 旧 base：$(human "$_old")"
        say "   备份为 ${BACKUP_TAG}（想回滚就 docker tag 回来再重建主镜像）"
        docker tag "$REF" "$BACKUP_TAG" || true
    else
        say "== 本地还没有 $REF（首次构建或已被清理）"
    fi

    if ! docker image inspect docker.1ms.run/library/ubuntu:24.04 >/dev/null 2>&1; then
        say "! 本地没有 docker.1ms.run/library/ubuntu:24.04，构建会尝试拉取"
        say "  出网 TLS 被拦截时会报 x509 —— 那就先在别的机器上 docker save 这个镜像带过来"
    fi

    CTX=$(mktemp -d 2>/dev/null || echo "/tmp/mybooks-base-ctx.$$")
    mkdir -p "$CTX"
    trap 'rm -rf "$CTX"' EXIT INT TERM
    prepare_context "$CTX"
    say "== 构建上下文：$CTX（$(du -sh "$CTX" | cut -f1)）"
    say "   注意：只有一项结构性改动 —— 装完包在同一层里删文档/手册/翻译"

    hr
    say "开始构建（apt + pip，5~20 分钟；日志里应能看到 rm -rf /usr/share/doc/*）"
    hr
    docker build $NO_CACHE \
        --build-arg BUILD_COUNTRY=CN \
        -f "$CTX/Dockerfile" \
        -t "$REF" -t "$ALT" \
        "$CTX"

    _new=$(img_size "$REF")
    hr
    say "旧 base ：$(human "$_old")"
    say "新 base ：$(human "$_new")"
    if [ -n "$_old" ] && [ -n "$_new" ]; then
        say "差值    ：$(( (_old - _new) / 1024 / 1024 )) MB（docker images 口径，压缩后）"
    fi
    hr

    do_verify "$REF"
    do_report "$REF"

    cat <<EOF

下一步：
  1) 重建业务镜像（Dockerfile 的 FROM 会用到新 base）：
       sh scripts/deploy.sh build-only
     或者整包升级：
       sh scripts/upgrade.sh /path/to/audiobook-deploy-<版本>.tar.gz
  2) 其它站点要跟着瘦身，就把新 base 导出成离线包：
       sh scripts/export-images.sh          # 生成 images/mybooks_base.tar.gz
  3) 确认业务镜像跑起来没问题后，再回收旧层（顺序别颠倒，删早了没得回滚）：
       docker rmi ${BACKUP_TAG}      # 先摘掉备份标签，旧层才变悬空
       docker image prune -f         # 再清悬空层，空间这时才真的回来
  4) 回滚（体积换稳定）：把备份标签打回原名再重建主镜像
       docker tag ${BACKUP_TAG} ${REF}
       sh scripts/deploy.sh build-only
EOF
}

case "$MODE" in
    report) do_report "${2:-$REF}" ;;
    verify) do_verify "${2:-$REF}" ;;
    build)  do_build ;;
esac
