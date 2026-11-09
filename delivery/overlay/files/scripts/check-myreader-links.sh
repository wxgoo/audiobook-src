#!/bin/sh
# ============================================================
# check-myreader-links.sh —— myreader-dist 符号链接的权威校验 / 重建
#
# 背景：myreader-dist 是 Next.js standalone 产物，三层 node_modules 里
#   的 119 根相对符号链接是运行时的依赖解析路径。Windows 检出/上传/
#   图形界面解压都会把它们压扁成「内容=目标路径文本」的普通文件或
#   空目录，导致：
#     - myreader 启动即 Cannot find module（supervisor FATAL）
#     - 或 Next.js 显示 Ready，但首个 /reader/open 请求就 500
#   按包名推断是猜不出来的：.next 层链接名带哈希
#   （clsx-531b805f92b6415e），且同名包在 .pnpm 里有多个版本
#   （@opentelemetry/api 1.9.0 / 1.9.1）。
#
# 因此以 scripts/myreader-links.manifest 为唯一权威：从完好部署包
# 导出的「相对路径 -> 链接目标」逐根比对，缺什么补什么，不猜。
#
# 用法：
#   sh scripts/check-myreader-links.sh                  # 只读校验（默认）
#   sh scripts/check-myreader-links.sh --fix           # 校验并重建缺失/错误的链接
#   sh scripts/check-myreader-links.sh --fix /var/www/myreader   # 容器内用
#   sh scripts/check-myreader-links.sh --manifest <清单> <根目录>
#
# 退出码：0 = 全部完好（或已修复成功）；1 = 仍有缺失/错误链接；2 = 参数/文件错误
# ============================================================
set -u

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
MANIFEST="$SCRIPT_DIR/myreader-links.manifest"
ROOT=""
MODE=check

# ---- 参数解析 ----
while [ $# -gt 0 ]; do
    case "$1" in
        --fix)      MODE=fix; shift ;;
        --check)    MODE=check; shift ;;
        --manifest) [ $# -ge 2 ] || { echo "!! --manifest 缺参数" >&2; exit 2; }
                    MANIFEST="$2"; shift 2 ;;
        -*)         echo "!! 未知参数: $1" >&2; exit 2 ;;
        *)          ROOT="$1"; shift ;;
    esac
done

[ -f "$MANIFEST" ] || { echo "!! 找不到链接清单: $MANIFEST" >&2; exit 2; }
if [ -z "$ROOT" ]; then
    # 默认：脚本位于 <项目>/scripts/，产物在 <项目>/myreader-dist/
    ROOT="$(dirname "$SCRIPT_DIR")/myreader-dist"
fi
[ -d "$ROOT" ] || { echo "!! 找不到 myreader-dist 目录: $ROOT" >&2; exit 2; }
ROOT=$(cd "$ROOT" && pwd)

echo "==> MyReader 链接校验（清单驱动，不猜版本）"
echo "    清单: $MANIFEST"
echo "    目录: $ROOT"
echo "    模式: $MODE"

total=0; ok=0; wrong=0; missing=0; fixed=0; broken=0

while IFS='	' read -r rel target; do
    case "$rel" in ''|'#'*) continue ;; esac
    [ -n "$target" ] || continue
    total=$((total + 1))
    path="$ROOT/$rel"
    state=ok

    if [ -L "$path" ]; then
        cur=$(readlink "$path" 2>/dev/null || echo "")
        [ "$cur" = "$target" ] || state=wrong
        [ -e "$path" ] || state=broken   # 链接在但目标不存在
    else
        state=missing
    fi

    case "$state" in
        ok)      ok=$((ok + 1)) ;;
        wrong)   wrong=$((wrong + 1)) ;;
        missing) missing=$((missing + 1)) ;;
        broken)  broken=$((broken + 1)) ;;
    esac

    if [ "$state" != "ok" ] && [ "$MODE" = "fix" ]; then
        mkdir -p "$(dirname "$path")" || continue
        rm -rf "$path"
        if ln -s "$target" "$path" && [ -e "$path" ]; then
            fixed=$((fixed + 1))
            echo "    ++ $rel -> $target"
        else
            echo "    !! 重建失败: $rel -> $target" >&2
        fi
    elif [ "$state" != "ok" ]; then
        echo "    ?? [$state] $rel (应为 $target)"
    fi
done < "$MANIFEST"

echo "    清单 $total 根：完好 $ok / 目标不符 $wrong / 缺失 $missing / 断链 $broken"
[ "$MODE" = "fix" ] && echo "    本次重建: $fixed 根"

if [ "$MODE" = "fix" ]; then
    # 修复后再逐根确认目标可解析
    still=0
    while IFS='	' read -r rel target; do
        case "$rel" in ''|'#'*) continue ;; esac
        [ -n "$target" ] || continue
        [ -L "$ROOT/$rel" ] && [ -e "$ROOT/$rel" ] || {
            still=$((still + 1))
            echo "    !! 仍不可用: $rel" >&2
        }
    done < "$MANIFEST"
    if [ "$still" -gt 0 ]; then
        echo "==> 失败：修复后仍有 $still 根不可用（检查 .pnpm 实体是否齐全）"
        exit 1
    fi
    echo "==> OK：全部 $total 根链接校验通过"
    exit 0
fi

if [ "$wrong" -gt 0 ] || [ "$missing" -gt 0 ] || [ "$broken" -gt 0 ]; then
    echo "==> 发现 $((wrong + missing + broken)) 根异常，执行 --fix 可自动重建："
    echo "    sh scripts/check-myreader-links.sh --fix"
    exit 1
fi
echo "==> OK：全部 $total 根链接完好"
exit 0
