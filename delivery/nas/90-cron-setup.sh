#!/bin/bash
set -euo pipefail

# =============================================================================
# 90-cron-setup.sh —— 生成备份定时任务配置（DSM 任务计划 / crontab）
#
# 默认只打印配置，不改动系统。加 --apply 才会写入当前用户的 crontab，
# 写入前自动备份原有 crontab 到 $HOME/.crontab.bak.<时间戳>。
#
# 群晖 DSM 推荐用「控制面板 -> 任务计划 -> 新增 -> 计划的任务 -> 用户定义脚本」，
# 按本脚本打印的步骤填写即可，无需 --apply。
#
# 退出码：
#   0 成功（已打印或已写入）
#   2 用法错误
#   3 缺少依赖 / 目标脚本不存在
#   4 写入 crontab 失败
# =============================================================================

# ---------- 路径与部署参数：统一来自同目录 paths.conf ----------
MODE="both"          # both | cron | dsm
DO_APPLY=0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATHS_CONF="${PATHS_CONF:-$SCRIPT_DIR/paths.conf}"
if [ ! -f "$PATHS_CONF" ]; then
    printf '错误: 找不到路径配置 %s（应与脚本同目录，或用 PATHS_CONF 指定）\n' "$PATHS_CONF" >&2
    exit 3
fi
# shellcheck source=paths.conf
. "$PATHS_CONF"

BACKUP_SCRIPT="${BACKUP_SCRIPT:-$SCRIPT_DIR/20-backup-full.sh}"
VERIFY_SCRIPT="${VERIFY_SCRIPT:-$SCRIPT_DIR/30-verify-backup.sh}"
SCHEDULE="${SCHEDULE:-0 3 * * *}"
CRON_MARK="# audiobook-backup (由 90-cron-setup.sh 生成)"

usage() {
    cat <<'EOF'
用法: 90-cron-setup.sh [选项]

默认打印 crontab 行和 DSM 任务计划配置步骤，不改动系统。
加 --apply 才写入当前用户的 crontab（写入前自动备份原文件）。

选项:
  --schedule "M H * * *"   cron 表达式（默认 "0 3 * * *"，即每天 03:00）
  --log FILE               日志文件（默认见 paths.conf）
  --backup-script FILE     备份脚本（默认同目录 20-backup-full.sh）
  --verify-script FILE     校验脚本（默认同目录 30-verify-backup.sh）
  --dsm                    只打印 DSM 任务计划的配置步骤
  --cron                   只打印 crontab 行
  --apply                  写入当前用户 crontab（需手动执行，脚本不会自动调用）
  -h, --help               显示帮助

退出码: 0 成功 / 2 用法错误 / 3 缺少依赖 / 4 写入 crontab 失败
EOF
}

die() { printf '错误: %s\n' "$1" >&2; exit "${2:-3}"; }
info() { printf '[90-cron-setup] %s\n' "$*"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --schedule)       SCHEDULE="${2:?缺少参数}"; shift 2 ;;
        --log)            LOG_FILE="${2:?缺少参数}"; shift 2 ;;
        --backup-script)  BACKUP_SCRIPT="${2:?缺少参数}"; shift 2 ;;
        --verify-script)  VERIFY_SCRIPT="${2:?缺少参数}"; shift 2 ;;
        --dsm)            MODE="dsm"; shift ;;
        --cron)           MODE="cron"; shift ;;
        --apply)          DO_APPLY=1; shift ;;
        -h|--help)        usage; exit 0 ;;
        *) echo "未知参数: $1" >&2; usage; exit 2 ;;
    esac
done

[ -f "$BACKUP_SCRIPT" ] || die "备份脚本不存在: $BACKUP_SCRIPT（用 --backup-script 指定）" 3
[ -f "$VERIFY_SCRIPT" ] || die "校验脚本不存在: $VERIFY_SCRIPT（用 --verify-script 指定）" 3

# cron 表达式必须是 5 段（用数组解析，避免 * 被当成文件名通配符展开）
read -r -a CRON_FIELDS <<< "$SCHEDULE"
[ "${#CRON_FIELDS[@]}" -eq 5 ] || die "cron 表达式必须是 5 段（分 时 日 月 周），当前: $SCHEDULE" 2

CRON_LINE="$SCHEDULE /bin/bash $BACKUP_SCRIPT >> $LOG_FILE 2>&1"
VERIFY_LINE="30 6 * * 1 /bin/bash $VERIFY_SCRIPT >> $LOG_FILE 2>&1"

print_cron() {
    printf 'crontab 行（备份）:\n'
    printf '  %s\n' "$CRON_LINE"
    printf 'crontab 行（每周一校验，可选）:\n'
    printf '  %s\n' "$VERIFY_LINE"
}

print_dsm() {
    cat <<EOF
DSM 任务计划配置步骤（推荐，不需要 --apply）:
  1. 控制面板 -> 任务计划 -> 新增 -> 计划的任务 -> 用户定义脚本
  2. 常规:
       任务名称: audiobook-backup
       用户:     root
  3. 计划:
       按日期运行，选择「每天」，时间按需设置（当前 cron: $SCHEDULE）
       若希望更细粒度，可改为「重复任务」每 6 小时一次
  4. 任务设置 -> 用户定义脚本，粘贴以下一行（不要换行、不要加缩进）:
       /bin/bash $BACKUP_SCRIPT >> $LOG_FILE 2>&1
  5. 保存后选中任务，点「运行」做一次手动测试，再查看日志:
       tail -n 50 $LOG_FILE
  6. 如需每周校验，重复以上步骤新建任务，脚本改为:
       /bin/bash $VERIFY_SCRIPT >> $LOG_FILE 2>&1
EOF
}

apply_cron() {
    command -v crontab >/dev/null 2>&1 || die "系统没有 crontab 命令，请改用 DSM 任务计划（--dsm 查看步骤）" 3
    mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true

    CURRENT="$(crontab -l 2>/dev/null || true)"
    if printf '%s\n' "$CURRENT" | grep -F -- "$BACKUP_SCRIPT" >/dev/null 2>&1; then
        info "crontab 已存在引用 $BACKUP_SCRIPT 的条目，未重复写入。"
        printf '%s\n' "$CURRENT" | grep -F -- "$BACKUP_SCRIPT"
        return 0
    fi

    BAK="$HOME/.crontab.bak.$(date +%Y%m%d-%H%M%S)"
    printf '%s\n' "$CURRENT" > "$BAK" || die "无法备份原 crontab 到 $BAK" 4
    info "原 crontab 已备份: $BAK"

    # 用临时文件写入，避免管道内容为空时误清空 crontab
    TMP_CRON="$(mktemp "${TMPDIR:-/tmp}/audiobook-cron.XXXXXX")"
    trap 'rm -f "$TMP_CRON"' EXIT
    {
        printf '%s\n' "$CURRENT"
        printf '%s\n' "$CRON_MARK"
        printf '%s\n' "$CRON_LINE"
    } > "$TMP_CRON"

    if ! crontab "$TMP_CRON"; then
        die "写入 crontab 失败，原 crontab 未改动（备份: $BAK）" 4
    fi
    info "已写入 crontab。用 crontab -l 确认，或 crontab $BAK 回滚。"
}

echo "备份脚本: $BACKUP_SCRIPT"
echo "校验脚本: $VERIFY_SCRIPT"
echo "日志文件: $LOG_FILE"
echo "计划:     $SCHEDULE"
echo

case "$MODE" in
    cron) print_cron ;;
    dsm)  print_dsm ;;
    both) print_cron; echo; print_dsm ;;
esac

if [ "$DO_APPLY" -eq 1 ]; then
    echo
    apply_cron
fi
