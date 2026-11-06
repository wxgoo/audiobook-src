#!/bin/bash
set -euo pipefail

# =============================================================================
# 10-backup-db.sh —— 仅备份数据库（在线备份，不锁库）
#
# 退出码：
#   0 成功
#   2 用法/配置错误，或备份告警（原样透传 scripts/backup.sh 的 2）
#   3 缺少依赖 / 备份失败
#   4 路径不允许（备份目录位于数据目录内部）
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATHS_CONF="${PATHS_CONF:-$SCRIPT_DIR/paths.conf}"
if [ ! -f "$PATHS_CONF" ]; then
    printf '错误: 找不到路径配置 %s（应与脚本同目录，或用 PATHS_CONF 指定）\n' "$PATHS_CONF" >&2
    exit 3
fi
# shellcheck source=paths.conf
. "$PATHS_CONF"

REPO_DIR="$APP_ROOT"
RUNNER="${RUNNER:-auto}"
DOCKER_USER="${DOCKER_USER:-0:0}"
MIN_FREE_GB="${MIN_FREE_GB:-5}"
LOCK_WAIT="${LOCK_WAIT:-0}"

DRY_RUN=0

usage() {
    cat <<'EOF'
用法: 10-backup-db.sh [选项]

只备份两个 SQLite 数据库（站点库 + calibre 元数据库），走在线备份 API，
不停止容器、不锁库。产物: <备份目录>/db/<时间戳>/ 与 manifests/。

选项:
  --data-dir DIR        数据目录（默认见 paths.conf）
  --backup-root DIR     备份目录（默认见 paths.conf）
  --repo-dir DIR        源码目录（默认见 paths.conf）
  --app-container NAME  应用容器名（默认 audiobook-mybooks-1）
  --image NAME          备份镜像（默认 mybooks-local:latest）
  --runner auto|local|docker
  --dry-run             只打印计划，不写文件
  -h, --help            显示帮助

退出码: 0 成功 / 2 告警或用法错误 / 3 失败 / 4 路径不允许
EOF
}

die() { printf '错误: %s\n' "$1" >&2; exit "${2:-3}"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --data-dir)      DATA_DIR="${2:?缺少参数}"; shift 2 ;;
        --backup-root)   BACKUP_ROOT="${2:?缺少参数}"; shift 2 ;;
        --repo-dir)      REPO_DIR="${2:?缺少参数}"; shift 2 ;;
        --app-container) APP_CONTAINER="${2:?缺少参数}"; shift 2 ;;
        --image)         BACKUP_IMAGE="${2:?缺少参数}"; shift 2 ;;
        --runner)        RUNNER="${2:?缺少参数}"; shift 2 ;;
        --dry-run)       DRY_RUN=1; shift ;;
        -h|--help)       usage; exit 0 ;;
        *) echo "未知参数: $1" >&2; usage; exit 2 ;;
    esac
done

[ -d "$DATA_DIR" ] || die "数据目录不存在: $DATA_DIR" 3
[ -f "$REPO_DIR/scripts/backup.sh" ] || die "找不到备份入口: $REPO_DIR/scripts/backup.sh（用 --repo-dir 指定）" 3

norm() { ( cd "$1" 2>/dev/null && pwd -P ) || true; }
DATA_N="$(norm "$DATA_DIR")"
BACK_PROBE="$BACKUP_ROOT"
while [ ! -d "$BACK_PROBE" ] && [ "$BACK_PROBE" != "/" ]; do BACK_PROBE="$(dirname "$BACK_PROBE")"; done
BACK_N="$(norm "$BACK_PROBE")"
if [ -n "$DATA_N" ] && [ -n "$BACK_N" ] && [[ "$BACK_N" == "$DATA_N"/* ]]; then
    die "备份目录不能位于数据目录内部: $BACKUP_ROOT" 4
fi

printf '[10-backup-db] 数据=%s 备份=%s 运行器=%s 容器=%s\n' \
       "$DATA_DIR" "$BACKUP_ROOT" "$RUNNER" "$APP_CONTAINER"

ARGS="--db-only"
[ "$DRY_RUN" -eq 1 ] && ARGS="$ARGS --dry-run"

set +e
env DATA_DIR="$DATA_DIR" \
    BACKUP_ROOT="$BACKUP_ROOT" \
    APP_CONTAINER="$APP_CONTAINER" \
    BACKUP_IMAGE="$BACKUP_IMAGE" \
    RUNNER="$RUNNER" \
    DOCKER_USER="$DOCKER_USER" \
    TZ="$TZ" \
    MIN_FREE_GB="$MIN_FREE_GB" \
    LOCK_WAIT="$LOCK_WAIT" \
    bash "$REPO_DIR/scripts/backup.sh" $ARGS
RC=$?
set -e

case "$RC" in
    0) printf '完成：数据库备份成功。\n' ;;
    2) printf '完成但有告警（退出码 2），请检查上面的 !! 行。\n' ;;
    *) printf '失败（退出码 %d），修复后重跑。\n' "$RC" ;;
esac
exit "$RC"
