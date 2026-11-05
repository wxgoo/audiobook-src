#!/bin/sh
# r11 升级事故热修：给 NAS 上的 readers 表补 birth_year 列
#
# 现象：升级 r11 后任何需要读 readers 的接口都 500，日志里
#   sqlite3.OperationalError: no such column: readers.birth_year
#
# 原因：r11 的迁移没执行（版本号没变 → 判定成"不是升级"），
# 但模型已经要读这个列。这里手工把列补上，并把老 age 换算成出生年份。
#
# 用法（在 NAS 上，容器已启动过一次的前提下）：
#   sh hotfix-r11-birth-year.sh
#   sh hotfix-r11-birth-year.sh /volume1/docker/audiobook/config/auto.py   # 指定配置
#
# 幂等：重复跑是安全的，已有 birth_year 列就直接跳过。
set -e

CONF="${1:-/volume1/docker/audiobook/config/auto.py}"

if [ ! -f "$CONF" ]; then
    echo "找不到配置文件: $CONF"
    echo
    echo "如果部署路径不是 /volume1/docker/audiobook，把实际的 auto.py 路径带上："
    echo "  sh $0 /实际路径/config/auto.py"
    echo
    echo "找一下它在哪："
    echo "  find /volume1 -name auto.py -path '*audiobook*' 2>/dev/null"
    exit 1
fi

# 从配置里找 db 路径
DB=$(grep -E "^\s*['\"]?db['\"]?\s*[:=]" "$CONF" | head -1 | sed -E "s/.*[:=]\s*//" | tr -d "'\" ,")
if [ -z "$DB" ]; then
    echo "配置里没找到 db 路径，请手工指定："
    echo "  sh $0 <auto.py> <metadata.db 路径>"
    exit 1
fi
if [ -n "$2" ]; then DB="$2"; fi

if [ ! -f "$DB" ]; then
    echo "数据库文件不存在: $DB"
    exit 1
fi

echo "配置: $CONF"
echo "数据库: $DB"
echo

echo "--- 修复前 ---"
python3 - "$DB" <<'PY'
import sqlite3, sys
db = sys.argv[1]
c = sqlite3.connect(db)
cols = [r[1] for r in c.execute("PRAGMA table_info(readers)")]
print("readers 列数:", len(cols))
print("有 birth_year:", "birth_year" in cols)
print("有 age:", "age" in cols)
c.close()
PY

echo
echo "--- 执行修复 ---"
python3 - "$DB" <<'PY'
import sqlite3, sys
db = sys.argv[1]
c = sqlite3.connect(db)
cols = [r[1] for r in c.execute("PRAGMA table_info(readers)")]

if not cols:
    print("readers 表不存在，这个库可能不对（是不是 calibre 的 metadata.db？）")
    sys.exit(1)

if "birth_year" in cols:
    print("birth_year 已存在，跳过补列")
else:
    c.execute("ALTER TABLE readers ADD COLUMN birth_year INTEGER NOT NULL DEFAULT 0")
    print("已添加 birth_year 列")

    if "age" in cols:
        cur = c.execute("""
            UPDATE readers
               SET birth_year = CAST(strftime('%Y','now') AS INTEGER) - age
             WHERE age > 0 AND (birth_year IS NULL OR birth_year = 0)
        """)
        print(f"已按 age 回填 {cur.rowcount} 个用户的出生年份")
    else:
        print("没有 age 列，不回填（所有人 birth_year=0，等于未填）")

c.commit()
print("已提交")
c.close()
PY

echo
echo "--- 修复后 ---"
python3 - "$DB" <<'PY'
import sqlite3, sys
db = sys.argv[1]
c = sqlite3.connect(db)
cols = [r[1] for r in c.execute("PRAGMA table_info(readers)")]
print("有 birth_year:", "birth_year" in cols)
rows = c.execute(
    "SELECT username, COALESCE(age,-1), birth_year FROM readers ORDER BY id LIMIT 10"
).fetchall()
print(f"抽查前 {len(rows)} 个用户：")
for name, age, by in rows:
    print(f"  {name:16} age={age:<5} birth_year={by}")
c.close()
PY

echo
echo "完成。重启容器后再试："
echo "  docker restart <容器名>"
echo
echo "重启后如果日志里还有 no such column，说明连的不是这个库，"
echo "检查 config/auto.py 里 db 的实际值。"
