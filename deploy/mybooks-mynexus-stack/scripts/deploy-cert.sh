#!/bin/sh
# ============================================================
# deploy-cert.sh —— Let's Encrypt 证书签发 + 装进 mybooks 容器（全自动续期）
#
# 用法（域名买好后，NAS 上执行）：
#   0. 前置：先装 acme.sh（curl https://get.acme.sh | sh）并配好 DNS API 密钥
#      export Ali_Key=xxx Ali_Secret=xxx          # 阿里云；DNSPod/CF 换对应变量
#      sh deploy-cert.sh book.example.com
#   2. 完。之后 90 天证书到期前 acme.sh 自动续期 → 自动写入 ssl 目录 → 自动 reload nginx。
#      手机/电脑从此访问 https://你的域名:88 不再告警。
#
# 日常命令：
#   sh deploy-cert.sh status            # 看当前证书有效期/域名/剩余天数
#   sh deploy-cert.sh reload            # 手动把 acme.sh 暂存的新证书装入并 reload（一般不用手动）
#
# 设计要点：
#   - acme.sh 先把新证书写到暂存目录（staging），本脚本校验通过才 mv 进 ssl 目录：
#     避免把没校验过的文件直接盖掉正在用的证书。
#   - 覆盖前把当前证书滚动备份为 ssl.crt.bak / ssl.key.bak，nginx -t 不过就回滚。
#   - reload 用 `docker exec nginx -s reload`，不重启容器、阅读/播放不中断。
#
# 退出码：0 成功；1 参数/环境错误；2 证书校验失败；3 reload 失败
# ============================================================
set -eu

DOMAIN=${1:-}
ACME_HOME=${ACME_HOME:-$HOME/.acme.sh}
ACME="$ACME_HOME/acme.sh"
DATA_DIR=${DATA_DIR:-/volume1/docker/audiobook-data}
SSL_DIR="$DATA_DIR/books/ssl"
STAGE="$SSL_DIR/.staging"
CONTAINER=${CONTAINER:-mybooks}
# DNS 服务商插件：dns_ali(阿里云) | dns_dp(DNSPod) | dns_cf(Cloudflare)
DNS_PROVIDER=${DNS_PROVIDER:-dns_ali}
LE_SERVER=letsencrypt

SELF=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/$(basename -- "$0")

die() { _m=$1; _c=${2:-1}; echo "ERROR: $_m" >&2; exit "$_c"; }
say() { echo ""; echo "==> $*"; }

# ---------------- 子命令: 校验一对证书文件 ----------------
# $1=crt $2=key  通过返回 0；失败打印原因返回非 0
verify_pair() {
  _crt=$1; _key=$2
  openssl x509 -in "$_crt" -noout >/dev/null 2>&1 || { echo "crt 不是有效证书: $_crt"; return 2; }
  openssl pkey -in "$_key" -noout >/dev/null 2>&1 || { echo "key 不是有效私钥: $_key"; return 2; }
  # 公钥指纹必须一致，防止 crt 和 key 张冠李戴（nginx 会直接启动失败）
  # 注意：openssl pkey 的选项是 -pubout（-pubkey 是 x509 的，混用会解析成密码参数报错）
  a=$(openssl x509 -in "$_crt" -noout -pubkey 2>/dev/null | openssl md5 | awk '{print $NF}')
  b=$(openssl pkey -in "$_key" -pubout 2>/dev/null | openssl md5 | awk '{print $NF}')
  [ -n "$a" ] && [ "$a" = "$b" ] || { echo "crt 与 key 不配对（公钥指纹不一致）"; return 2; }
  # 剩余有效期必须为正（date 解析不了就跳过此项检查，宁可漏检不误报）
  end=$(openssl x509 -in "$_crt" -noout -enddate 2>/dev/null | sed 's/notAfter=//')
  [ -n "$end" ] || { echo "读不到有效期"; return 2; }
  end_ts=$(date -d "$end" +%s 2>/dev/null || echo "")
  if [ -n "$end_ts" ] && [ "$end_ts" -le "$(date +%s)" ]; then
    echo "证书已过期: $end"; return 2
  fi
  echo "$end"
  return 0
}

# ---------------- 子命令: deploy（由 acme.sh 续期后自动调用）----------------
do_deploy() {
  [ -f "$STAGE/ssl.crt" ] && [ -f "$STAGE/ssl.key" ] \
    || die "暂存目录没有新证书（$STAGE），acme.sh 的 --install-cert 目标路径配错了吧" 1

  say "校验暂存的新证书"
  END=$(verify_pair "$STAGE/ssl.crt" "$STAGE/ssl.key") || die "$END" 2
  SUBJ=$(openssl x509 -in "$STAGE/ssl.crt" -noout -subject)
  echo "    域名/主体: $SUBJ"
  echo "    有效期至  : $END"

  say "备份当前证书并原子替换"
  for f in crt key; do
    if [ -f "$SSL_DIR/ssl.$f" ]; then cp -p "$SSL_DIR/ssl.$f" "$SSL_DIR/ssl.$f.bak"; fi
    mv "$STAGE/ssl.$f" "$SSL_DIR/ssl.$f"
  done
  chmod 644 "$SSL_DIR/ssl.crt"; chmod 600 "$SSL_DIR/ssl.key"
  # 滚动备份里不放 key 的旧明文超过一份，避免备份目录越堆越多
  echo "    已保留上一版为 ssl.crt.bak / ssl.key.bak"

  say "nginx 配置测试"
  # 注意不能用 `docker exec ... | sed`，管道退出码取自 sed 会吞掉 nginx -t 的失败
  if docker exec "$CONTAINER" nginx -t; then
    echo "    nginx -t 通过"
  else
    say "nginx -t 失败，回滚上一版证书"
    for f in crt key; do
      if [ -f "$SSL_DIR/ssl.$f.bak" ]; then mv "$SSL_DIR/ssl.$f.bak" "$SSL_DIR/ssl.$f"; fi
    done
    docker exec "$CONTAINER" nginx -t 2>&1 | sed 's/^/    /' || true
    die "新证书装进去后 nginx 配置测试不过，已回滚。把上面输出发给作者吧。" 3
  fi

  say "热重载 nginx（不重启容器）"
  if ! docker exec "$CONTAINER" nginx -s reload; then
    die "reload 失败（nginx 未运行？容器名不对？证书文件已就位，可手动 docker exec $CONTAINER nginx -s reload）" 3
  fi
  echo "    完成。当前生效: $SUBJ / 至 $END"
}

# ---------------- 子命令: status ----------------
do_status() {
  [ -f "$SSL_DIR/ssl.crt" ] || die "还没有证书: $SSL_DIR/ssl.crt" 1
  echo "== $SSL_DIR/ssl.crt"
  openssl x509 -in "$SSL_DIR/ssl.crt" -noout -subject -issuer -dates || true
  echo ""
  if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER"; then
    echo "== 容器内实际加载的证书（nginx 内存里的）"
    docker exec "$CONTAINER" sh -c \
      "echo | openssl s_client -connect 127.0.0.1:443 -servername localhost 2>/dev/null | openssl x509 -noout -subject -enddate" 2>/dev/null \
      || echo "    （读不到，可能 nginx 未监听 443 或容器名不对）"
  fi
  echo ""
  echo "== acme.sh 续期任务"
  if [ -x "$ACME" ]; then
    "$ACME" --cron --home "$ACME_HOME" 2>&1 | tail -5 || true
  else
    echo "    （未安装 acme.sh，续期任务未注册）"
  fi
}

# ---------------- 主流程: 签发 + 安装 ----------------
do_issue() {
  [ -n "$DOMAIN" ] || die "用法: sh deploy-cert.sh 你的域名     （域名先买好、DNS 托管好）" 1
  [ -x "$ACME" ] || die "找不到 acme.sh: $ACME —— 先安装 acme.sh" 1
  command -v openssl >/dev/null 2>&1 || die "缺 openssl"
  command -v docker >/dev/null 2>&1 || die "缺 docker"
  [ -d "$SSL_DIR" ] || die "数据目录不存在: $SSL_DIR（确认 DATA_DIR）"
  docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER" \
    || die "容器不在运行: $CONTAINER（用 CONTAINER=xxx 环境变量指定）" 1

  # 环境变量探活：不同的 DNS 插件要的 key 不一样，缺了提前说，别等跑到一半才报
  case "$DNS_PROVIDER" in
    dns_ali)  [ -n "${Ali_Key:-}" ]  && [ -n "${Ali_Secret:-}" ] || die "阿里云需要 export Ali_Key=xxx Ali_Secret=xxx" 1 ;;
    dns_dp)   [ -n "${DP_Id:-}" ]    && [ -n "${DP_Key:-}" ]    || die "DNSPod 需要 export DP_Id=xxx DP_Key=xxx" 1 ;;
    dns_cf)   [ -n "${CF_Token:-}" ]                            || die "Cloudflare 需要 export CF_Token=xxx" 1 ;;
    *) : ;;   # 其它插件不拦，让 acme.sh 自己报
  esac

  mkdir -p "$STAGE"

  say "1/3 签发证书（$DOMAIN，DNS 验证，与端口无关）"
  "$ACME" --issue -d "$DOMAIN" --dns "$DNS_PROVIDER" --server "$LE_SERVER" \
          --keylength ec-256 --home "$ACME_HOME"

  say "2/3 挂载自动部署钩子（新证书先进暂存，本脚本校验后才替换）"
  # --install-cert 会把续期命令注册进 acme.sh 的 cron，以后全自动。
  # reloadcmd 必须用绝对路径，cron 环境下没有你的当前目录。
  "$ACME" --install-cert -d "$DOMAIN" --ecc --home "$ACME_HOME" \
          --fullchain-file "$STAGE/ssl.crt" \
          --key-file      "$STAGE/ssl.key" \
          --reloadcmd     "sh '$SELF' deploy"

  say "3/3 首次部署"
  sh "$SELF" deploy

  echo ""
  echo "============================================================"
  echo " 完成，以后不用再管"
  echo "------------------------------------------------------------"
  echo " 浏览器访问: https://$DOMAIN:88"
  echo "            （按你 compose 里 \"8443:443\" 的映射应为 8443，"
  echo "             端口以你实际映射为准；想改 88 就把 compose 端口改成 \"88:443\"）"
  echo " 续期      : acme.sh cron 自动（可用 'sh $0 status' 确认）"
  echo " 换证书    : 重新跑本脚本即可，旧版自动备份成 ssl.*.bak"
  echo "============================================================"
}

# ---------------- 入口 ----------------
# `sh deploy-cert.sh <域名>` 默认走签发；`sh deploy-cert.sh status|deploy` 走子命令
case "${1:-}" in
  status|deploy) ACTION=$1; DOMAIN="" ;;
  "")            die "用法: sh deploy-cert.sh 你的域名 | sh deploy-cert.sh status" 1 ;;
  *)             DOMAIN=$1; ACTION=${2:-issue} ;;
esac
case "$ACTION" in
  issue)  do_issue ;;
  deploy) do_deploy ;;
  status) do_status ;;
  *) die "未知子命令: $ACTION（可用: issue / deploy / status）" 1 ;;
esac
