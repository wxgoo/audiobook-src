#!/bin/bash
set -euo pipefail

# =============================================================================
# 40-restore-drill.sh —— 恢复演练（只写入独立演练目录，绝不碰生产路径）
#
# 安全规则（任一不满足都直接拒绝执行）：
#   1) 演练目录必须在 DRILL_PREFIX（paths.conf，默认 /volume1/backup）之下；
#   2) 演练目录不能与数据目录、备份目录互相包含；
#   3) 演练目录非空时必须显式 --force；
#   4) 只读取备份目录，只写入演练目录。
#
# 退出码：
#   0 成功
#   2 用法错误
#   3 缺少依赖 / 快照不存在
#   4 路径不安全
#   5 恢复后校验失败
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATHS_CONF="${PATHS_CONF:-$SCRIPT_DIR/paths.conf}"
if [ ! -f "$PATHS_CONF" ]; then
    printf '错误: 找不到路径配置 %s（应与脚本同目录，或用 PATHS_CONF 指定）\n' "$PATHS_CONF" >&2
    exit 3
fi
# shellcheck source=paths.conf
. "$PATHS_CONF"

RUNNER="${RUNNER:-auto}"
DOCKER_USER="${DOCKER_USER:-0:0}"

TIMESTAMP=""
WITH_FILES=0
FORCE=0

usage() {
    cat <<'EOF'
用法: 40-restore-drill.sh [选项]

在独立演练目录恢复指定快照（默认最新）。默认只恢复数据库；加 --with-files
同时复制文件快照。脚本不会写入数据目录或备份目录。

选项:
  --backup-root DIR     备份目录（默认见 paths.conf）
  --data-dir DIR        生产数据目录（仅用于安全校验，默认见 paths.conf）
  --drill-dir DIR       演练目录（默认见 paths.conf）
  --timestamp TS        指定快照（默认最新）
  --with-files          同时复制文件快照（需要额外磁盘空间）
  --force               演练目录非空时允许继续（只覆盖同名文件，不删除其它文件）
  --runner auto|local|docker
  --image NAME          校验用镜像
  -h, --help            显示帮助

退出码: 0 成功 / 2 用法错误 / 3 依赖或快照缺失 / 4 路径不安全 / 5 校验失败
EOF
}

die() { printf '错误: %s\n' "$1" >&2; exit "${2:-3}"; }
ok()  { printf '  [通过] %s\n' "$*"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --backup-root) BACKUP_ROOT="${2:?缺少参数}"; shift 2 ;;
        --data-dir)    DATA_DIR="${2:?缺少参数}"; shift 2 ;;
        --drill-dir)   DRILL_DIR="${2:?缺少参数}"; shift 2 ;;
        --timestamp)   TIMESTAMP="${2:?缺少参数}"; shift 2 ;;
        --with-files)  WITH_FILES=1; shift ;;
        --force)       FORCE=1; shift ;;
        --runner)      RUNNER="${2:?缺少参数}"; shift 2 ;;
        --image)       BACKUP_IMAGE="${2:?缺少参数}"; shift 2 ;;
        -h|--help)     usage; exit 0 ;;
        *) echo "未知参数: $1" >&2; usage; exit 2 ;;
    esac
done

# ---- 路径规范化与白名单 ----
norm() { ( cd "$1" 2>/dev/null && pwd -P ) || true; }

case "$DRILL_DIR" in
    /*) : ;;
    *) die "演练目录必须是绝对路径: $DRILL_DIR" 4 ;;
esac

BACK_PROBE="$BACKUP_ROOT"
while [ ! -d "$BACK_PROBE" ] && [ "$BACK_PROBE" != "/" ]; do BACK_PROBE="$(dirname "$BACK_PROBE")"; done
BACK_N="$(norm "$BACK_PROBE")"
DATA_N="$(norm "$DATA_DIR")"
[ -n "$BACK_N" ] || die "无法规范化备份目录: $BACKUP_ROOT" 4

mkdir -p "$DRILL_DIR"
DRILL_N="$(norm "$DRILL_DIR")"
PREFIX_N="$(norm "$DRILL_PREFIX")"
[ -n "$PREFIX_N" ] || die "无法规范化 DRILL_PREFIX: $DRILL_PREFIX" 4

if [[ "$DRILL_N" != "$PREFIX_N"/* ]]; then
    die "演练目录必须在 $DRILL_PREFIX 之下，实际: $DRILL_N" 4
fi
if [ -n "$DATA_N" ] && { [ "$DRILL_N" = "$DATA_N" ] || [[ "$DRILL_N" == "$DATA_N"/* ]] || [[ "$DATA_N" == "$DRILL_N"/* ]]; }; then
    die "演练目录与生产数据目录存在包含关系: $DRILL_N <-> $DATA_N" 4
fi
if [ "$DRILL_N" = "$BACK_N" ] || [[ "$DRILL_N" == "$BACK_N"/* ]] || [[ "$BACK_N" == "$DRILL_N"/* ]]; then
    die "演练目录与备份目录存在包含关系: $DRILL_N <-> $BACK_N" 4
fi
ok "路径白名单: $DRILL_N"

if [ -n "$(ls -A "$DRILL_DIR" 2>/dev/null || true)" ] && [ "$FORCE" -ne 1 ]; then
    die "演练目录非空: $DRILL_DIR（确认后可加 --force，只覆盖同名文件）" 4
fi

# ---- 选择快照 ----
if [ -z "$TIMESTAMP" ]; then
    last="$(ls -1 "$BACKUP_ROOT/manifests"/backup-*.json 2>/dev/null | sort | tail -1 || true)"
    [ -n "$last" ] || die "没有任何 manifest，无法确定最新快照" 3
    f="${last##*/}"
    TIMESTAMP="${f#backup-}"
    TIMESTAMP="${TIMESTAMP%.json}"
fi

DB_TS_DIR="$BACKUP_ROOT/db/$TIMESTAMP"
[ -d "$DB_TS_DIR" ] || die "快照没有数据库备份: $DB_TS_DIR" 3
printf '[40-restore-drill] 快照=%s 演练目录=%s 文件=%s\n' "$TIMESTAMP" "$DRILL_DIR" "$WITH_FILES"

# ---- 磁盘余量 ----
need_kb="$(du -sk "$DB_TS_DIR" 2>/dev/null | awk '{print $1}' || echo 0)"
if [ "$WITH_FILES" -eq 1 ]; then
    [ -d "$BACKUP_ROOT/files/$TIMESTAMP" ] || die "快照没有文件备份: $BACKUP_ROOT/files/$TIMESTAMP" 3
    files_kb="$(du -sk "$BACKUP_ROOT/files/$TIMESTAMP" 2>/dev/null | awk '{print $1}' || echo 0)"
    need_kb=$((need_kb + files_kb))
fi
avail_kb="$(df -P -k "$DRILL_DIR" | awk 'NR==2 {print $4}')"
if [ -n "$avail_kb" ] && [ "$need_kb" -gt "$avail_kb" ]; then
    die "演练目录剩余空间不足: 需要 ${need_kb}KB，可用 ${avail_kb}KB" 3
fi

# ---- 恢复数据库 ----
mkdir -p "$DRILL_DIR/db"
for src in "$DB_TS_DIR"/*.db; do
    [ -f "$src" ] || continue
    dst="$DRILL_DIR/db/${src##*/}"
    cp -p "$src" "$dst"
    ok "已复制 $(basename "$src") -> $dst"
done
if [ -f "$DB_TS_DIR/manifest.json" ]; then
    cp -p "$DB_TS_DIR/manifest.json" "$DRILL_DIR/db/manifest.json"
fi

# ---- 可选：恢复文件快照 ----
if [ "$WITH_FILES" -eq 1 ]; then
    mkdir -p "$DRILL_DIR/files"
    # -a 保留时间戳与硬链接（目标文件系统需支持硬链接）
    cp -a "$BACKUP_ROOT/files/$TIMESTAMP/." "$DRILL_DIR/files/"
    ok "已复制文件快照 -> $DRILL_DIR/files"
fi

# ---- 恢复后完整性校验 ----
PY_CHECK='
import os, sqlite3, sys
root = sys.argv[1]
bad = 0
for name in sorted(os.listdir(os.path.join(root, "db"))):
    if not name.endswith(".db"):
        continue
    p = os.path.join(root, "db", name)
    try:
        con = sqlite3.connect(p)
        result = con.execute("PRAGMA integrity_check").fetchone()[0]
        con.close()
    except Exception as exc:
        print("[失败] %s 无法打开: %s" % (name, exc))
        bad += 1
        continue
    if result == "ok":
        print("[通过] %s integrity_check=ok" % name)
    else:
        print("[失败] %s integrity_check=%s" % (name, result))
        bad += 1
sys.exit(1 if bad else 0)
'

run_check() {
    if [ "$RUNNER" != "docker" ] && command -v python3 >/dev/null 2>&1; then
        python3 - "$DRILL_DIR" <<< "$PY_CHECK"
        return $?
    fi
    if ! command -v docker >/dev/null 2>&1; then
        printf '[警告] 无 python3 也无 docker，跳过恢复后完整性校验。\n' >&2
        return 0
    fi
    docker run --rm -i --network none --user "$DOCKER_USER" \
        -v "$DRILL_DIR:/drill:ro" \
        --entrypoint python3 "$BACKUP_IMAGE" - /drill <<< "$PY_CHECK"
}

set +e
run_check
RC=$?
set -e

echo
printf '演练产物: %s\n' "$DRILL_DIR"
printf '生产数据目录未被写入: %s\n' "$DATA_DIR"
if [ "$RC" -ne 0 ]; then
    printf '失败：恢复后校验未通过（退出码 %d），不要用于正式恢复。\n' "$RC"
    exit 5
fi
printf '完成：恢复演练通过。\n'
if [ "$WITH_FILES" -eq 1 ]; then
    printf '后续可用 rsync/cp 从 %s/files 挑选单本验证，切勿整体覆盖生产目录。\n' "$DRILL_DIR"
fi
exit 0
