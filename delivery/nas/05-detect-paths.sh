#!/bin/bash
set -euo pipefail

# =============================================================================
# 05-detect-paths.sh —— 只读探测群晖 NAS 上的真实部署路径
#
# 做四件事：
#   1) 列 /volume*/ 下的候选目录，找 docker-compose.yml / metadata.db / .audio
#   2) 读 docker inspect 的 Mounts、镜像、端口、compose 工程标签
#   3) 汇总成可直接替换进 paths.conf 的建议值
#   4) 把探测不到、必须由你确认的项目列成清单
#
# 只读：只用 ls / find / docker inspect，不创建、不修改任何文件。
#
# 退出码：
#   0 关键项（数据目录 + 容器）已探明
#   1 有关键项未探明（看末尾「需要你确认」）
#   2 用法错误
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATHS_CONF="${PATHS_CONF:-$SCRIPT_DIR/paths.conf}"
if [ -f "$PATHS_CONF" ]; then
    # shellcheck source=paths.conf
    . "$PATHS_CONF"
fi

CONTAINER="${APP_CONTAINER:-audiobook-mybooks-1}"
MAX_DEPTH="${MAX_DEPTH:-6}"

usage() {
    cat <<'EOF'
用法: 05-detect-paths.sh [选项]

只读探测 NAS 实际部署路径，输出可替换进 paths.conf 的建议值与待确认清单。

选项:
  --container NAME   指定要 inspect 的容器（默认读 paths.conf 的 APP_CONTAINER）
  --max-depth N      find 的最大深度（默认 6）
  -h, --help         显示帮助

退出码: 0 关键项已探明 / 1 有关键项待确认 / 2 用法错误
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --container) CONTAINER="${2:?缺少参数}"; shift 2 ;;
        --max-depth) MAX_DEPTH="${2:?缺少参数}"; shift 2 ;;
        -h|--help)   usage; exit 0 ;;
        *) echo "未知参数: $1" >&2; usage; exit 2 ;;
    esac
done
case "$MAX_DEPTH" in
    [0-9]*) : ;;
    *) echo "错误: --max-depth 必须是数字" >&2; exit 2 ;;
esac

MISSING=""
add_missing() { MISSING="${MISSING}  - $1
"; }

echo "==== audiobook 实际路径探测（只读） ===="
echo "脚本目录: $SCRIPT_DIR"
echo "目标容器: $CONTAINER"
echo

# ---------- 1. /volume* 候选目录 ----------
echo "[1/4] /volume*/ 候选目录"
VOLUMES=""
for v in /volume*; do
    [ -d "$v" ] || continue
    VOLUMES="$VOLUMES $v"
    echo "  卷: $v"
    # 只列两层，避免刷屏
    find "$v" -maxdepth 2 -type d \( -iname '*audiobook*' -o -iname '*mybooks*' \) 2>/dev/null \
        | while read -r d; do echo "    候选: $d"; done
done
[ -n "$VOLUMES" ] || add_missing "没有发现 /volume* 目录（确认是否为群晖系统）"

# ---------- 2. docker inspect ----------
echo
echo "[2/4] docker inspect"
DOCKER_OK=0
C_NAME=""
MOUNT_DATA=""
COMPOSE_WORKDIR=""
COMPOSE_PROJECT=""
APP_IMAGE=""
HTTP_MAP=""
HTTPS_MAP=""
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER_OK=1
    if docker inspect "$CONTAINER" >/dev/null 2>&1; then
        C_NAME="$CONTAINER"
    else
        C_NAME="$(docker ps --format '{{.Names}}' 2>/dev/null | grep -i -E 'mybooks|audiobook' | head -n 1 || true)"
        [ -n "$C_NAME" ] && echo "  未找到 $CONTAINER，改用: $C_NAME"
    fi
    if [ -n "$C_NAME" ]; then
        echo "  容器: $C_NAME"
        while IFS='|' read -r src dst typ; do
            [ -n "$dst" ] || continue
            echo "    挂载: $src -> $dst ($typ)"
            case "$dst" in
                /data|/data/) MOUNT_DATA="$src" ;;
            esac
        done <<EOF
$(docker inspect -f '{{range .Mounts}}{{.Source}}|{{.Destination}}|{{.Type}}{{"\n"}}{{end}}' "$C_NAME" 2>/dev/null || true)
EOF
        COMPOSE_WORKDIR="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$C_NAME" 2>/dev/null || true)"
        COMPOSE_PROJECT="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$C_NAME" 2>/dev/null || true)"
        APP_IMAGE="$(docker inspect -f '{{.Config.Image}}' "$C_NAME" 2>/dev/null || true)"
        PORTS="$(docker inspect -f '{{range $p, $b := .NetworkSettings.Ports}}{{range $b}}{{.HostIp}}:{{.HostPort}}->{{$p}}{{"\n"}}{{end}}{{end}}' "$C_NAME" 2>/dev/null || true)"
        [ -n "$COMPOSE_WORKDIR" ] && echo "  compose 目录: $COMPOSE_WORKDIR"
        [ -n "$COMPOSE_PROJECT" ] && echo "  compose 工程: $COMPOSE_PROJECT"
        [ -n "$APP_IMAGE" ] && echo "  镜像: $APP_IMAGE"
        if [ -n "$PORTS" ]; then
            printf '  端口:\n'
            printf '%s\n' "$PORTS" | sed 's/^/    /'
            HTTP_MAP="$(printf '%s\n' "$PORTS" | awk -F'->' '$2=="80/tcp" {print $1}' | head -n 1 | sed 's/.*:/:/; s/^://')"
            HTTPS_MAP="$(printf '%s\n' "$PORTS" | awk -F'->' '$2=="443/tcp" {print $1}' | head -n 1 | sed 's/.*:/:/; s/^://')"
        fi
        [ -n "$MOUNT_DATA" ] || add_missing "容器里没有 Destination=/data 的挂载，请确认数据目录"
    else
        add_missing "没找到 mybooks/audiobook 容器，请用 --container NAME 指定"
    fi
else
    echo "  未安装 docker 或无法连接守护进程，跳过容器探测"
    add_missing "无法运行 docker inspect（需要 root 或 docker 权限）"
fi

# ---------- 3. 文件系统：metadata.db / .audio / compose ----------
echo
echo "[3/4] 文件系统探测"
FOUND_METADATA=""
FOUND_AUDIO=""
if [ -z "$MOUNT_DATA" ]; then
    for v in $VOLUMES; do
        FOUND_METADATA="$(find "$v" -maxdepth "$MAX_DEPTH" -type f -name metadata.db -print -quit 2>/dev/null || true)"
        [ -n "$FOUND_METADATA" ] && break
    done
else
    FOUND_METADATA="$(find "$MOUNT_DATA" -maxdepth "$MAX_DEPTH" -type f -name metadata.db -print -quit 2>/dev/null || true)"
fi
[ -n "$FOUND_METADATA" ] && echo "  metadata.db: $FOUND_METADATA"

if [ -n "$FOUND_METADATA" ]; then
    LIB="${FOUND_METADATA%/metadata.db}"
    FOUND_AUDIO="$(find "$LIB" -maxdepth 2 -type d -name .audio -print -quit 2>/dev/null || true)"
    if [ -n "$FOUND_AUDIO" ]; then
        echo "  音频目录: $FOUND_AUDIO"
    else
        echo "  音频目录: 未发现 .audio（可能尚未导入）"
        add_missing "音频库未发现：请确认有声书放在 DATA_DIR/books/有声书，还是独立卷"
    fi
else
    add_missing "未找到 books/library/metadata.db：请确认书库在哪个卷"
fi

FOUND_COMPOSE=""
if [ -n "$COMPOSE_WORKDIR" ] && [ -f "$COMPOSE_WORKDIR/docker-compose.yml" ]; then
    FOUND_COMPOSE="$COMPOSE_WORKDIR/docker-compose.yml"
else
    for v in $VOLUMES; do
        FOUND_COMPOSE="$(find "$v" -maxdepth 4 -type f \( -name docker-compose.yml -o -name compose.yml \) -print -quit 2>/dev/null || true)"
        [ -n "$FOUND_COMPOSE" ] && break
    done
fi
[ -n "$FOUND_COMPOSE" ] && echo "  compose 文件: $FOUND_COMPOSE"
[ -n "$FOUND_COMPOSE" ] || add_missing "未找到 docker-compose.yml：请提供 compose 文件位置"

if [ -d "$MOUNT_DATA" ] && [ -f "$MOUNT_DATA/books/calibre-webserver.db" ]; then
    echo "  站点库: $MOUNT_DATA/books/calibre-webserver.db"
fi

# ---------- 4. 建议值 ----------
echo
echo "[4/4] 建议写入 paths.conf 的值"
DATA_DIR="${MOUNT_DATA:-}"
[ -n "$DATA_DIR" ] || [ -z "$FOUND_METADATA" ] || DATA_DIR="$(cd "$(dirname "$FOUND_METADATA")/../.." && pwd -P)"
APP_ROOT=""
if [ -n "$COMPOSE_WORKDIR" ]; then
    APP_ROOT="$COMPOSE_WORKDIR"
elif [ -n "$FOUND_COMPOSE" ]; then
    APP_ROOT="$(cd "$(dirname "$FOUND_COMPOSE")" && pwd -P)"
fi
LIBRARY_DIR="${DATA_DIR:+$DATA_DIR/books/library}"
[ -n "$FOUND_METADATA" ] && LIBRARY_DIR="${FOUND_METADATA%/metadata.db}"
GIT_DIR_GUESS="${APP_ROOT:+$APP_ROOT-git}"
if [ -f "$GIT_DIR_GUESS/HEAD" ]; then
    APP_GIT_SUGGEST="$GIT_DIR_GUESS"
else
    APP_GIT_SUGGEST=""
    add_missing "未找到 git 历史目录（按约定应类似 ${GIT_DIR_GUESS:-<APP_ROOT>-git}）：请确认升级用的 git 目录"
fi
BACKUP_ROOT_GUESS=""
for v in $VOLUMES; do
    if [ -d "$v/backup" ]; then
        BACKUP_ROOT_GUESS="$v/backup/audiobook"
        break
    fi
done
BACKUP_PREFIX_SUGGEST=""
[ -n "$BACKUP_ROOT_GUESS" ] && BACKUP_PREFIX_SUGGEST="$(dirname "$BACKUP_ROOT_GUESS")"

print_kv() {
    # $1=变量名 $2=值 $3=说明
    if [ -n "$2" ]; then
        printf '%-16s = "%s"   # %s\n' "$1" "$2" "$3"
    else
        printf '# %-14s = ""   # 待确认：%s\n' "$1" "$3"
    fi
}

print_kv APP_ROOT "$APP_ROOT" "源码 + 部署脚本目录"
print_kv APP_GIT_DIR "$APP_GIT_SUGGEST" "git 历史目录"
print_kv APP_CONFIG_DIR "${APP_ROOT:+$APP_ROOT/config}" "站点配置目录"
print_kv DATA_DIR "$DATA_DIR" "容器 /data 的宿主机挂载点"
print_kv LIBRARY_DIR "$LIBRARY_DIR" "calibre 书库"
print_kv METADATA_DB "${LIBRARY_DIR:+$LIBRARY_DIR/metadata.db}" "calibre 元数据库"
print_kv WEB_DB "${DATA_DIR:+$DATA_DIR/books/calibre-webserver.db}" "站点 SQLite"
print_kv AUDIO_ROOT "${LIBRARY_DIR:-$DATA_DIR}" "音频在每本书目录的 .audio/ 内"
print_kv BACKUP_ROOT "$BACKUP_ROOT_GUESS" "备份根目录（确认目标盘空闲空间）"
print_kv DRILL_PREFIX "$BACKUP_PREFIX_SUGGEST" "演练目录白名单前缀"
print_kv DRILL_DIR "${BACKUP_PREFIX_SUGGEST:+$BACKUP_PREFIX_SUGGEST/audiobook-restore-drill}" "恢复演练目录"
print_kv COMPOSE_FILE "$FOUND_COMPOSE" "compose 文件"
print_kv COMPOSE_PROJECT "$COMPOSE_PROJECT" "compose 工程名"
print_kv APP_SERVICE "mybooks" "compose 服务名"
print_kv APP_CONTAINER "$C_NAME" "容器名"
print_kv BACKUP_IMAGE "$APP_IMAGE" "本地镜像名"
print_kv HTTP_PORT "$HTTP_MAP" "宿主机 HTTP 端口"
print_kv HTTPS_PORT "$HTTPS_MAP" "宿主机 HTTPS 端口"

if [ -z "$BACKUP_ROOT_GUESS" ]; then
    add_missing "备份目标盘未确定：请提供打算存放备份的卷（建议独立于数据盘）"
fi
[ -n "$C_NAME" ] || add_missing "容器名未确定：请提供 docker ps 里的 mybooks 容器名"
[ -n "$APP_ROOT" ] || add_missing "源码目录未确定：请提供 docker-compose.yml 所在目录"

echo
if [ -n "$MISSING" ]; then
    echo "==== 需要你确认 ===="
    printf '%s' "$MISSING"
    echo
    echo "把上面值填进 $PATHS_CONF 后，再跑 00-check-env.sh 复核。"
else
    echo "关键项均已探明，可把上面值填入 $PATHS_CONF。"
fi

if [ -n "$DATA_DIR" ] && [ -n "$C_NAME" ]; then
    exit 0
fi
exit 1
