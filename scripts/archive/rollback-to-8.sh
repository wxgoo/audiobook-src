#!/bin/sh
# ============================================================================
# 【已归档 · 一次性脚本 · 过时】
# 当初 v9 出问题时的退路：退回 4.6.0-8。现在现役是 4.6.0-10，
# 跑它等于把作者归一化、坏字体剥离、阅读器统计修复全部丢掉。
#
# 只在一种情况下还有意义：v9/v10 的某个改动被确认是线上故障根因，
# 且来不及修 —— 那时先退回 v8 保可用，再回头定位。
# 日常"想退回上一版"请用 scripts/upgrade.sh 装上一个版本的包，
# 不要用这个（它会重解压 v8 源码，绕开 upgrade.sh 的备份与校验）。
# 需要完整回滚（含旧镜像）时，参照本脚本里的备份/切镜像写法自己改。
#
# 下面这段是原始说明，保留原样：
# ------------------------------------------------------------
# rollback-to-8.sh —— 把 /volume1/docker/audiobook 回滚到 4.6.0-8
#
# 设计前提（都是实测确认过的）：
#   1. 全部运行数据在 /volume1/docker/audiobook-data，**不在源码目录里**，
#      所以删除/重解压 audiobook 目录不会丢书、丢库、丢日志。
#   2. docker-compose.yml 里 image 是本地标签 mybooks-local:latest，配 build，
#      不会去拉远程镜像。回滚 = 换源码 + 重新 build。
#   3. 旧镜像不删，出问题可以立刻切回去。
#
# 用法：
#   sh rollback-to-8.sh /path/to/audiobook-deploy-4.6.0-8.tar.gz
#   sh rollback-to-8.sh /path/to/xxx.tar.gz --dry-run    # 只体检不动手
#   sh rollback-to-8.sh /path/to/xxx.tar.gz --no-build   # 换源码但不起容器
#
# 群晖上建议用 root 执行：sudo -i 之后再跑。
# ============================================================================

set -u

PKG="${1:-}"
MODE="${2:-}"

DOCKER_DIR="/volume1/docker"
SRC_DIR="$DOCKER_DIR/audiobook"
DATA_DIR="$DOCKER_DIR/audiobook-data"
BACKUP_ROOT="$DOCKER_DIR/audiobook-backup"
STAMP=$(date +%Y%m%d-%H%M%S)
IMAGE="mybooks-local:latest"

say()  { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[1;31m!! %s\033[0m\n' "$*"; exit 1; }

# ---------------------------------------------------------------- 0. 参数校验
[ -n "$PKG" ] || die "用法: sh rollback-to-8.sh <4.6.0-8的tar.gz路径> [--dry-run|--no-build]"
[ -f "$PKG" ] || die "找不到文件: $PKG"
case "$MODE" in ""|--dry-run|--no-build) ;; *) die "未知参数: $MODE" ;; esac

say "[0] 环境体检"
[ "$(id -u)" = "0" ] || die "请用 root 执行（sudo -i 之后再跑）"
ok "当前是 root"

command -v docker >/dev/null 2>&1 || die "没有 docker 命令"
if docker info >/dev/null 2>&1; then
    ok "docker 可用"
else
    die "docker 连不上（permission denied？没启动？）"
fi

if docker compose version >/dev/null 2>&1; then
    DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DC="docker-compose"
else
    die "docker compose / docker-compose 都不可用"
fi
ok "compose 命令: $DC"

[ -d "$SRC_DIR" ] || die "源码目录不存在: $SRC_DIR"
[ -d "$DATA_DIR" ] || die "数据目录不存在: $DATA_DIR（回滚不能凭空造，先确认路径）"

# 数据目录里必须有东西，否则说明路径搞错了，这时候继续等于毁库
DATASZ=$(du -sm "$DATA_DIR" 2>/dev/null | awk '{print $1}')
[ "${DATASZ:-0}" -gt 10 ] || die "数据目录只有 ${DATASZ:-0}MB，路径可能不对，已中止"
ok "数据目录: $DATA_DIR（${DATASZ}MB，回滚不会碰它）"

# ---------------------------------------------------------------- 1. 验包
say "[1] 校验 4.6.0-8 包"
PKGSZ=$(du -m "$PKG" | awk '{print $1}')
ok "包大小: ${PKGSZ}MB"

# 顶层必须是 audiobook/ 目录，否则 --strip-components=1 会解错地方
TOP=$(tar -tzf "$PKG" 2>/dev/null | head -1)
case "$TOP" in
    audiobook/) ok "顶层目录正确: audiobook/" ;;
    *) die "包顶层不是 audiobook/（实际是: $TOP），不敢解压" ;;
esac

for f in docker-compose.yml Dockerfile app/nuxt.config.js; do
    if tar -tzf "$PKG" | grep -qx "audiobook/$f"; then
        ok "关键文件存在: $f"
    else
        die "包内缺少 audiobook/$f —— 这不是完整的部署包"
    fi
done

# 阅读器产物完整性：基准是 3526 条目 / 1958 个 node_modules 条目。
# ⚠️ 实测 audiobook-deploy-4.6.0-8.tar.gz 里的 myreader-dist 只有 1521 条、
#    node_modules 一条没有 —— 是残缺产物。而用户手里能跑起来的那份是完整的。
#    所以下面要做两件事：
#      a) 先看当前现装目录里有没有完整产物，有就备份
#      b) 解压后若包内产物残缺，用备份补上
MYR_CNT=$(tar -tzf "$PKG" | grep -c "^audiobook/myreader-dist/")
MYR_NM=$(tar -tzf "$PKG" | grep -c "^audiobook/myreader-dist/node_modules/")
ok "包内 myreader-dist: $MYR_CNT 条目 / $MYR_NM 个 node_modules"

PKG_MYR_OK=1
if [ "$MYR_NM" -lt 100 ]; then
    PKG_MYR_OK=0
    warn "包内阅读器产物不完整（node_modules 缺失）"
    warn "→ 将改用现装目录里的完整产物，或用 MYREADER= 指定的产物包"
fi

# 现装目录里的产物是否完整
CUR_MYR_OK=0
if [ -d "$SRC_DIR/myreader-dist/app/.next" ] && [ -d "$SRC_DIR/myreader-dist/node_modules" ]; then
    # 不用 `ls -a | wc -l`：pnpm 的 node_modules 顶层可能只有 .pnpm 一个条目
    # （普通 ls 看不到点开头的，-a 数出来也就 3 项），用 find 递归数文件更可靠
    CUR_CNT=$(find "$SRC_DIR/myreader-dist/node_modules" -type f 2>/dev/null | wc -l)
    CUR_LNK=$(find "$SRC_DIR/myreader-dist/node_modules" -type l 2>/dev/null | wc -l)
    [ $((CUR_CNT + CUR_LNK)) -gt 100 ] && CUR_MYR_OK=1
fi
if [ "$PKG_MYR_OK" -eq 0 ]; then
    if [ "$CUR_MYR_OK" -eq 1 ]; then
        ok "现装目录有完整产物，会先备份再复用"
    elif [ -n "${MYREADER:-}" ] && [ -f "$MYREADER" ]; then
        ok "使用 MYREADER 指定的产物: $MYREADER"
    else
        die "包内产物残缺，现装目录也没有完整产物，且未提供 MYREADER=<myreader-dist.tar.gz>。
    请先把完整产物包放到 NAS 上（31M，3526 条目），再执行：
      MYREADER=/path/to/myreader-dist.tar.gz sh rollback-to-8.sh $PKG"
    fi
fi

if [ "$MODE" = "--dry-run" ]; then
    say "dry-run 结束：以上全部通过，可以正式执行"
    exit 0
fi

# ---------------------------------------------------------------- 2. 记录现状
say "[2] 记录当前状态（回滚依据）"
CUR_VER="未知"
if [ -f "$SRC_DIR/CHANGELOG.md" ]; then
    CUR_VER=$(grep -m1 -oE "4\.6\.0-[0-9]+" "$SRC_DIR/CHANGELOG.md" 2>/dev/null || echo "未知")
fi
ok "当前源码版本线索: $CUR_VER"

mkdir -p "$BACKUP_ROOT"
ok "备份目录: $BACKUP_ROOT"

# 保存容器的实际配置，万一 compose 文件有本地改动可以比对
if docker ps -a --format '{{.Names}}' | grep -q "audiobook"; then
    docker ps -a --filter "name=audiobook" --format "{{.Names}}\t{{.Image}}\t{{.Status}}" \
        > "$BACKUP_ROOT/containers-$STAMP.txt" 2>/dev/null
    ok "已记录容器清单: containers-$STAMP.txt"
fi

# 给当前源码目录改名保留（不删！），出问题一条 mv 就能回来
MYR_BAK=""
if [ -d "$SRC_DIR" ]; then
    if [ "$PKG_MYR_OK" -eq 0 ] && [ "$CUR_MYR_OK" -eq 1 ]; then
        # 先单独把完整产物抠出来，稍后补进新目录
        MYR_BAK="$BACKUP_ROOT/myreader-dist-from-$CUR_VER-$STAMP.tar.gz"
        ( cd "$SRC_DIR" && tar -czf "$MYR_BAK" myreader-dist ) && \
            ok "已备份现装的完整阅读器产物: $MYR_BAK" || die "备份阅读器产物失败"
    fi
    mv "$SRC_DIR" "$BACKUP_ROOT/audiobook-$CUR_VER-$STAMP" || die "移动旧目录失败"
    ok "旧源码已保留: $BACKUP_ROOT/audiobook-$CUR_VER-$STAMP"
fi

# ---------------------------------------------------------------- 3. 停容器
say "[3] 停止并移除旧容器"
cd "$BACKUP_ROOT" || die "进不去备份目录"
# compose 要用原目录名才能对上 project name，所以先在新目录里停
mkdir -p "$SRC_DIR"
cd "$SRC_DIR" || die "建不了 $SRC_DIR"

# 直接用 docker 按名字清理，避免依赖 compose 文件
OLDS=$(docker ps -a --filter "name=audiobook" --format '{{.Names}}')
if [ -n "$OLDS" ]; then
    for c in $OLDS; do
        docker rm -f "$c" >/dev/null 2>&1 && ok "已移除容器: $c" || warn "移除失败: $c"
    done
else
    ok "没有遗留容器"
fi

# 处理 marked for removal 残留
sleep 1
LEFTOVER=$(docker ps -a --filter "status=removing" --format '{{.Names}}' 2>/dev/null)
[ -n "$LEFTOVER" ] && warn "仍有 removing 状态容器: $LEFTOVER"

# ---------------------------------------------------------------- 4. 解包
say "[4] 解压 4.6.0-8 源码"
# $SRC_DIR 此时是空目录，strip 顶层 audiobook/ 直接铺进去
tar -xzf "$PKG" -C "$SRC_DIR" --strip-components=1 || die "解压失败"
ok "解压完成"

for f in docker-compose.yml Dockerfile app/nuxt.config.js myreader-dist/app/server.js myreader-dist/app/.next/BUILD_ID; do
    [ -e "$SRC_DIR/$f" ] && ok "  $f" || die "解压后缺少 $f"
done

# ---- 补齐阅读器产物（包内残缺时）----
if [ "$PKG_MYR_OK" -eq 0 ]; then
    say "[4.1] 补齐阅读器产物"
    rm -rf "$SRC_DIR/myreader-dist"
    if [ -n "$MYR_BAK" ] && [ -f "$MYR_BAK" ]; then
        tar -xzf "$MYR_BAK" -C "$SRC_DIR" || die "还原备份产物失败"
        ok "已用现装目录的完整产物补齐"
    elif [ -n "${MYREADER:-}" ] && [ -f "$MYREADER" ]; then
        tar -xzf "$MYREADER" -C "$SRC_DIR" || die "解压 MYREADER 产物失败"
        # 兼容包里带不带顶层 myreader-dist/ 两种结构
        if [ ! -d "$SRC_DIR/myreader-dist" ] && [ -d "$SRC_DIR/app" ]; then
            mkdir -p "$SRC_DIR/myreader-dist" && mv "$SRC_DIR/app" "$SRC_DIR/myreader-dist/app"
        fi
        ok "已用 $MYREADER 补齐"
    fi

    # 补完再验一次，这是最后一道防线
    NM=$(find "$SRC_DIR/myreader-dist/node_modules" -type f -o -type l 2>/dev/null | wc -l)
    [ "$NM" -gt 100 ] || die "补齐后 node_modules 仍不完整（$NM 项），阅读器会起不来，已中止"
    [ -f "$SRC_DIR/myreader-dist/app/server.js" ] || die "补齐后缺 app/server.js，已中止"
    [ -f "$SRC_DIR/myreader-dist/app/.next/BUILD_ID" ] || die "补齐后缺 app/.next/BUILD_ID，已中止"
    TOT=$(find "$SRC_DIR/myreader-dist" | wc -l)
    ok "补齐后检查通过: $TOT 条目 / node_modules $NM 个文件+链接"
fi

# 权限归一：root 打包的产物权限可能是 0700，gosu 下的 node 读不到
# 会报 "Cannot find module"，这个坑 4.6.0-9 已经踩过一次
if [ -d "$SRC_DIR/myreader-dist" ]; then
    chown -R root:root "$SRC_DIR/myreader-dist" 2>/dev/null
    chmod -R u+rwX,go+rX "$SRC_DIR/myreader-dist" 2>/dev/null
    ok "myreader-dist 权限已归一: $(ls -ld "$SRC_DIR/myreader-dist/app" | awk '{print $1}')"
fi

# ---------------------------------------------------------------- 5. 构建
if [ "$MODE" = "--no-build" ]; then
    say "[5] 按 --no-build 跳过构建"
    warn "源码已就位，需要手动执行: cd $SRC_DIR && $DC up -d --build"
    exit 0
fi

say "[5] 构建镜像（首次约 20-40 分钟，有缓存会快很多）"
cd "$SRC_DIR" || die "进不去 $SRC_DIR"
$DC build 2>&1 | tail -40
BUILD_RC=$?
[ "$BUILD_RC" -eq 0 ] || die "构建失败（返回码 $BUILD_RC），旧源码仍在 $BACKUP_ROOT，可用 mv 换回"

# ---------------------------------------------------------------- 6. 启动
say "[6] 启动容器"
$DC up -d || die "启动失败"
sleep 3
docker ps --filter "name=audiobook" --format "{{.Names}}\t{{.Status}}"

# ---------------------------------------------------------------- 7. 验证
say "[7] 启动验证（最多等 180 秒）"
i=0
while [ "$i" -lt 36 ]; do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:9800/ 2>/dev/null)
    [ -z "$CODE" ] && CODE=$(wget -q -O /dev/null -S http://127.0.0.1:9800/ 2>&1 | grep -o "HTTP/[0-9.]* [0-9]*" | tail -1 | awk '{print $2}')
    case "$CODE" in
        200) ok "首页返回 200（等待 $((i*5)) 秒）"; break ;;
        *)   printf '.'; sleep 5; i=$((i+1)) ;;
    esac
done
[ "$i" -ge 36 ] && warn "180 秒内首页没返回 200（最后状态: ${CODE:-无响应}），查看日志: docker logs audiobook-mybooks-1 --tail 80"

say "回滚完成"
cat <<EOF

  版本      : 4.6.0-8
  源码目录  : $SRC_DIR
  数据目录  : $DATA_DIR（未改动）
  旧源码    : $BACKUP_ROOT/audiobook-$CUR_VER-$STAMP
  旧镜像    : 仍在本机，重新打回标签即可切回

  如果 4.6.0-8 也不行，一条命令切回旧源码：
    docker compose down
    rm -rf $SRC_DIR
    mv $BACKUP_ROOT/audiobook-$CUR_VER-$STAMP $SRC_DIR
    cd $SRC_DIR && docker compose up -d --build

  必查：
    1. 浏览器打开 http://<NAS_IP>:9800 ，书架能出来
    2. 点任意一本书，F12 → Network，看 /api/book/<id> 是否 200
    3. 若仍空白，把 Network 面板完整截图发我（全部请求，不要过滤）

EOF
