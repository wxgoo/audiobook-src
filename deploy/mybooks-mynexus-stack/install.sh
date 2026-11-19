#!/usr/bin/env bash
# ============================================================================
# MyBooks + MyNexus 二合一【统一安装器】
#
# 自动识别两种场景，无需你判断：
#   · 全新安装：NAS 上没有旧 mybooks 容器、没有旧 audiobook 目录
#               → 自动建好数据目录骨架，直接起栈
#   · 老用户迁移：检测到旧容器 / 旧 audiobook 目录
#               → 自动探测真实书库、停旧栈、旧目录改名 .old，再起新栈
#
# 已内置兜住的问题（不用你操心）：
#   - bind mount 目录（mynexus-data/config、DATA_DIR/books 骨架）自动预建 + 授权
#   - 镜像本地没有就自动从旁边的离线包 docker load，不让你去 pull（绕开群晖 TLS 证书坑）
#   - DATA_DIR 自动探测 + 体检，填错会明确警告
#   - 起完容器做健康检查，没起来直接给排查命令
#
# 用法：
#   ./install.sh                # 逐步确认（推荐）
#   ./install.sh --yes          # 跳过确认，全自动
#   ./install.sh --dry-run      # 只打印计划，不实际执行
#   OLD_DIR=/path/audiobook ./install.sh   # 手动指定旧目录
#
# 前置：.env 里填好 LLM_API_KEY / AI_API_KEY（你的 OpenRouter key，私人凭证无法代填）。
#       两个离线镜像包（mybooks full + mynexus）会按需自动 load。
# ============================================================================
set -euo pipefail

# ---------- 可配置项 ----------
OLD_CONTAINER="${OLD_CONTAINER:-mybooks}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OLD_DIR="${OLD_DIR:-$SCRIPT_DIR/../audiobook}"
BACKUP_SUFFIX="${BACKUP_SUFFIX:-.old}"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
ENV_FILE="$SCRIPT_DIR/.env"

# ---------- 参数 ----------
YES=0; DRY=0
for arg in "$@"; do
  case "$arg" in
    --yes) YES=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,32p' "$0"; exit 0 ;;
    *) echo "[!] 未知参数: $arg（可用 --yes / --dry-run / --help）"; exit 1 ;;
  esac
done

# ---------- 日志 / 执行封装 ----------
log()  { printf '%s\n' "$*"; }
ok()   { printf '  [OK] %s\n' "$*"; }
warn() { printf '  [!] %s\n' "$*"; }
err()  { printf '  [X] %s\n' "$*"; }
step() { printf '\n==> %s\n' "$*"; }
run() {
  if [ "$DRY" = 1 ]; then printf '  [DRY-RUN] '; printf '%q ' "$@"; printf '\n'
  else "$@"; fi
}
confirm() {
  [ "$YES" = 1 ] && return 0
  [ "$DRY" = 1 ] && return 0
  printf '\n>>> %s [y/N] ' "$1"; read -r ans
  case "$ans" in y|Y|yes|YES) return 0 ;; *) log "已取消。"; exit 0 ;; esac
}
die() { err "$1"; shift; [ $# -gt 0 ] && printf '%s\n' "$@"; exit 1; }

# 从 .env 读某个 key（去引号/去 \r）
env_get() {
  grep -E "^[[:space:]]*$1=" "$ENV_FILE" | head -1 \
    | sed "s/^[^=]*=//; s/^[\"']//; s/[\"']$//" | tr -d '\r'
}

# ---------- 0. 前置检查 ----------
step "前置检查"
command -v docker >/dev/null 2>&1 || die "找不到 docker 命令，请在能运行 docker 的用户下执行。"
[ -f "$COMPOSE_FILE" ] || die "找不到 $COMPOSE_FILE"
[ -f "$ENV_FILE" ]    || die "找不到 $ENV_FILE"
ok "docker 可用，compose 与 .env 就位"

# ---------- 工具：书库判定 ----------
looks_like_library() {
  local d="$1"
  [ -d "$d/books/settings" ] && return 0
  [ -d "$d/books/library" ] && return 0
  [ -f "$d/books/search_index.db" ] && return 0
  return 1
}
count_books() {
  local lib="$1/books/library"
  [ -d "$lib" ] && find "$lib" -mindepth 1 -maxdepth 1 2>/dev/null | wc -l | tr -d ' ' || printf '0'
}

# ============ 1. 自动判定场景 ============
step "1/7 判定安装场景"
HAS_OLD_CONTAINER=0
HAS_OLD_DIR=0
docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$OLD_CONTAINER" && HAS_OLD_CONTAINER=1
[ -d "$OLD_DIR" ] && HAS_OLD_DIR=1

if [ "$HAS_OLD_CONTAINER" = 1 ] || [ "$HAS_OLD_DIR" = 1 ]; then
  MODE="migrate"; log "  检测到旧部署 → 场景：老用户迁移"
  [ "$HAS_OLD_CONTAINER" = 1 ] && log "    · 旧容器 $OLD_CONTAINER 存在"
  [ "$HAS_OLD_DIR" = 1 ] && log "    · 旧目录 $OLD_DIR 存在"
else
  MODE="fresh"; log "  未检测到旧部署 → 场景：全新安装"
fi

# ============ 2. 确定 DATA_DIR ============
step "2/7 确定数据目录 DATA_DIR"
DATA_DIR=""
ENV_DEFAULT="$(env_get DATA_DIR)"

# 探测顺序：旧容器挂载 → 旧目录 .env → 扫同级候选书库
if [ "$HAS_OLD_CONTAINER" = 1 ]; then
  CAND="$(docker inspect "$OLD_CONTAINER" \
    --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}' 2>/dev/null || true)"
  [ -n "$CAND" ] && DATA_DIR="$CAND" && ok "从旧容器探测到: $DATA_DIR"
fi
if [ -z "$DATA_DIR" ] && [ -f "$OLD_DIR/.env" ]; then
  CAND="$(grep -E '^[[:space:]]*DATA_DIR=' "$OLD_DIR/.env" | head -1 \
    | sed 's/^[^=]*=//; s/^["'"'"']//; s/["'"'"']$//' | tr -d '\r')"
  [ -n "$CAND" ] && DATA_DIR="$CAND" && ok "从旧 .env 读到: $DATA_DIR"
fi
if [ -z "$DATA_DIR" ] && [ "$MODE" = migrate ]; then
  PARENT="$(dirname "$OLD_DIR")"
  for d in "$PARENT"/*; do
    [ -d "$d" ] || continue
    if looks_like_library "$d"; then
      log "    候选书库: $d  (书数: $(count_books "$d"))"
      [ -z "$DATA_DIR" ] && DATA_DIR="$d"
    fi
  done
  [ -n "$DATA_DIR" ] && ok "扫描候选选中: $DATA_DIR"
fi

# 没探测到：全新安装用 .env 预填值；迁移则让用户确认
if [ -z "$DATA_DIR" ]; then
  if [ "$MODE" = fresh ]; then
    DATA_DIR="$ENV_DEFAULT"
    ok "全新安装，采用 .env 预填值: $DATA_DIR"
  else
    warn "迁移模式下没能探测到书库，请手动输入书库绝对路径。"
    printf '  书库路径（直接回车用 .env 值 [%s]）: ' "$ENV_DEFAULT"
    read -r DATA_DIR
    [ -z "$DATA_DIR" ] && DATA_DIR="$ENV_DEFAULT"
  fi
fi

# 绝对路径校验
case "$DATA_DIR" in
  /*) ;;
  *) die "DATA_DIR 必须是绝对路径，收到: [$DATA_DIR]。请在 .env 里改成 / volume1/... 这种绝对路径。" ;;
esac

# 体检 / 自动建骨架
if [ -d "$DATA_DIR" ]; then
  if looks_like_library "$DATA_DIR"; then
    ok "书库体检通过: $DATA_DIR (书数: $(count_books "$DATA_DIR"))"
  elif [ "$MODE" = fresh ]; then
    ok "数据目录已存在（全新安装，稍后建书库骨架）: $DATA_DIR"
  else
    warn "⚠ $DATA_DIR 看起来不像书库（无 books/settings 或 books/library）。"
    confirm "确认用这个路径吗？填错会导致书库为空。"
  fi
else
  if [ "$MODE" = fresh ]; then
    ok "数据目录不存在，稍后自动创建: $DATA_DIR"
  else
    warn "⚠ 迁移模式但数据目录不存在: $DATA_DIR（将创建空书库，原有书不会自动出现）"
    confirm "确认继续吗？"
  fi
fi

# 若数据目录恰好在旧程序目录内，改名后路径要跟着改
if [ "$MODE" = migrate ] && [ -d "$OLD_DIR" ]; then
  OLD_ABS="$(cd "$OLD_DIR" 2>/dev/null && pwd)"
  case "$DATA_DIR" in
    "$OLD_ABS"/*)
      NEW_DATA="${OLD_ABS}${BACKUP_SUFFIX}${DATA_DIR#$OLD_ABS}"
      warn "数据目录在旧程序目录内，改名后变为: $NEW_DATA"
      DATA_DIR="$NEW_DATA" ;;
  esac
fi
ok "最终 DATA_DIR = $DATA_DIR"

# ============ 3. 配置检查 / 生成 ============
step "3/7 检查 LLM Key 与 API Token"
LLM_KEY="$(env_get LLM_API_KEY)"
AI_KEY="$(env_get AI_API_KEY)"
if printf '%s' "$LLM_KEY" | grep -q '在这里填\|^[[:space:]]*$'; then
  warn "LLM_API_KEY 还是占位符：MyBooks 正常用，但 AI 伴读/解析不工作。"
else
  ok "LLM_API_KEY 已填写"
fi
if [ -n "$AI_KEY" ] && ! printf '%s' "$AI_KEY" | grep -q '在这里填\|^[[:space:]]*$'; then
  ok "AI_API_KEY 已填写（全局 AI 助手）"
fi

TOKEN="$(env_get MYNEXUS_API_TOKEN)"
if printf '%s' "$TOKEN" | grep -q 'please-change-me\|^[[:space:]]*$'; then
  if command -v openssl >/dev/null 2>&1; then NEWTOKEN="$(openssl rand -hex 24)"
  else NEWTOKEN="mynx-$(date +%s)-$$-$(head -c6 /dev/urandom | od -An -tx1 | tr -d ' \n')"; fi
  ok "自动生成随机 token（长度 ${#NEWTOKEN}）"
  [ "$DRY" = 0 ] && sed -i.bak "s|^[[:space:]]*MYNEXUS_API_TOKEN=.*|MYNEXUS_API_TOKEN=$NEWTOKEN|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
else
  ok "MYNEXUS_API_TOKEN 已配置"
fi
# 写回 DATA_DIR
if [ "$DRY" = 0 ]; then
  sed -i.bak "s|^[[:space:]]*DATA_DIR=.*|DATA_DIR=$DATA_DIR|" "$ENV_FILE" && rm -f "${ENV_FILE}.bak"
fi
ok "DATA_DIR 已写入 .env"

# ============ 4. 预建所有 bind mount 目录（关键：群晖不会自动建）============
step "4/7 预建挂载目录并授权"
PUID_VAL="$(env_get PUID)"; [ -z "$PUID_VAL" ] && PUID_VAL=1026
PGID_VAL="$(env_get PGID)"; [ -z "$PGID_VAL" ] && PGID_VAL=100

# 需要存在的目录：数据目录骨架 + mynexus 两个挂载点
DIRS_TO_MAKE="$DATA_DIR/books/settings $DATA_DIR/books/library $SCRIPT_DIR/mynexus-data $SCRIPT_DIR/mynexus-config"
for d in $DIRS_TO_MAKE; do
  if [ ! -d "$d" ]; then run mkdir -p "$d"; ok "已创建 $d"
  else ok "已存在 $d"; fi
done
if [ "$DRY" != 1 ]; then
  for d in $DIRS_TO_MAKE; do
    chown -R "${PUID_VAL}:${PGID_VAL}" "$d" 2>/dev/null \
      || warn "授权失败（可手动 chown -R ${PUID_VAL}:${PGID_VAL} $d）"
  done
fi

# ============ 5. 镜像准备（本地优先，缺失自动从离线包 load）============
step "5/7 检查镜像（本地优先，缺失自动导入离线包）"
ensure_image() {
  local tag="$1"; shift
  local tars=("$@")
  if docker image inspect "$tag" >/dev/null 2>&1; then
    ok "本地已有镜像: $tag"; return 0
  fi
  log "本地无 $tag，查找离线包..."
  local found=""
  for t in "${tars[@]}"; do
    for cand in "$SCRIPT_DIR/$t" "$SCRIPT_DIR/../$t"; do
      [ -f "$cand" ] && found="$cand" && break 2
    done
  done
  if [ -n "$found" ]; then
    log "从离线包导入: $found"
    if [ "$DRY" = 1 ]; then run sh -c "gunzip -c '$found' | docker load"
    else
      gunzip -c "$found" | docker load || die "镜像导入失败: $found"
      ok "已导入: $tag"
    fi
    return 0
  fi
  die "缺少镜像 $tag，且未找到任何离线包（${tars[*]}）。请把离线镜像包放到本目录后重跑。" \
      "  群晖直连 Docker Hub 常有 x509 证书错误，务必用离线包，不要在线 pull。"
}
MYBOOKS_TAG="$(env_get MYBOOKS_IMAGE)"; [ -z "$MYBOOKS_TAG" ] && MYBOOKS_TAG="mybooks:4.7.0-build.09-full"
MYNEXUS_TAG="$(env_get MYNEXUS_IMAGE)"; [ -z "$MYNEXUS_TAG" ] && MYNEXUS_TAG="poxenstudio/mynexus:latest"
ensure_image "$MYBOOKS_TAG" "mybooks-image-4.7.0-build.09-full.tar.gz"
ensure_image "$MYNEXUS_TAG" "mynexus-image-latest.tar.gz"

# ============ 6. 停旧栈 + 改名（仅迁移）============
step "6/7 处理旧部署"
if [ "$MODE" = migrate ]; then
  if [ -f "$OLD_DIR/docker-compose.yml" ] || [ -f "$OLD_DIR/compose.yml" ]; then
    ok "旧目录执行 docker compose down"
    if [ "$DRY" = 1 ]; then run docker compose -f "$OLD_DIR/docker-compose.yml" down
    else (cd "$OLD_DIR" && docker compose down) || warn "compose down 有报错，继续兜底停容器"; fi
  fi
  if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -qx "$OLD_CONTAINER"; then
    run docker stop "$OLD_CONTAINER" || true
    run docker rm "$OLD_CONTAINER" || true
    ok "旧容器 $OLD_CONTAINER 已移除"
  else
    ok "旧容器 $OLD_CONTAINER 不存在"
  fi
  if [ -d "$OLD_DIR" ]; then
    if [ -e "${OLD_DIR}${BACKUP_SUFFIX}" ]; then
      warn "${OLD_DIR}${BACKUP_SUFFIX} 已存在，跳过改名"
    else
      run mv "$OLD_DIR" "${OLD_DIR}${BACKUP_SUFFIX}"
      ok "旧目录改名为 $(basename "$OLD_DIR")${BACKUP_SUFFIX}"
    fi
  else
    ok "旧目录不存在，无需改名"
  fi
else
  ok "全新安装，跳过旧部署处理"
fi

# ============ 7. 启动 + 健康检查 ============
step "7/7 启动并健康检查"
run docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d
if [ "$DRY" = 1 ]; then
  run docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps
else
  # 等待容器起来（最多 40 秒）
  ok "等待容器启动..."
  sleep 5
  HEALTHY=0
  for i in $(seq 1 7); do
    ST_MB="$(docker inspect -f '{{.State.Status}}' mybooks 2>/dev/null || true)"
    ST_MX="$(docker inspect -f '{{.State.Status}}' mynexus 2>/dev/null || true)"
    if [ "$ST_MB" = running ] && [ "$ST_MX" = running ]; then HEALTHY=1; break; fi
    sleep 5
  done
  run docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps
  if [ "$HEALTHY" = 1 ]; then
    ok "两个容器均已启动（Status: running）"
  else
    warn "⚠ 容器未在预期时间内进入 running，请排查："
    log "    docker logs mybooks --tail 50"
    log "    docker logs mynexus --tail 50"
    log "    docker compose -f '$COMPOSE_FILE' ps"
    warn "常见原因：端口 9800/8443/3000 被占用、数据目录权限、镜像不完整。"
  fi
fi

log ""
log "==================== 部署完成 ===================="
log "  场景      : $([ "$MODE" = fresh ] && echo '全新安装' || echo '老用户迁移')"
log "  MyBooks   : http://你的NAS_IP:9800   (HTTPS: 8443)"
log "  MyNexus   : http://你的NAS_IP:3000   (首次 admin/admin，立刻改密码)"
log "  数据目录  : $DATA_DIR"
[ "$MODE" = migrate ] && log "  旧目录备份: ${OLD_DIR}${BACKUP_SUFFIX}"
log ""
log "下一步："
log "  1. 打开 https://你的NAS_IP:8443 设置页，确认 MyNexus 三项已自动填好"
log "  2. 若没填 Key：vi .env 填 LLM_API_KEY 和 AI_API_KEY，再 docker compose up -d"
log "  3. 顶部 AI 助手 / 书详情页 AI 伴读 均可用（麦克风语音输入需 HTTPS）"
log "  4. 语音首次用会下 whisper 模型（走 hf-mirror），可在 docker logs 看进度"
