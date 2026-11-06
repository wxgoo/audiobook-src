#!/bin/bash
set -euo pipefail

# =============================================================================
# 50-apply-patches.sh —— 把 delivery/patches 下的补丁应用到目标源码目录
#
# 默认行为：dry-run（在临时 worktree 里顺序试应用，不触碰目标工作区）。
# 加 --apply 才真正写入目标仓库。
#
# 退出码：
#   0 成功（dry-run 或应用成功）
#   2 用法错误
#   3 缺少 git / 补丁 / 目标目录
#   4 目标仓库状态不允许（脏工作区、基线不符）
#   6 冲突/应用失败（已列出冲突文件）
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
BASE_REV="${BASE_REV:-32bc1d4}"

TARGET_DIR=""
DO_APPLY=0
METHOD="am"
ONLY=""
ALLOW_DIRTY=0
ALLOW_BASE_DIFF=0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -n "$PATCHES_DIR" ] || PATCHES_DIR="$SCRIPT_DIR/../patches"

usage() {
    cat <<'EOF'
用法: 50-apply-patches.sh [选项]

把补丁按编号顺序应用到目标仓库。默认 dry-run：从 HEAD 导出临时快照顺序试应用，
不修改目标工作区；确认无误后加 --apply 写入。

选项:
  --target DIR          目标源码目录（默认见 paths.conf 的 APP_ROOT）
  --patches DIR         补丁目录（默认本脚本同级的 ../patches）
  --base REV            期望基线提交（默认 32bc1d4）
  --only IDS            只应用指定编号，如 --only 01,05,07
  --apply               真正写入（默认只检查）
  --method am|apply     应用方式：am 保留提交（默认）/ apply 只改工作区
  --allow-dirty         允许目标工作区有未提交改动
  --allow-base-diff     允许 HEAD 不等于基线（仍会检查补丁能否应用）
  -h, --help            显示帮助

退出码: 0 成功 / 2 用法错误 / 3 缺依赖 / 4 状态不允许 / 6 冲突或应用失败
EOF
}

die() { printf '错误: %s\n' "$1" >&2; exit "${2:-3}"; }
info() { printf '[50-apply-patches] %s\n' "$*"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --target)          TARGET_DIR="${2:?缺少参数}"; shift 2 ;;
        --patches)         PATCHES_DIR="${2:?缺少参数}"; shift 2 ;;
        --base)            BASE_REV="${2:?缺少参数}"; shift 2 ;;
        --only)            ONLY="${2:?缺少参数}"; shift 2 ;;
        --apply)           DO_APPLY=1; shift ;;
        --method)          METHOD="${2:?缺少参数}"; shift 2 ;;
        --allow-dirty)     ALLOW_DIRTY=1; shift ;;
        --allow-base-diff) ALLOW_BASE_DIFF=1; shift ;;
        -h|--help)         usage; exit 0 ;;
        *) echo "未知参数: $1" >&2; usage; exit 2 ;;
    esac
done

[ -n "$TARGET_DIR" ] || TARGET_DIR="$REPO_DIR"
case "$METHOD" in am|apply) : ;; *) die "--method 只能是 am 或 apply" 2 ;; esac

command -v git >/dev/null 2>&1 || die "未安装 git" 3
[ -d "$PATCHES_DIR" ] || die "补丁目录不存在: $PATCHES_DIR" 3
PATCHES_DIR="$(cd "$PATCHES_DIR" && pwd -P)"

# 部署目录内通常没有 .git（历史在 APP_GIT_DIR），两种布局都支持
GIT_DIR_ABS=""
if [ -d "$TARGET_DIR/.git" ]; then
    GIT_DIR_ABS=""
elif [ -f "$APP_GIT_DIR/HEAD" ]; then
    GIT_DIR_ABS="$APP_GIT_DIR"
else
    die "目标既不是 git 仓库、也没有可用的 $APP_GIT_DIR：$TARGET_DIR" 3
fi
if [ -n "$GIT_DIR_ABS" ]; then
    info "使用分离式 git 目录: $GIT_DIR_ABS + 工作树 $TARGET_DIR"
fi
gt() {
    if [ -n "$GIT_DIR_ABS" ]; then
        git --git-dir="$GIT_DIR_ABS" --work-tree="$TARGET_DIR" "$@"
    else
        git -C "$TARGET_DIR" "$@"
    fi
}

PATCH_LIST=()
for p in "$PATCHES_DIR"/*.patch; do
    [ -f "$p" ] || continue
    name="${p##*/}"
    id="${name%%-*}"
    if [ -n "$ONLY" ]; then
        keep=0
        for want in ${ONLY//,/ }; do
            [ "$want" = "$id" ] && keep=1
        done
        [ "$keep" -eq 1 ] || continue
    fi
    PATCH_LIST+=("$p")
done
[ "${#PATCH_LIST[@]}" -gt 0 ] || die "没有可应用的补丁（目录: $PATCHES_DIR）" 3

HEAD_REV="$(gt rev-parse HEAD)"
if ! gt rev-parse --verify --quiet "$BASE_REV^{commit}" >/dev/null; then
    if [ "$ALLOW_BASE_DIFF" -eq 1 ]; then
        printf '[警告] 基线提交 %s 不存在，继续（补丁可能冲突）。\n' "$BASE_REV" >&2
    else
        die "目标仓库没有基线提交 $BASE_REV（确认仓库/分支，或加 --allow-base-diff）" 4
    fi
fi
if [ -n "$(gt status --porcelain)" ] && [ "$ALLOW_DIRTY" -ne 1 ]; then
    die "目标工作区有未提交改动，请先提交或 git stash（或加 --allow-dirty）" 4
fi
if [ "$ALLOW_BASE_DIFF" -ne 1 ] && [ "$HEAD_REV" != "$(gt rev-parse "$BASE_REV^{commit}")" ]; then
    die "HEAD=$HEAD_REV 与基线 $BASE_REV 不一致（或加 --allow-base-diff）" 4
fi

info "目标=$TARGET_DIR HEAD=$HEAD_REV 补丁数=${#PATCH_LIST[@]} 方式=$METHOD apply=$DO_APPLY"

extract_conflicts() {
    # 从 git apply/am 输出中提取冲突文件名
    sed -n -e 's/^error: patch failed: \([^:]*\):.*/\1/p' \
           -e 's/^error: \([^:]*\): patch does not apply/\1/p' | sort -u
}

if [ "$DO_APPLY" -eq 0 ]; then
    TMP_WT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/audiobook-patch-check.XXXXXX")"
    cleanup() { rm -rf "$TMP_WT_DIR"; }
    trap cleanup EXIT
    # 从 HEAD 导出干净快照，不依赖 worktree，也不动目标工作区
    gt archive --format=tar HEAD > "$TMP_WT_DIR/.snapshot.tar" \
        || die "无法导出 HEAD 快照（检查 git 目录可读）" 3
    tar -xf "$TMP_WT_DIR/.snapshot.tar" -C "$TMP_WT_DIR" \
        || die "无法解包 HEAD 快照" 3
    rm -f "$TMP_WT_DIR/.snapshot.tar"

    n=0
    for p in "${PATCH_LIST[@]}"; do
        n=$((n + 1))
        name="${p##*/}"
        if out="$( ( cd "$TMP_WT_DIR" && git apply --check --whitespace=nowarn "$p" ) 2>&1 )"; then
            if out="$( ( cd "$TMP_WT_DIR" && git apply --whitespace=nowarn "$p" ) 2>&1 )"; then
                printf '  [可应用] %s\n' "$name"
            else
                printf '  [失败] %s\n%s\n' "$name" "$out"
                printf '冲突文件:\n'; printf '%s\n' "$out" | extract_conflicts | sed 's/^/  - /'
                exit 6
            fi
        else
            printf '  [失败] %s\n%s\n' "$name" "$out"
            printf '冲突文件:\n'; printf '%s\n' "$out" | extract_conflicts | sed 's/^/  - /'
            exit 6
        fi
    done
    printf '结论：%d 个补丁可在当前 HEAD 顺序应用（dry-run，未修改目标）。加 --apply 写入。\n' "$n"
    exit 0
fi

n=0
for p in "${PATCH_LIST[@]}"; do
    n=$((n + 1))
    name="${p##*/}"
    if [ "$METHOD" = "am" ]; then
        if out="$(gt -c user.name="${GIT_AUTHOR_NAME:-wxgoo}" \
                 -c user.email="${GIT_AUTHOR_EMAIL:-wxgoo@gitee.com}" am "$p" 2>&1)"; then
            printf '  [已应用] %s\n' "$name"
        else
            printf '  [失败] %s\n%s\n' "$name" "$out"
            printf '冲突文件:\n'; printf '%s\n' "$out" | extract_conflicts | sed 's/^/  - /'
            gt am --abort >/dev/null 2>&1 || true
            printf '已执行 git am --abort，目标仓库回到应用前状态。\n' >&2
            exit 6
        fi
    else
        if out="$(gt apply --whitespace=nowarn "$p" 2>&1)"; then
            printf '  [已应用] %s\n' "$name"
        else
            printf '  [失败] %s\n%s\n' "$name" "$out"
            printf '冲突文件:\n'; printf '%s\n' "$out" | extract_conflicts | sed 's/^/  - /'
            exit 6
        fi
    fi
done
printf '结论：%d 个补丁已应用。\n' "$n"
