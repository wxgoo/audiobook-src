#!/bin/bash
set -euo pipefail

# =============================================================================
# 60-apply-overlay.sh —— 不依赖 git 的文件覆盖包应用/回滚
#
# 适用前提：宿主机上有源码目录（APP_ROOT，含 webserver/）
# 不适用：宿主机只有预构建镜像、没有源码 —— 必须在构建镜像的机器上改源码再构建
#
# 行为：
#   - 默认 dry-run：只比对与打印计划，不写任何文件
#   - --apply：逐个校验基线 sha256，一致才覆盖；不一致默认跳过并列出
#   - --force：允许覆盖基线不一致的文件（覆盖前仍会备份）
#   - 覆盖前备份到 <ops目录>/rollback/<时间戳>/，可 --rollback 一键还原
#   - 默认只打印生效命令；--tag-only / --build / --rollback-image 才真正操作镜像
#
# 退出码：0 成功 / 2 用法错误 / 3 缺依赖 / 4 有冲突（已跳过） / 5 包校验失败
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATHS_CONF="${PATHS_CONF:-$SCRIPT_DIR/paths.conf}"
if [ ! -f "$PATHS_CONF" ]; then
    printf '错误: 找不到路径配置 %s（应与脚本同目录，或用 PATHS_CONF 指定）\n' "$PATHS_CONF" >&2
    exit 3
fi
# shellcheck source=paths.conf
. "$PATHS_CONF"

OVERLAY_DIR="${OVERLAY_DIR:-$SCRIPT_DIR/../overlay}"
TARGET_DIR="${TARGET_DIR:-$APP_ROOT}"
ROLLBACK_ROOT="${ROLLBACK_ROOT:-$SCRIPT_DIR/../rollback}"
LOG_DIR="${LOG_DIR:-$SCRIPT_DIR/../logs}"

APPLY=0
FORCE=0
ROLLBACK_TS=""
LIST_ONLY=0
DO_TAG=0
DO_BUILD=0
DO_ROLLBACK_IMAGE=0

usage() {
    cat <<'EOF'
用法: 60-apply-overlay.sh [选项]

默认 dry-run：只比对目标文件与 MANIFEST.tsv 的基线 sha256，打印计划，不写文件。
确认后加 --apply 执行；覆盖前自动备份到 rollback/<时间戳>/。

选项:
  --apply                 真正覆盖文件（默认只检查）
  --force                 基线不一致也覆盖（仍先备份）
  --rollback[=时间戳]     回滚源码；省略时间戳则用最近一次
  --list                  只列出覆盖包内容
  --tag-only              仅给当前镜像打 pre-opt 标签
  --build                 执行 打标签 -> compose build -> up -d（显式才执行）
  --rollback-image        执行 镜像标签回滚 -> up -d（显式才执行）
  --overlay DIR           覆盖包目录（默认 ../overlay）
  --target DIR            目标源码目录（默认 paths.conf 的 APP_ROOT）
  -h, --help              显示帮助

退出码: 0 成功 / 2 用法错误 / 3 缺依赖 / 4 有冲突已跳过 / 5 包校验失败
EOF
}

die() { printf '错误: %s\n' "$1" >&2; exit "${2:-3}"; }
info() { printf '[overlay] %s\n' "$*"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --apply)         APPLY=1; shift ;;
        --force)         FORCE=1; shift ;;
        --rollback)      ROLLBACK_TS="__latest__"; shift ;;
        --rollback=*)    ROLLBACK_TS="${1#*=}"; shift ;;
        --list)          LIST_ONLY=1; shift ;;
        --tag-only)      DO_TAG=1; shift ;;
        --build)         DO_BUILD=1; shift ;;
        --rollback-image) DO_ROLLBACK_IMAGE=1; shift ;;
        --overlay)       OVERLAY_DIR="${2:?缺少参数}"; shift 2 ;;
        --target)        TARGET_DIR="${2:?缺少参数}"; shift 2 ;;
        -h|--help)       usage; exit 0 ;;
        *) echo "未知参数: $1" >&2; usage; exit 2 ;;
    esac
done

[ -d "$TARGET_DIR" ] || die "目标源码目录不存在: $TARGET_DIR" 3
[ -f "$OVERLAY_DIR/MANIFEST.tsv" ] || die "覆盖包不完整: 缺少 $OVERLAY_DIR/MANIFEST.tsv" 3

IMAGE="$BACKUP_IMAGE"
IMAGE_REPO="${IMAGE%:*}"
if [ "$IMAGE_REPO" = "$IMAGE" ]; then
    PRE_TAG="${IMAGE}:pre-opt"
else
    PRE_TAG="${IMAGE_REPO}:pre-opt"
fi
COMPOSE_CMD="docker compose -f $COMPOSE_FILE"

# ---------- 生效方式：读 compose 判断 bind mount 还是打进镜像 ----------
detect_mode() {
    if [ ! -f "$COMPOSE_FILE" ]; then
        echo "image"
        return
    fi
    if grep -qE "^[[:space:]]*-[[:space:]]*${TARGET_DIR}:/|/var/www/mybooks|:/app([[:space:]]*)" "$COMPOSE_FILE"; then
        echo "bind"
    else
        echo "image"
    fi
}
EFFECTIVE_MODE="$(detect_mode)"

print_effective() {
    echo
    echo "==== 生效方式 ===="
    if [ "$EFFECTIVE_MODE" = "bind" ]; then
        echo "compose 把源码目录挂载进了容器：覆盖后只需重启容器。"
        printf '  docker restart %s\n' "$APP_CONTAINER"
        printf '  # 或 %s restart %s\n' "$COMPOSE_CMD" "$APP_SERVICE"
    else
        echo "源码是打进镜像的（compose 有 build、没有源码挂载）：必须重建镜像。"
        echo "建议按以下顺序执行（脚本默认只打印，不执行）："
        printf '  docker tag %s %s\n' "$IMAGE" "$PRE_TAG"
        printf '  mkdir -p %s\n' "$LOG_DIR"
        printf '  %s build %s 2>&1 | tee %s/build-%s.log\n' "$COMPOSE_CMD" "$APP_SERVICE" "$LOG_DIR" "$(date +%Y%m%d-%H%M%S)"
        printf '  %s up -d %s\n' "$COMPOSE_CMD" "$APP_SERVICE"
        echo "镜像回滚："
        printf '  docker tag %s %s && %s up -d %s\n' "$PRE_TAG" "$IMAGE" "$COMPOSE_CMD" "$APP_SERVICE"
        echo "构建失败时先看日志："
        printf '  tail -n 100 %s/build-*.log\n' "$LOG_DIR"
        echo "判断网络问题：日志出现 Could not resolve host / Temporary failure in name resolution /"
        echo "Connection timed out / proxy / dial tcp 时，多为外网或镜像源问题；"
        echo "若停在 pip/apt/calibre 下载之外的具体源码行，才是代码问题。"
    fi
}

run_effective() {
    if [ "$DO_TAG" -eq 0 ] && [ "$DO_BUILD" -eq 0 ] && [ "$DO_ROLLBACK_IMAGE" -eq 0 ]; then
        return 0
    fi
    command -v docker >/dev/null 2>&1 || die "未安装 docker" 3
    if [ "$DO_TAG" -eq 1 ]; then
        info "打标签: $IMAGE -> $PRE_TAG"
        docker tag "$IMAGE" "$PRE_TAG"
    fi
    if [ "$DO_BUILD" -eq 1 ]; then
        [ "$EFFECTIVE_MODE" = "bind" ] && die "--build 不适用于 bind mount 模式，请直接重启容器" 2
        mkdir -p "$LOG_DIR"
        local log="$LOG_DIR/build-$(date +%Y%m%d-%H%M%S).log"
        info "打标签: $IMAGE -> $PRE_TAG"
        docker tag "$IMAGE" "$PRE_TAG"
        info "构建: $COMPOSE_CMD build $APP_SERVICE（日志 $log）"
        if ! $COMPOSE_CMD build "$APP_SERVICE" 2>&1 | tee "$log"; then
            printf '构建失败。先查日志: tail -n 100 %s\n' "$log" >&2
            printf '若含 Could not resolve host/Temporary failure/Connection timed out，先排查网络与镜像源；否则看最后一条源码报错。\n' >&2
            exit 6
        fi
        info "启动: $COMPOSE_CMD up -d $APP_SERVICE"
        $COMPOSE_CMD up -d "$APP_SERVICE"
    fi
    if [ "$DO_ROLLBACK_IMAGE" -eq 1 ]; then
        info "镜像回滚: $PRE_TAG -> $IMAGE"
        docker tag "$PRE_TAG" "$IMAGE"
        $COMPOSE_CMD up -d "$APP_SERVICE"
    fi
}

# ---------- 覆盖包内容 ----------
ENTRIES="$OVERLAY_DIR/MANIFEST.tsv"
count_entries() { grep -vc '^#' "$ENTRIES" || true; }
if [ "$LIST_ONLY" -eq 1 ]; then
    printf '覆盖包: %s\n条目: %s\n\n' "$OVERLAY_DIR" "$(count_entries)"
    grep -v '^#' "$ENTRIES" | while IFS='|' read -r act rel mode base new; do
        printf '%-6s %-8s %s\n' "$act" "$mode" "$rel"
    done
    exit 0
fi

if [ "$APPLY" -eq 1 ] || [ "$DO_BUILD" -eq 1 ]; then
    command -v sha256sum >/dev/null 2>&1 || die "缺少 sha256sum" 3
    if ( cd "$OVERLAY_DIR" && sha256sum -c SHA256SUMS >/dev/null 2>&1 ); then
        info "覆盖包 SHA256 校验通过"
    else
        ( cd "$OVERLAY_DIR" && sha256sum -c SHA256SUMS ) || true
        die "覆盖包校验失败，文件可能损坏" 5
    fi
fi

file_sha() { [ -f "$1" ] && sha256sum "$1" | awk '{print $1}' || echo "-"; }

# ---------- 回滚 ----------
rollback() {
    local ts="$1"
    if [ "$ts" = "__latest__" ]; then
        ts="$(basename "$(ls -1d "$ROLLBACK_ROOT"/[0-9]* 2>/dev/null | sort | tail -n 1)")"
    fi
    [ -n "$ts" ] || die "没有可用的回滚记录（$ROLLBACK_ROOT）" 3
    local dir="$ROLLBACK_ROOT/$ts"
    [ -d "$dir" ] || die "回滚目录不存在: $dir" 3
    [ -f "$dir/ROLLBACK.tsv" ] || die "回滚清单缺失: $dir/ROLLBACK.tsv" 3
    local n_restore=0 n_remove=0
    while IFS='|' read -r act rel; do
        [ -n "$rel" ] || continue
        case "$act" in
            M)
                cp -a "$dir/files/$rel" "$TARGET_DIR/$rel" || die "恢复失败: $rel" 4
                n_restore=$((n_restore + 1)) ;;
            A)
                rm -f "$TARGET_DIR/$rel"
                n_remove=$((n_remove + 1)) ;;
        esac
    done < "$dir/ROLLBACK.tsv"
    info "已回滚 $ts：恢复 $n_restore 个文件，删除 $n_remove 个新增文件"
    echo "注意：回滚只还原源码，不还原镜像。若已重建镜像，执行下面命令回到旧镜像："
    printf '  docker tag %s %s && %s up -d %s\n' "$PRE_TAG" "$IMAGE" "$COMPOSE_CMD" "$APP_SERVICE"
}

if [ -n "$ROLLBACK_TS" ]; then
    rollback "$ROLLBACK_TS"
    exit 0
fi

# 只做镜像操作（不覆盖文件）
if [ "$APPLY" -eq 0 ] && { [ "$DO_TAG" -eq 1 ] || [ "$DO_BUILD" -eq 1 ] || [ "$DO_ROLLBACK_IMAGE" -eq 1 ]; }; then
    print_effective
    run_effective
    exit 0
fi

# ---------- 应用 ----------
TS="$(date +%Y%m%d-%H%M%S)"
TS_DIR="$ROLLBACK_ROOT/$TS"
[ "$APPLY" -eq 1 ] && mkdir -p "$TS_DIR/files"
[ "$APPLY" -eq 1 ] && : > "$TS_DIR/ROLLBACK.tsv"

CONFLICT_FILE="$(mktemp "${TMPDIR:-/tmp}/overlay-conflict.XXXXXX")"
trap 'rm -f "$CONFLICT_FILE"' EXIT
n_update=0; n_add=0; n_skip=0; n_same=0

while IFS='|' read -r act rel mode base new; do
    case "$act" in ''|'#'*) continue ;; esac
    src="$OVERLAY_DIR/files/$rel"
    dst="$TARGET_DIR/$rel"
    [ -f "$src" ] || { printf 'missing|%s|覆盖包缺文件（请重新解压）\n' "$rel" >> "$CONFLICT_FILE"; n_skip=$((n_skip + 1)); continue; }

    if [ "$act" = "add" ]; then
        if [ -e "$dst" ]; then
            if [ "$(file_sha "$dst")" = "$new" ]; then
                # 已存在且内容与本包一致（例如先手工拷过 scripts/backup.sh），视为已完成
                n_same=$((n_same + 1))
                info "已存在且内容一致，无需处理: $rel"
                continue
            fi
            if [ "$FORCE" -ne 1 ]; then
                printf 'add|%s|新增文件已存在\n' "$rel" >> "$CONFLICT_FILE"
                n_skip=$((n_skip + 1)); continue
            fi
            info "强制覆盖已存在的新增文件: $rel"
            if [ "$APPLY" -eq 1 ]; then
                mkdir -p "$TS_DIR/files/$(dirname "$rel")"
                cp -a "$dst" "$TS_DIR/files/$rel" || die "备份失败: $rel" 4
                cp -a "$src" "$dst"; chmod "$mode" "$dst"
                printf 'M|%s\n' "$rel" >> "$TS_DIR/ROLLBACK.tsv"
            fi
            n_update=$((n_update + 1))
            continue
        fi
        n_add=$((n_add + 1))
        if [ "$APPLY" -eq 1 ]; then
            mkdir -p "$(dirname "$dst")"
            cp -a "$src" "$dst"; chmod "$mode" "$dst"
            printf 'A|%s\n' "$rel" >> "$TS_DIR/ROLLBACK.tsv"
        fi
        continue
    fi

    # update
    if [ ! -f "$dst" ]; then
        if [ "$FORCE" -ne 1 ]; then
            printf 'update|%s|目标文件不存在\n' "$rel" >> "$CONFLICT_FILE"
            n_skip=$((n_skip + 1)); continue
        fi
        info "强制新增原缺失文件: $rel"
        [ "$APPLY" -eq 1 ] && { mkdir -p "$(dirname "$dst")"; cp -a "$src" "$dst"; chmod "$mode" "$dst"; printf 'A|%s\n' "$rel" >> "$TS_DIR/ROLLBACK.tsv"; }
        n_add=$((n_add + 1)); continue
    fi
    cur="$(file_sha "$dst")"
    if [ "$cur" != "$base" ] && [ "$FORCE" -ne 1 ]; then
        printf 'update|%s|基线 sha256 不一致（当前 %s，期望 %s）\n' "$rel" "${cur:0:12}" "${base:0:12}" >> "$CONFLICT_FILE"
        n_skip=$((n_skip + 1)); continue
    fi
    if [ "$APPLY" -eq 1 ]; then
        mkdir -p "$TS_DIR/files/$(dirname "$rel")"
        cp -a "$dst" "$TS_DIR/files/$rel" || die "备份失败: $rel" 4
        cp -a "$src" "$dst"; chmod "$mode" "$dst"
        printf 'M|%s\n' "$rel" >> "$TS_DIR/ROLLBACK.tsv"
    fi
    n_update=$((n_update + 1))
done < "$ENTRIES"

printf '\n计划结果: 覆盖 %d，新增 %d，已最新 %d，跳过 %d\n' "$n_update" "$n_add" "$n_same" "$n_skip"
if [ -s "$CONFLICT_FILE" ]; then
    echo "以下文件未处理（目标与基线不一致或已存在）："
    while IFS='|' read -r kind rel why; do
        printf '  - %s（%s：%s）\n' "$rel" "$kind" "$why"
    done < "$CONFLICT_FILE"
fi

if [ "$APPLY" -eq 0 ]; then
    echo
    echo "这是 dry-run，未修改任何文件。确认无误后执行："
    printf '  /bin/bash %s --apply\n' "$SCRIPT_DIR/$(basename "$0")"
    print_effective
    [ -s "$CONFLICT_FILE" ] && exit 4
    exit 0
fi

if [ ! -s "$CONFLICT_FILE" ]; then
    echo "已应用。源码备份: $TS_DIR"
else
    echo "已应用不冲突的文件；跳过项见上。"
    echo "如需强制覆盖：--apply --force"
    echo "回滚：/bin/bash $SCRIPT_DIR/$(basename "$0") --rollback=$TS"
fi
print_effective
run_effective
[ -s "$CONFLICT_FILE" ] && exit 4
exit 0
