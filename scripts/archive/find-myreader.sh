#!/bin/sh
# 【已归档 · 一次性脚本】
# 排查用的辅助手段：在 NAS 上翻遍各处找完整 myreader-dist。功能已被 export-myreader.sh 覆盖。
# 不随版本更新，不要在这些文件上打补丁；需要类似能力请新写一个放 scripts/ 根。
# 下面保留原始内容：
# ============================================================
# find-myreader.sh —— 在 NAS 上把所有可能含完整 myreader-dist 的地方翻一遍
#
# 用法（在当前目录）：
#   sh find-myreader.sh
#
# 只读，不解压、不改动。找到后会给出一条「下一步」命令。
# ============================================================

line() { echo "------------------------------------------------------------"; }

echo "============================================================"
echo " MyReader 产物搜寻"
echo " 目标：找到含 node_modules 的 myreader-dist（完整产物约 92M / 2600 文件）"
echo "============================================================"

need_pw=0
[ "$(id -u)" = "0" ] || need_pw=1

line
echo "[A] 先看还活着的部署目录（容器正在用的那份）"
for d in /volume1/docker/audiobook /volume*/docker/audiobook; do
    [ -d "$d/myreader-dist" ] || continue
    echo "    $d/myreader-dist"
    echo -n "        文件数: "; find "$d/myreader-dist" -type f 2>/dev/null | wc -l
    echo -n "        node_modules: "
    if [ -d "$d/myreader-dist/node_modules" ]; then echo "有"; else echo "无"; fi
done

line
echo "[B] 旧目录（upgrade.sh 会改名成 audiobook.old，这里最可能命中）"
found_old=""
for d in /volume*/docker/audiobook.old* /volume*/docker/audiobook-4* /volume*/docker/audiobook.bak*; do
    [ -d "$d" ] || continue
    echo "    $d"
    if [ -d "$d/myreader-dist" ]; then
        echo -n "        myreader-dist 文件数: "; find "$d/myreader-dist" -type f 2>/dev/null | wc -l
        echo -n "        node_modules: "
        [ -d "$d/myreader-dist/node_modules" ] && echo "有 ✔" || echo "无 ✘"
        [ -d "$d/myreader-dist/node_modules" ] && found_old="$d"
    else
        echo "        没有 myreader-dist"
    fi
done
[ -z "$found_old" ] && echo "    （没有可用的旧目录）"

line
echo "[C] 所有 tar.gz 部署包（含 node_modules 的才算数）"
for f in /volume*/docker/*.tar.gz; do
    [ -f "$f" ] || continue
    sz=$(du -h "$f" 2>/dev/null | awk '{print $1}')
    n=$(tar -tzf "$f" 2>/dev/null | grep -c 'myreader-dist/node_modules/' 2>/dev/null)
    n=${n:-0}
    if [ "$n" -gt 500 ] 2>/dev/null; then
        mark="✔ 有完整产物（$n 条）"
    elif [ "$n" -gt 0 ] 2>/dev/null; then
        mark="△ 有 $n 条，不像完整"
    else
        mark="✘ 无 node_modules"
    fi
    printf "    %-46s %6s  %s\n" "$(basename "$f")" "$sz" "$mark"
done

line
echo "[D] 备份盘 / 其他卷"
for v in /volume2 /volume3 /volumeUSB1 /volumeUSB2; do
    [ -d "$v" ] || continue
    hits=$(find "$v" -maxdepth 4 -name 'myreader-dist' -type d 2>/dev/null | head -5)
    if [ -n "$hits" ]; then
        echo "    $v 下找到："
        echo "$hits" | sed 's/^/        /'
    else
        echo "    $v：无（或没权限）"
    fi
done

line
echo "【结论怎么看】"
echo "  只要上面任意一处标了 ✔ 或文件数在 2500 以上："
echo "      cd 到它的上一级，执行"
echo "      tar -czf /volume1/docker/myreader-dist.tar.gz myreader-dist"
echo "      然后 scp 回来（不要加 -h，不要用 File Station 打包）"
echo ""
echo "  全是 ✘ / 文件数都在 1300 左右："
echo "      说明产物从没随包分发过，只能重新构建（见 PORTING_NOTES.md 第四节之二）"
line
