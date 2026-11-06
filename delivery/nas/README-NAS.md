# 群晖 DSM 7 脚本集（audiobook 备份 / 恢复 / 补丁）

本目录的脚本是为群晖 DSM 7 准备的**真实可执行文件**，不是文档里的命令片段。
请直接调用脚本，不要从 Markdown 复制命令（缩进、换行、引号、全角字符都会导致执行失败）。

所有脚本：

- `#!/bin/bash` + `set -euo pipefail`
- LF 换行，zip 内权限 `0755`
- 路径、容器名、镜像名集中在本目录的 `paths.conf`，环境变量可覆盖，命令行参数最终覆盖
- 支持 `--help`；出错输出中文提示并返回明确退出码

## 零、快速开始（复制即用）

以下命令全部按顺序执行，**一律用 `/bin/bash`，不要用 `sh`**（DSM 的 `sh` 是 BusyBox，会直接报语法错误）。

### 第 1 步：解压与校验

```bash
cd /volume1/docker
tar -xzf audiobook-nas-release.tar.gz
cd audiobook-ops
/bin/bash ./install.sh
```

`install.sh` 会校验 `SHA256SUMS`（79 个文件）、统一权限（脚本 0755、其余 0644）并打印后续命令。
如果提示 SHA256 失败，说明包不完整，重新上传/解压，不要继续。

### 第 2 步：只读预检

```bash
/bin/bash nas/00-check-env.sh
```

退出码 0 = 通过。有 `!!` 项先按提示修（缺 `sha256sum`、磁盘余量不足、数据文件不可读等）。

### 第 3 步：探测路径并核对 paths.conf

```bash
/bin/bash nas/05-detect-paths.sh
```

退出码 0 = 关键项已探明；1 = 有关键项待确认（看输出末尾「需要你确认」）。
按输出修订 `nas/paths.conf` 的主机路径，然后重跑一次 `00`。

### 第 4 步：把备份脚本放进源码目录

```bash
mkdir -p /volume1/docker/audiobook/scripts
cp -a scripts/backup.sh scripts/backup_run.py /volume1/docker/audiobook/scripts/
chmod 755 /volume1/docker/audiobook/scripts/backup.sh /volume1/docker/audiobook/scripts/backup_run.py
```

`20-backup-full.sh` 最终调用的就是 `APP_ROOT/scripts/backup.sh`，所以先放进去。
（第 6 步的覆盖包也会写这两个文件；已拷过且内容一致时，`60` 会识别为「已最新」，不算冲突。）

### 第 5 步：备份链路（先演练再正式）

```bash
/bin/bash nas/10-backup-db.sh --dry-run
/bin/bash nas/10-backup-db.sh
/bin/bash nas/20-backup-full.sh
/bin/bash nas/30-verify-backup.sh
/bin/bash nas/40-restore-drill.sh
```

`10` 只备数据库，用来验证链路；`20` 全量；`30` 校验 SHA256/SQLite；`40` 在独立演练目录恢复，不碰生产数据。

### 第 6 步：应用覆盖包（无 git 方案）

```bash
/bin/bash nas/60-apply-overlay.sh --list     # 看 34 个文件（18 新增 / 16 覆盖）
/bin/bash nas/60-apply-overlay.sh            # dry-run，逐个比对基线 sha256
/bin/bash nas/60-apply-overlay.sh --apply    # 确认后覆盖，原文件备份到 rollback/<时间戳>/
```

**dry-run 预期输出（干净源码树，未预先拷贝 scripts）**：

```text
计划结果: 覆盖 16，新增 18，已最新 0，跳过 0
```

若第 4 步已拷过 `backup.sh`、`backup_run.py`（两文件内容与本包一致），应为：

```text
计划结果: 覆盖 16，新增 16，已最新 2，跳过 0
```

若出现 `跳过 N`，会逐个列出文件名与原因（基线 sha256 不一致 = 该文件被你改过或版本不同）。
确认要覆盖再加 `--force`（仍会先备份）。退出码 4 表示有跳过项，其余文件已应用。

### 第 7 步：打标签 → 构建 → 启动（源码打进镜像，必须重建）

```bash
docker tag mybooks-local:latest mybooks-local:pre-opt
mkdir -p ./logs
docker compose -f /volume1/docker/audiobook/docker-compose.yml build mybooks \
  2>&1 | tee ./logs/build-$(date +%Y%m%d-%H%M%S).log
docker compose -f /volume1/docker/audiobook/docker-compose.yml up -d mybooks
```

等价脚本入口（`--build` 会自动先打标签）：

```bash
/bin/bash nas/60-apply-overlay.sh --build
```

**构建失败的处理**：

- 日志出现 `Could not resolve host` / `Temporary failure in name resolution` / `Connection timed out` /
  `dial tcp` / `Failed to fetch` → **网络或镜像源问题**，不是代码问题；换时段重试。
- 停在仓内源码路径或 `SyntaxError` / `ImportError` / `ModuleNotFoundError` → **代码问题**，
  用 `--rollback` 还原源码后排查。
- **失败时旧镜像 `mybooks-local:pre-opt` 仍在，容器未重启，站点不受影响**。
- 看日志：`tail -n 100 ./logs/build-*.log`；容器日志：`docker compose ... logs --tail 100 mybooks`。

### 第 8 步：确认镜像已包含最新源码

```bash
/bin/bash nas/70-check-image.sh
```

只读校验，不构建、不重启。容器在跑就 `docker exec` 进去算 sha256；没在跑就用 `docker run --rm` 拿镜像算，
再逐个对照 `overlay/MANIFEST.tsv` 的 `new_sha256`，输出三类结果：

| 结果 | 含义 |
|---|---|
| `OK` | 已包含，sha256 与覆盖包完全一致 |
| `DIFF` | 文件存在但内容旧（没覆盖成功，或构建用的是旧源码） |
| `MISSING` | 文件不存在（新增项没进镜像） |

同时打印镜像 Id、创建时间、标签、容器启动时间，以及**容器实际运行的镜像是否等于 `mybooks-local:latest`**——
不一致就说明「构建了但没 `up -d`」，此时 `OK` 数偏少是假象，先重启再重跑。

```text
==== 结论 ====
镜像已包含全部 34 项优化
```

退出码：`0` 全部包含 / `3` 部分或未包含 / `1` 执行错误。脚本化消费：

```bash
/bin/bash nas/70-check-image.sh --json
```

其他选项：`--image NAME`、`--container NAME`、`--app-dir DIR`（容器内源码根，默认自动探测 `/app`、
`/var/www/mybooks` 等）。

### 第 9 步：回滚（代码与镜像各一条）

```bash
# 源码回滚（省略时间戳 = 最近一次）
/bin/bash nas/60-apply-overlay.sh --rollback

# 镜像回滚（回到构建前的镜像）
docker tag mybooks-local:pre-opt mybooks-local:latest
docker compose -f /volume1/docker/audiobook/docker-compose.yml up -d mybooks
# 或
/bin/bash nas/60-apply-overlay.sh --rollback-image
```

两者独立：源码回滚不会自动回退镜像；镜像回滚也不会改源码。要完全回到旧状态，先源码回滚再镜像回滚。

### 第 10 步：定时任务

```bash
/bin/bash nas/90-cron-setup.sh --dsm
```

只打印 DSM「控制面板 → 任务计划」的配置步骤；确认后再 `--apply`（仅在你明确需要系统 crontab 时使用）。

## 一、执行顺序

| 顺序 | 脚本 | 作用 | 是否改动系统 |
|---|---|---|---|
| 1 | `00-check-env.sh` | 只读预检：bash、docker、命令、数据文件、路径可写、磁盘余量 | 否 |
| 2 | `05-detect-paths.sh` | 只读探测真实路径（挂载、metadata.db、.audio、compose），输出 paths.conf 建议值 | 否 |
| 3 | `10-backup-db.sh` | 仅数据库在线备份（先验证备份链路） | 只写备份目录 |
| 4 | `20-backup-full.sh` | 数据库 + 书籍 + 音频全量/增量 + 保留策略 | 只写备份目录 |
| 5 | `30-verify-backup.sh` | 校验最新（或指定）快照的 manifest、SHA256、SQLite 完整性 | 否 |
| 6 | `40-restore-drill.sh` | 在独立演练目录恢复并校验，不写生产路径 | 只写演练目录 |
| 7 | `60-apply-overlay.sh` | **无 git 时的源码覆盖**：校验基线、备份、应用、回滚；默认只打印生效命令 | 仅 `--apply` 时改源码 |
| 8 | `70-check-image.sh` | 只读检查镜像/容器内源码是否与覆盖包一致，并核对容器是否跑在新镜像上 | 否 |
| 9 | `50-apply-patches.sh` | git 仓库方式的补丁应用（无 git 时改用 `60`，二者不要同时用） | 仅 `--apply` 时改源码 |
| 10 | `90-cron-setup.sh` | 打印 crontab 行 / DSM 任务计划步骤，`--apply` 才写 crontab | 仅 `--apply` 时改 crontab |

完整命令见「零、快速开始」；本表只说明先后关系。备份（3–6）与源码覆盖（7）互不影响，
先备份再改源码更稳妥；改了源码并重建后，用 `70` 确认镜像里真的是新代码。

## 二、paths.conf（唯一的路径配置）

脚本不再各自写死路径，全部 `source` 同目录的 `paths.conf`。文件里的值是依据部署包
`docker-compose.yml`、`INSTALL_GUIDE.md` 和上传说明整理出的实际布局：

| 变量 | 默认值 | 依据 |
|---|---|---|
| `APP_ROOT` | `/volume1/docker/audiobook` | INSTALL_GUIDE 目录布局、升级脚本路径 |
| `APP_GIT_DIR` | `/volume1/docker/audiobook-git` | INSTALL_GUIDE：站点目录无 `.git`，历史在站点外 |
| `APP_CONFIG_DIR` | `$APP_ROOT/config` | 上传说明 hotfix 的 `config/auto.py` |
| `DATA_DIR` | `/volume1/docker/audiobook-data` | `docker-compose.yml` 的 `/data` 挂载 |
| `LIBRARY_DIR` | `$DATA_DIR/books/library` | INSTALL_GUIDE、容器内 `/data/books/library` |
| `METADATA_DB` | `$LIBRARY_DIR/metadata.db` | calibre 元数据库 |
| `WEB_DB` | `$DATA_DIR/books/calibre-webserver.db` | 站点 SQLite |
| `AUDIO_ROOT` | `$LIBRARY_DIR` | 音频在每本书目录的 `.audio/` 内 |
| `BACKUP_ROOT` | `/volume1/backup/audiobook` | INSTALL_GUIDE 备份示例；**目标盘待你确认** |
| `DRILL_PREFIX` / `DRILL_DIR` | `/volume1/backup` / `.../audiobook-restore-drill` | 与备份同盘、且不在备份目录内 |
| `COMPOSE_FILE` | `$APP_ROOT/docker-compose.yml` | 部署包 |
| `COMPOSE_PROJECT` / `APP_SERVICE` | `audiobook` / `mybooks` | 由容器名 `audiobook-mybooks-1` 推断 |
| `APP_CONTAINER` | `audiobook-mybooks-1` | `docker-compose.yml` 工程目录名 |
| `BACKUP_IMAGE` | `mybooks-local:latest` | `docker-compose.yml` |
| `HTTP_PORT` / `HTTPS_PORT` | `9800` / `8443` | `docker-compose.yml` 端口映射 |
| `TZ` / `PUID` / `PGID` | `Asia/Shanghai` / `1026` / `100` | `docker-compose.yml` |

临时覆盖（不改文件）：

```bash
DATA_DIR=/volume1/docker/audiobook-data2 BACKUP_ROOT=/volume2/backup \
  /bin/bash ./20-backup-full.sh --dry-run
```

## 三、备份实现的两个入口

| 文件 | 来源 | 适用场景 |
|---|---|---|
| `delivery/scripts/backup.sh` + `backup_run.py` | **补丁 01-P0-backup 新增**，基线 `32bc1d4` 里没有 | 已 `50-apply-patches.sh --apply` 后，源码内的正式实现 |
| `delivery/nas/20-backup-full.sh` | 独立外壳，不属于补丁 | 未打补丁也能用；负责校验路径、参数、退出码，再调用 `APP_ROOT/scripts/backup.sh` |

`20` 不是另一套备份逻辑：它最终执行 `APP_ROOT/scripts/backup.sh`。所以：

1. 未打补丁：`APP_ROOT/scripts/backup.sh` 不存在，`20` 会提示补丁未应用；可先按 `50` 应用补丁，或把 `delivery/scripts/backup.sh`、`backup_run.py` 复制到 `APP_ROOT/scripts/`（两文件均为 0755、LF）。
2. 已打补丁：直接用 `20`（或 `10`）即可，`delivery/scripts/` 仅作备份/对照。

## 四、无 git 环境：文件覆盖包（`60-apply-overlay.sh`）

目标目录不是 git 仓库、也没有 `/volume1/docker/audiobook-git` 时，**不要用 `50`**，改用 `60`。
`60` 不调用 git，直接把最终树（`fdbf006`）里**有改动的文件**按原相对路径覆盖过去。

### 4.1 覆盖包里有什么

`delivery/overlay/`：

| 文件/目录 | 内容 |
|---|---|
| `files/` | 34 个改动文件的完整内容，保持原相对路径（如 `webserver/handlers/base.py`） |
| `MANIFEST.tsv` | 每行 `action|path|mode|base_sha256|new_sha256`；`add` 表示新增文件、`update` 表示覆盖已有文件；`base_sha256` 是基线 `32bc1d4` 的哈希，用于校验目标是否同一版本 |
| `SHA256SUMS` | 覆盖包自身完整性校验（`60 --apply/--build` 前自动 `sha256sum -c`） |

34 个 = 18 个新增（含 `scripts/backup.sh`、`scripts/backup_run.py`、`scripts/search_index.py`、
`webserver/base/pagination.py`、`webserver/services/search_index.py`、`webserver/handlers/search_index.py`、
`docs/` 文档、`tests/`）+ 16 个覆盖（`webserver/main.py`、`webserver/settings.py`、各 handlers/services 等）。

先看清单，不写任何文件：

```bash
/bin/bash ./60-apply-overlay.sh --list
```

### 4.2 校验与跳过规则

| 情况 | 默认行为 | 加 `--force` |
|---|---|---|
| `update` 文件存在且 sha256 与基线一致 | 备份后覆盖 | 同左 |
| `update` 文件存在但 sha256 不一致（你改过/版本不同） | **跳过并列出** | 备份后覆盖 |
| `update` 文件不存在 | **跳过并列出** | 备份后作为新增写入 |
| `add` 文件不存在 | 直接新增 | 同左 |
| `add` 文件已存在且 sha256 与本包一致 | 视为已应用（计为「已最新」），不算冲突 | 同左 |
| `add` 文件已存在但内容不同 | **按冲突跳过** | 备份原文件后覆盖 |

这样设计的目的：防止把你自己改过的文件、或不同版本部署包的文件，被本包无声覆盖。有跳过项时退出码为 `4`。

### 4.3 应用、回滚源码

```bash
# 1. dry-run：只比对基线，打印 覆盖/新增/跳过 结果
/bin/bash ./60-apply-overlay.sh

# 2. 确认无误后应用（先备份原文件到 rollback/<时间戳>/）
/bin/bash ./60-apply-overlay.sh --apply

# 3. 有冲突时，确认那些文件确实要覆盖（仍先备份）
/bin/bash ./60-apply-overlay.sh --apply --force

# 4. 一键还原源码（省略时间戳即最近一次）
/bin/bash ./60-apply-overlay.sh --rollback
/bin/bash ./60-apply-overlay.sh --rollback=20261106-120000
```

第 1 条 dry-run 在干净源码树上应为 `覆盖 16，新增 18，已最新 0，跳过 0`；
若已手工拷过 `scripts/backup.sh`、`backup_run.py`，则为 `覆盖 16，新增 16，已最新 2，跳过 0`。

备份目录 `<ops目录>/rollback/<YYYYmmdd-HHMMSS>/`：

- `files/<相对路径>`：被覆盖前的原文件（`M|路径`）
- `ROLLBACK.tsv`：`M|路径` = 需恢复原文件，`A|路径` = 本次新增、回滚时删除
- 回滚只还原源码，**不还原镜像**；镜像回滚命令见 4.5。

### 4.4 生效方式：compose 判断 bind mount 还是打进镜像

`60` 会读 `COMPOSE_FILE` 自动判断，并在末尾**直接打印要执行的命令**，不需要你自己判断：

| compose 特征 | 判定 | 覆盖后生效命令 |
|---|---|---|
| 有源码目录挂载（`- /path:/app`、`/var/www/mybooks` 等） | `bind` | `docker restart <容器>` 或 `docker compose ... restart` |
| 有 `build:`、只挂载数据目录（本部署包即此形态） | `image` | 必须重建镜像：`tag → build → up -d` |

本部署包的 `docker-compose.yml` 是 `build: context: .` + `image: mybooks-local:latest`，卷只有
`- /volume1/docker/audiobook-data:/data` —— 结论：**源码打进镜像（baked in）**，只重启容器不会生效，
必须重建镜像。镜像名从 `paths.conf` 的 `BACKUP_IMAGE` 读取，不写死。

### 4.5 完整生效命令序列（默认只打印，不自动执行）

```bash
# ① 备份当前镜像（失败可一键回滚）
docker tag mybooks-local:latest mybooks-local:pre-opt

# ② 重建镜像（日志同时写到 logs/build-<时间戳>.log）
mkdir -p ./logs
docker compose -f /volume1/docker/audiobook/docker-compose.yml build mybooks \
  2>&1 | tee ./logs/build-$(date +%Y%m%d-%H%M%S).log

# ③ 用新镜像重启
docker compose -f /volume1/docker/audiobook/docker-compose.yml up -d mybooks

# ④ 镜像回滚（代码没动、只想回到旧镜像）
docker tag mybooks-local:pre-opt mybooks-local:latest \
  && docker compose -f /volume1/docker/audiobook/docker-compose.yml up -d mybooks
```

对应脚本入口（只有显式加开关才会真正执行 docker 命令）：

```bash
/bin/bash ./60-apply-overlay.sh --tag-only          # ① 仅打 pre-opt 标签
/bin/bash ./60-apply-overlay.sh --build             # ①+②+③（自动先打标签）
/bin/bash ./60-apply-overlay.sh --rollback-image    # ④ 回到旧镜像
```

不带上述开关时 `60` 只做文件比对/覆盖并**打印**这些命令，不改镜像、不 build、不重启容器。

### 4.6 构建可能失败：先分清网络还是代码

镜像构建会重新执行 Dockerfile 里的 `apt` / `pip` / `npm` / `calibre` 层，需要外网或国内镜像源
（compose 里 `BUILD_COUNTRY=CN` 就是为此）。判断方法：

```bash
tail -n 100 ./logs/build-*.log
docker compose -f /volume1/docker/audiobook/docker-compose.yml logs --tail 100 mybooks
```

- 日志出现 `Could not resolve host`、`Temporary failure in name resolution`、`Connection timed out`、
  `proxy`、`dial tcp`、`Failed to fetch`、`Read timed out` → **网络/镜像源问题**，不是代码问题；
  换时段重试或改 `BUILD_COUNTRY` / pip 源后重跑 `build`。
- 日志停在具体仓内源码路径或 `SyntaxError` / `ImportError` / `ModuleNotFoundError` → **代码问题**，
  用 `60 --rollback` 还原源码，再排查对应文件。
- 构建失败不会自动回退镜像，旧镜像 `mybooks-local:pre-opt` 仍在，容器本身未重启，站点不受影响。

### 4.7 这种方式什么时候无效

覆盖包的前提是**宿主机上有源码目录**（`webserver/` 这个子目录存在即满足）。以下情况无效：

- 宿主机只有预构建镜像，没有源码、没有 `Dockerfile` —— 无从覆盖，也无从重建；
- 镜像由别处 CI/构建机产出，NAS 只 `docker pull` —— 必须**在构建镜像的机器上改源码、重新构建并推送**，
  再在 NAS 上 `docker compose pull && up -d`（或导入新镜像后 `up -d`）。

判断当前是不是这种情况：

```bash
ls -l /volume1/docker/audiobook/webserver        # 有 → 覆盖可行
grep -nE 'build:|image:' /volume1/docker/audiobook/docker-compose.yml
```

`build:` 存在且本机有源码 → 覆盖可行；只有 `image:` 指向远程仓库 → 覆盖无效。

### 4.8 `50` 与 `60` 怎么选

| 条件 | 用哪个 |
|---|---|
| 目标目录是 git 仓库，或存在可用 `APP_GIT_DIR` | `50-apply-patches.sh`（可 `git apply --check` 预演） |
| 不是 git 仓库（本环境） | `60-apply-overlay.sh` |
| 只想要备份功能 | 只应用覆盖包里 `scripts/backup.sh`、`scripts/backup_run.py`（`--list` 看路径） |
| 想回滚某几个文件 | `60 --rollback=<时间戳>` 会整体还原该次应用，或用 `rollback` 目录里的 `files/` 手工挑选 |

## 五、常用命令

```bash
# 1. 预检与路径探测（都只读）
/bin/bash ./00-check-env.sh
/bin/bash ./05-detect-paths.sh

# 2. 按 05 输出修订 paths.conf 后重新预检
/bin/bash ./00-check-env.sh

# 3. 仅数据库备份，先演练
/bin/bash ./10-backup-db.sh --dry-run
/bin/bash ./10-backup-db.sh

# 4. 全量/增量备份（默认保留 7 日 / 4 周 / 6 月）
/bin/bash ./20-backup-full.sh
/bin/bash ./20-backup-full.sh --keep-daily 14 --no-prune

# 5. 校验最新快照；大库可加 --deep 重数文件
/bin/bash ./30-verify-backup.sh
/bin/bash ./30-verify-backup.sh --timestamp 20261106-030000 --deep

# 6. 恢复演练（默认只恢复数据库；--with-files 连文件快照一起复制）
/bin/bash ./40-restore-drill.sh
/bin/bash ./40-restore-drill.sh --with-files --force

# 7. 源码改动（二选一，见第四章）
/bin/bash ./60-apply-overlay.sh            # 无 git：dry-run
/bin/bash ./60-apply-overlay.sh --apply
/bin/bash ./60-apply-overlay.sh --build    # 打进镜像的部署：tag -> build -> up -d
/bin/bash ./50-apply-patches.sh            # 有 git：dry-run
/bin/bash ./50-apply-patches.sh --apply

# 8. 定时任务：先看配置，再决定是否写入
/bin/bash ./90-cron-setup.sh --dsm
/bin/bash ./90-cron-setup.sh --apply
```

每个脚本的完整参数用 `--help` 查看。

## 六、待确认项（05 会重新探测并列出）

以下项目文档与部署包没有写全，脚本不做猜测：

1. **备份目标盘**：默认 `/volume1/backup/audiobook` 来自安装指南的备份示例；若没有 `/volume1/backup` 或想备份到独立盘，请改 `BACKUP_ROOT`。
2. **音频库位置**：源码把音频放在每本书目录的 `.audio/` 内，因此随书库一起备份；如果你另建了音频卷或独立「有声书」目录，请提供路径并改 `AUDIO_ROOT` / `DATA_DIR`。
3. **git 历史目录**：默认 `/volume1/docker/audiobook-git`；若你的升级历史在别处，改 `APP_GIT_DIR`（`50` 用分离式 git 目录）。
4. **对外访问方式**：默认 HTTP `9800`、HTTPS `8443`；如做了反代或改端口，改 `HTTP_PORT` / `HTTPS_PORT`。

`05-detect-paths.sh` 会把探不到的项目打印在「需要你确认」，并在退出码上返回 1。

## 七、退出码

| 脚本 | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| `00-check-env.sh` | 通过 | 存在未通过项 | 用法/配置错误 | - | - | - | - |
| `05-detect-paths.sh` | 关键项已探明 | 有关键项待确认 | 用法错误 | - | - | - | - |
| `10-backup-db.sh` | 成功 | - | 告警/用法错误 | 失败/缺依赖 | 路径不允许 | - | - |
| `20-backup-full.sh` | 成功 | - | 告警/用法错误 | 失败/缺依赖 | 路径不允许 | - | - |
| `30-verify-backup.sh` | 通过 | - | 用法错误 | 缺依赖 | - | 校验未通过 | - |
| `40-restore-drill.sh` | 成功 | - | 用法错误 | 依赖/快照缺失 | 路径不安全 | 校验失败 | - |
| `50-apply-patches.sh` | 成功 | - | 用法错误 | 缺依赖 | 状态不允许 | - | 冲突/应用失败 |
| `60-apply-overlay.sh` | 成功 | - | 用法错误 | 缺依赖/目录不存在 | 有冲突已跳过 | 包校验失败 | 构建失败 |
| `70-check-image.sh` | 全部包含 | - | 用法错误 | 执行错误（docker/镜像/源码目录） | - | 部分或未包含 | - |
| `90-cron-setup.sh` | 成功 | - | 用法错误 | 缺依赖 | 写入失败 | - | - |

脚本透传 `scripts/backup.sh` 的退出码；出现 `!!` 告警行时退出码为 2，上一份可用快照不受影响。

## 八、DSM 注意事项

1. **不要用 `sh` 执行**：DSM 默认 `sh` 是 BusyBox，请显式 `/bin/bash`。
2. **权限**：脚本需要读取数据目录、写入备份目录；建议用 `root` 执行（DSM 任务计划里选 `root` 用户）。
3. **换行与权限**：解压 zip 后如权限丢失，执行一次 `chmod 755 ./*.sh`；如文件被 Windows 编辑器改过，用 `sed -i 's/\r$//' ./*.sh` 去掉 CRLF。
4. **路径**：备份目录必须与数据目录分离，`00` / `20` / `40` 都会做包含关系校验并拒绝危险路径。
5. **恢复**：`40-restore-drill.sh` 只写演练目录，永远不会覆盖生产数据；正式恢复请人工按演练结果操作。
6. **补丁**：`50-apply-patches.sh` 默认从 `HEAD` 导出临时快照做 dry-run，不修改工作区；目标可用普通 `.git` 或 `APP_GIT_DIR` 分离式 git 目录；冲突时返回 6 并列出文件。
7. **定时任务**：DSM 优先用「控制面板 → 任务计划 → 用户定义脚本」；`90-cron-setup.sh --apply` 仅在明确需要系统 crontab 时使用，写入前会备份到 `$HOME/.crontab.bak.<时间戳>`。
8. **覆盖包**：`60` 不使用 git，也不依赖 `APP_GIT_DIR`；它比对的是 `MANIFEST.tsv` 里的基线 sha256。源码打进镜像时，`--apply` 后必须执行 `--build`（或手工 `tag → build → up -d`），只重启容器不生效。

## 九、相关文档

- `overlay/README.md`：覆盖包的构成、基线校验、回滚与生效方式
- `docs/交付/应用与回滚.md`：补丁顺序、基线、冲突处理
- `docs/交付/NAS备份演练清单.md`：恢复演练步骤与成功判定
- `docs/交付/交付索引.md`：补丁校验值、交付物来源说明
- `docs/备份与恢复演练.md`：备份设计与 manifest 结构

文档只做索引和说明，实际操作一律以本目录脚本为准。
