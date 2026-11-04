#!/bin/bash
# =====================================================================
# 从上游 mybooks 站点迁移图书数据 + 用户数据库 到 本改版站点
# 用法（在 NAS 的 ssh 里跑）：
#   1. 打开脚本开头，把 UPSTREAM_DIR / OUR_DIR 改成实际路径
#   2. 先跑一次默认（dry-run 模式）看看会复制什么
#   3. 确认无误后加 --apply 真正执行
# =====================================================================
set -eu

# ---------------- 改这三行 ----------------
# 上游 mybooks 源码/数据目录（就是挂到上游容器 /data 的那个宿主机目录）
# 找不准就跑: docker inspect <上游容器名> --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
UPSTREAM_DIR="/volume1/docker/mybooks"

# 本改版站点目录（源码 + 部署脚本）
OUR_DIR="/volume1/docker/audiobook"

# 本改版数据目录（挂到 audiobook 容器 /data，与源码目录分离，重装源码不伤数据）
OUR_DATA="/volume1/docker/audiobook-data"

# 上游容器名 / 本站容器名（用于自动停启，找不到容器则跳过停启）
UPSTREAM_CONTAINER="mybooks-mybooks-1"
OUR_CONTAINER="audiobook-mybooks-1"
# ------------------------------------------

MODE="${1:-}"
case "$MODE" in
    --apply) APPLY=1; MOVE=0 ;;
    --move)  APPLY=1; MOVE=1 ;;
    *)       APPLY=0; MOVE=0 ;;
esac

SRC_BOOKS="$UPSTREAM_DIR/books"        # calibre 书库（含 metadata.db 与书文件）
SRC_WEBDB="$UPSTREAM_DIR/books/calibre-webserver.db"   # 用户/权限库（多数部署在这）

if [ ! -d "$SRC_BOOKS" ]; then
    echo "!! 在 $UPSTREAM_DIR/books 下没找到书库目录。"
    echo "!! 请先确认上游目录："
    echo "!!   docker inspect $UPSTREAM_CONTAINER --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{\"\\n\"}}{{end}}'"
    exit 1
fi

echo "==> 迁移计划（dry-run 预览）"
echo "    上游书库     : $SRC_BOOKS"
echo "    上游用户库   : $SRC_WEBDB $( [ -f "$SRC_WEBDB" ] || echo '（未找到，稍后自动再找）' )"
echo "    本站目录     : $OUR_DIR"
if [ $APPLY = 0 ]; then
    echo "    模式         : dry-run（--apply 复制迁移 / --move 移动迁移）"
elif [ $MOVE = 1 ]; then
    echo "    模式         : ★ --move：移动（mv，跨同一文件系统秒完成，上游 books 会被腾空）★"
else
    echo "    模式         : ★ --apply：复制（rsync，上游原样保留）★"
fi
echo

# ---------- 0a. --move 模式先停上游容器（数据搬走后上游不能再写） ----------
if [ $MOVE = 1 ] && docker ps --format '{{.Names}}' | grep -qx "$UPSTREAM_CONTAINER"; then
    echo "==> [0/6] --move 模式：停止上游容器 $UPSTREAM_CONTAINER"
    docker stop "$UPSTREAM_CONTAINER" >/dev/null || true
fi

# ---------- 0b. 备份本站现有数据（只在真正执行时做） ----------
if [ $APPLY = 1 ]; then
    BK="$OUR_DIR/../audiobook-backup-$(date +%Y%m%d-%H%M%S)"
    echo "==> [0/6] 备份本站现有数据到 $BK"
    mkdir -p "$BK"
    [ -d "$OUR_DATA/books" ] && cp -a "$OUR_DATA/books" "$BK/books" 2>/dev/null || true
    [ -f "$OUR_DATA/books/calibre-webserver.db" ] && cp -a "$OUR_DATA/books/calibre-webserver.db" "$BK/" || true
    echo "    备份完成"
fi

# ---------- 1. 停本站容器（避免它持有 SQLite 句柄时被覆盖） ----------
if [ $APPLY = 1 ] && docker ps --format '{{.Names}}' | grep -qx "$OUR_CONTAINER"; then
    echo "==> [1/6] 停止本站容器 $OUR_CONTAINER"
    docker stop "$OUR_CONTAINER" >/dev/null
else
    echo "==> [1/6] 跳过停止容器（dry-run 或容器未运行）"
fi

# ---------- 2. 迁移书库（书文件 + metadata.db + audios 音频） ----------
echo "==> [2/6] $([ $MOVE = 1 ] && echo 移动 || echo 同步)书库 -> $OUR_DATA/books/"
if [ $MOVE = 1 ]; then
    # 同一文件系统内 mv 是瞬间完成的 rename，不做逐字节拷贝。
    # 逐个条目移动，把已存在的同名文件（如本站自己的 calibre-webserver.db
    # 已在第 3 步处理）跳过，其余直接让上游的顶上来。
    mkdir -p "$OUR_DATA/books"
    for item in "$SRC_BOOKS"/* "$SRC_BOOKS"/.[!.]*; do
        [ -e "$item" ] || continue
        base=$(basename "$item")
        [ "$base" = "calibre-webserver.db" ] && continue
        if [ -e "$OUR_DATA/books/$base" ]; then
            echo "    本站已有 $base，改用替换（先备份到备份目录）"
            mv "$OUR_DATA/books/$base" "$BK/books.$base.bak" 2>/dev/null || true
        fi
        mv "$item" "$OUR_DATA/books/$base"
    done
    echo "    移动完成，上游 books/ 只剩空壳。"
else
    RSYNC_FLAGS=(-a --info=stats1)
    [ $APPLY = 0 ] && RSYNC_FLAGS+=(--dry-run)
    # 注意：用 --delete 前请三思；这里默认不加，避免误删本站已有文件。
    rsync "${RSYNC_FLAGS[@]}" \
          --exclude 'calibre-webserver.db' \
          --exclude '.calibredb_import_temp*' \
          "$SRC_BOOKS/" "$OUR_DATA/books/"
fi

# ---------- 3. 迁移用户/权限库（Calibre-Web 侧） ----------
echo "==> [3/6] 同步用户数据库"
if [ -f "$SRC_WEBDB" ]; then
    if [ $MOVE = 1 ]; then
        if [ $APPLY = 0 ]; then
            echo "    dry-run：将移动 $SRC_WEBDB -> 本站（本站原库备份为 .bak）"
        else
            [ -f "$OUR_DATA/books/calibre-webserver.db" ] && \
                mv "$OUR_DATA/books/calibre-webserver.db" "$BK/calibre-webserver.db.bak" || true
            mv "$SRC_WEBDB" "$OUR_DATA/books/calibre-webserver.db"
            echo "    已移入上游用户库（本站原库备份为 calibre-webserver.db.bak）"
        fi
    else
        rsync "${RSYNC_FLAGS[@]}" "$SRC_WEBDB" "$OUR_DATA/books/calibre-webserver.db"
    fi
else
    # 有些部署放在别的位置，扫一遍找出来
    echo "    $SRC_WEBDB 不存在，尝试在上游目录里找 calibre-webserver.db："
    FOUND=$(find "$UPSTREAM_DIR" -maxdepth 4 -name 'calibre-webserver.db' 2>/dev/null | head -5)
    if [ -n "$FOUND" ]; then
        echo "$FOUND" | while read -r f; do echo "    发现: $f"; done
        if [ $APPLY = 1 ]; then
            FIRST=$(echo "$FOUND" | head -1)
            rsync -a "$FIRST" "$OUR_DATA/books/calibre-webserver.db"
            echo "    已用 $(echo "$FOUND" | head -1) 覆盖本站用户库"
        else
            echo "    dry-run：实际执行时会用第一个覆盖 $OUR_DATA/books/calibre-webserver.db"
        fi
    else
        echo "    !! 上游没有 calibre-webserver.db，只迁书不迁用户。"
    fi
fi

# ---------- 4. 修属主（容器内按 PUID/PGID 读写） ----------
if [ $APPLY = 1 ]; then
    echo "==> [4/6] 修正属主为 1026:100（与 docker-compose.yml 的 PUID/PGID 一致）"
    chown -R 1026:100 "$OUR_DATA/books" 2>/dev/null || \
        echo "    chown 失败（可能需要 sudo），稍后如遇写权限报错请手动: sudo chown -R 1026:100 $OUR_DATA/books"
else
    echo "==> [4/6] dry-run 跳过 chown"
fi

# ---------- 5. 重启本站容器 ----------
if [ $APPLY = 1 ]; then
    echo "==> [5/6] 启动本站容器"
    docker start "$OUR_CONTAINER" >/dev/null
    echo "    等 25 秒让 supervisord 拉起全部进程..."
    sleep 25
else
    echo "==> [5/6] dry-run 跳过启动"
fi

# ---------- 6. 验证 ----------
echo "==> [6/6] 验证（真正执行后才有意义）"
if [ $APPLY = 1 ]; then
    docker exec "$OUR_CONTAINER" python3 - <<'PY' 2>/dev/null || echo "    （容器刚起，查询失败可稍后手动再跑）"
import sqlite3
db = sqlite3.connect('/data/books/library/metadata.db')
print('    书数:', db.execute('select count(*) from books').fetchone()[0])
print('    标签数:', db.execute('select count(*) from tags').fetchone()[0])
PY
    docker exec "$OUR_CONTAINER" supervisorctl status 2>/dev/null || true
    echo
    echo "==> 完成。浏览器打开 https://NAS_IP:9800 检查书籍、用户、封面是否正常。"
else
    echo "    （dry-run 结束，加 --apply 执行）"
fi
