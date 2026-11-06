#!/bin/bash
set -euo pipefail

# =============================================================================
# 30-verify-backup.sh —— 校验备份产物完整性与 manifest
#
# 校验内容：
#   1) manifests/backup-<ts>.json 存在且 status=ok / ok-with-warnings
#   2) 每个数据库副本存在、大小与 SHA256 与 manifest 一致、PRAGMA integrity_check=ok
#   3) files/<ts> 快照存在（若本次含文件备份）；--deep 时重新统计文件数
#
# 退出码：
#   0 通过
#   2 用法错误
#   3 缺少 python3 / 镜像
#   5 校验未通过
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATHS_CONF="${PATHS_CONF:-$SCRIPT_DIR/paths.conf}"
if [ ! -f "$PATHS_CONF" ]; then
    printf '错误: 找不到路径配置 %s（应与脚本同目录，或用 PATHS_CONF 指定）\n' "$PATHS_CONF" >&2
    exit 3
fi
# shellcheck source=paths.conf
. "$PATHS_CONF"

RUNNER="${RUNNER:-auto}"
DOCKER_USER="${DOCKER_USER:-0:0}"

TIMESTAMP=""
DEEP=0

usage() {
    cat <<'EOF'
用法: 30-verify-backup.sh [选项]

校验指定（默认最新）备份快照：manifest、数据库 SHA256、SQLite 完整性、文件快照。

选项:
  --backup-root DIR     备份目录（默认见 paths.conf）
  --timestamp TS        指定快照，格式 YYYYmmdd-HHMMSS（默认取最新）
  --deep                重新遍历文件快照并核对文件数（大库较慢）
  --runner auto|local|docker
  --image NAME          校验用镜像（默认 mybooks-local:latest）
  -h, --help            显示帮助

退出码: 0 通过 / 2 用法错误 / 3 缺少依赖 / 5 校验未通过
EOF
}

die() { printf '错误: %s\n' "$1" >&2; exit "${2:-5}"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --backup-root) BACKUP_ROOT="${2:?缺少参数}"; shift 2 ;;
        --timestamp)   TIMESTAMP="${2:?缺少参数}"; shift 2 ;;
        --deep)        DEEP=1; shift ;;
        --runner)      RUNNER="${2:?缺少参数}"; shift 2 ;;
        --image)       BACKUP_IMAGE="${2:?缺少参数}"; shift 2 ;;
        -h|--help)     usage; exit 0 ;;
        *) echo "未知参数: $1" >&2; usage; exit 2 ;;
    esac
done

[ -d "$BACKUP_ROOT" ] || die "备份目录不存在: $BACKUP_ROOT" 3
[ -d "$BACKUP_ROOT/manifests" ] || die "找不到 manifests 目录: $BACKUP_ROOT/manifests" 3

if [ -z "$TIMESTAMP" ]; then
    last="$(ls -1 "$BACKUP_ROOT/manifests"/backup-*.json 2>/dev/null | sort | tail -1 || true)"
    [ -n "$last" ] || die "没有任何 manifest，无法确定最新快照" 3
    f="${last##*/}"
    TIMESTAMP="${f#backup-}"
    TIMESTAMP="${TIMESTAMP%.json}"
fi
printf '[30-verify] 备份目录=%s 快照=%s deep=%s\n' "$BACKUP_ROOT" "$TIMESTAMP" "$DEEP"

PYTHON_CHECK='
import hashlib, json, os, sqlite3, sys

root, ts, deep = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
fail = []
warn = []

def sha256(path, buf=1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(buf)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

man_path = os.path.join(root, "manifests", "backup-%s.json" % ts)
if not os.path.isfile(man_path):
    print("[失败] manifest 不存在: %s" % man_path)
    sys.exit(5)
try:
    with open(man_path, encoding="utf-8") as f:
        man = json.load(f)
except Exception as exc:
    print("[失败] manifest 无法解析: %s" % exc)
    sys.exit(5)
print("[通过] manifest: %s" % man_path)

status = man.get("status")
if status in ("ok", "ok-with-warnings"):
    print("[通过] 状态: %s" % status)
    if status == "ok-with-warnings":
        warn.append("manifest 状态为 ok-with-warnings")
else:
    fail.append("manifest 状态异常: %s" % status)

dbs = man.get("databases") or []
if not dbs:
    fail.append("manifest 中没有数据库记录")
for entry in dbs:
    name = os.path.basename(entry.get("dest") or "")
    if not name:
        fail.append("数据库记录缺少 dest: %s" % entry.get("source"))
        continue
    path = os.path.join(root, "db", ts, name)
    if not os.path.isfile(path):
        fail.append("数据库副本不存在: %s" % path)
        continue
    if entry.get("status") != "ok":
        fail.append("%s 记录状态为 %s" % (name, entry.get("status")))
    size = os.path.getsize(path)
    if entry.get("bytes") is not None and size != entry["bytes"]:
        fail.append("%s 大小不一致: 实际 %d / 清单 %d" % (name, size, entry["bytes"]))
    if entry.get("sha256"):
        actual = sha256(path)
        if actual != entry["sha256"]:
            fail.append("%s SHA256 不一致" % name)
        else:
            print("[通过] %s SHA256 一致（%d 字节）" % (name, size))
    try:
        con = sqlite3.connect(path)
        result = con.execute("PRAGMA integrity_check").fetchone()[0]
        con.close()
    except Exception as exc:
        fail.append("%s 无法打开: %s" % (name, exc))
        result = None
    if result is None:
        pass
    elif result == "ok":
        print("[通过] %s integrity_check=ok" % name)
    else:
        fail.append("%s integrity_check=%s" % (name, result))

files = man.get("files")
snap = os.path.join(root, "files", ts)
if files is None:
    print("[提示] 本次快照未包含文件备份")
elif not os.path.isdir(snap):
    fail.append("文件快照目录不存在: %s" % snap)
else:
    print("[通过] 文件快照目录存在: %s" % snap)
    if files.get("errors"):
        warn.append("文件快照记录了 %d 个错误" % files["errors"])
    if deep:
        count = 0
        for dirpath, _dirnames, filenames in os.walk(snap):
            count += len(filenames)
        expected = files.get("files")
        if expected is not None and count != expected:
            fail.append("文件数不一致: 实际 %d / 清单 %d" % (count, expected))
        else:
            print("[通过] 文件数一致: %d" % count)

for item in warn:
    print("[警告] %s" % item)
for item in fail:
    print("[失败] %s" % item)
if fail:
    print("结论：校验未通过（失败 %d 项，警告 %d 项）" % (len(fail), len(warn)))
    sys.exit(5)
print("结论：校验通过（警告 %d 项）" % len(warn))
'

run_python() {
    if [ "$RUNNER" != "docker" ] && command -v python3 >/dev/null 2>&1; then
        python3 - "$BACKUP_ROOT" "$TIMESTAMP" "$DEEP" <<< "$PYTHON_CHECK"
        return $?
    fi
    if ! command -v docker >/dev/null 2>&1; then
        die "本机无 python3，且 docker 不可用（可用 --runner docker / 安装 python3）" 3
    fi
    if ! docker image inspect "$BACKUP_IMAGE" >/dev/null 2>&1; then
        die "镜像不存在: $BACKUP_IMAGE（先构建，或用 --image 指定）" 3
    fi
    docker run --rm -i --network none --user "$DOCKER_USER" \
        -v "$BACKUP_ROOT:/backup:ro" \
        --entrypoint python3 "$BACKUP_IMAGE" - /backup "$TIMESTAMP" "$DEEP" <<< "$PYTHON_CHECK"
}

set +e
run_python
RC=$?
set -e
if [ "$RC" -eq 0 ]; then
    printf '完成：备份 %s 校验通过。\n' "$TIMESTAMP"
else
    printf '失败：备份 %s 校验未通过（退出码 %d）。\n' "$TIMESTAMP" "$RC"
fi
exit "$RC"
