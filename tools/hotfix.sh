#!/bin/sh
# ============================================================
# 热更新脚本：不重建镜像，把源码里的 .py / .vue 改动直接推进正在运行的容器
#
# 适用场景：改的是 Python 后端（settings.py、i18n.py、handlers、services）
# 或想快速验证一处改动，不想等 docker compose build（那要跑 npm run build-spa）。
#
# 用法（在 audiobook 目录下）：
#   sh tools/hotfix.sh             # 只推 Python 文件（快，1 分钟）
#   sh tools/hotfix.sh --frontend  # 顺带提示前端改动无法热更
#   sh tools/hotfix.sh --dry-run   # 只列出会推哪些文件，不动容器
#
# 注意：
#   * 前端（app/ 下的 .vue、locales/*.json）已编译进静态 dist，无法热替换，
#     必须 docker compose build。本脚本只处理 Python 侧。
#   * 热更不持久：容器重建/镜像重建后回到镜像里的旧版本。
#     所以热更只用于验证，验证通过后仍要跑一次完整 build 固化。
# ============================================================
set -eu

DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

CONTAINER="${CONTAINER:-audiobook-mybooks-1}"
DEST="/var/www/mybooks"
DRY=0
WARN_FRONT=0

for arg in "$@"; do
    case "$arg" in
        --dry-run)  DRY=1 ;;
        --frontend) WARN_FRONT=1 ;;
        -h|--help)
            sed -n '3,17p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) echo "未知参数: $arg（用 --help 看用法）"; exit 1 ;;
    esac
done

# ---------- 0. 容器必须在跑 ----------
if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "==> 容器 $CONTAINER 没在运行。先启动：cd $DIR && docker compose up -d"
    exit 1
fi

# ---------- 1. 收集要同步的 Python 文件 ----------
# 只同步 webserver/ 与 server.py —— 这是 Dockerfile 里 COPY 进 /var/www/mybooks 的部分。
# tools/ 也在镜像里（COPY tools/），一并同步，方便直接 docker exec 跑脚本。
echo "==> [1/3] 收集变更文件（对比容器内 mtime）"

TMPLIST="$(mktemp)"
trap 'rm -f "$TMPLIST"' EXIT

# 找出源码里所有可能进镜像的 .py
find webserver server.py tools -name '*.py' -type f 2>/dev/null | sort > "$TMPLIST"

CHANGED=0
NEWCOUNT=0
while IFS= read -r f; do
    # 跳过缓存
    case "$f" in *__pycache__*|*.pyc) continue ;; esac

    src_mtime=$(stat -c %Y "$f" 2>/dev/null || echo 0)
    dst_mtime=$(docker exec "$CONTAINER" stat -c %Y "$DEST/$f" 2>/dev/null || echo -1)

    if [ "$dst_mtime" = "-1" ]; then
        echo "    [新增] $f"
        NEWCOUNT=$((NEWCOUNT + 1))
    elif [ "$src_mtime" -gt "$dst_mtime" ]; then
        echo "    [更新] $f"
        CHANGED=$((CHANGED + 1))
    fi
done < "$TMPLIST"

TOTAL=$((CHANGED + NEWCOUNT))
echo "    共 $TOTAL 个文件需要同步（更新 $CHANGED，新增 $NEWCOUNT）"

if [ "$TOTAL" = "0" ]; then
    echo "==> 容器内已是最新，无需操作。"
    exit 0
fi

if [ "$DRY" = "1" ]; then
    echo "==> --dry-run：仅列出，不做任何修改。"
    exit 0
fi

# ---------- 2. 逐个 docker cp ----------
echo "==> [2/3] 复制到容器（$CONTAINER:$DEST）"
SUCCESS=0
FAIL=0
while IFS= read -r f; do
    case "$f" in *__pycache__*|*.pyc) continue ;; esac
    src_mtime=$(stat -c %Y "$f" 2>/dev/null || echo 0)
    dst_mtime=$(docker exec "$CONTAINER" stat -c %Y "$DEST/$f" 2>/dev/null || echo -1)
    need=0
    [ "$dst_mtime" = "-1" ] && need=1
    [ "$dst_mtime" != "-1" ] && [ "$src_mtime" -gt "$dst_mtime" ] && need=1
    [ "$need" = "0" ] && continue

    # 目标子目录可能不存在（新增文件），先建
    d=$(dirname "$DEST/$f")
    docker exec "$CONTAINER" mkdir -p "$d" 2>/dev/null || true
    if docker cp "$f" "$CONTAINER:$DEST/$f" >/dev/null 2>&1; then
        SUCCESS=$((SUCCESS + 1))
    else
        echo "    !! 失败: $f"
        FAIL=$((FAIL + 1))
    fi
done < "$TMPLIST"
echo "    成功 $SUCCESS，失败 $FAIL"

# 权限对齐：镜像里文件属 mybooks 用户，docker cp 复制进来默认是 root
docker exec "$CONTAINER" chown -R mybooks:mybooks "$DEST/webserver" "$DEST/tools" 2>/dev/null || true
docker exec "$CONTAINER" sh -c "chown mybooks:mybooks $DEST/server.py" 2>/dev/null || true

# 清掉字节码缓存，否则可能加载旧的 .pyc
docker exec "$CONTAINER" find "$DEST" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

# ---------- 3. 重启 tornado ----------
echo "==> [3/3] 重启 tornado（只重启 Python 服务，nginx / myreader 不动）"
docker exec "$CONTAINER" supervisorctl restart mybooks:tornado 2>&1 | sed 's/^/    /' || {
    echo "    !! supervisorctl 重启失败，尝试整组重启"
    docker exec "$CONTAINER" supervisorctl restart mybooks 2>&1 | sed 's/^/    /' || true
}

echo "==> 等待 5 秒后检查状态"
sleep 5
docker exec "$CONTAINER" supervisorctl status 2>&1 | sed 's/^/    /' || true
echo
echo "    tornado 日志末尾（应无 Traceback）："
docker exec "$CONTAINER" tail -12 /data/log/mybooks.log 2>/dev/null | sed 's/^/    /' || echo "    （日志暂不可读）"

# ---------- 前端提醒 ----------
if [ "$WARN_FRONT" = "1" ]; then
    echo
    echo "=================================================================="
    echo "注意：前端改动（app/**/*.vue、app/locales/*.json）无法热更新。"
    echo "Vue 组件和语言包在构建时已编译进静态 dist，热更后端不会生效。"
    echo "验证完后端后，跑一次完整构建把前端也固化进镜像："
    echo "    cd $DIR && docker compose build && docker compose up -d"
    echo "（npm 依赖层有缓存，不会重新下载，主要耗时在 npm run build-spa）"
    echo "=================================================================="
fi

echo
echo "==> 热更完成。浏览器强刷（Ctrl+Shift+R）后验证。"
echo "    固化：cd $DIR && docker compose build && docker compose up -d"
