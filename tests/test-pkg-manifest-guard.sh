#!/bin/sh
# ============================================================
# test-pkg-manifest-guard.sh —— 发布清单防线的回归契约测试
#
# 背景：r27 / r33 两次事故都是「包文件名是新版、包内 update/manifest.json
# 却是旧版」。本测试把事故重演一遍，确认 scripts/verify-pkg-manifest.sh
# 与 scripts/pack.sh 的产物门禁会拦下它。
#
# 用法（仓库根目录）： sh tests/test-pkg-manifest-guard.sh
# 不依赖真实交付包、不联网、不写仓库文件，只在临时目录里造小 tar。
# 退出码：0 全部通过；1 有用例失败
# ============================================================
set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
VM="$ROOT/scripts/verify-pkg-manifest.sh"
T=$(mktemp -d 2>/dev/null) || { echo "无法创建临时目录"; exit 1; }
trap 'rm -rf "$T"' EXIT HUP INT TERM

[ -f "$VM" ] || { echo "缺 $VM"; exit 1; }
command -v sha256sum >/dev/null 2>&1 || { echo "缺 sha256sum"; exit 1; }

pass=0; fail=0
ok()   { echo "  PASS  $1"; pass=$((pass + 1)); }
bad()  { echo "  FAIL  $1"; fail=$((fail + 1)); }

# expect_rc <期望退出码> <说明> <命令...>
expect_rc() {
    want=$1; label=$2; shift 2
    "$@" > "$T/out" 2>&1
    got=$?
    if [ "$got" = "$want" ]; then
        ok "$label (rc=$got)"
    else
        bad "$label：期望 rc=$want，实际 rc=$got"
        sed 's/^/        /' "$T/out" | head -8
    fi
}

mkdir -p "$T/src/audiobook/update" "$T/src/audiobook/scripts"
MF="$T/src/audiobook/update/manifest.json"
REV_NEW="4.6.0-build.27-r33"
REV_OLD="4.6.0-build.27-r32"

mk() {
    # mk <包路径> [revision|__missing__|__badjson__] [额外 notes 值]
    _pkg=$1; _rev=${2:-$REV_NEW}; _note=${3:-}
    if [ "$_rev" = "__missing__" ]; then
        rm -f "$MF"
    elif [ "$_rev" = "__badjson__" ]; then
        printf '{ this is not json' > "$MF"
    else
        printf '{"schema":1,"revision":"%s","base_revision":"%s","notes":"%s"}\n' \
               "$_rev" "$REV_OLD" "$_note" > "$MF"
    fi
    printf '#!/bin/sh\nexit 0\n' > "$T/src/audiobook/scripts/dummy.sh"
    tar -czf "$_pkg" -C "$T/src" audiobook
}

sha() { sha256sum "$1" | cut -d' ' -f1; }

echo "== 1. 合法包：基础校验 / 期望版本 / 字节比对都要通过"
mk "$T/good.tar.gz"
GOOD_SHA=$(sha "$MF")
expect_rc 0 "基础校验（revision 带 -rN）"            sh "$VM" "$T/good.tar.gz" --quiet
expect_rc 0 "--expect-rev 与包内一致"                sh "$VM" "$T/good.tar.gz" --expect-rev "$REV_NEW" --quiet
expect_rc 0 "--expect-sha256 与仓库清单字节一致"      sh "$VM" "$T/good.tar.gz" --expect-rev "$REV_NEW" --expect-sha256 "$GOOD_SHA" --quiet

echo "== 2. 事故重演：新包里塞旧 revision（r32 清单打进 r33 包）"
mk "$T/oldrev.tar.gz" "$REV_OLD"
# 不传期望值时脚本只能验「格式合法」，验不出「这是上一版」——
# 这正是出包必须传 --expect-rev / --expect-sha256 的原因，也是旧断言的盲区。
expect_rc 0 "不传期望值时旧 revision 也会放行（还原盲区）" \
    sh "$VM" "$T/oldrev.tar.gz" --quiet
expect_rc 1 "--expect-rev r33 时拦下 r32 清单"       sh "$VM" "$T/oldrev.tar.gz" --expect-rev "$REV_NEW" --quiet
expect_rc 1 "--expect-sha256 拦下被替换的清单"        sh "$VM" "$T/oldrev.tar.gz" --expect-rev "$REV_NEW" --expect-sha256 "$GOOD_SHA" --quiet

echo "== 3. 字节篡改：revision 没变，但清单内容被改过"
mk "$T/tampered.tar.gz" "$REV_NEW" "远端缓存混进来的旧字节"
expect_rc 1 "--expect-sha256 拦下内容被改的清单"      sh "$VM" "$T/tampered.tar.gz" --expect-rev "$REV_NEW" --expect-sha256 "$GOOD_SHA" --quiet

echo "== 4. 结构性坏包"
mk "$T/norev.tar.gz" "4.6.0-build.27"
expect_rc 1 "revision 不带 -rN（清单没更新就出包）"   sh "$VM" "$T/norev.tar.gz" --quiet
mk "$T/badjson.tar.gz" "__badjson__"
expect_rc 1 "清单不是合法 JSON"                       sh "$VM" "$T/badjson.tar.gz" --quiet
mk "$T/nomf.tar.gz" "__missing__"
expect_rc 1 "包内缺 update/manifest.json"             sh "$VM" "$T/nomf.tar.gz" --quiet

echo "== 5. 出包门禁确实挂着产物级断言（防止后人把校验删掉）"
if grep -q 'verify-pkg-manifest.sh.*\$OUT' "$ROOT/scripts/pack.sh" \
        || grep -q -- '--expect-sha256' "$ROOT/scripts/pack.sh"; then
    ok "pack.sh 打包后调用了 verify-pkg-manifest.sh 并传 --expect-sha256"
else
    bad "pack.sh 里找不到产物级清单断言"
fi
if grep -q 'rm -f "\$OUT"' "$ROOT/scripts/pack.sh"; then
    ok "门禁失败会删除半成品包"
else
    bad "门禁失败没有删包"
fi
if grep -qE '^[[:space:]]*(curl|wget)([[:space:]]|$)' "$ROOT/scripts/pack.sh"; then
    bad "pack.sh 出包链路里仍有网络调用"
else
    ok "pack.sh 出包链路零网络调用"
fi

echo
echo "结果: PASS=$pass FAIL=$fail"
[ "$fail" = "0" ] || exit 1
exit 0
