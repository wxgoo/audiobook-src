#!/bin/sh
# ============================================================
# rescue-from-248.sh —— 从 NAS 上那份 248M 的 4.6.0-8 里挖出完整 myreader-dist
#
# 用法（在 /volume1/docker 下）：
#   sh rescue-from-248.sh 旧包文件名.tar.gz
#   例： sh rescue-from-248.sh audiobook-deploy-4.6.0-8.tar.gz
#
# 只做三件事：验货 → 解产物 → 重新打包。
# 不改现有部署，不动容器。
# ============================================================
set -u
PKG="${1:-}"

if [ -z "$PKG" ]; then
    echo "用法: sh rescue-from-248.sh <包的完整路径或文件名>"
    echo ""
    echo "NAS 上现有的包："
    ls -lh /volume*/docker/*.tar.gz 2>/dev/null | awk '{printf "  %6s  %s\n", $5, $9}'
    exit 1
fi
[ -f "$PKG" ] || PKG="/volume1/docker/$PKG"
[ -f "$PKG" ] || { echo "!! 找不到文件：$PKG"; exit 1; }

WORK=/volume1/docker/rescue
line() { echo "------------------------------------------------------------"; }

echo "============================================================"
echo " 从旧包挖 MyReader 产物"
echo " 包: $PKG"
echo " 体积: $(du -h "$PKG" | awk '{print $1}')"
echo "============================================================"

# ---------- 第 1 步：验货 ----------
line
echo "[1/4] 数一数包里的 node_modules 条目（10 秒 ~ 1 分钟）"
N=$(tar -tzf "$PKG" 2>/dev/null | grep -c 'myreader-dist/node_modules/')
N=${N:-0}
echo "    myreader-dist/node_modules/ 条目数: $N"

if [ "$N" -le 0 ]; then
    echo ""
    echo "    ✘ 这个包里没有 node_modules —— 也是残缺的，换下一个包。"
    echo "      跑 sh find-myreader.sh 把所有包都扫一遍。"
    exit 1
elif [ "$N" -lt 500 ]; then
    echo ""
    echo "    △ 只有 $N 条，不像完整产物（完整应 >500，实际约 1300）。"
    echo "      仍继续解包看看，但大概率还是缺东西。"
else
    echo "    ✔ 看起来是完整产物。"
fi

line
echo "[2/4] 确认关键文件在不在"
KEY=$(tar -tzf "$PKG" 2>/dev/null | grep -E 'myreader-dist/(app/server\.js|app/\.next/BUILD_ID|app/\.next/required-server-files\.json)$')
echo "$KEY" | sed 's/^/    /'
if ! echo "$KEY" | grep -q 'app/server\.js'; then
    echo "    ✘ 连 server.js 都没有，这个包不对。"
    exit 1
fi

# ---------- 第 2 步：只解 myreader-dist ----------
line
echo "[3/4] 只解出 myreader-dist（不动包里其他东西）"
rm -rf "$WORK"
mkdir -p "$WORK"
if ! tar -xzf "$PKG" -C "$WORK" audiobook/myreader-dist 2>/dev/null; then
    # 有的包顶层目录名不叫 audiobook，重试
    TOP=$(tar -tzf "$PKG" 2>/dev/null | head -1 | cut -d/ -f1)
    echo "    顶层目录是 ./$TOP ，换路径重试"
    tar -xzf "$PKG" -C "$WORK" "$TOP/myreader-dist" || { echo "!! 解包失败"; exit 1; }
    [ -d "$WORK/audiobook/myreader-dist" ] || mv "$WORK/$TOP/myreader-dist" "$WORK/audiobook/myreader-dist" 2>/dev/null
fi

MR="$WORK/audiobook/myreader-dist"
if [ ! -d "$MR" ]; then
    echo "!! 解出来没找到 myreader-dist 目录"
    echo "   实际解出的内容："
    find "$WORK" -maxdepth 3 -type d | sed 's/^/     /' | head -20
    exit 1
fi

echo ""
echo "    体积:   $(du -sh "$MR" | awk '{print $1}')"
echo "    文件数: $(find "$MR" -type f | wc -l)"
echo ""
echo "    三个 node_modules："
for d in node_modules app/node_modules app/.next/node_modules; do
    if [ -d "$MR/$d" ]; then
        echo "        ✔ $d  （$(ls "$MR/$d" 2>/dev/null | wc -l) 项）"
    else
        echo "        ✘ $d  缺失"
    fi
done
echo ""
V=0; B=0
for l in $(find "$MR" -type l 2>/dev/null); do
    if [ -e "$l" ]; then V=$((V+1)); else B=$((B+1)); fi
done
echo "    符号链接: 有效 $V / 断链 $B"
echo "    （有效数应该接近 127；断链一堆说明这个包的链接也是坏的）"

# ---------- 第 3 步：重新打包 ----------
line
echo "[4/4] 重新打包成能传回来的样子"
OUT=/volume1/docker/myreader-dist.tar.gz
rm -f "$OUT"
cd "$WORK" || exit 1
tar -czf "$OUT" audiobook/myreader-dist
echo "    ✔ 已生成: $OUT  （$(du -h "$OUT" | awk '{print $1}')）"
echo ""
echo "    ⚠ 用的是 tar -czf，没有加 -h，符号链接原样保留。"
echo "      千万别用群晖 File Station 压这个目录，会把链接压扁。"
line
echo "【下一步】"
echo "    把这个文件传回电脑，然后发给我："
echo "      scp glyzx@<NAS地址>:$OUT ."
echo ""
echo "    我合并进部署包后重出一版完整的（回到 248M 量级）。"
echo ""
echo "    回滚备份：$WORK 里的产物先别删，合并成功后再 rm -rf $WORK"
line
