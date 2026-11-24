#!/usr/bin/env bash
# ============================================================================
# MyBooks + MyNexus 一键安装 / 升级（保住你上次填的 key）
#
# 它把《从这里开始.md》里的步骤 1~4 串成一条命令，专治两件事：
#   1) 手动解压 deploy-stack.tar.gz 会覆盖老 deploy-stack/.env（你的真 key 没了）；
#   2) 每次升级都要重新敲一堆 docker load / install.sh 命令。
#
# 用法：把本脚本和三个 tar.gz（+ 各自 .sha256）放同一目录，然后：
#   bash onekey-install.sh
#
# 它依次做：
#   1/5 校验三个包 sha256（传输出错直接停，不带着坏包装）
#   2/5 把老 deploy-stack 改名为 deploy-stack.old（这样新 .env 不会覆盖你的 key；
#       若 deploy-stack.old 已存在，轮转为带时间戳的目录，不删你任何东西）
#   3/5 解压新的 deploy-stack.tar.gz
#   4/5 导入两个离线镜像（按【包内容 sha256】判断，不看 tag：
#       历次修复共用同一个 .09 tag，光看 tag 会把旧的带 bug 镜像当成最新而跳过；
#       现在换了包就强制 load，同一包重复跑才跳过。load 是幂等的，不会堆积层。）
#   5/5 进入新目录调用 install.sh；它会自动从 deploy-stack.old/.env 继承 key/token
#
# 全新安装也能用：没有老 deploy-stack 时就跳过改名，照常提示输入 key。
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK="$SCRIPT_DIR/deploy-stack"
OLD_STACK="$SCRIPT_DIR/deploy-stack.old"
DEPLOY_TAR="deploy-stack.tar.gz"
MYBOOKS_TAR="mybooks-image-4.7.0-build.09-full-autosplit.tar.gz"
MYNEXUS_TAR="mynexus-image-latest.tar.gz"

log()  { printf '%s\n' "$*"; }
ok()   { printf '  [OK] %s\n' "$*"; }
warn() { printf '  [!] %s\n' "$*"; }
die()  { printf '  [X] %s\n' "$*" >&2; exit 1; }
step() { printf '\n==> %s\n' "$*"; }

# ---------- 前置 ----------
step "前置检查"
command -v docker >/dev/null 2>&1 || die "找不到 docker 命令，请在能跑 docker 的用户下执行。"
for f in "$DEPLOY_TAR" "$MYBOOKS_TAR" "$MYNEXUS_TAR"; do
  [ -f "$SCRIPT_DIR/$f" ] || die "缺少文件: $f —— 请把本脚本和三个 tar.gz 放同一目录。"
done
ok "docker 可用，三个安装包就位"

# ---------- 1/5 校验 ----------
step "1/5 校验安装包完整性"
for f in "$DEPLOY_TAR" "$MYBOOKS_TAR" "$MYNEXUS_TAR"; do
  if [ -f "$SCRIPT_DIR/$f.sha256" ]; then
    (cd "$SCRIPT_DIR" && sha256sum -c "$f.sha256") >/dev/null 2>&1 \
      && ok "$f 校验通过" \
      || die "$f 校验失败——文件可能在传输中损坏，请重新拷贝后再跑。"
  else
    warn "$f.sha256 不存在，跳过（建议连同校验文件一起拷贝）"
  fi
done

# ---------- 2/5 处理老目录（关键：先改名再解压）----------
step "2/5 处理老部署目录（保住 .env 里的 key）"
if [ -e "$STACK" ]; then
  if [ -e "$OLD_STACK" ]; then
    STAMP="$(date +%Y%m%d_%H%M%S)"
    ROT="${OLD_STACK}.${STAMP}"
    mv "$OLD_STACK" "$ROT"
    ok "旧的 deploy-stack.old 已轮转为 $(basename "$ROT")（没删任何东西）"
  fi
  mv "$STACK" "$OLD_STACK"
  ok "老目录已改名为 deploy-stack.old —— 你的 key 安全了，install.sh 会从这里继承"
else
  ok "没有老 deploy-stack 目录，按全新安装处理"
fi

# ---------- 3/5 解压 ----------
step "3/5 解压新部署包"
tar -xzf "$SCRIPT_DIR/$DEPLOY_TAR" -C "$SCRIPT_DIR"
[ -f "$STACK/install.sh" ] || die "解压后没找到 deploy-stack/install.sh，包可能不完整。"
ok "新的 deploy-stack/ 已就位"

# ---------- 4/5 导入镜像 ----------
# 关键：不能只看 tag。历次修复都沿用同一个 .09 tag，仅镜像 ID 变了，
# 若"本机 Docker 有 tag 就跳过"，旧的带 bug 镜像会骗过检查，新修复根本没 load 进去。
# 判断依据改为【包内容 sha256】：本机 Docker 有 tag 且该包确实导入过（标记一致）才跳过；
# 换了新包（哪怕同 tag）sha 变化 → 强制重新 load。docker load 本身是幂等的，
# 同一镜像重复 load 只会覆盖 tag 指向，不会堆积层，放心执行。
step "4/5 导入离线镜像（按包内容判断是否为最新，不看 tag）"
read_env_val() {
  grep -E "^[[:space:]]*$1=" "$STACK/.env" 2>/dev/null | head -1 \
    | sed "s/^[^=]*=//; s/^[\"']//; s/[\"']$//" | tr -d '\r'
}
ensure_image() {
  local tag="$1" file="$2"
  local pkg="$SCRIPT_DIR/$file"
  local marker="$SCRIPT_DIR/.loaded-$(echo "$file" | sed 's/\.tar\.gz$//').sha256"
  if [ -z "$tag" ]; then
    warn "没读到镜像 tag，跳过 $file 预导入（install.sh 会兜底）"; return 0
  fi
  if [ ! -f "$pkg" ]; then
    # 没有离线包时，只能退而求其次看本地 tag（并提醒风险）
    if docker image inspect "$tag" >/dev/null 2>&1; then
      warn "没找到 $file，只能沿用本机 Docker 已有的 $tag —— 若那是旧镜像，本次修复不会生效！建议补齐离线包。"
    else
      die "本机 Docker 无 $tag，且缺少 $file，无法导入镜像。请把离线包放到本目录后重跑。"
    fi
    return 0
  fi
  local cur_sha
  cur_sha="$(sha256sum "$pkg" | awk '{print $1}')"
  local local_exists=1 old_id=""
  if docker image inspect "$tag" >/dev/null 2>&1; then
    old_id="$(docker image inspect -f '{{.Id}}' "$tag" 2>/dev/null || true)"
  else
    local_exists=0
  fi
  if [ "$local_exists" = 1 ] && [ -f "$marker" ] && [ "$(cat "$marker" 2>/dev/null)" = "$cur_sha" ]; then
    ok "本机 Docker 已装 $tag（sha 匹配本包），跳过重复导入"
    return 0
  fi
  # 需要导入：换包 / 首次 / 标记丢失 —— 即便 tag 已存在也强制 load
  if [ "$local_exists" = 1 ]; then
    log "  本机 Docker 中已有同名镜像 $tag，但离线包内容已更新（同 tag 不同镜像），强制导入最新离线包..."
  else
    log "  本机 Docker 中还没有 $tag，正在从 $file 导入（约几十秒）..."
  fi
  gunzip -c "$pkg" | docker load || die "镜像导入失败: $file"
  printf '%s' "$cur_sha" > "$marker"
  ok "已导入最新镜像 $tag，并记录包校验值（sha ${cur_sha:0:12}...）"
  # 清理被顶替的旧镜像：docker load 遇到同名 tag 不会删旧镜像，只会把它的
  # tag 摘掉变成 <none> 悬空镜像继续占空间（就是日志里 "renaming ... to empty string"）。
  # 这里按旧 ID 精确删除；docker rmi 对仍被其它 tag/容器引用的镜像会自动拒绝，
  # 所以不会误删有用的镜像。
  if [ -n "$old_id" ]; then
    local new_id
    new_id="$(docker image inspect -f '{{.Id}}' "$tag" 2>/dev/null || true)"
    if [ -n "$new_id" ] && [ "$new_id" != "$old_id" ]; then
      if docker rmi "$old_id" >/dev/null 2>&1; then
        ok "已清理被顶替的旧镜像 ${old_id#sha256:}（约几 GB 空间）"
      else
        log "  旧镜像 ${old_id#sha256:} 仍被其它 tag/容器引用，已保留（未误删）"
      fi
    fi
  fi
}
ensure_image "$(read_env_val MYBOOKS_IMAGE)" "$MYBOOKS_TAR"
ensure_image "$(read_env_val MYNEXUS_IMAGE)" "$MYNEXUS_TAR"

# ---------- 5/5 调用 install.sh ----------
step "5/5 交给 install.sh 完成安装"
log "  接下来 install.sh 会：探测书库 → 继承旧 key → 起容器 → 健康检查。"
log "  如果提示输入 key，说明没找到旧 key，按它的提示填即可（全新安装属正常）。"
log ""
cd "$STACK"
bash ./install.sh
