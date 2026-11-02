#!/bin/sh
# 【已归档 · 一次性脚本】
# 从 -9 部署包反推出 -8 基准包，供 merge-4.6.0-9.sh 使用。两者同批，已一起归档。
# 不随版本更新，不要在这些文件上打补丁；需要类似能力请新写一个放 scripts/ 根。
# 下面保留原始内容：
# ============================================================
# make-base-4.6.0-8.sh —— 从 -9 部署包反推出 -8 基准包
#
# 为什么需要：
#   merge-4.6.0-9.sh 必须有一个「-8 基准包」才能合成。
#   换 NAS / 换机器时，很多人手上只有 -9 成品包，没有 -8 基准包，
#   于是无法重新合成。本脚本把这件事补上。
#
# 原理：
#   -9 部署包 = -8 基准包 + 23 个补丁文件（覆盖）
#   所以反向操作即可：
#     · 4 个「新增」文件 → 直接从包里删掉
#     · 19 个「修改」文件 → 换成补丁前的旧版（由 git 提供）
#
# 用法：
#   sh make-base-4.6.0-8.sh
#   sh make-base-4.6.0-8.sh /path/to/audiobook-deploy-4.6.0-9.tar.gz
#
# 产出：
#   audiobook-deploy-4.6.0-8.tar.gz（与 -9 同目录）
#
# 注意：本脚本需要 git 仓库（提供旧版文件）。仓库默认找 /root/work/audiobook-src，
#       也可用 SRC= 指定。
# ============================================================
set -e

SELF_DIR=$(cd "$(dirname "$0")" 2>/dev/null && pwd || echo ".")
IN="${1:-$SELF_DIR/audiobook-deploy-4.6.0-9.tar.gz}"
OUT="${OUT:-$SELF_DIR/audiobook-deploy-4.6.0-8.tar.gz}"
SRC="${SRC:-/root/work/audiobook-src}"

[ -f "$IN" ] || { echo "!! 找不到 -9 部署包: $IN"; exit 1; }
[ -d "$SRC/.git" ] || { echo "!! 找不到 git 仓库: $SRC（用 SRC= 指定）"; exit 1; }

# 补丁前的提交：HEAD~1 是「还没打 4.6.0-9 补丁」的状态
PREV=$(git -C "$SRC" rev-parse HEAD~1 2>/dev/null) || {
    echo "!! $SRC 里取不到 HEAD~1"; exit 1; }

echo "==> 源包: $IN"
echo "==> 旧版来源: $SRC @ $PREV"
echo "==> 输出: $OUT"

WORK=/tmp/mkbase-8
rm -rf "$WORK" && mkdir -p "$WORK"
tar -xzf "$IN" -C "$WORK" || { echo "!! 解压失败"; exit 1; }
D="$WORK/audiobook"
[ -d "$D" ] || { echo "!! 包里没有 audiobook/ 顶层目录"; exit 1; }

# ---------- 1) 删除 4.6.0-9 新增的文件 ----------
echo "==> 移除 4.6.0-9 新增的文件（4 个）"
for f in webserver/base/author_norm.py \
         webserver/handlers/author_norm.py \
         tests/test_author_norm.py \
         app/src/pages/toolbox/author_norm.vue; do
    if [ -f "$D/$f" ]; then
        rm -f "$D/$f"
        echo "    移除 $f"
    fi
done
# 空目录顺手清掉
rmdir "$D/app/src/pages/toolbox" 2>/dev/null || true

# ---------- 2) 还原 19 个被修改的文件 ----------
echo "==> 还原被修改的文件（19 个）"
N=0
for f in webserver/base/meta_helper.py \
         webserver/base/formatter.py \
         webserver/services/autofill.py \
         webserver/services/audios_import.py \
         webserver/services/book_dedup.py \
         webserver/plugins/meta/douban_v2/api.py \
         webserver/plugins/meta/baike/api.py \
         webserver/plugins/meta/youshu/api.py \
         webserver/plugins/meta/xhsd/api.py \
         webserver/plugins/meta/neodb/api.py \
         webserver/plugins/meta/ujxsw/api.py \
         webserver/handlers/book.py \
         webserver/constants.py \
         webserver/main.py \
         app/src/pages/admin/books.vue \
         app/src/components/AppHeader.vue \
         app/locales/zh.json \
         app/locales/zh-TW.json \
         app/locales/en.json; do
    git -C "$SRC" show "$PREV:$f" > "$D/$f" 2>/dev/null || {
        echo "    !! 取旧版失败: $f"; exit 1; }
    N=$((N + 1))
done
echo "    已还原 $N 个文件"

# ---------- 3) 复检：-8 里不应该有 4.6.0-9 的痕迹 ----------
echo "==> 复检（应全部无 4.6.0-9 痕迹）"
BAD=0
chk() {
    if grep -q "$2" "$D/$1" 2>/dev/null; then
        echo "    !! $1 仍有 $2"; BAD=1
    fi
}
chk webserver/base/formatter.py "author_locked"
chk webserver/services/book_dedup.py "authors_conflict"
chk webserver/base/meta_helper.py "_DUTY_PREFIX"
chk webserver/constants.py "CALIBRE_COLUMN_AUTHOR_LOCKED"
chk app/src/pages/admin/books.vue "author_locked"
chk app/src/components/AppHeader.vue "authorNorm"
chk app/locales/zh.json "authorNorm"

[ -f "$D/webserver/base/author_norm.py" ] && { echo "    !! author_norm.py 还在"; BAD=1; }
[ -f "$D/app/src/pages/toolbox/author_norm.vue" ] && { echo "    !! author_norm.vue 还在"; BAD=1; }

[ "$BAD" -ne 0 ] && { echo "!! 反推失败，未出包"; exit 1; }
echo "    ✓ 干净"

# ---------- 4) 清运行时数据（-8 原本也不该有）----------
rm -rf "$D/cache" "$D/sync" "$D/books" "$D/audio" 2>/dev/null || true
find "$D" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find "$D" -name '*.pyc' -delete 2>/dev/null || true

# ---------- 5) 打包 ----------
echo "==> 打包"
rm -rf /tmp/mkbase-out && mkdir -p /tmp/mkbase-out
cp -a "$D" /tmp/mkbase-out/audiobook
( cd /tmp/mkbase-out && tar -czf "$OUT" audiobook )

echo "==> 成品"
ls -lh "$OUT" | awk '{print "    "$9"  "$5}'
echo "    文件数: $(tar -tzf "$OUT" | wc -l)"
echo "    符号链接: $(find /tmp/mkbase-out/audiobook -type l | wc -l)"
echo "    污染条目: $(tar -tzf "$OUT" | grep -cE '^audiobook/(cache|sync|books|audio)/' || echo 0)"

rm -rf "$WORK" /tmp/mkbase-out
echo
echo "✅ 基准包已生成：$OUT"
echo "   现在可以用它重新合成："
echo "   sh merge-4.6.0-9.sh $(basename "$OUT")"
