#!/bin/sh
# ============================================================
# protect-custom.sh —— 保护「跟随上游时容易被整段覆盖」的自定义内容
#
# 背景：上游升级（git merge / 直接覆盖文件）时，下面这些文件会被整段替换。
# 它们恰好是我们改动最集中、又最容易"静默丢功能"的地方：
#
#   webserver/settings.py    BOOK_NAV —— 默认分类导航。上游 9 组，我们 13 组。
#                            被覆盖后分类导航直接变回上游版本，我们的分组全丢。
#   app/locales/*.json       三语文案。上游覆盖后，我们新增的键（read_range、
#                            reader_group_strict、audioResumeAt、transcribe…）
#                            全部消失，界面上显示原始键名像 "settings.xxx"。
#
# 做法：把这两类内容抽成快照。合并前快照 → 合并后回灌 → 校验。
#
# 用法：
#   sh protect-custom.sh save   <源码目录>   # 合并前：存快照到 /tmp/custom-snap
#   sh protect-custom.sh apply  <源码目录>   # 合并后：把快照回灌进去
#   sh protect-custom.sh check  <源码目录>   # 校验：缺了什么就报错退出
#
# 设计取舍：
#   * BOOK_NAV 整段替换而不是逐行 merge —— 上游改动这段时是"重排分类"，
#     逐行 merge 只会产出一堆无意义冲突破坏分组结构。
#   * locale 按 key 合并（不是整文件替换）：上游可能新增键，我们只负责
#     "把我们自己的键补回去"，上游的新键保留。
# ============================================================

set -e
SNAP=/tmp/custom-snap
ACTION="${1:-}"
SRC="${2:-}"

[ -n "$ACTION" ] || { echo "用法: sh protect-custom.sh save|apply|check <源码目录>"; exit 2; }
[ -n "$SRC" ] && [ -d "$SRC" ] || { echo "!! 源码目录不存在: $SRC"; exit 2; }

PY=${PYTHON:-python3}
command -v "$PY" >/dev/null 2>&1 || PY=python

# ---------- 需要保护的 locale 文件（只有 app 前端这一套；webserver 无 i18n 目录） ----------
LOCALES_APP="app/locales/zh.json app/locales/zh-TW.json app/locales/en.json"

do_save() {
    rm -rf "$SNAP"; mkdir -p "$SNAP"
    echo "==> 存快照 -> $SNAP"

    # 1) BOOK_NAV 整段
    "$PY" - "$SRC" "$SNAP" <<'PYEOF'
import re, sys, os
src, snap = sys.argv[1], sys.argv[2]
p = os.path.join(src, "webserver/settings.py")
if not os.path.isfile(p):
    print("   ! 没有 settings.py，跳过 BOOK_NAV"); sys.exit(0)
s = open(p, encoding="utf8").read()
m = re.search(r"^([ \t]*['\"]BOOK_NAV['\"]\s*:\s*)'''.*?'''", s, re.S | re.M)
if not m:
    print("   ! 找不到 BOOK_NAV 定义"); sys.exit(0)
open(os.path.join(snap, "BOOK_NAV.txt"), "w", encoding="utf8").write(m.group(0))
print("   + BOOK_NAV (%d 字节)" % len(m.group(0)))
PYEOF

    # 2) locale 键快照（只存我们"额外有的"那部分在 apply 时算）
    for f in $LOCALES_APP; do
        [ -f "$SRC/$f" ] || continue
        out="$SNAP/$(echo "$f" | tr '/' '_')"
        cp "$SRC/$f" "$out"
        echo "   + $f"
    done
    echo "==> 快照完成"
}

do_apply() {
    [ -d "$SNAP" ] || { echo "!! 没有快照，先跑 save"; exit 1; }
    echo "==> 回灌快照 -> $SRC"

    # 1) BOOK_NAV：整段替换
    if [ -f "$SNAP/BOOK_NAV.txt" ]; then
        "$PY" - "$SRC" "$SNAP" <<'PYEOF'
import re, sys, os
src, snap = sys.argv[1], sys.argv[2]
snap_block = open(os.path.join(snap, "BOOK_NAV.txt"), encoding="utf8").read()
p = os.path.join(src, "webserver/settings.py")
s = open(p, encoding="utf8").read()
m = re.search(r"^([ \t]*['\"]BOOK_NAV['\"]\s*:\s*)'''.*?'''", s, re.S | re.M)
if not m:
    print("   ! 现版找不到 BOOK_NAV，放弃回灌（需人工检查）"); sys.exit(1)
s2 = s[:m.start()] + snap_block + s[m.end():]
open(p, "w", encoding="utf8").write(s2)
inner = re.search(r"={3}(.*?)={3}", snap_block, re.S)
body = inner.group(1) if inner else snap_block
groups = [l for l in body.strip().split("\n") if "=" in l]
print("   ✓ BOOK_NAV 已恢复（%d 组）" % len(groups))
PYEOF
        [ $? -eq 0 ] || return 1
    fi

    # 2) locale：按 key 深度合并，把我们有的键补回去，上游新键保留
    for f in $LOCALES_APP; do
        out="$SNAP/$(echo "$f" | tr '/' '_')"
        [ -f "$out" ] || continue
        [ -f "$SRC/$f" ] || mkdir -p "$(dirname "$SRC/$f")"
        "$PY" - "$out" "$SRC/$f" "$f" <<'PYEOF'
import json, sys, os
snapf, curf, label = sys.argv[1], sys.argv[2], sys.argv[3]

def load(p):
    if not os.path.isfile(p): return {}
    try: return json.load(open(p, encoding="utf8"))
    except Exception as e:
        print("   ! %s 读不了: %s" % (p, e)); return {}

def merge(base, mine, stats):
    """mine 的键覆盖 base，base 独有的键保留（上游新增的）"""
    out = dict(base)
    for k, v in mine.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = merge(out[k], v, stats)
        else:
            if k not in base:
                stats["added"] += 1
            out[k] = v
    return out

snap = load(snapf)
cur  = load(curf)
stats = {"added": 0}
merged = merge(cur, snap, stats)
if merged:
    json.dump(merged, open(curf, "w", encoding="utf8"),
              ensure_ascii=False, indent=2)
    open(curf, "a", encoding="utf8").write("\n")
    print("   ✓ %s（补回 %d 个键）" % (label, stats["added"]))
PYEOF
    done
    echo "==> 回灌完成"
}

do_check() {
    echo "==> 校验自定义内容是否健在"
    fail=0

    # BOOK_NAV 组数
    n=$("$PY" - "$SRC" <<'PYEOF'
import re, sys, os
p = os.path.join(sys.argv[1], "webserver/settings.py")
if not os.path.isfile(p):
    print(-1); raise SystemExit
s = open(p, encoding="utf8").read()
m = re.search(r"['\"]BOOK_NAV['\"]\s*:\s*'''(.*?)'''", s, re.S)
if not m: print(0)
else:
    body = m.group(1)
    print(len([l for l in body.strip().split("\n") if "=" in l]))
PYEOF
)
    if [ "$n" -lt 0 ]; then
        echo "   ✗ 找不到 webserver/settings.py（源码目录传错？）"; fail=1
    elif [ "$n" -lt 13 ]; then
        echo "   ✗ BOOK_NAV 只有 $n 组（应 >=13），分类导航被覆盖了"; fail=1
    else
        echo "   ✓ BOOK_NAV $n 组"
    fi

    # 文案键：有快照就按快照逐键比对（不漏任何自定义键）；
    # 没快照就退回一份最小硬编码清单兜底
    "$PY" - "$SRC" "$SNAP" <<'PYEOF'
import json, sys, os

src, snapdir = sys.argv[1], sys.argv[2]

# 兜底清单：只在没有快照时用（merge-4.6.0-N.sh 那种没有 save 的场景）
FALLBACK = [
    ("settings", "reader_group_strict"),
    ("settings", "allow_read_range_setting"),
    ("settings", "audio_link_to_existing_book"),
    ("settings", "transcribe_keep_txt"),
    ("book", "audioResumeAt"),
    ("book", "audioList"),
]

def load(p):
    try: return json.load(open(p, encoding="utf8"))
    except Exception: return None

def keys_of(j, node):
    """把某个顶层节点下的键摊平成 node.key[.subkey] 列表"""
    if not isinstance(j.get(node), dict):
        return set()
    return _walk(j[node], node)

def _walk(d, base):
    out = set()
    for k, v in d.items():
        path = "%s.%s" % (base, k)
        out.add(path)
        if isinstance(v, dict):
            out |= _walk(v, path)
    return out

zh = os.path.join(src, "app/locales/zh.json")
cur = load(zh)
if cur is None:
    print("   ✗ 读不到 app/locales/zh.json（源码目录传错？）"); sys.exit(1)

snap = load(os.path.join(snapdir, "app_locales_zh.json")) if os.path.isdir(snapdir) else None

if snap:
    want = set()
    for node in snap:
        want |= keys_of(snap, node)
    have = set()
    for node in cur:
        have |= keys_of(cur, node)
    missing = sorted(want - have)
    if missing:
        print("   ✗ 相比快照少了 %d 个文案键：" % len(missing))
        for k in missing[:15]:
            print("       - " + k)
        if len(missing) > 15:
            print("       ... 还有 %d 个" % (len(missing) - 15))
        sys.exit(1)
    print("   ✓ 文案键与快照一致（%d 个）" % len(want))
else:
    missing = ["%s.%s" % (n, k) for n, k in FALLBACK if k not in (cur.get(n) or {})]
    if missing:
        print("   ✗ 缺失文案键: " + ", ".join(missing))
        sys.exit(1)
    print("   ✓ 保底文案键齐全（%d 个，无快照可用）" % len(FALLBACK))
PYEOF
    [ $? -eq 0 ] || fail=1

    if [ "$fail" -ne 0 ]; then
        echo
        echo "!! 自定义内容有缺失。修复方式："
        echo "     sh protect-custom.sh apply $SRC"
        echo "   然后 git diff 看一眼，确认无误再继续。"
        return 1
    fi
    echo "==> 校验通过"
}
case "$ACTION" in
    save)  do_save ;;
    apply) do_apply ;;
    check) do_check ;;
    *) echo "未知动作: $ACTION（save|apply|check）"; exit 2 ;;
esac
