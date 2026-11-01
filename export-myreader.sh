#!/bin/sh
# ============================================================
# export-myreader.sh —— 从 NAS 上把完整的 myreader-dist 产物打包出来
#
# 用途：部署包里缺 myreader-dist/node_modules（阅读器启动报
#       Cannot find module 'next'），需要把 NAS 上那份完整的取回来，
#       再合并进新的部署包。
#
# 在 NAS 上跑（/volume1/docker 目录下）：
#   sh export-myreader.sh
#   sh export-myreader.sh audiobook          # 自定义容器名
#
# 产出：myreader-dist.tar.gz（约 40-60MB），传回沙箱即可。
# ============================================================
CONTAINER="${1:-audiobook}"
OUT="myreader-dist.tar.gz"

echo "==> 容器: $CONTAINER"

if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER"; then
    echo "!! 容器 $CONTAINER 没在运行"
    echo "   当前容器名列表："
    docker ps --format '   {{.Names}}' 2>/dev/null
    exit 1
fi

echo "==> 先确认产物是否完整"
docker exec "$CONTAINER" sh -c '
cd /var/www/myreader || { echo "!! /var/www/myreader 不存在"; exit 1; }
ok=1
[ -f app/server.js ]     || { echo "!! 缺 app/server.js"; ok=0; }
[ -d node_modules ]      || { echo "!! 缺 node_modules（这就是阅读器起不来的原因）"; ok=0; }
[ -d app/node_modules ]  || { echo "!! 缺 app/node_modules"; ok=0; }
[ -d app/.next ]         || { echo "!! 缺 app/.next"; ok=0; }
[ "$ok" = "1" ] || exit 1
n=$(find . -type l | wc -l)
v=0
for l in $(find . -type l); do [ -e "$l" ] && v=$((v+1)); done
echo "    文件数: $(find . -type f | wc -l)"
echo "    体积:   $(du -sh . | cut -f1)"
echo "    符号链接: $n（其中有效 $v）"
[ "$v" -lt 100 ] && { echo "!! 有效链接只有 $v 个，产物可能不完整"; exit 1; }
' || { echo "!! 产物不完整，不打包。请先看 check-reader.sh 的输出。"; exit 1; }

echo "==> 打包（保留符号链接，这点很关键）"
# -h 会把链接展开成实体文件（体积暴涨且结构变形），这里必须不加 -h
docker exec "$CONTAINER" tar -czf /tmp/myreader-dist.tar.gz -C /var/www myreader
docker cp "$CONTAINER:/tmp/myreader-dist.tar.gz" "./$OUT"
docker exec "$CONTAINER" rm -f /tmp/myreader-dist.tar.gz

echo "==> 完成: $(pwd)/$OUT"
ls -lh "$OUT" | awk '{print "    "$9"  "$5}'
echo
echo "把这个文件传回沙箱（或放到工作目录），然后告诉我，我合并进部署包。"
