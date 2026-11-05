#!/bin/bash
# 交付包冒烟测试。打包之后、发出去之前必须跑这一遍。
#
# 为什么需要它：
#   r11 那次 `/admin/users` 500 的事故里，以下三项全是绿的——
#     · nuxt generate 退出码 0
#     · 构建日志无 warning
#     · 链接探测 219 项全通（它只查文件在不在）
#   页面却是坏的。所以「构建成功」和「文件存在」都不能当验收标准，
#   必须是「解出真实产物、用 Chromium 点开关键页面、断言 DOM 里该有的东西」。
#
# 用法：
#   sh scripts/smoke.sh /workspace/audiobook-deploy-4.6.0-19-r11.tar.gz
#   sh scripts/smoke.sh <包> --keep       # 保留解包目录便于排查
#
# 退出码：0 全过；非 0 表示有探针失败，**不许发布**。
set -u

PKG="${1:-}"
KEEP=0
[ "${2:-}" = "--keep" ] && KEEP=1

if [ -z "$PKG" ] || [ ! -f "$PKG" ]; then
    echo "用法: sh $0 <交付包.tar.gz> [--keep]"
    exit 2
fi

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PROBE_DIR="$SCRIPT_DIR/smoke"
WORK=$(mktemp -d /tmp/smoke.XXXXXX)

echo "=============================================================="
echo "交付包冒烟测试"
echo "  包:   $PKG"
echo "  大小: $(du -h "$PKG" | cut -f1)"
echo "  md5:  $(md5sum "$PKG" | cut -d' ' -f1)"
echo "  工作区: $WORK"
echo "=============================================================="
echo

FAILED=""
PASSED=""

run_probe() {
    local name="$1"; shift
    local script="$PROBE_DIR/$1"; shift
    echo "--------------------------------------------------------------"
    echo "[$name]"
    echo "--------------------------------------------------------------"
    if [ ! -f "$script" ]; then
        echo "  跳过：找不到 $script"
        return 0
    fi
    if python3 "$script" "$DIST" "$@"; then
        PASSED="$PASSED $name"
        echo "  >>> $name 通过"
    else
        FAILED="$FAILED $name"
        echo "  >>> $name 失败"
    fi
    echo
}

# ---- 1. 解包 ----
echo "[1/4] 解包"
tar -xzf "$PKG" -C "$WORK" 2>/dev/null
DIST="$WORK/audiobook/app/dist"
if [ ! -d "$DIST" ]; then
    echo "  ✗ 包里没有 app/dist：$DIST"
    exit 1
fi
echo "  ✓ app/dist 存在 ($(find "$DIST" -type f | wc -l) 个文件)"

# ---- 2. dist 形态：必须是 SPA 外壳 ----
echo
echo "[2/4] dist 形态检查（防 r11 的 --spa 事故）"
SHAPE_OK=1
for page in index.html admin/users/index.html; do
    f="$DIST/$page"
    if [ ! -f "$f" ]; then
        echo "  ✗ 缺少 $page"
        SHAPE_OK=0
        continue
    fi
    sz=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f")
    if grep -q "data-server-rendered" "$f" 2>/dev/null; then
        echo "  ✗ $page 含 data-server-rendered（预渲染 DOM，会 hydrate 失败）"
        SHAPE_OK=0
    elif [ "$sz" -gt 20000 ]; then
        echo "  ✗ $page 体积 ${sz}B 偏大，疑似预渲染"
        SHAPE_OK=0
    else
        echo "  ✓ $page ${sz}B SPA 外壳"
    fi
done
if [ "$SHAPE_OK" -ne 1 ]; then
    FAILED="$FAILED dist形态"
fi

# ---- 3. 后端关键代码在位 ----
echo
echo "[3/4] 后端关键修复在位检查"
BK="$WORK/audiobook"
check_code() {
    local desc="$1" file="$2" pat="$3"
    if grep -q "$pat" "$BK/$file" 2>/dev/null; then
        echo "  ✓ $desc"
    else
        echo "  ✗ $desc（$file 里找不到 $pat）"
        FAILED="$FAILED $desc"
    fi
}
check_code "迁移不看版本号（r11 事故修复）" "webserver/main.py" "should_check_db_structure"
check_code "迁移逐步提交" "webserver/services/async_service.py" "_step_reader_table"
check_code "分类下拉 JOIN 书籍（r12 修复）" "webserver/handlers/reader_group.py" "books_custom_column_%d_link"
check_code "出生年份补列" "webserver/services/async_service.py" "ADD COLUMN birth_year"

# ---- 4. 浏览器探针 ----
echo
echo "[4/4] 浏览器交互探针"
run_probe "管理员页/出生年份" "probe_admin_birthyear.py"
run_probe "补填入口可点性" "probe_dash_click.py"
run_probe "注册页/年份校验" "probe_signup_r11.py"
run_probe "链接完整性" "probe_links.py"

# ---- 汇总 ----
echo "=============================================================="
echo "结果汇总"
echo "  通过:${PASSED:- 无}"
if [ -n "$FAILED" ]; then
    echo "  失败:$FAILED"
    echo
    echo "  ✗ 有失败项，不许发布。"
    echo "  排查用：sh $0 $PKG --keep   （保留解包目录）"
    echo "=============================================================="
    if [ "$KEEP" -ne 1 ]; then rm -rf "$WORK"; fi
    exit 1
fi
echo "  失败: 无"
echo
echo "  ✓ 全部通过"
echo "=============================================================="
if [ "$KEEP" -ne 1 ]; then rm -rf "$WORK"; fi
exit 0
