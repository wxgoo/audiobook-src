#!/bin/bash
# 【已归档 · 一次性脚本】
# 出 4.6.0-9 v2 包的组装脚本，已被 build-v3.sh 取代。当时基准包 myreader-dist 残缺，需要从多份来源拼。
# 不随版本更新，不要在这些文件上打补丁；需要类似能力请新写一个放 scripts/ 根。
# 下面保留原始内容：
# ============================================================
# build-v2.sh —— 在本机出 4.6.0-9 v2 干净部署包
#
# 组成：
#   基准 = audiobook-deploy-4.6.0-8.tar.gz（94M 版，源码正确，仅产物残缺）
#   补丁 = audiobook-patch-4.6.0-9.tar.gz（-9 全部前后端改动）
#   覆盖 = 当前仓库 HEAD（含 Dockerfile 预构建 dist 支持、权限修复、脚本）
#   产物 = myreader-dist.tar.gz（3526 条目完整版）+ app/dist（本地构建已实测）
#
# v2 的两个决定性差异（相对出事的 v1）：
#   1. SPA dist 在打包机预构建、预校验，NAS 构建时直接 COPY，不再现场 build
#   2. 阅读器产物用验证过的完整版替换，权限归一
# ============================================================
set -e
W=/workspace
REPO=/root/work/audiobook-src
BASE=$W/audiobook-deploy-4.6.0-8.tar.gz
PATCH=$W/audiobook-patch-4.6.0-9.tar.gz
MRTAR=$W/myreader-dist.tar.gz
OUT=$W/audiobook-deploy-4.6.0-9-v2.tar.gz
TMP=/tmp/v2

step(){ printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok(){ printf '  \033[32m✔\033[0m %s\n' "$*"; }
die(){ printf '\n\033[1;31m!! %s\033[0m\n' "$*"; exit 1; }

rm -rf $TMP && mkdir -p $TMP/base $TMP/patch

step "1/8 解压基准包(-8 源码)"
tar -xzf $BASE -C $TMP/base
D=$(find $TMP/base -maxdepth 1 -type d -name 'audiobook' | head -1)
[ -n "$D" ] || die "基准包顶层异常"
ok "$D"

step "2/8 注入 -9 补丁"
tar -xzf $PATCH -C $TMP/patch
cp -R "$TMP/patch/audiobook-patch-4.6.0-9/audiobook/." "$D/"
ok "补丁文件覆盖完成"

step "3/8 用仓库 HEAD 覆盖（含 v2 Dockerfile / 权限修复 / 脚本）"
cd $REPO
# 中文文件名：关掉 quotepath，用 -z + bash 的 read -d 处理
git -c core.quotepath=off ls-files -z | while IFS= read -r -d '' f; do
    mkdir -p "$D/$(dirname "$f")"
    cp -a "$REPO/$f" "$D/$f"
done
ok "HEAD 文件同步完成（$(git -c core.quotepath=off ls-files | wc -l) 个）"
[ -f "$D/rollback-to-8.sh" ] && [ -f "$D/Dockerfile" ] || die "HEAD 覆盖未生效"

step "4/8 注入完整 MyReader 产物"
rm -rf "$D/myreader-dist" $TMP/mr && mkdir -p $TMP/mr
tar -xzf $MRTAR -C $TMP/mr
SRC=$(find $TMP/mr -maxdepth 3 -type d -name myreader-dist | head -1)
[ -n "$SRC" ] || die "产物包里找不到 myreader-dist"
cp -a "$SRC" "$D/myreader-dist"
N=$(find "$D/myreader-dist" | wc -l)
NM=$(find "$D/myreader-dist/node_modules" -type f -o -type l 2>/dev/null | wc -l)
[ "$N" -gt 3000 ] && [ "$NM" -gt 1000 ] || die "产物仍不完整: $N / $NM"
ok "产物 $N 条目 / node_modules $NM"
[ -f "$D/myreader-dist/app/server.js" ] && [ -f "$D/myreader-dist/app/.next/BUILD_ID" ] || die "server.js / BUILD_ID 缺失"
ok "server.js + BUILD_ID 在位（BUILD_ID=$(cat "$D/myreader-dist/app/.next/BUILD_ID")）"

step "5/8 注入预构建 SPA dist（本地已实测渲染正常）"
rm -rf "$D/app/dist"
cp -a $REPO/app/dist "$D/app/dist"
[ -f "$D/app/dist/index.html" ] && [ -f "$D/app/dist/200.html" ] && [ -d "$D/app/dist/_nuxt" ] || die "dist 不完整"
NU=$(ls "$D/app/dist/_nuxt" | wc -l)
ok "dist 就位（_nuxt $NU 个文件）"

step "6/8 权限归一 + 清除构建污染"
chown -R root:root "$D/myreader-dist" 2>/dev/null || true
chmod -R u+rwX,go+rX "$D/myreader-dist"
rm -rf "$D/app/node_modules" "$D/app/.nuxt" "$D/cache" "$D/sync" "$D/.git"
ok "权限: $(ls -ld "$D/myreader-dist/app" | awk '{print $1}')；node_modules/.nuxt/cache 已清"

step "7/8 成包"
tar -czf $OUT -C $TMP/base audiobook
ok "$OUT ($(du -sh $OUT | awk '{print $1}'))"

step "8/8 终检"
T=$(tar -tzf $OUT)
echo "$T" | grep -q "^audiobook/Dockerfile$" || die "缺 Dockerfile"
echo "$T" | grep -q "^audiobook/myreader-dist/app/server.js$" || die "缺 myreader server.js"
echo "$T" | grep -c "^audiobook/myreader-dist/node_modules/" | grep -qv "^0$" || true
MR=$(echo "$T" | grep -c "^audiobook/myreader-dist/")
NMN=$(echo "$T" | grep -c "^audiobook/myreader-dist/node_modules/")
DS=$(echo "$T" | grep -c "^audiobook/app/dist/")
echo "$T" | grep -q "^audiobook/app/dist/index.html$" || die "缺预构建 dist"
echo "$T" | grep -q "^audiobook/app/src/pages/toolbox/author_norm.vue$" || die "缺 -9 前端"
echo "$T" | grep -q "^audiobook/webserver/base/author_norm.py$" || die "缺 -9 后端"
echo "$T" | grep -q "^audiobook/rollback-to-8.sh$" || die "缺回滚脚本"
echo "$T" | grep -q "^audiobook/app/node_modules/" && die "app/node_modules 混进包了"
ok "myreader-dist: $MR 条目 / node_modules $NMN 条"
ok "预构建 dist: $DS 条"
ok "-9 前后端 + v2 Dockerfile + 回滚脚本 全部在位"
echo ""
echo "===== 打包完成: $OUT ====="
md5sum $OUT
