#!/bin/sh
# ============================================================
# pack-image.sh —— 把本机已构建好的镜像打成「可直接分发给他人」的离线包
#
#   sh pack-image.sh                 # 自动从镜像里读版本号
#   sh pack-image.sh 4.6.0-build.27-r30
#   IMG=mybooks-local:latest OUT_ROOT=/volume1/docker/audiobook-delivery sh pack-image.sh
#
# 产物（一个目录，整目录拷给别人即可）：
#   mybooks-image-<版本>/
#     ├── mybooks-image-<版本>.tar.gz   # docker load 即用，无需构建、无需联网
#     ├── docker-compose.yml            # 已去掉 build 段，只认镜像
#     ├── .env.example                  # 端口/PUID/PGID/数据目录
#     ├── README-部署.md                 # 三步启动 + 已知坑
#     └── SHA256SUMS
#
# 这个脚本**只装程序**：镜像里的 /data 是 VOLUME，书库、音频、站点数据库、
# 账号密码全部运行时落在宿主机挂载目录，不在镜像层里。
# 所以它适合「给别人装一套新站」，**不能**当作你自己站的灾备——
# 你自己的数据请用 scripts/backup.sh。
#
# 退出码：0 成功；1 参数/环境错误；2 安全扫描拦下（发现疑似真实数据）；3 打包失败
# ============================================================
set -eu

IMG=${IMG:-mybooks-local:latest}
OUT_ROOT=${OUT_ROOT:-/volume1/docker/audiobook-delivery}
GZIP_LEVEL=${GZIP_LEVEL:-1}      # 1=快（层本来就压过，再压收益很小）；9=最小
KEEP_TAR=${KEEP_TAR:-0}          # 1=保留未压缩 tar

die() { _m=$1; _c=${2:-1}; echo "ERROR: $_m" >&2; exit "$_c"; }
say() { echo ""; echo "==> $*"; }

# ---------------- 0. 环境 ----------------
command -v docker >/dev/null 2>&1 || die "找不到 docker"
docker image inspect "$IMG" >/dev/null 2>&1 || die "镜像不存在: $IMG（先 docker compose build）"

VER=${1:-}
if [ -z "$VER" ]; then
  VER=$(docker run --rm --network none "$IMG" sh -c \
        'sed -n "s/^VERSION = \"\\(.*\\)\"/\\1/p" /var/www/mybooks/webserver/version.py' 2>/dev/null || true)
  [ -n "$VER" ] || die "读不到镜像内版本号，请显式传入，如：sh pack-image.sh 4.6.0-build.27-r30"
  echo "从镜像内读到版本：$VER"
fi

SAFE_VER=$(printf '%s' "$VER" | tr '/: ' '___')
WORK="$OUT_ROOT/mybooks-image-$SAFE_VER"

echo "镜像    : $IMG"
echo "版本    : $VER"
echo "输出    : $WORK"

# ---------------- 0.5 磁盘空间 ----------------
# docker save 期间要落地一个和镜像等大的 tar，峰值占用约等于镜像大小，
# 写到一半空间不足会留下半个文件，且 docker 报错信息很难看懂，所以先挡。
RAW_IMG_MB=$(docker image inspect "$IMG" --format '{{.Size}}' 2>/dev/null | awk '{printf "%d", $1/1048576}')
if [ -n "$RAW_IMG_MB" ] && [ "$RAW_IMG_MB" -gt 0 ]; then
  PARENT=$(dirname "$OUT_ROOT")
  [ -d "$PARENT" ] || PARENT=$(dirname "$PARENT")
  AVAIL_MB=$(df -m "$PARENT" 2>/dev/null | awk 'NR==2{print $4}')
  NEED_MB=$((RAW_IMG_MB + 512))
  echo "镜像大小: ${RAW_IMG_MB} MB；$PARENT 可用: ${AVAIL_MB:-未知} MB"
  if [ -n "${AVAIL_MB:-}" ] && [ "$AVAIL_MB" -lt "$NEED_MB" ]; then
    die "磁盘空间不足：$PARENT 剩 ${AVAIL_MB}MB，本次预计需要 ${NEED_MB}MB。清理旧包或改 OUT_ROOT 到别的盘。" 1
  fi
fi

# ---------------- 1. 安全扫描 ----------------
# 目的只有一个：确认镜像层里没有混进真实书籍/音频/站点配置。
# 任何一项命中就中止——分发出去就收不回来了。
say "安全扫描（镜像内是否夹带真实数据）"

SCAN=$(cat <<'SCANEOF'
fail=0
echo "--- /prebuilt 与 /data 体积"
du -sh /prebuilt /data 2>/dev/null || true

echo "--- 疑似书籍/音频文件（>200KB，排除 logo/avatar）"
hits=$(find /prebuilt /data -type f \
        \( -iname "*.epub" -o -iname "*.mobi" -o -iname "*.azw3" -o -iname "*.pdf" \
        -o -iname "*.mp3" -o -iname "*.m4b" -o -iname "*.m4a" -o -iname "*.flac" -o -iname "*.wav" \) \
        -size +200k 2>/dev/null | grep -v -E "/(logo|avatar)/" | head -20)
if [ -n "$hits" ]; then
  echo "!! 发现疑似内容文件："
  echo "$hits"
  fail=1
else
  echo "OK 无大于 200KB 的内容文件"
fi

echo "--- settings 里是否写了真实密钥/口令"
leak=""
for f in /prebuilt/books/settings/*.py /data/books/settings/*.py; do
  [ -f "$f" ] || continue
  # 匹配 形如  XXX_TOKEN = "非空值" / 'password': '非空'
  m=$(grep -nE "(smtp_password|SMTP_PASSWORD|AI_DEEPSEEK_API_KEY|AI_MCP_TOKEN|BOOKBARN_TOKEN|MYNEXUS_TOKEN|cookie_secret|DOUBAN_API_KEY)[^=:]*[=:][[:space:]]*[\"'][^\"']{6,}" "$f" 2>/dev/null || true)
  if [ -n "$m" ]; then leak="$leak
$f: $m"; fi
done
if [ -n "$leak" ]; then
  echo "!! settings 里有非空密钥："
  echo "$leak"
  fail=1
else
  echo "OK settings 无硬编码密钥"
fi

echo "--- 站点数据库"
dbs=$(find /prebuilt /data -maxdepth 3 \( -name "*.db" -o -name "*.sqlite" -o -name "*.sqlite3" \) 2>/dev/null | head -10)
if [ -n "$dbs" ]; then
  echo "说明：以下为构建期生成的空库（含默认管理员账号，交付后须改密）"
  echo "$dbs" | while read -r d; do
    sz=$(wc -c < "$d" 2>/dev/null || echo 0)
    echo "    $d = ${sz} 字节"
  done
else
  echo "OK 无预置数据库"
fi

echo "--- 用户数据目录是否为空"
for d in /prebuilt/books/library /data/books/library; do
  if [ -d "$d" ]; then
    n=$(find "$d" -mindepth 1 -maxdepth 2 2>/dev/null | wc -l | tr -d ' ')
    echo "    $d 条目数 = $n"
    if [ "$n" -gt 0 ]; then echo "!! $d 非空，疑似带书"; fail=1; fi
  fi
done

echo "--- 版本号"
cat /var/www/mybooks/webserver/version.py 2>/dev/null || true

echo "SCAN_RESULT=$fail"
SCANEOF
)

SCAN_OUT=$(printf '%s\n' "$SCAN" | docker run --rm -i --network none --entrypoint /bin/sh "$IMG" -s 2>&1 || true)
printf '%s\n' "$SCAN_OUT" | sed 's/^/    /'

case "$SCAN_OUT" in
  *"SCAN_RESULT=0"*) echo "    扫描通过" ;;
  *"SCAN_RESULT="*)  die "安全扫描未通过（见上方 !! 行）。镜像里疑似夹带真实数据，已中止，未产出任何文件。" 2 ;;
  *) echo "!! 扫描脚本本身没跑完（镜像里可能没有 /bin/sh，或 docker 拒绝执行）。原始输出见上，请人工确认后再重试。" >&2
     exit 2 ;;
esac

# ---------------- 2. 打标签 ----------------
# 换成本项目专属 tag，避免和对方机器上已有的 mybooks-local:latest 冲突
DELIVER_IMG="mybooks:$SAFE_VER"
say "打交付标签 $IMG -> $DELIVER_IMG"
docker tag "$IMG" "$DELIVER_IMG"

# ---------------- 3. 导出 ----------------
mkdir -p "$WORK"
TAR="$WORK/mybooks-image-$SAFE_VER.tar"
GZ="$TAR.gz"

say "docker save（这一步慢，2-3GB 需要几分钟）"
rm -f "$TAR" "$GZ"
docker save -o "$TAR" "$DELIVER_IMG" || die "docker save 失败" 3

say "压缩（gzip -$GZIP_LEVEL）"
gzip -"$GZIP_LEVEL" -f "$TAR" || die "gzip 失败" 3
[ "$KEEP_TAR" = "1" ] || rm -f "$TAR"

RAW_IMG_MB=$(docker image inspect "$DELIVER_IMG" --format '{{.Size}}' 2>/dev/null | awk '{printf "%.0f", $1/1048576}')
PKG_MB=$(du -m "$GZ" 2>/dev/null | awk '{print $1}')

# ---------------- 4. 生成配套文件 ----------------
say "生成 compose / env / README"

cat > "$WORK/docker-compose.yml" <<'YAMLEOF'
# mybooks 交付版 compose
# 与作者本机的区别：这里**只有 image，没有 build**，不依赖源码，也不需要联网构建。
services:
  mybooks:
    image: ${IMAGE_TAG}
    container_name: ${CONTAINER_NAME:-mybooks}
    restart: always
    # 保留此项：部分老内核 + 新版 glibc 组合下 docx->pdf 会因 getrandom 崩溃，
    # 该选项无害，去掉也无妨，详见 README。
    security_opt:
      - seccomp:unconfined
    volumes:
      # ★ 全部数据都在这一个目录里：书库、音频、数据库、设置、日志。
      #   备份就备份它；换机就搬它；删容器不会伤到它。
      - ${DATA_DIR}:/data
    ports:
      - "${HTTP_PORT:-9800}:80"
    environment:
      - PUID=${PUID}
      - PGID=${PGID}
      - TZ=${TZ:-Asia/Shanghai}

# 不用 docker compose，直接命令行等价于：
#   docker run -d --name mybooks --restart always \
#     --security-opt seccomp=unconfined \
#     -v /你的/数据目录:/data -p 9800:80 \
#     -e PUID=$(id -u) -e PGID=$(id -g) -e TZ=Asia/Shanghai \
#     @IMAGE_TAG@
YAMLEOF

cat > "$WORK/.env.example" <<ENVEOF
# 复制一份改名 .env，按自己环境改。docker compose 会自动读取。
IMAGE_TAG=$DELIVER_IMG

# 数据目录（绝对路径最稳）。空目录即可，首次启动自动初始化。
DATA_DIR=./data

# 宿主机端口。被占用就换，比如 9801。
HTTP_PORT=9800

# 群晖/威联通：SSH 里执行 id 你的用户名 拿 UID/GID，常见 1026/100。
# Linux 普通用户通常是 1000/1000。填错会导致「上传不了书 / 设置存不下」。
PUID=1000
PGID=1000

TZ=Asia/Shanghai
ENVEOF

sed -i.bak "s|@IMAGE_TAG@|$DELIVER_IMG|g" "$WORK/docker-compose.yml" 2>/dev/null || \
  sed -i '' "s|@IMAGE_TAG@|$DELIVER_IMG|g" "$WORK/docker-compose.yml"
rm -f "$WORK/docker-compose.yml.bak"

cat > "$WORK/README-部署.md" <<READMEEOF
# mybooks 部署说明（镜像离线包）

版本：\`$VER\`
镜像：\`$DELIVER_IMG\`
包大小：约 ${PKG_MB} MB（解压后的镜像约 ${RAW_IMG_MB} MB）

这个包**只含程序**，不含任何书籍、音频、账号或站点配置。
首次启动会在数据目录里自动初始化一套空站。

---

## 一、三步启动

\`\`\`bash
# 1. 导入镜像（约 1-3 分钟）
gunzip -c mybooks-image-$SAFE_VER.tar.gz | docker load

# 2. 配置
cp .env.example .env
vi .env          # 至少改 DATA_DIR、PUID、PGID

# 3. 启动
docker compose up -d
\`\`\`

浏览器打开 \`http://<这台机器的IP>:9800\`。

没有 docker compose 的话，用命令行（等价）：

\`\`\`bash
docker run -d --name mybooks --restart always \\
  --security-opt seccomp=unconfined \\
  -v /你的/数据目录:/data \\
  -p 9800:80 \\
  -e PUID=\$(id -u) -e PGID=\$(id -g) \\
  -e TZ=Asia/Shanghai \\
  $DELIVER_IMG
\`\`\`

> 端口被占用就换左边那个数字；\`DATA_DIR\` 用绝对路径最稳。

---

## 二、第一次进去要做的事

1. **改管理员密码**。初始化会建一个默认管理员账号，具体账号名以登录页/日志提示为准，
   不改等于把站敞开。
2. 进「设置 → 基本」改站点名称、端口对外地址。
3. 上传/导入你的第一本书，确认能读、能听。

---

## 三、数据在哪、怎么备份

所有东西都在 \`DATA_DIR\`（容器内 \`/data\`）：

\`\`\`
<DATA_DIR>/books/library/   书库（含每本书的音频 .audio/）
<DATA_DIR>/books/settings/  站点设置
<DATA_DIR>/*.db             站点数据库（账号、进度、书架）
<DATA_DIR>/log/             日志
\`\`\`

**备份 = 打包这一个目录。** 换机器 = 把目录搬过去 + 用同一个镜像启动。

\`\`\`bash
# 停服冷备（最稳）
docker compose stop
tar -czf mybooks-data-\$(date +%F).tar.gz -C "\$DATA_DIR" .
docker compose start
\`\`\`

热备（不停服）需要数据库一致性处理，别直接 tar 正在写的 sqlite。

---

## 四、已知坑（重要）

### 1. 老内核 + docx/pdf 转换崩溃

如果这台机器内核低于 3.17（群晖 Braswell 等老平台常见 3.10.x），
把 docx 转 pdf 时会报 \`Fatal glibc error: cannot get entropy for arc4random\` 并崩溃。
这是内核 \`getrandom()\` 缺失导致的，**不是镜像问题**，\`seccomp=unconfined\` 也解决不了。
规避：别用 docx→pdf 转换功能；或用虚拟机跑新内核。

### 2. HTTPS 是自签 demo 证书

镜像里带的是 \`CN=demo.com\` 的演示证书，浏览器必然告警。
要么只用 HTTP（默认只映射了 80），要么自己换成真证书放进
\`<DATA_DIR>/books/ssl/\`（\`ssl.crt\` / \`ssl.key\`）。

### 3. 首次启动慢

第一次启动要初始化数据库、解压依赖、建目录，可能 1-3 分钟，
期间访问是 502/空白，属正常。看日志确认：

\`\`\`bash
docker logs -f mybooks
\`\`\`

### 4. 语音转写要联网下模型

镜像里装了转写框架，但模型不在镜像内，首次使用会从镜像站下载到数据目录。
离线环境用不了这个功能。

### 5. 权限不对的症状

「上传书籍失败」「设置保存不了」「封面不显示」基本都是 \`PUID/PGID\` 填错。
让 \`PUID/PGID\` 等于你在宿主机上 \`id\` 看到的自己的 uid/gid。

---

## 五、校验包完整性

\`\`\`bash
sha256sum -c SHA256SUMS
\`\`\`
READMEEOF

# ---------------- 5. 校验和 ----------------
say "生成校验和"
( cd "$WORK" && { command -v sha256sum >/dev/null 2>&1 && sha256sum "mybooks-image-$SAFE_VER.tar.gz" || shasum -a 256 "mybooks-image-$SAFE_VER.tar.gz"; } > SHA256SUMS )

# ---------------- 6. 报告 ----------------
echo ""
echo "============================================================"
echo " 完成"
echo "------------------------------------------------------------"
echo " 目录    : $WORK"
echo " 镜像    : $DELIVER_IMG"
echo " 镜像大小: ${RAW_IMG_MB} MB（解压后）"
echo " 包大小  : ${PKG_MB} MB"
echo " 校验和  :"
sed 's/^/           /' "$WORK/SHA256SUMS"
echo "------------------------------------------------------------"
echo " 自检（换台机器前建议先在本机 verify 一次）："
echo "   gunzip -c $WORK/mybooks-image-$SAFE_VER.tar.gz | docker load"
echo "   docker run --rm $DELIVER_IMG cat /var/www/mybooks/webserver/version.py"
echo "------------------------------------------------------------"
echo " 给别人的时候，把整个目录拷走："
echo "   $WORK/"
echo "============================================================"
