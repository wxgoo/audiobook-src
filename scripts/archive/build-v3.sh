#!/bin/bash
# 【已归档 · 一次性脚本】
# 出 4.6.0-9 v3 包的组装脚本，以 NAS 上 248M 的 4.6.0-8 全量包为基准。v9 最终就是它出的。
# 不随版本更新，不要在这些文件上打补丁；需要类似能力请新写一个放 scripts/ 根。
# 下面保留原始内容：
# ============================================================================
# build-v3.sh —— 以「NAS 上的 4.6.0-8 全量包（248MB）」为唯一基准，组装 -9 v3
#
#   基准包 BASE（必须是你 NAS 上那个 248M 的 audiobook-deploy-4.6.0-8.tar.gz）：
#     app/node_modules      41232 条  ← 供 npm ci 加速 / 源码可现场构建
#     app/dist                979 条  ← 预构建 SPA（含 _bookid.vue 编译产物）
#     app/.nuxt               255 条
#     app/public/static       625 条  ← epubreader/pdfjs/djvureader/epub_to_audio/mimo_tts
#     app/src                 180 条  ← 含 pages/book/_bookid.vue（3655 行详情页）
#     myreader-dist          3398 条
#     webserver/resources/book/epubjs.html   ← 「纯本地 epub reader」必需
#
#   与 v2 的差别（v2 为什么还空白）：
#     v2 的基准是工作区里那个 94M 残缺包，app/src 里根本没有 pages/book/，
#     所以「现场 build-spa」或「塞进去的 dist」都是错的。v3 直接继承 248M 包
#     的原生 dist 与原生源码，再用 -9 的补丁文件覆盖，并做硬校验。
#
# 用法：
#   ./build-v3.sh --base /path/to/audiobook-deploy-4.6.0-8-full.tar.gz \
#                 --src  /root/work/audiobook-src \
#                 --out  /workspace/audiobook-deploy-4.6.0-9-v3.tar.gz
#   ./build-v3.sh ... --dry-run      # 只做校验与统计，不出包
# ============================================================================
set -euo pipefail

BASE=""
SRC=""
OUT=""
DRY=0
MYREADER_TGZ=""

while [ $# -gt 0 ]; do
    case "$1" in
        --base)      BASE="$2"; shift 2 ;;
        --src)       SRC="$2";  shift 2 ;;
        --out)       OUT="$2";  shift 2 ;;
        --myreader)  MYREADER_TGZ="$2"; shift 2 ;;
        --dry-run)   DRY=1; shift ;;
        -h|--help)   sed -n '2,30p' "$0"; exit 0 ;;
        *) echo "未知参数: $1"; exit 2 ;;
    esac
done

[ -n "$BASE" ] && [ -n "$SRC" ] && [ -n "$OUT" ] || { echo "缺参数：--base / --src / --out"; exit 2; }
[ -f "$BASE" ] || { echo "基准包不存在: $BASE"; exit 1; }
[ -d "$SRC/.git" ] || { echo "源码目录不是 git 仓库: $SRC"; exit 1; }

STAMP=$(date +%Y%m%d-%H%M%S)
WORK="/root/work/build-v3-$STAMP"
TREE="$WORK/audiobook"
mkdir -p "$TREE"

say() { echo; echo "========== $* =========="; }
ok()  { echo "  ✔ $*"; }
bad() { echo "  ✘ $*"; exit 1; }

# ---------------------------------------------------------------------------
say "[1] 校验基准包（必须是全量包）"
echo "  文件: $BASE  ($(du -h "$BASE" | cut -f1))"
gzip -t "$BASE" || bad "gzip 校验失败，包不完整"
BCOUNT=$(tar -tzf "$BASE" | wc -l)
echo "  条目: $BCOUNT"
[ "$BCOUNT" -gt 40000 ] || bad "条目只有 $BCOUNT，这不是全量包（全量应 > 47000）"
tar -tzf "$BASE" > "$WORK/base.list"
for p in \
    audiobook/app/dist/index.html \
    audiobook/app/dist/200.html \
    audiobook/app/src/pages/book/_bookid.vue \
    audiobook/app/src/pages/book/_bid/edit.vue \
    audiobook/webserver/resources/book/epubjs.html \
    audiobook/app/public/static/epubreader/js/epubreader.min-v0.3.5.js \
    audiobook/myreader-dist/app/server.js \
    audiobook/Dockerfile \
    audiobook/docker-compose.yml
do
    grep -qxF "$p" "$WORK/base.list" || bad "基准包缺关键文件: $p"
done
ok "关键文件齐全"

for pair in "app/node_modules:30000" "app/dist:900" "app/.nuxt:200" \
            "app/public/static:400" "app/src:150" "myreader-dist:3000"
do
    d="${pair%%:*}"; n="${pair##*:}"
    c=$(grep -c "^audiobook/$d/" "$WORK/base.list" || true)
    echo "  $d = $c 条（下限 $n）"
    [ "$c" -ge "$n" ] || bad "$d 条目不足"
done

# dist 里必须有详情页特征字符串（kindle_sender 只在 book/_bookid.vue 出现）
say "[2] 解包基准"
tar -xzf "$BASE" --strip-components=1 -C "$TREE"
ok "已解到 $TREE"
HB=$(grep -l "kindle_sender" "$TREE"/app/dist/_nuxt/*.js 2>/dev/null | head -1 || true)
[ -n "$HB" ] || bad "app/dist 里找不到含 kindle_sender 的 chunk —— 这个 dist 不是详情页版本"
ok "dist 详情页 chunk: $(basename "$HB")"

# ---------------------------------------------------------------------------
say "[3] 注入 -9 补丁（按白名单，避免覆盖基准包里的产物）"
PATCH_LIST="$SRC/build/patch-files-v3.txt"
[ -f "$PATCH_LIST" ] || bad "缺补丁清单: $PATCH_LIST"

n_patch=0
while IFS= read -r rel; do
    case "$rel" in ""|\#*) continue ;; esac
    s="$SRC/$rel"
    [ -f "$s" ] || { echo "  ! 源码无此文件，跳过: $rel"; continue; }
    d="$TREE/$rel"
    mkdir -p "$(dirname "$d")"
    cp -a "$s" "$d"
    n_patch=$((n_patch + 1))
    echo "  + $rel"
done < "$PATCH_LIST"
ok "补丁文件 $n_patch 个"

# myreader-dist：基准包自带就用基准包的；外部给了新包则替换
if [ -n "$MYREADER_TGZ" ]; then
    [ -f "$MYREADER_TGZ" ] || bad "myreader tan 包不存在: $MYREADER_TGZ"
    rm -rf "$TREE/myreader-dist"
    mkdir -p "$TREE/myreader-dist"
    tar -xzf "$MYREADER_TGZ" -C "$TREE/myreader-dist" --strip-components=1
    ok "myreader-dist 已用外部包替换"
    else
        ok "myreader-dist 沿用基准包（$(find "$TREE/myreader-dist" \( -type f -o -type l \) | wc -l) 条）"
fi

# ---------------------------------------------------------------------------
say "[3.5] 替换预构建 dist（源码树的新 dist 优先于基准包的旧 dist）"
# 为什么必须替换：-9 改了前端（作者归一化菜单/页面、书籍列表锁图标），
# 基准包的 dist 编译于这些改动之前。沿用旧 dist 会导致"源码里全都在、
# 界面上什么都看不见"。dist 必须和 src 同源编译。
if [ -f "$SRC/app/dist/index.html" ] && [ -f "$SRC/app/dist/200.html" ] \
   && [ -d "$SRC/app/dist/_nuxt" ]; then
    # 校验新 dist 的两个硬指标
    grep -rq "kindle_sender" "$SRC"/app/dist/_nuxt/*.js \
        || bad "源码树 dist 缺详情页 chunk（kindle_sender）—— 先跑 npm run build-spa"
    grep -rq "author_norm" "$SRC"/app/dist/_nuxt/*.js \
        || bad "源码树 dist 缺归一化 chunk（author_norm）—— AppHeader 菜单没编进去？"
    rm -rf "$TREE/app/dist"
    cp -a "$SRC/app/dist" "$TREE/app/dist"
    N_DIST=$(find "$TREE/app/dist" -type f | wc -l)
    ok "dist 已替换为源码树版本（$N_DIST 个文件）"
else
    echo "  ! 源码树没有 dist，沿用基准包的旧 dist（归一化菜单将不可见！）"
fi

# ---------------------------------------------------------------------------
say "[4] 硬校验（任何一项不过就中止）"
CHK=0
chk_file() { [ -f "$1" ] && { echo "  ✔ ${1#$TREE/}"; CHK=$((CHK+1)); } || bad "缺文件: $1"; }
chk_file "$TREE/app/dist/index.html"
chk_file "$TREE/app/dist/200.html"
chk_file "$TREE/app/src/pages/book/_bookid.vue"
chk_file "$TREE/webserver/resources/book/epubjs.html"
chk_file "$TREE/app/public/static/epubreader/index.html"
chk_file "$TREE/app/public/static/epubreader/js/epubreader.min-v0.3.5.js"
chk_file "$TREE/app/public/static/pdfjs/web/viewer.html"
chk_file "$TREE/myreader-dist/app/server.js"
chk_file "$TREE/rollback-to-8.sh"

# 详情页 chunk 必须还在（补丁不碰 dist，但防止误操作）
[ -n "$(grep -l "kindle_sender" "$TREE"/app/dist/_nuxt/*.js 2>/dev/null || true)" ] \
    && echo "  ✔ dist 内含详情页 chunk" || bad "dist 详情页 chunk 丢失"

# -9 的两处功能补丁必须在（前端作者归一 / 后端作者归一）
grep -q "author_norm" "$TREE/app/src/pages/toolbox/author_norm.vue" 2>/dev/null \
    && echo "  ✔ author_norm.vue (-9)" || bad "author_norm.vue 未注入"
[ -f "$TREE/webserver/handlers/author_norm.py" ] \
    && echo "  ✔ author_norm.py (-9)" || echo "  ! author_norm.py 不在基准包里（若 -9 需要，请加入补丁清单）"

# node_modules 不能混进 DEST（历史上导致镜像 3G）
if [ -d "$TREE/app/node_modules" ]; then
    echo "  ✔ app/node_modules 保留（$(find "$TREE/app/node_modules" -maxdepth 1 -type d | wc -l) 个顶层包）"
fi

# 权限归一：基准包内全是 600/glyzx:users，NAS 上容器非 root 会读不到
say "[5] 权限归一"
chown -R root:root "$TREE"
chmod -R u+rwX,go+rX "$TREE"
find "$TREE" -name "*.sh" -exec chmod +x {} \;
ok "$(stat -c '%a %U' "$TREE/app/dist/index.html")  $TREE/app/dist/index.html"

# 属主写回 glyzx/users（与 -8 全量包一致）。为什么不是 root：
# 用户在 NAS 上 `tar -xzf` 时若是普通用户 glyzx（uid 1026），包里属主为 root
# 的话解出来全是 root 所有，后续 rsync/chown/synology 套件都会报权限错。
# 容器内不需要 root 属主 —— Dockerfile 里有 chown mybooks:mybooks。
tar --owner=glyzx --group=users -cf "$WORK/pack.tar" -C "$WORK" audiobook
ok "包内属主已写回 glyzx:users"

# ---------------------------------------------------------------------------
say "[6] 输出"
if [ "$DRY" = "1" ]; then
    echo "  --dry-run：不出包。组装树在 $TREE"
    du -sh "$TREE"
    exit 0
fi

mkdir -p "$(dirname "$OUT")"
gzip -c "$WORK/pack.tar" > "$OUT"
echo "  包: $OUT  ($(du -h "$OUT" | cut -f1))"
echo "  md5: $(md5sum "$OUT" | cut -d' ' -f1)"

say "[7] 成品包终检（从 tar 直接读，不信任源树）"
tar -tzf "$OUT" > "$WORK/out.list"
OC=$(wc -l < "$WORK/out.list")
[ "$OC" -ge 47000 ] || bad "成品包条目只有 $OC"
for p in \
    audiobook/app/dist/index.html \
    audiobook/app/src/pages/book/_bookid.vue \
    audiobook/webserver/resources/book/epubjs.html \
    audiobook/app/public/static/epubreader/index.html \
    audiobook/myreader-dist/app/server.js \
    audiobook/rollback-to-8.sh
do
    grep -qxF "$p" "$WORK/out.list" || bad "成品包缺: $p"
done
grep -q "^audiobook/app/node_modules/next/" "$WORK/out.list" && ok "app/node_modules 在包内"
echo "  成品包条目: $OC"
echo
echo "组装树保留在: $TREE"
