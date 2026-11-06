#!/bin/bash
set -uo pipefail

# =============================================================================
# 70-check-image.sh —— 只读检查「当前镜像/容器是否已包含覆盖包里的最新源码」
#
# 做法：
#   1) 容器在运行 -> docker exec 进容器算 sha256
#      容器未运行 -> docker run --rm --entrypoint sh 用镜像算（一次性容器）
#   2) 对照 overlay/MANIFEST.tsv 的 new_sha256，逐文件给出
#      已包含(OK) / 版本不符(DIFF) / 缺失(MISSING) / 无法计算(ERR)
#   3) 同时输出镜像 Id、创建时间、标签、容器启动时间、容器镜像与 tag 是否一致
#      （避免「构建了但没 up -d」的假阳性）
#   4) 结论行 + 退出码：0 全部包含 / 3 部分或未包含 / 1 执行错误 / 2 用法错误
#
# 只读：不 build、不 restart、不改任何文件。
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATHS_CONF="${PATHS_CONF:-$SCRIPT_DIR/paths.conf}"
if [ ! -f "$PATHS_CONF" ]; then
    printf '错误: 找不到路径配置 %s（应与脚本同目录，或用 PATHS_CONF 指定）\n' "$PATHS_CONF" >&2
    exit 1
fi
# shellcheck source=paths.conf
. "$PATHS_CONF"

OVERLAY_DIR="${OVERLAY_DIR:-$SCRIPT_DIR/../overlay}"
IMAGE="${CHECK_IMAGE:-$BACKUP_IMAGE}"
CONTAINER="${CHECK_CONTAINER:-$APP_CONTAINER}"
APP_DIR=""          # 容器内源码根目录；空=自动探测
JSON=0

usage() {
    cat <<'EOF'
用法: 70-check-image.sh [选项]

只读检查当前镜像/容器里的源码是否与覆盖包（overlay/MANIFEST.tsv）一致。
不构建、不重启、不改文件。

选项:
  --json               以 JSON 输出（便于脚本消费）
  --image NAME         检查的镜像（默认 paths.conf 的 BACKUP_IMAGE）
  --container NAME     检查的容器（默认 paths.conf 的 APP_CONTAINER）
  --app-dir DIR        容器内源码根目录（默认自动探测 /app、/var/www/mybooks 等）
  --overlay DIR        覆盖包目录（默认 ../overlay）
  -h, --help           显示帮助

退出码: 0 全部包含 / 3 部分或未包含 / 1 执行错误 / 2 用法错误
EOF
}

die() { printf '错误: %s\n' "$1" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --json)      JSON=1; shift ;;
        --image)     IMAGE="${2:?缺少参数}"; shift 2 ;;
        --container) CONTAINER="${2:?缺少参数}"; shift 2 ;;
        --app-dir)   APP_DIR="${2:?缺少参数}"; shift 2 ;;
        --overlay)   OVERLAY_DIR="${2:?缺少参数}"; shift 2 ;;
        -h|--help)   usage; exit 0 ;;
        *) printf '未知参数: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done

MANIFEST="$OVERLAY_DIR/MANIFEST.tsv"
[ -f "$MANIFEST" ] || die "覆盖包清单不存在: $MANIFEST"
command -v docker >/dev/null 2>&1 || die "未安装 docker 或不在 PATH 中"

# ---------- 镜像元信息 ----------
IMAGE_ID="$(docker inspect --format '{{.Id}}' "$IMAGE" 2>/dev/null || true)"
[ -n "$IMAGE_ID" ] || die "镜像不存在: $IMAGE（先 docker compose build，或在 60 里加 --build）"
IMAGE_CREATED="$(docker inspect --format '{{.Created}}' "$IMAGE" 2>/dev/null || true)"
IMAGE_TAGS="$(docker inspect --format '{{join .RepoTags ", "}}' "$IMAGE" 2>/dev/null || true)"

# ---------- 容器状态 ----------
C_RUNNING="$(docker inspect --format '{{.State.Running}}' "$CONTAINER" 2>/dev/null || true)"
C_EXISTS=0
[ -n "$C_RUNNING" ] && C_EXISTS=1
C_STARTED=""
C_IMAGE_ID=""
C_CONFIG_IMAGE=""
if [ "$C_EXISTS" -eq 1 ]; then
    C_STARTED="$(docker inspect --format '{{.State.StartedAt}}' "$CONTAINER" 2>/dev/null || true)"
    C_IMAGE_ID="$(docker inspect --format '{{.Image}}' "$CONTAINER" 2>/dev/null || true)"
    C_CONFIG_IMAGE="$(docker inspect --format '{{.Config.Image}}' "$CONTAINER" 2>/dev/null || true)"
fi

if [ "$C_RUNNING" = "true" ]; then
    MODE="container"
    TARGET="$CONTAINER"
    RUNNER=(docker exec -i "$CONTAINER" sh)
else
    MODE="image"
    TARGET="$IMAGE"
    RUNNER=(docker run --rm -i --entrypoint sh "$IMAGE")
fi

# ---------- 容器内源码根目录 ----------
DETECT='for d in /app /var/www/mybooks /opt/mybooks /usr/src/app /books /data/mybooks; do if [ -d "$d/webserver" ]; then printf "%s\n" "$d"; exit 0; fi; done; exit 1'
if [ -n "$APP_DIR" ]; then
    :
else
    APP_DIR="$("${RUNNER[@]}" -c "$DETECT" 2>/dev/null | tail -n 1 || true)"
    [ -n "$APP_DIR" ] || die "未能在${MODE}中找到源码目录（含 webserver/），请用 --app-dir 指定"
fi

# ---------- 容器内可用的哈希工具 ----------
HASH_TOOL="$("${RUNNER[@]}" -c 'command -v sha256sum >/dev/null 2>&1 && echo sha256sum || (command -v python3 >/dev/null 2>&1 && echo python3 || echo none)' 2>/dev/null | tail -n 1 || true)"
[ "$HASH_TOOL" != "none" ] || die "容器内既无 sha256sum 也无 python3，无法校验"

# ---------- 生成容器内检查脚本 ----------
TMP_SCRIPT="$(mktemp "${TMPDIR:-/tmp}/check70.XXXXXX")"
TMP_RESULT="$(mktemp "${TMPDIR:-/tmp}/check70r.XXXXXX")"
trap 'rm -f "$TMP_SCRIPT" "$TMP_RESULT"' EXIT

{
    printf "ROOT='%s'\n" "$APP_DIR"
    if [ "$HASH_TOOL" = "sha256sum" ]; then
        cat <<'EOS'
hashfile() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1; }
EOS
    else
        cat <<'EOS'
hashfile() { python3 -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$1" 2>/dev/null; }
EOS
    fi
    cat <<'EOS'
check() {
    p="$1"; want="$2"; f="$ROOT/$p"
    if [ ! -f "$f" ]; then printf 'MISSING\t%s\n' "$p"; return 0; fi
    got="$(hashfile "$f")"
    if [ -z "$got" ]; then printf 'ERR\t%s\n' "$p"
    elif [ "$got" = "$want" ]; then printf 'OK\t%s\n' "$p"
    else printf 'DIFF\t%s\t%s\n' "$p" "$got"; fi
}
EOS
    while IFS='|' read -r act rel mode base new; do
        case "$act" in ''|'#'*) continue ;; esac
        printf "check '%s' '%s'\n" "$rel" "$new"
    done < "$MANIFEST"
} > "$TMP_SCRIPT"

"${RUNNER[@]}" < "$TMP_SCRIPT" > "$TMP_RESULT" 2>/dev/null || die "在${MODE}内执行校验失败（docker 返回非 0）"

# ---------- 统计 ----------
n_ok=0; n_diff=0; n_missing=0; n_err=0; n_total=0
ok_list=""; diff_list=""; missing_list=""; err_list=""
while IFS=$'\t' read -r st rel extra; do
    [ -n "${st:-}" ] || continue
    n_total=$((n_total + 1))
    case "$st" in
        OK)      n_ok=$((n_ok + 1)); ok_list="$ok_list$rel"$'\n' ;;
        DIFF)    n_diff=$((n_diff + 1)); diff_list="$diff_list$rel  (容器内 $extra)"$'\n' ;;
        MISSING) n_missing=$((n_missing + 1)); missing_list="$missing_list$rel"$'\n' ;;
        *)       n_err=$((n_err + 1)); err_list="$err_list$rel"$'\n' ;;
    esac
done < "$TMP_RESULT"

[ "$n_total" -gt 0 ] || die "校验结果为空，可能容器内脚本执行异常"

if [ "$n_ok" -eq "$n_total" ]; then
    CONCLUSION="镜像已包含全部 $n_total 项优化"
    RC=0
elif [ "$n_ok" -eq 0 ]; then
    CONCLUSION="镜像未包含优化（$n_total 项全部缺失或版本不符）"
    RC=3
else
    CONCLUSION="部分包含：已包含 $n_ok 项，版本不符 $n_diff 项，缺失 $n_missing 项，无法校验 $n_err 项"
    RC=3
fi

MATCH="unknown"
if [ -n "$C_IMAGE_ID" ]; then
    if [ "$C_IMAGE_ID" = "$IMAGE_ID" ]; then MATCH="true"; else MATCH="false"; fi
fi
MATCH_J="null"
[ "$MATCH" != "unknown" ] && MATCH_J="$MATCH"

# ---------- 输出 ----------
if [ "$JSON" -eq 1 ]; then
    esc() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
    printf '{\n'
    printf '  "mode": "%s",\n' "$MODE"
    printf '  "target": "%s",\n' "$(esc "$TARGET")"
    printf '  "image": {"ref": "%s", "id": "%s", "created": "%s", "repo_tags": "%s"},\n' \
        "$(esc "$IMAGE")" "$(esc "$IMAGE_ID")" "$(esc "$IMAGE_CREATED")" "$(esc "$IMAGE_TAGS")"
    printf '  "container": {"name": "%s", "exists": %s, "running": %s, "started_at": "%s", "image_id": "%s", "matches_image_tag": %s},\n' \
        "$(esc "$CONTAINER")" "$C_EXISTS" "$([ "$C_RUNNING" = "true" ] && echo true || echo false)" \
        "$(esc "$C_STARTED")" "$(esc "$C_IMAGE_ID")" "$MATCH_J"
    printf '  "app_dir": "%s",\n' "$(esc "$APP_DIR")"
    printf '  "summary": {"total": %d, "ok": %d, "diff": %d, "missing": %d, "error": %d},\n' \
        "$n_total" "$n_ok" "$n_diff" "$n_missing" "$n_err"
    printf '  "conclusion": "%s",\n' "$(esc "$CONCLUSION")"
    printf '  "included": %s,\n' "$([ "$RC" -eq 0 ] && echo true || echo false)"
    printf '  "items": [\n'
    awk -F'\t' 'BEGIN{first=1} {if(!first)printf ",\n"; first=0;
        printf "    {\"path\": \"%s\", \"status\": \"%s\"", $2, $1;
        if ($3 != "") printf ", \"sha256\": \"%s\"", $3;
        printf "}"}' "$TMP_RESULT"
    printf '\n  ]\n}\n'
else
    echo "==== 检查对象 ===="
    printf '镜像: %s\n  Id: %s\n  创建: %s\n  标签: %s\n' "$IMAGE" "$IMAGE_ID" "$IMAGE_CREATED" "$IMAGE_TAGS"
    if [ "$C_EXISTS" -eq 1 ]; then
        printf '容器: %s（%s）\n  启动: %s\n  运行镜像 Id: %s\n' \
            "$CONTAINER" "$([ "$C_RUNNING" = "true" ] && echo 运行中 || echo 未运行)" "$C_STARTED" "$C_IMAGE_ID"
        if [ "$MATCH" = "true" ]; then
            echo "  与当前 tag: 一致"
        elif [ "$MATCH" = "false" ]; then
            echo "  与当前 tag: 不一致 —— 容器可能仍在旧镜像上（构建后未 up -d），本次结论反映的是容器里的旧代码"
        fi
    else
        printf '容器: %s（不存在，按镜像内容检查）\n' "$CONTAINER"
    fi
    printf '检查方式: %s（%s 内执行）\n源码目录: %s\n\n' \
        "$([ "$MODE" = "container" ] && echo "docker exec 进运行中的容器" || echo "docker run --rm 一次性容器")" \
        "$MODE" "$APP_DIR"

    echo "==== 逐文件结果（共 $n_total 项） ===="
    if [ -n "$ok_list" ]; then
        echo "[已包含 $n_ok]"
        printf '%s' "$ok_list" | sed 's/^/  OK      /'
    fi
    if [ -n "$diff_list" ]; then
        echo "[版本不符 $n_diff]"
        printf '%s' "$diff_list" | sed 's/^/  DIFF    /'
    fi
    if [ -n "$missing_list" ]; then
        echo "[缺失 $n_missing]"
        printf '%s' "$missing_list" | sed 's/^/  MISSING /'
    fi
    if [ -n "$err_list" ]; then
        echo "[无法计算 $n_err]"
        printf '%s' "$err_list" | sed 's/^/  ERR     /'
    fi
    echo
    echo "==== 结论 ===="
    echo "$CONCLUSION"
    if [ "$RC" -ne 0 ]; then
        echo "下一步："
        echo "  /bin/bash $SCRIPT_DIR/60-apply-overlay.sh            # 源码是否已覆盖"
        echo "  /bin/bash $SCRIPT_DIR/60-apply-overlay.sh --build    # 重建镜像并 up -d"
        echo "  /bin/bash $SCRIPT_DIR/70-check-image.sh              # 重跑本检查"
    fi
fi

exit "$RC"
