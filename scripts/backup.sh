#!/bin/sh
# ============================================================
# audiobook 数据备份（P0）
#
# 备份内容：书库（含每本书的 .audio/ 音频）、calibre 元数据库、
#           站点数据库、reader/sync 等 /data 下除缓存/日志外的全部数据。
#
# 两种备份粒度：
#   - 数据库：SQLite 在线备份 API，站点运行中也能拿到一致副本；
#   - 文件：硬链接快照。每份快照都是完整目录树，未变化文件与上一份
#           共享 inode（等价 rsync --link-dest），所以「全量可恢复、
#           增量只占新增空间」。
#
# 用法：
#   sh scripts/backup.sh                 # 全量一次（DB + 文件 + 清理旧快照）
#   sh scripts/backup.sh --db-only       # 只备份数据库（秒级，适合高频）
#   sh scripts/backup.sh --files-only    # 只备份文件
#   sh scripts/backup.sh --dry-run       # 只打印计划，不写任何文件
#   sh scripts/backup.sh --no-prune      # 本次不清理旧快照
#   sh scripts/backup.sh --list          # 查看已有快照
#
# 全部参数都可用环境变量覆盖，默认值见下方「参数」段。
# 备份根目录、保留份数、排除目录都是可调项，详见 docs/备份与恢复演练.md。
#
# 退出码：0 成功；2 部分成功（有告警，备份仍可用）；3 失败/中止。
# ============================================================
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

# ---------------- 参数（全部可通过环境变量覆盖） ----------------
DATA_DIR=${DATA_DIR:-/volume1/docker/audiobook-data}
BACKUP_ROOT=${BACKUP_ROOT:-/volume1/docker/audiobook-backup}
APP_CONTAINER=${APP_CONTAINER:-audiobook-mybooks-1}
BACKUP_IMAGE=${BACKUP_IMAGE:-mybooks-local:latest}
RUNNER=${RUNNER:-auto}                 # auto | docker | local
DOCKER_USER=${DOCKER_USER:-0:0}
TZ=${TZ:-Asia/Shanghai}
KEEP_DAILY=${KEEP_DAILY:-7}            # 保留最近 7 天，每天一份
KEEP_WEEKLY=${KEEP_WEEKLY:-4}          # 保留最近 4 周，每周一份
KEEP_MONTHLY=${KEEP_MONTHLY:-6}        # 保留最近 6 个月，每月一份
EXCLUDE_DIRS=${EXCLUDE_DIRS:-cache,log,.backup-tmp}
EXCLUDE_PATTERNS=${EXCLUDE_PATTERNS:-*.tmp,*.part,*.partial,*.swp}
MIN_FREE_GB=${MIN_FREE_GB:-5}          # 备份盘剩余空间低于此值则中止
MODE=all
PRUNE=1
DRY_RUN=0
LOCK_WAIT=${LOCK_WAIT:-0}              # 已有备份在跑时，最多等待多少秒
PYTHON_BIN=${PYTHON_BIN:-}

usage() {
    cat <<'EOF'
用法: sh scripts/backup.sh [选项]

  （无参数）        全量一次：数据库 + 文件快照 + 清理旧快照
  --db-only        只备份数据库（秒级）
  --files-only     只备份书库/音频文件
  --dry-run        只打印参数与计划，不写任何文件
  --no-prune       本次不清理旧快照
  --list           查看已有快照及占用空间
  -h, --help       显示本帮助

常用环境变量（都可调，默认值如下）：
  DATA_DIR=/volume1/docker/audiobook-data
  BACKUP_ROOT=/volume1/docker/audiobook-backup
  APP_CONTAINER=audiobook-mybooks-1
  BACKUP_IMAGE=mybooks-local:latest    # docker 运行器使用的镜像
  RUNNER=auto                          # auto | docker | local
  KEEP_DAILY=7  KEEP_WEEKLY=4  KEEP_MONTHLY=6
  EXCLUDE_DIRS=cache,log,.backup-tmp
  EXCLUDE_PATTERNS=*.tmp,*.part,*.partial,*.swp
  MIN_FREE_GB=5
  LOCK_WAIT=0                          # 已有备份在跑时最多等待秒数

示例：
  # 每天 03:30 备份一次，日志追加到备份目录
  30 3 * * * /bin/sh /volume1/docker/audiobook/scripts/backup.sh \
      >> /volume1/docker/audiobook-backup/backup.log 2>&1

  # 只保留 3 天、2 周、3 个月，并包含日志目录
  KEEP_DAILY=3 KEEP_WEEKLY=2 KEEP_MONTHLY=3 EXCLUDE_DIRS=cache \
      sh scripts/backup.sh

完整说明见 docs/备份与恢复演练.md。
EOF
}

# ---------------- 参数解析 ----------------
while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --dry-run) DRY_RUN=1 ;;
        --db-only) MODE=db ;;
        --files-only) MODE=files ;;
        --no-prune) PRUNE=0 ;;
        --list) MODE=list ;;
        *) echo "未知参数: $1（用 --help 查看用法）"; exit 1 ;;
    esac
    shift
done

# ---------------- 快照列表 ----------------
if [ "$MODE" = "list" ]; then
    for kind in db files; do
        d="$BACKUP_ROOT/$kind"
        [ -d "$d" ] || continue
        count=$(ls -1 "$d" 2>/dev/null | wc -l | tr -d ' ')
        echo "[$kind] 共 $count 份（最新 10 份）："
        ls -1 "$d" | sort | tail -n 10 | while read -r name; do
            echo "  $name  $(du -sh "$d/$name" 2>/dev/null | cut -f1)"
        done
    done
    echo "备份根目录: $BACKUP_ROOT"
    exit 0
fi

# ---------------- 基本检查 ----------------
if [ ! -d "$DATA_DIR" ]; then
    echo "!! 数据目录不存在: $DATA_DIR"
    exit 3
fi
if ! mkdir -p "$BACKUP_ROOT" 2>/dev/null; then
    echo "!! 无法创建备份目录: $BACKUP_ROOT（检查权限）"
    exit 3
fi
DATA_REAL=$(CDPATH= cd -- "$DATA_DIR" && pwd -P)
BACKUP_REAL=$(CDPATH= cd -- "$BACKUP_ROOT" && pwd -P)
case "$BACKUP_REAL" in
    "$DATA_REAL"|"$DATA_REAL"/*)
        echo "!! 备份目录不能位于数据目录内部: $BACKUP_REAL"
        exit 3 ;;
esac

# ---------------- 运行器选择 ----------------
APP_RUNNING=0
if command -v docker >/dev/null 2>&1; then
    if [ "$(docker inspect -f '{{.State.Running}}' "$APP_CONTAINER" 2>/dev/null || echo false)" = "true" ]; then
        APP_RUNNING=1
    fi
fi

if [ "$RUNNER" = "auto" ]; then
    if command -v docker >/dev/null 2>&1 && \
       docker image inspect "$BACKUP_IMAGE" >/dev/null 2>&1; then
        RUNNER=docker
    else
        RUNNER=local
    fi
fi

if [ "$RUNNER" = "docker" ]; then
    if ! command -v docker >/dev/null 2>&1; then
        echo "!! RUNNER=docker 但找不到 docker 命令"
        exit 3
    fi
    if ! docker image inspect "$BACKUP_IMAGE" >/dev/null 2>&1; then
        echo "!! 找不到镜像 $BACKUP_IMAGE，请先 cd 到源码目录执行 docker compose build，"
        echo "   或改用 RUNNER=local 并保证本机有 python3"
        exit 3
    fi
else
    if [ -z "$PYTHON_BIN" ]; then
        if command -v python3 >/dev/null 2>&1; then
            PYTHON_BIN=python3
        elif command -v python >/dev/null 2>&1; then
            PYTHON_BIN=python
        fi
    fi
    if [ -z "$PYTHON_BIN" ]; then
        echo "!! 本机没有 python3，且 RUNNER=local。请改用 RUNNER=docker（推荐）"
        exit 3
    fi
fi

# ---------------- 单实例锁 ----------------
LOCK_DIR="$BACKUP_ROOT/.backup.lock"
acquire_lock() {
    waited=0
    while :; do
        if mkdir "$LOCK_DIR" 2>/dev/null; then
            echo $$ > "$LOCK_DIR/pid"
            trap 'rm -rf "$LOCK_DIR"' EXIT INT TERM HUP
            return 0
        fi
        pid=""
        [ -f "$LOCK_DIR/pid" ] && pid=$(cat "$LOCK_DIR/pid" 2>/dev/null || true)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            if [ "$waited" -ge "$LOCK_WAIT" ]; then
                echo "!! 已有备份进程在运行（pid $pid），本次跳过"
                echo "   若确认是残留进程，可手工删除 $LOCK_DIR"
                exit 2
            fi
        else
            # 无 pid 可能是刚抢到锁还没写，等 2 秒确认一次
            sleep 2
            pid2=""
            [ -f "$LOCK_DIR/pid" ] && pid2=$(cat "$LOCK_DIR/pid" 2>/dev/null || true)
            if [ -z "$pid2" ] || ! kill -0 "$pid2" 2>/dev/null; then
                echo "[backup] 清理失效锁（pid ${pid2:-无}）"
                rm -rf "$LOCK_DIR"
                continue
            fi
        fi
        if [ "$waited" -ge "$LOCK_WAIT" ]; then
            echo "!! 无法获取备份锁，本次跳过"
            exit 2
        fi
        sleep 5
        waited=$((waited + 5))
    done
}
acquire_lock

# ---------------- 执行 ----------------
TODAY=$(date "+%Y-%m-%d %H:%M:%S")
echo "============================================================"
echo " audiobook 数据备份  $TODAY"
echo "   数据目录 : $DATA_DIR$( [ "$APP_RUNNING" = "1" ] && echo '（站点运行中，数据库走在线备份）' || echo '（站点未运行）' )"
echo "   备份目录 : $BACKUP_ROOT"
echo "   模式     : $MODE   清理旧快照: $PRUNE   dry-run: $DRY_RUN"
echo "   保留策略 : 日 $KEEP_DAILY / 周 $KEEP_WEEKLY / 月 $KEEP_MONTHLY"
echo "   排除目录 : $EXCLUDE_DIRS"
echo "   排除文件 : $EXCLUDE_PATTERNS"
echo "   运行器   : $RUNNER$( [ "$RUNNER" = docker ] && echo " ($BACKUP_IMAGE)" || echo " ($PYTHON_BIN)" )"
echo "============================================================"

NO_PRUNE_FLAG=""
[ "$PRUNE" = "0" ] && NO_PRUNE_FLAG="--no-prune"
DRY_FLAG=""
[ "$DRY_RUN" = "1" ] && DRY_FLAG="--dry-run"
COLD_FLAG=""
[ "$APP_RUNNING" = "0" ] && COLD_FLAG="--allow-cold-copy"

set +e
if [ "$RUNNER" = "docker" ]; then
    # 一次性容器：只读挂载数据目录（脚本只会读 /data），写 /backup。
    # --network none：备份过程不需要网络，减少暴露面。
    docker run --rm -i --network none \
        --user "$DOCKER_USER" \
        -e "TZ=$TZ" \
        -v "$DATA_DIR:/data" \
        -v "$BACKUP_ROOT:/backup" \
        --entrypoint python3 "$BACKUP_IMAGE" - \
        --data /data --backup /backup --mode "$MODE" \
        --exclude-dirs "$EXCLUDE_DIRS" \
        --exclude-patterns "$EXCLUDE_PATTERNS" \
        --keep-daily "$KEEP_DAILY" \
        --keep-weekly "$KEEP_WEEKLY" \
        --keep-monthly "$KEEP_MONTHLY" \
        --min-free-gb "$MIN_FREE_GB" \
        $NO_PRUNE_FLAG $DRY_FLAG $COLD_FLAG < "$SCRIPT_DIR/backup_run.py"
else
    "$PYTHON_BIN" "$SCRIPT_DIR/backup_run.py" \
        --data "$DATA_DIR" --backup "$BACKUP_ROOT" --mode "$MODE" \
        --exclude-dirs "$EXCLUDE_DIRS" \
        --exclude-patterns "$EXCLUDE_PATTERNS" \
        --keep-daily "$KEEP_DAILY" \
        --keep-weekly "$KEEP_WEEKLY" \
        --keep-monthly "$KEEP_MONTHLY" \
        --min-free-gb "$MIN_FREE_GB" \
        $NO_PRUNE_FLAG $DRY_FLAG $COLD_FLAG
fi
RC=$?
set -e

echo "============================================================"
case "$RC" in
    0) echo " 备份成功。恢复步骤见 docs/备份与恢复演练.md" ;;
    2) echo " 备份完成但有告警（见上方 !! 行），数据仍可恢复。" ;;
    *) echo " 备份失败（退出码 $RC），上一份可用快照未受影响。" ;;
esac
echo "============================================================"
exit $RC
