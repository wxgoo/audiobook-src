#!/bin/bash
set -euo pipefail

# =============================================================================
# install.sh —— audiobook-ops 发布包引导脚本
#
# 做的事：
#   1) 校验包内文件齐全、SHA256SUMS 校验通过
#   2) 统一修正权限（脚本 0755、文档/配置 0644、目录 0755）
#   3) 打印后续执行顺序与把 scripts/ 拷到 APP_ROOT/scripts/ 的命令
#
# 不做的事：不改 crontab、不重启容器、不改 docker-compose、不写系统配置。
# 只读探测路径，所有改动都发生在本发布包目录内。
#
# 退出码：0 成功 / 2 用法错误 / 3 校验失败 / 4 权限或写入失败
# =============================================================================

BASE_DIR="${BASE_DIR:-/volume1/docker}"
TARGET_DIR="${TARGET_DIR:-$BASE_DIR/audiobook-ops}"
DO_COPY=0

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    cat <<'EOF'
用法: install.sh [选项]

默认在当前目录校验完整性、修正权限并打印执行顺序，不做任何系统配置。

选项:
  --copy        若当前目录不是 /volume1/docker/audiobook-ops，
                则创建目标目录并把本包内容复制过去（其他位置保持只读）
  --base DIR    安装根目录（默认 /volume1/docker）
  --target DIR  目标目录（默认 <base>/audiobook-ops）
  -h, --help    显示帮助

退出码: 0 成功 / 2 用法错误 / 3 校验失败 / 4 权限或写入失败
EOF
}

die() { printf '错误: %s\n' "$1" >&2; exit "${2:-3}"; }
info() { printf '[install] %s\n' "$*"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --copy)        DO_COPY=1; shift ;;
        --base)        BASE_DIR="${2:?缺少参数}"; shift 2 ;;
        --target)      TARGET_DIR="${2:?缺少参数}"; shift 2 ;;
        -h|--help)     usage; exit 0 ;;
        *) echo "未知参数: $1" >&2; usage; exit 2 ;;
    esac
done

REQUIRED="VERSION SHA256SUMS install.sh nas/00-check-env.sh nas/05-detect-paths.sh \
nas/10-backup-db.sh nas/20-backup-full.sh nas/30-verify-backup.sh \
nas/40-restore-drill.sh nas/50-apply-patches.sh nas/60-apply-overlay.sh \
nas/70-check-image.sh nas/90-cron-setup.sh \
nas/paths.conf nas/README-NAS.md scripts/backup.sh scripts/backup_run.py \
overlay/MANIFEST.tsv overlay/SHA256SUMS"

verify_pkg() {
    local dir="$1" missing=""
    for f in $REQUIRED; do
        [ -f "$dir/$f" ] || missing="$missing $f"
    done
    [ -d "$dir/patches" ] || missing="$missing patches/"
    [ -d "$dir/docs" ] || missing="$missing docs/"
    [ -d "$dir/overlay/files" ] || missing="$missing overlay/files/"
    if [ -n "$missing" ]; then
        die "包内缺少文件:$missing（请重新完整解压 tar.gz）" 3
    fi
    command -v sha256sum >/dev/null 2>&1 || die "系统缺少 sha256sum，无法校验完整性" 3
    if ( cd "$dir" && sha256sum -c SHA256SUMS >/dev/null 2>&1 ); then
        info "SHA256SUMS 校验通过（$(wc -l < "$dir/SHA256SUMS" | tr -d ' ') 个文件）"
    else
        ( cd "$dir" && sha256sum -c SHA256SUMS ) || true
        die "SHA256SUMS 校验失败，包可能损坏或被修改" 3
    fi
}

fix_modes() {
    local dir="$1"
    find "$dir" -type d -exec chmod 755 {} + 2>/dev/null || die "设置目录权限失败: $dir" 4
    find "$dir" -type f -name '*.sh' -exec chmod 755 {} + 2>/dev/null || die "设置脚本权限失败" 4
    find "$dir" -type f -name '*.py' -exec chmod 755 {} + 2>/dev/null || die "设置脚本权限失败" 4
    find "$dir" -type f ! -name '*.sh' ! -name '*.py' -exec chmod 644 {} + 2>/dev/null || die "设置文件权限失败" 4
    info "权限已统一：脚本 0755，其余 0644"
}

print_next() {
    local dir="$1" app_root=""
    if [ -f "$dir/nas/paths.conf" ]; then
        app_root="$( . "$dir/nas/paths.conf" 2>/dev/null; printf '%s' "${APP_ROOT:-}" )"
    fi
    [ -n "$app_root" ] || app_root="/volume1/docker/audiobook"

    cat <<EOF

==== 接下来按顺序执行（每步都可先看 --help） ====
cd $dir
/bin/bash nas/00-check-env.sh
/bin/bash nas/05-detect-paths.sh    # 路径不确定时先跑，按输出修订 nas/paths.conf
/bin/bash nas/10-backup-db.sh --dry-run
/bin/bash nas/10-backup-db.sh
/bin/bash nas/20-backup-full.sh
/bin/bash nas/30-verify-backup.sh
/bin/bash nas/40-restore-drill.sh
# 源码不是 git 仓库：覆盖包 dry-run，确认后 --apply
/bin/bash nas/60-apply-overlay.sh --list
/bin/bash nas/60-apply-overlay.sh
/bin/bash nas/60-apply-overlay.sh --apply
# 源码是打进镜像的：打标签 -> 构建 -> 启动（--build 才会真正执行）
/bin/bash nas/60-apply-overlay.sh --tag-only
/bin/bash nas/60-apply-overlay.sh --build
# 构建重启后确认镜像里确实是新代码（只读）
/bin/bash nas/70-check-image.sh

完整说明见 nas/README-NAS.md 的「零、快速开始」，全部用 /bin/bash，不要用 sh。

==== scripts/ 与覆盖包的关系 ====
overlay/ 里的文件已包含 scripts/backup.sh 与 backup_run.py；
执行 60 --apply 后会写入 $app_root/scripts/，无需再手工复制。
若只想先恢复备份功能、不应用全部优化，也可手工：
mkdir -p $app_root/scripts
cp -a scripts/backup.sh scripts/backup_run.py $app_root/scripts/
chmod 755 $app_root/scripts/backup.sh $app_root/scripts/backup_run.py

==== 定时任务（默认只打印，不写系统） ====
/bin/bash nas/90-cron-setup.sh --dsm

以上命令均需 /bin/bash，不要用 sh；DSM 需先在「控制面板 → 终端机和 SNMP」开启 SSH。
EOF
}

if [ "$SELF_DIR" = "$TARGET_DIR" ] || { [ ! -d "$TARGET_DIR" ] && [ "$DO_COPY" -eq 0 ]; }; then
    verify_pkg "$SELF_DIR"
    fix_modes "$SELF_DIR"
    print_next "$SELF_DIR"
    exit 0
fi

if [ "$DO_COPY" -eq 1 ]; then
    if [ "$SELF_DIR" = "$TARGET_DIR" ]; then
        info "当前已在目标目录，无需复制"
        verify_pkg "$SELF_DIR"
        fix_modes "$SELF_DIR"
        print_next "$SELF_DIR"
        exit 0
    fi
    command -v cp >/dev/null 2>&1 || die "系统缺少 cp" 3
    mkdir -p "$TARGET_DIR" || die "无法创建 $TARGET_DIR（需要 root 或目录权限）" 4
    [ -w "$TARGET_DIR" ] || die "$TARGET_DIR 不可写" 4
    info "复制到 $TARGET_DIR ..."
    cp -a "$SELF_DIR"/. "$TARGET_DIR"/ || die "复制失败" 4
    verify_pkg "$TARGET_DIR"
    fix_modes "$TARGET_DIR"
    print_next "$TARGET_DIR"
    exit 0
fi

verify_pkg "$SELF_DIR"
fix_modes "$SELF_DIR"
info "当前目录不是推荐位置 $TARGET_DIR。"
info "可手动移动，或执行: /bin/bash install.sh --copy"
print_next "$SELF_DIR"
