# NAS 一次性备份演练清单

目标：在 NAS 上**不碰真实书库改动**的前提下，完整跑一次「全量 → 增量 → 校验 → 清理」，
确认 `scripts/backup.sh` 可用，并把结果留下作为上线前证据。

> 演练使用**独立的备份目录**（`audiobook-backup-drill`），成功后再切到正式目录。
> 原始部署包不要动；本清单只读数据目录，只写演练备份目录。

## 0. 准备：路径与环境变量

先 SSH 登录 NAS，进入源码目录（按实际位置替换）：

```sh
export SRC_DIR=/volume1/docker/audiobook-src-opt      # 源码仓库（含 scripts/backup.sh）
export DATA_DIR=/volume1/docker/audiobook-data        # 站点数据目录（真实数据）
export DRILL_ROOT=/volume1/docker/audiobook-backup-drill   # 演练备份目录（独立）
export APP_CONTAINER=audiobook-mybooks-1              # 正在运行的应用容器名
cd "$SRC_DIR"
```

逐条确认（每条都要有输出，否则先解决）：

```sh
ls -ld "$DATA_DIR"                    # 目录存在
ls -l "$DATA_DIR/books/library/metadata.db"      # calibre 元数据库存在
ls -l "$DATA_DIR/books/calibre-webserver.db"     # 站点数据库存在
df -h "$(dirname "$DRILL_ROOT")"      # 剩余空间 ≥ 数据目录 × 1.2
docker inspect -f '{{.State.Running}}' "$APP_CONTAINER"   # 期望 true
```

创建演练目录（必须位于数据目录之外，脚本会拒绝备份目录落在数据目录内部）：

```sh
mkdir -p "$DRILL_ROOT"
```

> 可调参数（都有默认值，演练先用默认）：
> `KEEP_DAILY=7`、`KEEP_WEEKLY=4`、`KEEP_MONTHLY=6`、`MIN_FREE_GB=5`、
> `EXCLUDE_DIRS=cache,log,.backup-tmp`、`EXCLUDE_PATTERNS=*.tmp,*.part,*.partial,*.swp`。

## 1. 预检：帮助与 dry-run（不写任何文件）

```sh
RUNNER=local sh scripts/backup.sh --help
RUNNER=local DATA_DIR="$DATA_DIR" BACKUP_ROOT="$DRILL_ROOT" sh scripts/backup.sh --dry-run
```

预期输出（摘录）：

```
 audiobook 数据备份  ...
   数据目录 : /volume1/docker/audiobook-data（站点运行中，数据库走在线备份）
   备份目录 : /volume1/docker/audiobook-backup-drill
   模式     : all   清理旧快照: 1   dry-run: 1
   保留策略 : 日 7 / 周 4 / 月 6
   运行器   : local (python3)
...
[backup] [dry-run] 数据目录: ...
[backup] [dry-run] 备份目录: ...
[backup] [dry-run] 时间戳: ...，模式: all
```

判定：无 `!!` 行、退出码 0。若提示 `本机没有 python3` → 改用第 6 节 docker 路径。

## 2. 第一步：只备份数据库（秒级）

```sh
RUNNER=local DATA_DIR="$DATA_DIR" BACKUP_ROOT="$DRILL_ROOT" \
  sh scripts/backup.sh --db-only
echo "exit=$?"
```

预期输出（关键行）：

```
   数据目录 : ...（站点运行中，数据库走在线备份）
[backup] 数据库已备份: <DATA_DIR>/books/calibre-webserver.db -> <DRILL_ROOT>/db/<ts>/webserver.db（x.x MB，sqlite-backup-api）
[backup] 数据库已备份: <DATA_DIR>/books/library/metadata.db -> <DRILL_ROOT>/db/<ts>/calibre-metadata.db（x.x MB，sqlite-backup-api）
[backup] 备份完成，状态=ok，清单=<DRILL_ROOT>/manifests/backup-<ts>.json
 备份成功。恢复步骤见 docs/备份与恢复演练.md
exit=0
```

检查点（全部满足才算通过）：

```sh
TS=$(ls -1 "$DRILL_ROOT/db" | sort | tail -1); echo "$TS"
ls -l "$DRILL_ROOT/db/$TS"/            # webserver.db、calibre-metadata.db、manifest.json
python3 - <<'PY'
import json, os, sqlite3, glob
root = os.environ["DRILL_ROOT"]
ts = sorted(os.listdir(os.path.join(root, "db")))[-1]
for name in ("webserver.db", "calibre-metadata.db"):
    p = os.path.join(root, "db", ts, name)
    con = sqlite3.connect(p)
    print(name, con.execute("PRAGMA integrity_check").fetchone()[0],
          "tables=", con.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0])
    con.close()
m = json.load(open(os.path.join(root, "manifests", "backup-%s.json" % ts)))
print("manifest:", m["status"], len(m.get("databases", [])))
PY
```

期望：两个库都打印 `ok`；`manifest: ok 2`。

## 3. 第二步：第一次全量（数据库 + 文件）

```sh
RUNNER=local DATA_DIR="$DATA_DIR" BACKUP_ROOT="$DRILL_ROOT" \
  KEEP_DAILY=7 KEEP_WEEKLY=4 KEEP_MONTHLY=6 MIN_FREE_GB=5 \
  sh scripts/backup.sh
echo "exit=$?"
```

预期输出（关键行）：

```
[backup] 数据库已备份: ...（sqlite-backup-api）
[backup] 文件快照完成：N 个文件、M 个目录，复制 N 个（x.x GB），硬链接复用 0 个，耗时 xx.xs
[backup] 备份完成，状态=ok，清单=<DRILL_ROOT>/manifests/backup-<ts>.json
 备份成功。恢复步骤见 docs/备份与恢复演练.md
exit=0
```

判定：`硬链接复用 0 个`（首份没有可复用文件）；无 `!!` 行；`files/<ts>/books/library/metadata.db` 存在。

记录体积：

```sh
TS=$(ls -1 "$DRILL_ROOT/files" | sort | tail -1)
du -sh "$DRILL_ROOT/files/$TS"
find "$DRILL_ROOT/files/$TS" -type f | wc -l
```

## 4. 第三步：第二次全量（验证增量）

至少间隔 60 秒再跑（时间戳精确到秒，避免目录同名）：

```sh
sleep 60
RUNNER=local DATA_DIR="$DATA_DIR" BACKUP_ROOT="$DRILL_ROOT" sh scripts/backup.sh
echo "exit=$?"
```

预期：第二份的 `硬链接复用` 数量 **接近文件总数**（未变化文件共享 inode），
`复制` 数量与字节数应很小。检查：

```sh
TS2=$(ls -1 "$DRILL_ROOT/files" | sort | tail -1)
du -sh "$DRILL_ROOT/files/$TS2"                         # 应明显小于第一份
stat -c '%i %n' "$DRILL_ROOT/files/$TS2/books/library/metadata.db" \
              "$DRILL_ROOT/files/$TS"/books/library/metadata.db 2>/dev/null
# 两次输出的 inode 相同 = 硬链接复用成功
```

若提示 `!! 备份目录不支持硬链接`：说明备份盘是 exFAT/FAT 或无硬链接权限，
仍可恢复但空间会翻倍，需改用支持硬链接的文件系统（ext4/Btrfs/XFS）。

## 5. 第四步：校验与保留策略

```sh
RUNNER=local DATA_DIR="$DATA_DIR" BACKUP_ROOT="$DRILL_ROOT" sh scripts/backup.sh --list
python3 - <<'PY'
import json, glob, os
root = os.environ["DRILL_ROOT"]
for p in sorted(glob.glob(os.path.join(root, "manifests", "*.json")):
    m = json.load(open(p))
    print(os.path.basename(p), m["status"], m.get("files", {}).get("copied"))
PY
```

期望：两份 manifest 都为 `ok`（或 `ok-with-warnings`，并确认告警只是被忽略的临时文件）。

演练成功判定（5 项全过）：

1. 三次执行退出码均为 `0`；
2. 两份 manifest 存在且 `status=ok`；
3. 两个数据库副本 `PRAGMA integrity_check = ok`；
4. 第二份快照 `硬链接复用 > 0` 且体积明显小于第一份；
5. `--list` 能看到 `db/`、`files/`、`manifests/` 三个目录。

## 6. docker 路径（Windows 上未验证，必须在 NAS 上单独跑一次）

前置：NAS 上已构建应用镜像（`docker image ls mybooks-local:latest` 有输出）。
若没有：在 compose 目录执行 `docker compose build`（或 `docker build -t mybooks-local:latest .`）。

```sh
RUNNER=docker BACKUP_IMAGE=mybooks-local:latest DOCKER_USER=0:0 \
  DATA_DIR="$DATA_DIR" BACKUP_ROOT="$DRILL_ROOT" \
  sh scripts/backup.sh --dry-run

RUNNER=docker BACKUP_IMAGE=mybooks-local:latest DOCKER_USER=0:0 \
  DATA_DIR="$DATA_DIR" BACKUP_ROOT="$DRILL_ROOT" \
  sh scripts/backup.sh --db-only
```

脚本内部实际执行（可复制出来单独排障）：

```sh
docker run --rm -i --network none --user 0:0 -e TZ=Asia/Shanghai \
  -v "$DATA_DIR:/data" -v "$DRILL_ROOT:/backup" \
  --entrypoint python3 mybooks-local:latest - \
  --data /data --backup /backup --mode db --keep-daily 7 --keep-weekly 4 --keep-monthly 6 \
  < scripts/backup_run.py
```

docker 路径检查点：

- `docker image inspect mybooks-local:latest` 成功，否则脚本退出 3 并提示构建；
- 容器内以 `--user 0:0` 运行，写 `/backup` 时不应出现 `Permission denied`；
- `--network none` 下仍能完成（备份不需要网络）；
- 容器一次性退出，`docker ps -a` 不应留下名字含 `mybooks` 的临时容器。

常见失败：

| 现象 | 原因 | 处理 |
|---|---|---|
| `找不到镜像 mybooks-local:latest` | 镜像名与 compose 不一致 | `docker images` 查实际 tag，用 `BACKUP_IMAGE=` 覆盖 |
| `Permission denied` 写 `/backup` | 目录属主/权限 | `DOCKER_USER=0:0`；或 `chown` 备份目录 |
| 数据目录为空 | 挂载路径写错 | 用绝对路径，`ls -ld` 先确认 |
| 退出码 3 且提示「备份目录不能位于数据目录内部」 | 路径包含关系 | 换到独立目录 |

> **重要**：docker 路径当前只在代码层验证过，尚未在 Windows 或 NAS 实机跑通；
> 首次务必用 `--db-only` 小步验证，再跑全量。

## 7. 失败排查（local / docker 通用）

| 退出码 / 输出 | 含义 | 处理 |
|---|---|---|
| `2` + `已有备份进程在运行（pid …）` | 上一轮未结束 | 等它结束；确认无进程后删 `$BACKUP_ROOT/.backup.lock` |
| `2` + `备份完成但有告警` | 部分文件被跳过 | 看 `!!` 行；临时文件可忽略，权限错误需修 |
| `3` + `备份盘剩余空间不足` | 低于 `MIN_FREE_GB` | 扩容或调小 `MIN_FREE_GB` |
| `3` + `在线备份失败（容器可能在写入）` | 容器未停且不能冷拷贝 | 保持容器运行（走在线备份）；或停容器后 `--db-only` 会冷拷贝 |
| `3` + `完整性校验失败` | 副本损坏 | 检查源库磁盘健康；重跑一次；仍失败则停容器冷拷贝 |
| `3` + `文件快照失败，已清理不完整快照` | 读取中断/权限 | 看日志错误；修权限后重跑 |
| `!! 有 N 个文件未能备份` | 个别文件读失败 | 输出前 10 条；确认是否可忽略 |

## 8. 演练收尾

1. 保留 `$DRILL_ROOT/manifests/*.json` 与执行日志作为证据。
2. 演练目录可保留数日再删；删除前确认 `BACKUP_ROOT` 不是正式目录：

```sh
echo "$DRILL_ROOT"     # 必须是 audiobook-backup-drill
# 确认无误后：rm -rf "$DRILL_ROOT"
```

3. 正式启用：把 cron 指向正式目录（默认值可覆盖）：

```sh
# 每天 03:30，日志追加
30 3 * * * /bin/sh $SRC_DIR/scripts/backup.sh \
  >> /volume1/docker/audiobook-backup/backup.log 2>&1
```
