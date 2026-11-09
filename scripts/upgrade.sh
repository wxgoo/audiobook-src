#!/bin/sh
# ============================================================
# audiobook（MyBooks 移植版）升级 / 重装脚本（基于上游 mybooks tag 4.6.0）
#
# 解决的问题：
#   直接在 audiobook/ 里 tar -xzf 新包 → 旧目录残留 + 新包叠加，
#   历史版本还把 books/ 数据落在源码目录里，导致"源码目录不干净"、
#   "数据目录不唯一"。本脚本用 原子替换 的方式彻底避免。
#
# 用法（在 /volume1/docker 下执行，或任意位置带绝对路径）：
#   sh scripts/upgrade.sh /volume1/docker/audiobook-deploy-<版本>.tar.gz
#
# 可选环境变量：
#   SKIP_BUILD=1   只解压不构建（先看代码）
#   SKIP_UP=1      只解压+构建，不启动
#   KEEP_OLD=1     保留 audiobook.old（默认成功后自动删）
#   NO_BACKUP=1    不备份数据（不推荐）
#
# 布局约定（自 4.6.0-1 起）：
#   /volume1/docker/audiobook/        源码 + 配置，可随意删了重解压
#   /volume1/docker/audiobook-data/   唯一数据目录，永不被本脚本触碰
# ============================================================
set -e

PKG="$1"
BASE="${BASE:-/volume1/docker}"
SRC="$BASE/audiobook"
DATA="$BASE/audiobook-data"
OLD="$BASE/audiobook.old"
CONTAINER="${CONTAINER:-audiobook-mybooks-1}"

# ---------- 参数校验 ----------
if [ -z "$PKG" ]; then
    echo "用法: sh scripts/upgrade.sh /path/to/audiobook-deploy-vX.Y.Z.tar.gz"
    exit 1
fi
if [ ! -f "$PKG" ]; then
    echo "!! 找不到压缩包: $PKG"
    exit 1
fi
case "$PKG" in
    /*) ;;
    *) PKG="$(cd "$(dirname "$PKG")" && pwd)/$(basename "$PKG")" ;;
esac

echo "============================================================"
echo " audiobook 升级 / 重装"
echo "   包   : $PKG"
echo "   源码 : $SRC"
echo "   数据 : $DATA"
echo "============================================================"

# ---------- 0. 包结构预检：确认包内不含数据目录 ----------
echo "==> [0/8] 预检压缩包结构"
PKG_TOP=$(tar -tzf "$PKG" 2>/dev/null | head -1 | sed 's#/.*##' || true)
echo "    包内顶层: ${PKG_TOP:-<空>}"

# 检查包内是否混入数据目录（正常应为空）
DIRTY=$(tar -tzf "$PKG" 2>/dev/null | grep -E '(^|/)books/(library|audios|upload|imports)/' | head -5 || true)
if [ -n "$DIRTY" ]; then
    echo "    !! 警告：压缩包内疑似含用户数据目录，示例："
    echo "$DIRTY" | sed 's/^/       /'
    printf "    继续解压？(数据不会覆盖 audiobook-data，但会进源码目录) [y/N] "
    read ans
    [ "$ans" = "y" ] || [ "$ans" = "Y" ] || { echo "    已取消。"; exit 1; }
else
    echo "    包内无 books/ 数据目录，干净。"
fi

# ---------- 1. 数据目录检查 ----------
echo "==> [1/8] 检查数据目录"
if [ ! -d "$DATA/books" ]; then
    echo "    !! 未找到 $DATA/books"
    echo "    !! 若是首次安装，请改用: cd $SRC && sh deploy.sh"
    echo "    !! 若是旧布局（数据还在源码目录里），先按 INSTALL_GUIDE.md"
    echo "       “一次性：把数据目录分离出源码目录” 完成搬迁。"
    exit 1
fi
echo "    OK：$DATA/books 存在"
du -sh "$DATA" 2>/dev/null | sed 's/^/    数据体积: /'

# ---------- 1.5 旧布局音频残留检查（4.6.0-15 起不再读取 audios/<id>/） ----------
LEGACY_AUDIOS="$DATA/books/audios"
if [ -d "$LEGACY_AUDIOS" ]; then
    LEFT=$(find "$LEGACY_AUDIOS" -mindepth 2 -maxdepth 2 -type f \( -name '*.mp3' -o -name '*.m4a' -o -name '*.m4b' -o -name '*.flac' -o -name '*.wav' -o -name '*.opus' -o -name '*.ogg' -o -name '*.wma' -o -name '*.aac' \) 2>/dev/null | head -10)
    if [ -n "$LEFT" ]; then
        echo "    !! $LEGACY_AUDIOS 下仍发现有音频文件（示例）："
        echo "$LEFT" | sed 's/^/       /'
        echo "    !! 4.6.0-15 起旧布局 audios/<id>/ 不再被读取，这些音频升级后会变成孤儿。"
        echo "    !! 处理办法：把每个 audios/<书id>/ 里的音频移到对应书目录下的 .audio/"
        echo "    !!   （书目录形如 library/<作者>/<书名> (id)/，可用书 id 对应上面的目录名）"
        echo "    !!   搬不动的可先备份，升级后再手工补回书的 .audio/。"
        printf "    确认已处理或接受丢失风险，继续升级？[y/N] "
        read ans
        [ "$ans" = "y" ] || [ "$ans" = "Y" ] || { echo "    已取消。"; exit 1; }
    else
        echo "    旧布局 audios/ 无音频残留（如有空目录可整目录删除）。"
    fi
fi

# ---------- 2. 备份数据（可选，稳妥） ----------
if [ "$NO_BACKUP" != "1" ]; then
    echo "==> [2/8] 备份数据库（仅 *.db，不含书/音频，秒级）"
    BK="$BASE/audiobook-data-dbbackup-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$BK"
    find "$DATA/books" -maxdepth 1 -name '*.db*' -exec cp -a {} "$BK"/ \; 2>/dev/null || true
    echo "    已备份到: $BK"
else
    echo "==> [2/8] 跳过备份（NO_BACKUP=1）"
fi

# ---------- 3. 停容器 ----------
echo "==> [3/8] 停止容器"
# 用 down 而不是 down -v/rm：容器是「停止」不是「删除」，新代码靠 up -d 时
# 自动 recreate。这里如果留下一个「已标记删除但没删完」的容器，下一步 up 会报
# "container is marked for removal and cannot be started"。
if [ -f "$SRC/docker-compose.yml" ]; then
    ( cd "$SRC" && docker compose down --remove-orphans ) >/dev/null 2>&1 || \
    docker stop "$CONTAINER" >/dev/null 2>&1 || true
else
    docker stop "$CONTAINER" >/dev/null 2>&1 || true
fi
# 等容器真正退出，否则紧接着的 up -d 会和还在收尾的旧容器打架
i=0
while [ $i -lt 30 ]; do
    [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" = "true" ] || break
    i=$((i + 1))
    sleep 1
done
echo "    已停止。"

# ---------- 4. 旧源码归档 ----------
echo "==> [4/8] 归档旧源码"
if [ -d "$SRC" ]; then
    rm -rf "$OLD"
    mv "$SRC" "$OLD"
    echo "    旧源码已移到: $OLD"
else
    echo "    无旧源码，跳过。"
fi

# ---------- 5. 全新解压 ----------
echo "==> [5/8] 解压新包到全新目录"
mkdir -p "$SRC"

# 判断包是否带外层目录（如 audiobook-deploy-<版本>/）
if tar -tzf "$PKG" 2>/dev/null | head -1 | grep -q '/'; then
    echo "    检测到外层目录，使用 --strip-components=1"
    tar -xzf "$PKG" -C "$SRC" --strip-components=1
else
    echo "    无外层目录，直接解压"
    tar -xzf "$PKG" -C "$SRC"
fi

# 包内运行期版本（唯一权威）。构建时显式传给 Dockerfile，不依赖 compose 里的 GIT_VERSION：
# 现场常会保留自己那份 compose（PUID/PGID、路径本地化），里面版本号可能还是上一版，
# 用它构建就会把旧号写进 webserver/version.py，页脚一直显示旧版本（dist 却是新的）。
# 另：version.py 为 CRLF 时 sed 会残留行尾 \r，必须洗掉再当 --build-arg 用。
PKG_VER=$(sed -n 's/^VERSION[[:space:]]*=[[:space:]]*"\(.*\)"/\1/p' "$SRC/webserver/version.py" 2>/dev/null | head -1 | tr -d '\r')
[ -n "$PKG_VER" ] || { echo "    !! 读不出 $SRC/webserver/version.py 的 VERSION"; exit 1; }
echo "    包内版本: $PKG_VER"

# ---------- 6. 污染自检 ----------
echo "==> [6/8] 源码目录污染自检"
DIRTY_PATHS=""
for p in books book data audios library upload imports sync models cache logs log workspace; do
    [ -e "$SRC/$p" ] && DIRTY_PATHS="$DIRTY_PATHS $p"
done
if [ -n "$DIRTY_PATHS" ]; then
    echo "    !! 源码目录出现数据类目录:$DIRTY_PATHS"
    echo "    !! 这些不应存在于源码目录。处理方式："
    echo "       1) 确认其中的数据是否已在 $DATA 里（ls $DATA/books）"
    echo "       2) 若未搬走，先 mv 到 $DATA/ 下，再删除源码目录中的副本"
    echo "       3) 若已搬走，直接删除: rm -rf${DIRTY_PATHS// / $SRC/}"
    echo "    !! 已停止后续步骤，请处理后重新执行本脚本。"
    exit 1
fi
echo "    OK：源码目录干净（无 books/ data/ 等）"

# 校验关键文件
for f in Dockerfile docker-compose.yml; do
    [ -e "$SRC/$f" ] || { echo "    !! 缺少关键文件: $f"; exit 1; }
done
echo "    OK：关键文件齐全"

# 校验 compose 的数据挂载指向 audiobook-data
if ! grep -q "audiobook-data:/data" "$SRC/docker-compose.yml"; then
    echo "    !! docker-compose.yml 里没有 'audiobook-data:/data' 挂载"
    grep -n ":/data" "$SRC/docker-compose.yml" | sed 's/^/       /'
    echo "    !! 请手工修正 volumes 行为: - /volume1/docker/audiobook-data:/data"
    exit 1
fi
echo "    OK：数据挂载指向 audiobook-data"

# ---------- 6.2 MyReader 符号链接校验 / 重建 ----------
# 2026-11-09 现场实锤：包内 myreader-dist 有 119 根相对符号链接，
# Windows 检出 / File Station 上传 / 图形界面解压会把它压扁成普通文件，
# 于是 myreader 要么启动 FATAL，要么显示 Ready 但打开书 /reader/open 报 500。
# 这里必须在 docker build 之前把 $SRC/myreader-dist 修好——构建上下文里的
# 链接状态会被原样 COPY 进镜像，事后补容器是没用的（重建容器就丢）。
# 注意：本脚本可能仍是从旧目录里启动的旧版本，所以显式调用新解压出来的脚本。
if [ -f "$SRC/scripts/check-myreader-links.sh" ] && [ -f "$SRC/scripts/myreader-links.manifest" ]; then
    echo "==> [6.2/8] MyReader 119 根链接校验 / 重建"
    sh "$SRC/scripts/check-myreader-links.sh" --fix \
        --manifest "$SRC/scripts/myreader-links.manifest" \
        "$SRC/myreader-dist" || {
        echo "    !! MyReader 链接修复失败，停止部署（镜像会带着坏链接）"
        exit 1
    }
else
    echo "    !! 新包缺 scripts/check-myreader-links.sh 或 myreader-links.manifest，停止部署"
    exit 1
fi

# compose 里的版本号只服务于「手工 docker compose build」，本脚本用 --build-arg 覆盖。
# 但两者不一致时提示一句：手工 compose build 会写回旧版本，正是页脚显示旧号的成因。
CVER=$(sed -n 's/^[[:space:]]*GIT_VERSION:[[:space:]]*"\{0,1\}\([^"]*\)"\{0,1\}[[:space:]]*$/\1/p' "$SRC/docker-compose.yml" 2>/dev/null | head -1 | tr -d '\r')
if [ -n "$CVER" ] && [ "$CVER" != "$PKG_VER" ]; then
    echo "    ! 注意：compose 的 GIT_VERSION=$CVER，与包内 $PKG_VER 不同"
    echo "      本脚本构建时会覆盖成 $PKG_VER；但别手工 docker compose build，否则会写回旧号。"
fi

# ---------- 6.5 默认图标/二维码（只补缺失，绝不覆盖存量） ----------
# 镜像里的 /data/books/logo 会被宿主机 audiobook-data 的 bind mount 盖住，
# 所以包内 dist/logo 里的默认图标不会自己出现在数据目录。这里按“缺失才补”的原则：
# 全新部署（空数据目录）拿到包内新 favicon.ico / link_gongzhonghao.jpg；
# 存量站点已有文件一律不动，需要换由管理员手工放或后台选图上传。
seed_logo_defaults() {
    logo_src="$SRC/app/public/logo"
    logo_dst="$DATA/books/logo"
    [ -d "$logo_src" ] || return 0
    mkdir -p "$logo_dst" 2>/dev/null || return 0
    for f in favicon.ico link_gongzhonghao.jpg; do
        if [ ! -e "$logo_dst/$f" ] && [ -e "$logo_src/$f" ]; then
            cp "$logo_src/$f" "$logo_dst/$f" && chmod 644 "$logo_dst/$f" 2>/dev/null || true
            echo "    + 初始化默认图标: $logo_dst/$f"
        fi
    done
}
seed_logo_defaults

# ---------- 7. 构建 ----------
if [ "$SKIP_BUILD" = "1" ]; then
    echo "==> [7/8] 跳过构建（SKIP_BUILD=1）"
else
    echo "==> [7/8] 构建镜像（BuildKit，耗时较久，请耐心）"
    # 2026-11-09 修订：弃用 legacy builder（btrfs 每层一子卷，攒千级后 layer does not exist）。
    # NAS 没装独立 buildx 插件时 docker build 走不了 BuildKit，回退 compose build（内嵌 buildx）；
    # compose 快照判重的风险由下方 index.html 指纹比对 + 版本门禁兜底。
    ( cd "$SRC" && if docker buildx version >/dev/null 2>&1; then
          DOCKER_BUILDKIT=1 docker build --no-cache --build-arg "GIT_VERSION=$PKG_VER" -t mybooks-local:latest .
      else
          docker compose build --no-cache --build-arg "GIT_VERSION=$PKG_VER"
      fi ) || exit 1
    host_sha=$(sha256sum "$SRC/app/dist/index.html" | awk '{print $1}')
    img_sha=$(docker run --rm mybooks-local:latest sha256sum /var/www/mybooks/app/dist/index.html | awk '{print $1}')
    if [ "$host_sha" != "$img_sha" ]; then
        echo "!! 镜像内 index.html 与包内不一致：$img_sha != $host_sha"
        echo "   （上下文快照复用的典型症状）处理：docker builder prune -f 后重跑本脚本；"
        echo "    仍不行则 DOCKER_BUILDKIT=0 legacy 兜底一轮"
        exit 1
    fi
    echo "==> 镜像内 index.html: $img_sha"
    # 版本门禁：镜像内 version.py 必须等于包内版本。
    # 旧门禁只看 index.html，抓不到「dist 新、版本号旧」这种半新半旧的镜像。
    ( cd "$SRC" && CONTAINER="$CONTAINER" sh scripts/check-version.sh --image ) || {
        echo "!! 版本门禁未通过，已停止（容器未启动，站点仍是旧版本，不受影响）"
        exit 1
    }
fi

# ---------- 8. 启动与验证 ----------
if [ "$SKIP_UP" = "1" ] || [ "$SKIP_BUILD" = "1" ]; then
    echo "==> [8/8] 跳过启动"
    echo
    echo "后续手动执行："
    echo "  cd $SRC && docker compose up -d --force-recreate --no-build"
    echo "  确认无误后清理旧源码: rm -rf $OLD"
    exit 0
fi

echo "==> [8/8] 启动容器"
# 残留容器清理：上一次 down 如果被打断，会留下 State=removing 的容器，
# up -d 直接报 "container is marked for removal and cannot be started"。
# 发现就先把它删干净，再起新的（数据在 /data 里，删容器不影响任何书）。
if docker inspect -f '{{.State.Status}}' "$CONTAINER" 2>/dev/null | grep -q 'removing'; then
    echo "    检测到残留容器（removing），先清理..."
    i=0
    while [ $i -lt 20 ] && docker inspect "$CONTAINER" >/dev/null 2>&1; do
        i=$((i + 1)); sleep 2
    done
    docker rm -f "$CONTAINER" 2>/dev/null || true
fi
# 同名占用兜底：down 只能移除 compose 项目创建的容器。如果容器是手动
# docker run 建的（不属于本项目），up -d 会报
#   Conflict. The container name "/audiobook-mybooks-1" is already in use...
# 此时镜像已构建完，白白中断。发现同名容器还占着名字就删掉——
# 数据全在 /data（宿主机 audiobook-data），删容器不伤任何书。
if docker inspect "$CONTAINER" >/dev/null 2>&1; then
    echo "    检测到同名容器存在（可能是手动 docker run 建的，不属于本项目），删除后由 compose 重建..."
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
fi
( cd "$SRC" && docker compose up -d --force-recreate --no-build )

# ---------- 等容器真正跑起来再检查 ----------
# 踩过的坑：这里原来 fixed sleep 20 就直接 supervisorctl status，结果经常报
# "unix:///var/run/supervisor.sock no such file"。
# 原因不是升级失败，而是容器还在初始化：start.sh 要先把 /data 下缺的目录补出来，
# 再跑一次 --syncdb 和 --update-config，这两步在 62 本书的库上就可能超过 20 秒，
# 这期间 supervisord 根本还没 exec 起来，socket 自然不存在。
# 所以改成轮询：容器 Running → 等 sock 出现 → 再等 4 个 program 全 RUNNING。
echo "    等待容器初始化（首次启动要跑 syncdb / update-config，慢一点正常）..."
i=0
while [ $i -lt 60 ]; do
    RUNNING=$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || echo "false")
    [ "$RUNNING" = "true" ] && break
    i=$((i + 1))
    sleep 2
done
if [ "$RUNNING" != "true" ]; then
    echo " !! 容器没起来，看日志：docker logs --tail 80 $CONTAINER"
    docker logs --tail 80 "$CONTAINER" 2>&1 | sed 's/^/    /'
    exit 1
fi

# 等 supervisord socket 出现（最多约 3 分钟）
i=0
while [ $i -lt 90 ]; do
    if docker exec "$CONTAINER" test -S /var/run/supervisor.sock 2>/dev/null; then
        break
    fi
    # 容器中途死掉就别等了
    RUNNING=$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || echo "false")
    [ "$RUNNING" != "true" ] && break
    i=$((i + 1))
    sleep 2
done

if ! docker exec "$CONTAINER" test -S /var/run/supervisor.sock 2>/dev/null; then
    echo " !! supervisord 未启动（等了约 $((i * 2)) 秒）"
    echo "    容器内 start.sh 最后 30 行："
    docker logs --tail 30 "$CONTAINER" 2>&1 | sed 's/^/    /'
    exit 1
fi

# 再等各个 program 从 STARTING 变 RUNNING（tornado 要加载 calibre，通常 10~40 秒）
i=0
while [ $i -lt 60 ]; do
    ST=$(docker exec "$CONTAINER" supervisorctl status 2>/dev/null)
    # 出现 FATAL/BACKOFF 就没必要再等
    echo "$ST" | grep -qE 'FATAL|BACKOFF' && break
    if [ -n "$ST" ] && ! echo "$ST" | grep -qE 'STARTING'; then
        break
    fi
    i=$((i + 1))
    sleep 2
done

echo
echo "    supervisor 状态（应为 4 个 RUNNING）："
docker exec "$CONTAINER" supervisorctl status 2>&1 | sed 's/^/    /' || true
if docker exec "$CONTAINER" supervisorctl status 2>/dev/null | grep -qE 'FATAL|BACKOFF'; then
    echo
    echo " !! 有进程没起来，日志："
    docker exec "$CONTAINER" tail -30 /data/log/mybooks.log 2>&1 | sed 's/^/    /' || true
fi

# 从容器内部请求 nginx，确认真的能出页面（supervisorctl 全绿也可能 502）。
# 注意 python 那段必须用单引号：里面的 $ 不能被 NAS 的 shell 提前展开。
CODE=$(docker exec "$CONTAINER" python3 -c 'import urllib.request as u; print(u.urlopen("http://127.0.0.1/", timeout=10).status)' 2>&1 | tail -1)
case "$CODE" in
    200) echo
         echo "    HTTP 自检: 200 页面正常" ;;
    *)   echo
         echo "    HTTP 自检异常: $CODE"
         echo "    （容器内 nginx 没回 200，看：docker logs --tail 50 $CONTAINER）" ;;
esac
echo
echo "    数据校验（书数应与你原有的数量一致）："
# 用 python3 - <<'PY' 从 stdin 传脚本，避免内层双引号把外层 "..." 提前闭合
docker exec -i "$CONTAINER" python3 - <<'PY' 2>/dev/null || true
import sqlite3
try:
    c = sqlite3.connect('/data/books/library/metadata.db')
    print('    书数:', c.execute('select count(*) from books').fetchone()[0])
except Exception as e:
    print('    读取失败:', e)
PY

echo
echo "==> 版本自检（页脚显示的就是这个值）"
if ! ( cd "$SRC" && CONTAINER="$CONTAINER" sh scripts/check-version.sh ); then
    echo " !! 版本链路不一致，页脚会显示旧版本。"
    echo "    先跑 sh $SRC/scripts/check-version.sh 看是哪一环；"
    echo "    旧源码仍保留在 $OLD，需要回滚可: rm -rf $SRC && mv $OLD $SRC"
    exit 1
fi

if [ "$KEEP_OLD" != "1" ]; then
    echo
    echo "==> 清理旧源码"
    rm -rf "$OLD"
    echo "    已删除 $OLD"
else
    echo "    已保留旧源码: $OLD（KEEP_OLD=1）"
fi

echo
echo "============================================================"
echo " 升级完成"
echo "   源码: $SRC"
echo "   数据: $DATA   （唯一，未被触碰）"
echo "   访问: http://<NAS_IP>:9800"
echo "============================================================"
