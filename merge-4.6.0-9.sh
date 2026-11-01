#!/bin/sh
# ============================================================
# merge-4.6.0-9.sh —— 4.6.0-9：作者归一化 + 防刮削回滚 + 管理界面
#
# **前后端都动了，必须重建镜像**（含 npm run build-spa）；
# 另外新增了 calibre 自定义列 #author_locked，启动时自动建列。
#
# 补丁共 23 个文件：后端 16 + 前端 7
#   新增 4 个：author_norm.py(base/handlers)、test_author_norm.py、
#               app/src/pages/toolbox/author_norm.vue
#   修改 19 个：后端 14 + 前端 5（books.vue / AppHeader.vue / 3 个 locale）
#
# 内容：
#   · S0 作者锁定：人工改过的作者，自动刮削不再覆盖（#author_locked）
#   · S1 清洗增强：职责前缀/后缀、中文逗号分人、西文缩写不拆
#   · S2 别名表：同一作者的不同写法归一到标准名（config.json 可手工编辑）
#   · S3 刮削源补清洗：豆瓣V2 / 百科 / 优书 / 新华 / NeoDB / 续读 6 个源
#   · S4 入库归一：有声书导入 + 上传入库 + 分片上传 + 重置元数据 + 界面刮削
#   · S5 重复书守卫：同名但作者不同 → 跳过合并，不再误合并（book_dedup）
#   · S6 管理页：/toolbox/author_norm（体检 + 别名表编辑 + 归一化预览）
#   · S7 锁图标：管理端书籍列表作者列，点击解锁 / 保存后自动落锁
#
# 用法（NAS 上，包都放 /volume1/docker/）：
#   sh merge-4.6.0-9.sh
#   sh merge-4.6.0-9.sh /volume1/docker/audiobook-deploy-4.6.0-8.tar.gz   # 指定基准包
# ============================================================

SELF_DIR=$(cd "$(dirname "$0")" 2>/dev/null && pwd || echo ".")

find_base() {
    for name in audiobook-deploy-4.6.0-8.tar.gz \
                audiobook-deploy-4.6.0-7.tar.gz \
                audiobook-deploy-4.6.0-6.tar.gz \
                audiobook-deploy-4.6.0-4.tar.gz \
                audiobook-deploy-4.6.0-3.tar.gz \
                audiobook-deploy-4.6.0-2.tar.gz \
                audiobook-deploy-4.6.0-1.tar.gz \
                audiobook-deploy-v4.8.2.tar.gz; do
        for dir in "$SELF_DIR" /volume1/docker .; do
            [ -f "$dir/$name" ] && { echo "$dir/$name"; return 0; }
        done
    done
    return 1
}

if [ -n "$1" ]; then
    BASE="$1"
else
    BASE=$(find_base) || BASE=
fi

find_file() {
    for dir in "$SELF_DIR" /volume1/docker .; do
        [ -f "$dir/$1" ] && { echo "$dir/$1"; return 0; }
    done
    return 1
}

PATCH="${PATCH:-$(find_file audiobook-patch-4.6.0-9.tar.gz)}"
OUT="${OUT:-/volume1/docker/audiobook-deploy-4.6.0-9.tar.gz}"
[ -w "$(dirname "$OUT")" ] 2>/dev/null || OUT="$SELF_DIR/audiobook-deploy-4.6.0-9.tar.gz"
PREFIX=audiobook
PPREFIX=audiobook-patch-4.6.0-9

[ -n "$BASE" ] && [ -f "$BASE" ] || {
    echo "!! 找不到基准包 audiobook-deploy-4.6.0-8.tar.gz"
    echo "   已在这些位置查找：$SELF_DIR  /volume1/docker  当前目录"
    echo "   也可以显式指定：sh merge-4.6.0-9.sh /路径/audiobook-deploy-4.6.0-8.tar.gz"
    exit 1; }
[ -n "$PATCH" ] && [ -f "$PATCH" ] || { echo "!! 找不到补丁包 audiobook-patch-4.6.0-9.tar.gz"; exit 1; }
echo "==> 基准包: $BASE"
echo "==> 补丁包: $PATCH"

rm -rf /tmp/mp9 && mkdir -p /tmp/mp9

echo "==> 解压基准包"
tar -xzf "$BASE" -C /tmp/mp9 || exit 1
D=$(find /tmp/mp9 -maxdepth 1 -type d -name 'audiobook*' | head -1)
[ -z "$D" ] && { echo "!! 基准包里找不到 audiobook* 顶层目录"; exit 1; }
echo "==> 基准包顶层: $D"

echo "==> 注入补丁（相对路径覆盖）"
rm -rf /tmp/mp9-patch && mkdir -p /tmp/mp9-patch
tar -xzf "$PATCH" -C /tmp/mp9-patch || exit 1
cp -R "/tmp/mp9-patch/$PPREFIX/audiobook/." "$D/" || exit 1

# ---- 前置校验：基准包必须是 -8 及以上，否则书库会有两套不一致的刮削逻辑 ----
if ! grep -q "audiobook_preview_" "$D/app/src/components/AudioListDialog.vue" 2>/dev/null; then
    echo "!! 基准包不是 -8 及以上（AudioListDialog.vue 缺进度记忆）"
    echo "   请用 audiobook-deploy-4.6.0-8.tar.gz 作基准"
    exit 1
fi

# ---- 符号链接数（前端 node_modules 链接，缺了 build 会失败）----
n=$(find "$D/myreader-dist" -type l 2>/dev/null | wc -l)
if [ -d "$D/myreader-dist" ]; then
    echo "==> 符号链接: $n（应127）"
    [ "$n" -ne 127 ] && { echo "!! 符号链接数不对，中止"; exit 1; }
fi

echo "==> 校验补丁文件已落位（23 个：后端 16 + 前端 7）"
for f in webserver/base/author_norm.py \
         webserver/base/formatter.py \
         webserver/base/meta_helper.py \
         webserver/constants.py \
         webserver/handlers/author_norm.py \
         webserver/handlers/book.py \
         webserver/main.py \
         webserver/services/audios_import.py \
         webserver/services/autofill.py \
         webserver/services/book_dedup.py \
         webserver/plugins/meta/baike/api.py \
         webserver/plugins/meta/douban_v2/api.py \
         webserver/plugins/meta/neodb/api.py \
         webserver/plugins/meta/ujxsw/api.py \
         webserver/plugins/meta/xhsd/api.py \
         webserver/plugins/meta/youshu/api.py \
         tests/test_author_norm.py \
         app/src/pages/toolbox/author_norm.vue \
         app/src/pages/admin/books.vue \
         app/src/components/AppHeader.vue \
         app/locales/zh.json \
         app/locales/zh-TW.json \
         app/locales/en.json; do
    [ -f "$D/$f" ] || { echo "!! 缺少 $f"; exit 1; }
done

echo "==> 校验补丁内容（关键字必须在）"
grep -q "def resolve_alias" "$D/webserver/base/author_norm.py" || {
    echo "!! author_norm.py 没落位（缺 resolve_alias）"; exit 1; }
grep -q "_DUTY_PREFIX" "$D/webserver/base/meta_helper.py" || {
    echo "!! meta_helper.py 没落位（缺 _DUTY_PREFIX）"; exit 1; }
grep -q "_AUTHOR_INITIAL" "$D/webserver/base/meta_helper.py" || {
    echo "!! meta_helper.py 缺 _AUTHOR_INITIAL（西文缩写保护）"; exit 1; }
grep -q "CALIBRE_COLUMN_AUTHOR_LOCKED" "$D/webserver/constants.py" || {
    echo "!! constants.py 缺 CALIBRE_COLUMN_AUTHOR_LOCKED"; exit 1; }
grep -q "COLUMN_AUTHOR_LOCKED, \"Author Locked\"" "$D/webserver/main.py" || {
    echo "!! main.py 没注册 #author_locked 列"; exit 1; }
grep -q "is_author_locked" "$D/webserver/services/autofill.py" || {
    echo "!! autofill.py 没接作者锁定"; exit 1; }
grep -q "old_authors = list(mi.authors or \[\])" "$D/webserver/services/autofill.py" || {
    echo "!! autofill.py 单本路径没存 old_authors"; exit 1; }
grep -q "_cleaned_trans" "$D/webserver/services/audios_import.py" || {
    echo "!! audios_import.py 没接有声书归一化"; exit 1; }
grep -q "lock_author(self.calibre_db, bid)" "$D/webserver/handlers/book.py" || {
    echo "!! book.py 的 edit_book 没打锁"; exit 1; }
for p in baike douban_v2 neodb ujxsw xhsd youshu; do
    grep -q "4.6.0-9 作者清洗" "$D/webserver/plugins/meta/$p/api.py" || {
        echo "!! 刮削源 $p 没接清洗"; exit 1; }
done

# ---- 本批新增：dedup 守卫 / 管理接口 / 前端 ----
grep -q "def authors_conflict" "$D/webserver/base/author_norm.py" || {
    echo "!! author_norm.py 缺 authors_conflict（dedup 守卫依赖它）"; exit 1; }
grep -q "authors_conflict" "$D/webserver/services/book_dedup.py" || {
    echo "!! book_dedup.py 没接作者冲突守卫（同名不同作者会被误合并）"; exit 1; }
grep -q "def _build_report" "$D/webserver/handlers/author_norm.py" || {
    echo "!! handlers/author_norm.py 缺 _build_report"; exit 1; }
grep -q "author_norm.routes()" "$D/webserver/main.py" || {
    echo "!! main.py 没注册 author_norm 路由"; exit 1; }
grep -q "author_locked" "$D/webserver/base/formatter.py" || {
    echo "!! formatter.py 没透传 author_locked（前端锁图标会不显示）"; exit 1; }
grep -q "author_locked" "$D/app/src/pages/admin/books.vue" || {
    echo "!! books.vue 缺锁图标"; exit 1; }
grep -q "_lock_after_save" "$D/app/src/pages/admin/books.vue" || {
    echo "!! books.vue 缺「保存后锁定」勾选联动"; exit 1; }
grep -q "authorNorm" "$D/app/src/components/AppHeader.vue" || {
    echo "!! AppHeader.vue 缺工具箱入口"; exit 1; }
[ -s "$D/app/src/pages/toolbox/author_norm.vue" ] || {
    echo "!! author_norm.vue 为空或缺失"; exit 1; }
for loc in zh zh-TW en; do
    grep -q '"authorNorm"' "$D/app/locales/$loc.json" || {
        echo "!! $loc.json 缺 authorNorm 文案块"; exit 1; }
done

# ---- 危险写法自检：_ 被当作译者变量会遮蔽 i18n ----
echo "==> 校验 i18n 的 _ 没被遮蔽"
if grep -rn "guess_authors(.*)[[:space:]]*$" "$D/webserver" --include=*.py 2>/dev/null | \
   grep -E ",\s*_\s*=\s*guess_authors" >/dev/null 2>&1; then
    echo "!! 有 '_, _ = guess_authors(...)' 写法，会覆盖 i18n 函数："
    grep -rnE ",\s*_\s*=\s*guess_authors" "$D/webserver" --include=*.py | sed 's/^/     /'
    exit 1
fi
echo "   OK"

# ---- 语法自检：13 个 py 必须能 parse ----
echo "==> 校验 Python 语法"
if command -v python3 >/dev/null 2>&1; then
    python3 - "$D" <<'PY' || exit 1
import ast, sys, os
root = sys.argv[1]
files = ["webserver/base/author_norm.py","webserver/base/meta_helper.py",
         "webserver/base/formatter.py","webserver/constants.py",
         "webserver/handlers/author_norm.py","webserver/handlers/book.py",
         "webserver/main.py","webserver/services/book_dedup.py",
         "webserver/services/audios_import.py","webserver/services/autofill.py"] + \
        ["webserver/plugins/meta/%s/api.py" % p for p in
         ("baike","douban_v2","neodb","ujxsw","xhsd","youshu")] + \
        ["tests/test_author_norm.py"]
bad = 0
for f in files:
    p = os.path.join(root, f)
    try:
        ast.parse(open(p, encoding="utf-8").read())
    except Exception as e:
        bad += 1
        print("   !! %s: %s" % (f, e))
print("   %d 个文件语法 OK" % (len(files) - bad) if not bad else "   !! 语法错误 %d 个" % bad)
sys.exit(1 if bad else 0)
PY
else
    echo "   ! 找不到 python3，跳过语法自检"
fi

# ---- 前端：非法标签名 + 模板 v-for 用法 ----
# 教训：早期 fix-template-key.py 把 <div :key=> 改成了 <div:key=>（冒号粘进标签名），
# 这是非法 HTML，eslint 报 vue/valid-v-for，nuxt build 直接失败。脚本已删，检查留在这里。
echo "==> 校验 Vue 模板（非法标签名 / template v-for）"
python3 - "$D" <<'PYEOF' || exit 1
import re, sys, os, json

root = sys.argv[1]
bad = 0

# 1) 非法标签名：<div:key=  <v-btn:key= —— 冒号粘在标签名里，浏览器认不出这个标签
tag_bad = re.compile(r"<(?:div|span|v-[a-z-]+):(?:key|id|class)\s*=")

count = 0
for dirpath, _, files in os.walk(os.path.join(root, "app", "src")):
    for fn in files:
        if not fn.endswith(".vue"):
            continue
        path = os.path.join(dirpath, fn)
        count += 1
        for i, line in enumerate(open(path, encoding="utf-8"), 1):
            if tag_bad.search(line):
                print("   !! %s:%d 非法标签名（冒号粘进标签）: %s"
                      % (os.path.relpath(path, root), i, line.strip()[:70]))
                bad += 1

# 2) 三个 locale 必须是合法 JSON（结构错了整站文案会崩）
for loc in ("zh", "zh-TW", "en"):
    lp = os.path.join(root, "app", "locales", "%s.json" % loc)
    try:
        json.load(open(lp, encoding="utf-8"))
    except Exception as e:
        print("   !! %s.json 不是合法 JSON: %s" % (loc, e))
        bad += 1

if bad:
    print("   !! 模板/文案问题 %d 处，未出包" % bad)
else:
    print("   %d 个 .vue 模板 OK，3 个 locale 合法" % count)
sys.exit(1 if bad else 0)
PYEOF

# ---- 自定义内容保护（BOOK_NAV / 三语文案）----
echo "==> 校验自定义内容（BOOK_NAV / 三语文案）"
PROTECT="$SELF_DIR/protect-custom.sh"
[ -f "$PROTECT" ] || PROTECT="./protect-custom.sh"
[ -f "$PROTECT" ] || PROTECT=/volume1/docker/protect-custom.sh
if [ -f "$PROTECT" ]; then
    echo "   使用 $PROTECT"
    sh "$PROTECT" check "$D" || {
        echo "!! 自定义内容被覆盖了。先执行修复："
        echo "     sh $PROTECT save  <有自定义内容的源码目录>"
        echo "     sh $PROTECT apply $D"
        exit 1
    }
else
    echo "   ! 找不到 protect-custom.sh，跳过（BOOK_NAV 与三语文案未校验）"
fi

echo "==> 清理 .git / __pycache__ / *.pyc"
rm -rf "$D/.git"
find "$D" -name '__pycache__' -exec rm -rf {} + 2>/dev/null
find "$D" -name '*.pyc' -delete 2>/dev/null

# ------------------------------------------------------------------ #
# 剔除运行时数据（历史 bug：-7 起的基准包都带了这些，一路继承）
#
# 这些目录在源码根目录下，是程序跑起来才生成的，不属于源码：
#   cache/          缩略图缓存（cache/thumb/240x320/*.jpg），可再生
#   sync/           用户阅读进度（sync/<uid>/reading.json），**会覆盖新数据**
#   books/ audio/   书库与音频，体积大，绝不能进包
#
# 危害有两层：
#   1. 部署时污染新源码目录，deploy.sh 的「源码目录污染自检」会直接中止
#   2. sync/<uid>/reading.json 是**旧快照**，解压后盖掉现役数据 = 阅读进度回退
#
# ⚠️ calibre/ 不在这个列表里，**千万别加**：
#    它是 calibre 的补丁源码（calibre/7.6/calibre/*.py）与自定义插件
#    （calibre/plugins/cbz_meta/ 等），删了镜像构建会直接失败。
#    书库数据在 /volume1/docker/audiobook-data/books，不叫 calibre/。
# ------------------------------------------------------------------ #
echo "==> 剔除运行时数据目录（cache/ sync/ 等，不应进源码包）"
for d in cache sync books audio; do
    if [ -e "$D/$d" ]; then
        sz=$(du -sh "$D/$d" 2>/dev/null | awk '{print $1}')
        n=$(find "$D/$d" -type f 2>/dev/null | wc -l)
        echo "   移除 $d/（$n 个文件，$sz）"
        rm -rf "$D/$d"
    fi
done
# 兜底：其它常见运行时目录
for d in logs tmp temp .pytest_cache .mypy_cache .ruff_cache; do
    [ -e "$D/$d" ] && rm -rf "$D/$d"
done

echo "==> 重打包"
cd /tmp/mp9 && tar -czf "$OUT" "$PREFIX"

echo "==> 成品复检"
tar -tzf "$OUT" | grep -q "webserver/base/author_norm.py" || {
    echo "!! 成品里没有 author_norm.py"; exit 1; }
tar -tzf "$OUT" | grep -q "tests/test_author_norm.py" || {
    echo "!! 成品里没有测试文件"; exit 1; }
echo "   ✓ author_norm.py 已在包内"
echo "   ✓ test_author_norm.py 已在包内"

# 前端 7 个文件必须都在包里——漏一个就是「界面看着没变」的隐形故障
missing_front=""
for f in webserver/handlers/author_norm.py \
         webserver/base/formatter.py \
         webserver/services/book_dedup.py \
         app/src/pages/toolbox/author_norm.vue \
         app/src/pages/admin/books.vue \
         app/src/components/AppHeader.vue \
         app/locales/zh.json app/locales/zh-TW.json app/locales/en.json; do
    tar -tzf "$OUT" | grep -q "^$PREFIX/$f$" || missing_front="$missing_front $f"
done
[ -n "$missing_front" ] && { echo "!! 成品缺少:$missing_front"; exit 1; }
echo "   ✓ 新增/前端 9 个文件均在包内"

# 包内关键内容再确认一次（防止补丁被别的东西覆盖回旧版）
tmp_chk=$(mktemp -d)
tar -xzf "$OUT" -C "$tmp_chk" 2>/dev/null
CK="$tmp_chk/$PREFIX"
grep -q "def authors_conflict" "$CK/webserver/base/author_norm.py" 2>/dev/null || {
    echo "!! 成品里的 author_norm.py 没有 authors_conflict（被旧版覆盖了？）"; rm -rf "$tmp_chk"; exit 1; }
grep -q "authors_conflict" "$CK/webserver/services/book_dedup.py" 2>/dev/null || {
    echo "!! 成品里的 book_dedup.py 没接作者冲突守卫"; rm -rf "$tmp_chk"; exit 1; }
grep -q "author_locked" "$CK/app/src/pages/admin/books.vue" 2>/dev/null || {
    echo "!! 成品里的 books.vue 没有锁图标"; rm -rf "$tmp_chk"; exit 1; }
echo "   ✓ 关键逻辑已在成品内（dedup 守卫 / 锁图标）"
rm -rf "$tmp_chk"

# 复检：运行时数据必须已清干净，否则 deploy.sh 第 6 步会中止
bad=$(tar -tzf "$OUT" | grep -cE "^$PREFIX/(cache|sync|books|audio)/")
if [ "$bad" -ne 0 ]; then
    echo "!! 成品里仍有 $bad 条运行时数据路径，deploy.sh 会判定污染并中止："
    tar -tzf "$OUT" | grep -E "^$PREFIX/(cache|sync|books|audio)/" | head -10 | sed 's/^/     /'
    exit 1
fi
echo "   ✓ 无 cache/ sync/ 等运行时数据目录"

rm -rf /tmp/mp9 /tmp/mp9-patch
echo "==> 完成"
ls -lh "$OUT"
echo
echo "下一步: sh /volume1/docker/audiobook/upgrade.sh $OUT"
