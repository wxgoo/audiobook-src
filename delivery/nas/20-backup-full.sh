#!/bin/bash
set -euo pipefail

# =============================================================================
# 20-backup-full.sh —— 数据库 + 书籍 + 音频的全量/增量备份（含保留策略）
#
# 首次运行是全量（复制全部文件）；之后未变化的文件用硬链接复用，
# 所以逻辑上是全量快照，物理上接近增量。
#
# 退出码：
#   0 成功
#   2 告警或用法错误
#   3 备份失败 / 缺少依赖
#   4 路径不允许
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
KEEP_DAILY="${KEEP_DAILY:-7}"
KEEP_WEEKLY="${KEEP_WEEKLY:-4}"
KEEP_MONTHLY="${KEEP_MONTHLY:-6}"
MIN_FREE_GB="${MIN_FREE_GB:-5}"
LOCK_WAIT="${LOCK_WAIT:-0}"
EXCLUDE_DIRS="${EXCLUDE_DIRS:-cache,log,.backup-tmp}"
EXCLUDE_PATTERNS="${EXCLUDE_PATTERNS:-*.tmp,*.part,*.partial,*.swp}"

DRY_RUN=0
NO_PRUNE=0

usage() {
    cat <<'EOF'
用法: 20-backup-full.sh [选项]

全量/增量备份：两个数据库（在线备份）+ 书籍 + 音频目录（硬链接快照）。
未变化文件通过硬链接复用，随后按日/周/月保留策略清理旧快照。

选项:
  --data-dir DIR        数据目录（默认见 paths.conf）
  --backup-root DIR     备份目录（默认见 paths.conf）
  --repo-dir DIR        源码目录（默认见 paths.conf）
  --app-container NAME  应用容器名（默认 audiobook-mybooks-1）
  --image NAME          备份镜像（默认 mybooks-local:latest）
  --runner auto|local|docker
  --keep-daily N        保留最近 N 天（默认 7）
  --keep-weekly N       保留最近 N 周（默认 4）
  --keep-monthly N      保留最近 N 月（默认 6）
  --min-free-gb N       备份盘最低剩余空间 GB（默认 5）
  --exclude-dirs LIST   逗号分隔的排除目录名（默认 cache,log,.backup-tmp）
  --exclude-patterns L  逗号分隔的排除文件模式（默认 *.tmp,*.part,*.partial,*.swp）
  --dry-run             只打印计划，不写文件、不清理
  --no-prune            本次不清理旧快照
  -h, --help            显示帮助

退出码: 0 成功 / 2 告警或用法错误 / 3 失败 / 4 路径不允许
EOF
}

die() { printf '错误: %s\n' "$1" >&2; exit "${2:-3}"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --data-dir)         DATA_DIR="${2:?缺少参数}"; shift 2 ;;
        --backup-root)      BACKUP_ROOT="${2:?缺少参数}"; shift 2 ;;
        --repo-dir)         REPO_DIR="${2:?缺少参数}"; shift 2 ;;
        --app-container)    APP_CONTAINER="${2:?缺少参数}"; shift 2 ;;
        --image)            BACKUP_IMAGE="${2:?缺少参数}"; shift 2 ;;
        --runner)           RUNNER="${2:?缺少参数}"; shift 2 ;;
        --keep-daily)       KEEP_DAILY="${2:?缺少参数}"; shift 2 ;;
        --keep-weekly)      KEEP_WEEKLY="${2:?缺少参数}"; shift 2 ;;
        --keep-monthly)     KEEP_MONTHLY="${2:?缺少参数}"; shift 2 ;;
        --min-free-gb)      MIN_FREE_GB="${2:?缺少参数}"; shift 2 ;;
        --exclude-dirs)     EXCLUDE_DIRS="${2:?缺少参数}"; shift 2 ;;
        --exclude-patterns) EXCLUDE_PATTERNS="${2:?缺少参数}"; shift 2 ;;
        --dry-run)          DRY_RUN=1; shift ;;
        --no-prune)         NO_PRUNE=1; shift ;;
        -h|--help)          usage; exit 0 ;;
        *) echo "未知参数: $1" >&2; usage; exit 2 ;;
    esac
done

[ -d "$DATA_DIR" ] || die "数据目录不存在: $DATA_DIR" 3
[ -f "$REPO_DIR/scripts/backup.sh" ] || die "找不到备份入口: $REPO_DIR/scripts/backup.sh（用 --repo-dir 指定）" 3

case "$KEEP_DAILY" in ''|*[!0-9]*) die "KEEP_DAILY 必须是整数: $KEEP_DAILY" 2 ;; esac
case "$KEEP_WEEKLY" in ''|*[!0-9]*) die "KEEP_WEEKLY 必须是整数: $KEEP_WEEKLY" 2 ;; esac
case "$KEEP_MONTHLY" in ''|*[!0-9]*) die "KEEP_MONTHLY 必须是整数: $KEEP_MONTHLY" 2 ;; esac

norm() { ( cd "$1" 2>/dev/null && pwd -P ) || true; }
DATA_N="$(norm "$DATA_DIR")"
BACK_PROBE="$BACKUP_ROOT"
while [ ! -d "$BACK_PROBE" ] && [ "$BACK_PROBE" != "/" ]; do BACK_PROBE="$(dirname "$BACK_PROBE")"; done
BACK_N="$(norm "$BACK_PROBE")"
if [ -n "$DATA_N" ] && [ -n "$BACK_N" ] && [[ "$BACK_N" == "$DATA_N"/* ]]; then
    die "备份目录不能位于数据目录内部: $BACKUP_ROOT" 4
fi

printf '[20-backup-full] 数据=%s 备份=%s 运行器=%s\n' "$DATA_DIR" "$BACKUP_ROOT" "$RUNNER"
printf '[20-backup-full] 保留 日=%s 周=%s 月=%s，dry-run=%s，清理=%s\n' \
       "$KEEP_DAILY" "$KEEP_WEEKLY" "$KEEP_MONTHLY" "$DRY_RUN" "$((1 - NO_PRUNE))"

ARGS=""
[ "$DRY_RUN" -eq 1 ] && ARGS="$ARGS --dry-run"
[ "$NO_PRUNE" -eq 1 ] && ARGS="$ARGS --no-prune"

set +e
env DATA_DIR="$DATA_DIR" \
    BACKUP_ROOT="$BACKUP_ROOT" \
    APP_CONTAINER="$APP_CONTAINER" \
    BACKUP_IMAGE="$BACKUP_IMAGE" \
    RUNNER="$RUNNER" \
    DOCKER_USER="$DOCKER_USER" \
    TZ="$TZ" \
    KEEP_DAILY="$KEEP_DAILY" \
    KEEP_WEEKLY="$KEEP_WEEKLY" \
    KEEP_MONTHLY="$KEEP_MONTHLY" \
    MIN_FREE_GB="$MIN_FREE_GB" \
    LOCK_WAIT="$LOCK_WAIT" \
    EXCLUDE_DIRS="$EXCLUDE_DIRS" \
    EXCLUDE_PATTERNS="$EXCLUDE_PATTERNS" \
    bash "$REPO_DIR/scripts/backup.sh" $ARGS
RC=$?
set -e

case "$RC" in
    0) printf '完成：全量/增量备份成功。\n' ;;
    2) printf '完成但有告警（退出码 2），请检查上面的 !! 行；上一份可用快照未受影响。\n' ;;
    *) printf '失败（退出码 %d），上一份可用快照未受影响；修复后重跑。\n' "$RC" ;;
esac
exit "$RC"
