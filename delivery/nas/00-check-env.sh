#!/bin/bash
set -euo pipefail

# =============================================================================
# 00-check-env.sh —— 群晖 DSM 7 备份/补丁环境预检（只读，不修改任何东西）
#
# 退出码：
#   0 全部关键项通过（可能有警告）
#   1 存在未通过项
#   2 用法错误
# =============================================================================

# ---------- 路径与部署参数：统一来自同目录 paths.conf ----------
# 环境变量优先，命令行参数再覆盖；本项目实际路径见 paths.conf
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATHS_CONF="${PATHS_CONF:-$SCRIPT_DIR/paths.conf}"
if [ ! -f "$PATHS_CONF" ]; then
    printf '错误: 找不到路径配置 %s（应与脚本同目录，或用 PATHS_CONF 指定）\n' "$PATHS_CONF" >&2
    exit 2
fi
# shellcheck source=paths.conf
. "$PATHS_CONF"
REPO_DIR="$APP_ROOT"
RUNNER="${RUNNER:-auto}"
MIN_FREE_GB="${MIN_FREE_GB:-5}"

FAIL=0
WARN=0

ok()   { printf '  [通过] %s\n' "$*"; }
bad()  { printf '  [不通过] %s\n' "$*"; FAIL=$((FAIL + 1)); }
warn() { printf '  [警告] %s\n' "$*"; WARN=$((WARN + 1)); }

usage() {
    cat <<'EOF'
用法: 00-check-env.sh [选项]

只读预检：bash / 命令 / docker / 路径 / 磁盘余量，不创建或修改任何文件。

选项:
  --data-dir DIR        数据目录（默认见 paths.conf）
  --backup-root DIR     备份目录（默认见 paths.conf）
  --drill-dir DIR       恢复演练目录（默认见 paths.conf）
  --repo-dir DIR        源码目录（默认见 paths.conf）
  --app-container NAME  应用容器名（默认 audiobook-mybooks-1）
  --image NAME          备份用镜像（默认 mybooks-local:latest）
  --runner auto|local|docker
  --min-free-gb N       备份盘最低剩余空间（默认 5）
  -h, --help            显示帮助

退出码: 0 通过 / 1 存在未通过项 / 2 用法错误
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --data-dir)      DATA_DIR="${2:?缺少参数}"; shift 2 ;;
        --backup-root)   BACKUP_ROOT="${2:?缺少参数}"; shift 2 ;;
        --drill-dir)     DRILL_DIR="${2:?缺少参数}"; shift 2 ;;
        --repo-dir)      REPO_DIR="${2:?缺少参数}"; shift 2 ;;
        --app-container) APP_CONTAINER="${2:?缺少参数}"; shift 2 ;;
        --image)         BACKUP_IMAGE="${2:?缺少参数}"; shift 2 ;;
        --runner)        RUNNER="${2:?缺少参数}"; shift 2 ;;
        --min-free-gb)   MIN_FREE_GB="${2:?缺少参数}"; shift 2 ;;
        -h|--help)       usage; exit 0 ;;
        *) echo "未知参数: $1" >&2; usage; exit 2 ;;
    esac
done

printf '==== audiobook 环境预检 ====\n'
printf '  仓库: %s\n  数据: %s\n  备份: %s\n  演练: %s\n  运行器: %s\n\n' \
       "$REPO_DIR" "$DATA_DIR" "$BACKUP_ROOT" "$DRILL_DIR" "$RUNNER"

echo "[1/6] Bash 版本"
if [ -n "${BASH_VERSION:-}" ]; then
    if [ "${BASH_VERSINFO[0]:-0}" -ge 4 ]; then
        ok "bash $BASH_VERSION"
    else
        warn "bash $BASH_VERSION，低于 4.x；脚本可用但建议升级"
    fi
else
    bad "当前不是 bash（请用 /bin/bash 执行本脚本）"
fi

echo "[2/6] 必要命令"
for cmd in tar gzip find sha256sum awk sed date df ls cp mkdir; do
    if command -v "$cmd" >/dev/null 2>&1; then
        ok "$cmd -> $(command -v "$cmd")"
    else
        bad "缺少命令: $cmd"
    fi
done
if command -v python3 >/dev/null 2>&1; then
    ok "python3 -> $(python3 -c 'import sys;print(sys.version.split()[0])' 2>/dev/null || echo 未知版本)"
else
    warn "未找到 python3；local 运行器不可用，需要 docker 运行器"
fi
if command -v git >/dev/null 2>&1; then
    ok "git -> $(command -v git)"
else
    warn "未找到 git；50-apply-patches.sh 不可用"
fi

echo "[3/6] Docker（仅在需要时强制检查）"
DOCKER_OK=0
if command -v docker >/dev/null 2>&1; then
    if docker info >/dev/null 2>&1; then
        DOCKER_OK=1
        ok "docker 可用"
        if docker image inspect "$BACKUP_IMAGE" >/dev/null 2>&1; then
            ok "镜像存在: $BACKUP_IMAGE"
        else
            if [ "$RUNNER" = "docker" ]; then
                bad "镜像不存在: $BACKUP_IMAGE（先 docker compose build）"
            else
                warn "镜像不存在: $BACKUP_IMAGE（RUNNER=auto 时会回退 local）"
            fi
        fi
    else
        if [ "$RUNNER" = "docker" ]; then
            bad "docker 命令存在但无法连接守护进程（权限不足或未启动）"
        else
            warn "docker 无法连接守护进程，将回退 local 运行器"
        fi
    fi
else
    if [ "$RUNNER" = "docker" ]; then
        bad "RUNNER=docker 但未安装 docker"
    else
        warn "未安装 docker（RUNNER=auto 时需要 python3 兜底）"
    fi
fi
if [ "$RUNNER" = "local" ] && ! command -v python3 >/dev/null 2>&1; then
    bad "RUNNER=local 但未找到 python3"
fi
if [ "$RUNNER" = "auto" ] && [ "$DOCKER_OK" = "0" ] && ! command -v python3 >/dev/null 2>&1; then
    bad "RUNNER=auto 但既无可用 docker 也无 python3"
fi

echo "[4/6] 数据目录与文件"
if [ -d "$DATA_DIR" ]; then
    ok "数据目录存在: $DATA_DIR"
else
    bad "数据目录不存在: $DATA_DIR"
fi
for f in "$DATA_DIR/books/library/metadata.db" "$DATA_DIR/books/calibre-webserver.db"; do
    if [ -f "$f" ]; then
        ok "发现: $f"
    else
        warn "未发现: $f（若首次部署可忽略）"
    fi
done
if [ -f "$REPO_DIR/scripts/backup.sh" ]; then
    ok "备份入口存在: $REPO_DIR/scripts/backup.sh"
else
    warn "未发现 $REPO_DIR/scripts/backup.sh：它由补丁 01-P0-backup 新增，未打补丁时可先用本目录 20-backup-full.sh"
fi
if [ -f "$COMPOSE_FILE" ]; then
    ok "compose 文件存在: $COMPOSE_FILE（工程 $COMPOSE_PROJECT / 服务 $APP_SERVICE）"
else
    warn "未发现 compose 文件: $COMPOSE_FILE（检查 APP_ROOT 或 COMPOSE_FILE）"
fi
if [ -d "$APP_CONFIG_DIR" ]; then
    ok "配置目录存在: $APP_CONFIG_DIR"
else
    warn "未发现配置目录: $APP_CONFIG_DIR"
fi
if [ -f "$APP_GIT_DIR/HEAD" ]; then
    ok "git 历史目录存在: $APP_GIT_DIR"
else
    warn "未发现 git 历史: $APP_GIT_DIR（50-apply-patches.sh 将不可用）"
fi
if [ -f "$PATCHES_DIR/01-P0-backup.patch" ]; then
    ok "补丁目录存在: $PATCHES_DIR"
else
    warn "补丁目录不完整: $PATCHES_DIR（50 脚本将不可用）"
fi

echo "[5/6] 路径安全与可写性"
# 规范化（不依赖 realpath）
norm() { ( cd "$1" 2>/dev/null && pwd -P ) || true; }

if [ -d "$DATA_DIR" ] && [ -d "$BACKUP_ROOT" ]; then
    DATA_N="$(norm "$DATA_DIR")"
    BACK_N="$(norm "$BACKUP_ROOT")"
    if [ -z "$DATA_N" ] || [ -z "$BACK_N" ]; then
        warn "无法规范化路径（含符号链接），请人工确认"
    elif [ "$BACK_N" = "$DATA_N" ] || [[ "$BACK_N" == "$DATA_N"/* ]]; then
        bad "备份目录位于数据目录内部: $BACKUP_ROOT"
    else
        ok "备份目录与数据目录相互独立"
    fi
fi

check_writable() {
    local label="$1" path="$2" probe="$2"
    while [ ! -e "$probe" ] && [ "$probe" != "/" ]; do
        probe="$(dirname "$probe")"
    done
    if [ -w "$probe" ]; then
        ok "$label 可写（以 $probe 判断）"
    else
        bad "$label 不可写（以 $probe 判断）"
    fi
}
check_writable "备份目录" "$BACKUP_ROOT"
check_writable "演练目录" "$DRILL_DIR"

if [ -f "$DATA_DIR/books/library/metadata.db" ]; then
    if [ -r "$DATA_DIR/books/library/metadata.db" ]; then
        ok "calibre 元数据库可读"
    else
        bad "calibre 元数据库不可读（权限问题）"
    fi
fi

echo "[6/6] 磁盘余量"
for label_path in "备份盘:$BACKUP_ROOT" "数据盘:$DATA_DIR"; do
    label="${label_path%%:*}"
    path="${label_path#*:}"
    probe="$path"
    while [ ! -e "$probe" ] && [ "$probe" != "/" ]; do
        probe="$(dirname "$probe")"
    done
    if avail_kb="$(df -P -k "$probe" 2>/dev/null | awk 'NR==2 {print $4}')" && [ -n "$avail_kb" ]; then
        avail_gb=$((avail_kb / 1024 / 1024))
        if [ "$avail_gb" -ge "$MIN_FREE_GB" ]; then
            ok "$label 剩余 ${avail_gb}GB（阈值 ${MIN_FREE_GB}GB）"
        else
            bad "$label 剩余 ${avail_gb}GB，低于阈值 ${MIN_FREE_GB}GB"
        fi
    else
        warn "$label 无法读取剩余空间: $probe"
    fi
done

echo
if [ "$FAIL" -eq 0 ]; then
    printf '结论：通过（警告 %d 项）\n' "$WARN"
    exit 0
fi
printf '结论：未通过（失败 %d 项，警告 %d 项），请先修复 [不通过] 项。\n' "$FAIL" "$WARN"
exit 1
