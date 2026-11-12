# NAS Docker 缓存池重置与镜像备份恢复手册

> 机型：群晖 RS2416P / DSM 7.2 / ContainerManager 24.0.2（dockerd 24.0.2，storage-driver=btrfs）
> 场景：Docker 构建反复失败（`layer does not exist`）、dockerd 启动极慢、BuildKit 卡死。
> 根因（历史事故）：旧版 builder 每构建一次产生 60~70 个缓存子卷，btrfs 上累积到 1000+ 后层索引失手。
> 当前状态：**部署脚本已统一为 BuildKit**，不再产生这种碎渣；本手册用于复现事故时的恢复，以及日常体检。
> 事件记录：2026-11-08~09 实战验证，改符号链接方案约 1 分钟完成重置，空池 BuildKit 构建全程 12.6 分钟出图（旧池状态时卡死 17 分钟+）。
> 修订历史：
> - 2026-11-09 首次修订：按实战反馈修正 6 处（版本验证命令、base 镜像未落盘、构建耗时、prune 时机、podcast 恢复路径、旧池清理步骤）。
> - **2026-11-09 r7 修订**：构建口径改为脚本化 BuildKit + `buildx` 探测回退；内存已升级到 6G；
>   新增「版本检测与在线更新」「文档索引」两节；清理与预防补上热更新固化区的注意事项。
> 权威副本在 Gitee 仓库 `docs/` 下，随部署包一起分发；交付目录里的同名文件是同步副本。

---

## 0. 什么时候用这本手册（症状确认）

出现以下任一情况，先做本节的根因确认，再决定走手册：

- `docker compose build` 报 `failed to get layer sha256:xxx: layer does not exist`
- dockerd 启动要 4 分钟以上（`synopkg start` 后长时间 `docker info` 不通）
- BuildKit 卡在 `load build definition` 十几分钟不动
- `docker system df` 里 `Build Cache` 超过 300 条 / 超过 5GB
- `docker images -a` 出现大量 `<none>` 中间层

### 根因确认（两条命令，10 秒）

```bash
sudo -i
btrfs device stats /volume1     # 必须全 0；有非 0 值是硬盘/文件系统问题，不是本手册范围
df -h /volume1                  # Avail 应远大于 5GB；不足先清空间
docker system df                # 看 Build Cache 的 TOTAL 和 SIZE
```

**判断表：**

| btrfs device stats | Build Cache | 结论 |
|---|---|---|
| 全 0 | 几百条以上 | 缓存池碎渣 → 本手册 |
| 有非 0 值 | 任意 | 硬盘/文件系统故障 → 先修存储，勿动 Docker |
| 全 0 | 很少 | 其他原因（缺网、缺镜像），不走本手册 |

---

## 1. 备份镜像（动手前必做，跳过会丢东西）

三个必须备份的镜像及原因：

| 镜像 | 大小 | 为什么必须备份 |
|---|---|---|
| `codeberg.org/janw/podcast-archiver:latest` | 150M | 源站 codeberg.org 国内拉取极不稳定，丢了找不回 |
| `docker.1ms.run/library/node:20-alpine` | 136M | audiobook 构建的地基，备份省得重新拉 |
| `docker.1ms.run/poxenstudio/mybooks_base` | 1.72G | audiobook 生产阶段 base，备份省得重新下载 |

可选备份（视使用情况）：
- `mybooks-local:latest`：会被新版本替代，可不备份；要回滚旧版时从 `audiobook.old` 源码重建
- `synology/docviewer:latest`：群晖 Document Viewer 用的才备份，不用就让它消失

> **为什么 base 只有 1.6G，容器里加载出来却 2G+？**
> `docker images` 显示的是**各层去重后的逻辑大小**，而容器/镜像详情里看到的是这些层
> 逐层解压后的总和，加上可写层、元数据与上层 `COPY` 进来的前端产物。层是共享的、
> 不能「合并成一个文件」而不重新构建镜像；想真正变小只能改 `Dockerfile` 减少层数或
> 精简基础镜像。这不是缓存池故障，不用为它清池子。

### 操作

```bash
sudo -i
mkdir -p /volume1/docker/image-backup
cd /volume1/docker/image-backup

docker save codeberg.org/janw/podcast-archiver:latest | gzip -1 > podcast-archiver.tar.gz
docker save docker.1ms.run/library/node:20-alpine | gzip -1 > node20-alpine.tar.gz
docker save docker.1ms.run/poxenstudio/mybooks_base:latest | gzip -1 > mybooks-base.tar.gz

ls -lh    # 确认三个文件都在、大小不为 0
```

**预期大小：** podcast-archiver ≈ 57M、node ≈ 51M、mybooks-base ≈ 700~900M。

### 数据安全检查（唯一可能丢数据的关卡）

```bash
docker inspect podcast-archiver-podcast-archiver-1 --format '{{range .Mounts}}{{.Type}} {{.Name}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
```

- 输出全是 `bind /volume1/xxx -> /xxx` → 数据在宿主机，安全，继续
- 出现 `volume 某名字 -> /xxx` → 该卷数据在 `/volume1/@docker/volumes/`，先拷出来：

```bash
cp -a /volume1/@docker/volumes/<卷名> /volume1/docker/image-backup/vol-<卷名>
```

> `/volume1/docker/`（无 @ 前缀）是你自己的数据目录（书、音频、备份、源码），和 `/volume1/@docker`（Docker 内部存储）完全无关，重置碰不到它。

---

## 2. 重置缓存池

两条路线，选一条。**路线 A 首选**（1 分钟，不删任何文件，不需要重启）；路线 B 在路线 A 失败时用。

### 路线 A：改符号链接（推荐）

原理：`/var/packages/ContainerManager/var/docker` 是一个符号链接，指向真正的数据目录。把链接改向新空目录，daemon 就在空池子上运行；旧池子原地不动，以后再清理。

```bash
sudo -i

# 1. 停 Docker（容器全部会停，等下恢复）
synopkg stop ContainerManager

# 2. 建新目录
mkdir -p /volume1/@docker-new

# 3. 改链接（rm 只删链接本身，不删任何文件夹）
rm /var/packages/ContainerManager/var/docker
ln -s /volume1/@docker-new /var/packages/ContainerManager/var/docker

# 4. 确认链接指向
ls -ld /var/packages/ContainerManager/var/docker
# 预期：lrwxrwxrwx ... /var/packages/ContainerManager/var/docker -> /volume1/@docker-new

# 5. 启动（空池子，十几秒就绪）
synopkg start ContainerManager
for i in $(seq 1 60); do docker info >/dev/null 2>&1 && { echo ready; break; }; sleep 3; done

# 6. 验证归零（达标线）
docker system df
docker images
```

**第 6 步的达标线：Images 0 / Containers 0 / Local Volumes 0 / Build Cache 0。**
看到全 0，重置完成，跳到第 3 节。

### 路线 B：重启 NAS 后 mv（A 失败时用）

```bash
# 重启 NAS，等系统起来
sudo -i

# 等 daemon 就绪（重启后它会扫旧池子，可能要几分钟；扫不完也没关系）
for i in $(seq 1 120); do docker info >/dev/null 2>&1 && { echo ready; break; }; sleep 3; done

synopkg stop ContainerManager

# 重启后挂载已释放，mv 应该能成功（同分区 rename，几秒）
mv /volume1/@docker /volume1/@docker-bad
mkdir -p /volume1/@docker

synopkg start ContainerManager
for i in $(seq 1 60); do docker info >/dev/null 2>&1 && { echo ready; break; }; sleep 3; done

docker system df    # 验证归零
```

> 若 `mv` 仍报 `Device or resource busy`，说明还有子卷被挂载 —— 退回路线 A。

### 常见错误与规避

| 错误 | 原因 | 处理 |
|---|---|---|
| `mv: Device or resource busy` | 子卷还挂着 | 改用路线 A |
| 改完链接 DSM 里存储位置显示异常 | 正常，界面读的是旧配置 | 不用管，别在界面里改存储位置 |
| `rm /var/packages/.../docker` 报错 | 用了 `rm -r` 或路径不对 | 只用 `rm`（不带 -r），确认路径 `/var/packages/ContainerManager/var/docker` |
| 重置后 docker pull 慢 | registry 镜像源在 `dockerd.json` 里，重置不影响它 | 不用动 |

### 以后不要做的事

- **不要在 DSM 套件界面的「存储位置」里改设置** —— 那会把符号链接重置回旧路径，daemon 又跑回旧池子
- **不要直接 `rm -rf /volume1/@docker`** —— 子卷挂着删不掉，硬删会制造坏状态
- **不要卸载重装 Container Manager** —— 一样是逐个删子卷（数小时），且 registry 配置全丢

---

## 3. 恢复镜像

```bash
cd /volume1/docker/image-backup
for f in *.tar.gz; do echo "==> $f"; gunzip -c "$f" | docker load; done
docker images
```

**预期：** 看到 podcast-archiver、node:20-alpine、mybooks_base 三个镜像。

> `mybooks-local` 不在备份清单里 —— 它由第 4 节构建产生，load 不了。构建完成后想留底的话：
> ```bash
> docker save mybooks-local:latest | gzip -1 > /volume1/docker/image-backup/mybooks-build27.tar.gz
> ```

---

## 4. 重建 audiobook（r7 口径）

**不要手工敲 `docker build`。** `deploy.sh` / `upgrade.sh` 在构建前还有三个必做动作，漏了会出难查的现场：

1. 逐根校验 / 重建 MyReader 的 **119 根相对符号链接**（被 Windows 或图形界面解压压扁会导致阅读器 500）；
2. 调用 `scripts/sync-hotfix.sh`，把数据卷里尚未固化的在线热更新合并进源码目录（防止版本倒退）；
3. 校验 `update/manifest.json` 存在，并确认包内 `app/dist` 指纹。

```bash
cd /volume1/docker/audiobook
sh scripts/deploy.sh          # 全新部署
# 或：sh scripts/upgrade.sh   # 在已有站点上升级 / 重装
```

### 构建口径（2026-11-09 r7 已统一）

| 情况 | 脚本实际执行 |
|---|---|
| 有独立 `docker buildx` 组件 | `DOCKER_BUILDKIT=1 docker build --no-cache ...` |
| DSM / Container Manager 没装 buildx 插件 | 自动回退 `docker compose build`（compose 内嵌 BuildKit） |
| 起容器 | `docker compose up -d --force-recreate --no-build`，`--no-build` 不能省 |

- **不要再手工切回旧版 builder**，也不要靠 `export` 临时覆盖环境变量 —— 脚本里的探测与回退已经处理了这台机缺 buildx 组件的情况。
- 第一步若出现 `ERROR importing cache manifest from mybooks-local:latest` —— **无害**，本地还没有这个镜像，BuildKit 自动跳过。
- base 镜像已在本地（第 3 节 load 回来的），不会重新下载。
- 全程预期 **10~15 分钟**（实测 RS2416P 空池构建 43 步用了 12.6 分钟）。
- 解压新部署包一律用命令行 `tar -xzf`；File Station / GUI 解压会把符号链接压扁。

### 验收

```bash
# 注意：python -c 的方式会报 ModuleNotFoundError（容器工作目录不对），用 cat 直接看文件
docker exec audiobook-mybooks-1 cat /var/www/mybooks/webserver/version.py
sha256sum app/dist/index.html
```

- 运行期版本应为 `VERSION = "4.6.0-build.27"`。
- r7 包内 `app/dist/index.html` 的 sha256 应为
  `57185748414300406439733f44a072a7fccdeb14783a0845ff79549c80163270`（755 个文件 / 74 个页面）。
- 浏览器登录后，左侧管理树应出现「版本与更新」，页面 `/admin/version` 能打开。

> **实战坑：构建后 base 镜像不会以独立标签落盘。** BuildKit 拉取的 `mybooks_base` 只进构建缓存，
> `docker images` 里看不到它，之后 `docker save` 会报 `reference does not exist`。构建完成后补一条即可
> （层都在缓存里，秒级完成）：
> ```bash
> docker pull docker.1ms.run/poxenstudio/mybooks_base:latest
> ```
> 然后再做第 1 节的 base 备份。

**若构建又卡住：** 看卡住的 step 编号和 `top` 里的 `wa` 值。`wa` 超过 40% 说明有别的进程抢 IO（备份、prune、索引服务），等它结束再试。

---

## 5. 恢复 podcast-archiver

**首选：Container Manager 项目界面（实战验证有效）。** 重置只清了 `@docker` 里的容器元数据，**项目配置本身存在系统分区，会保留下来**。打开 DSM → Container Manager → 项目标签：

- 列表里有 podcast-archiver → 选中 → 操作 →「构建并启动」，UI 会按原配置重建容器，挂载/端口/环境变量全部照旧
- 实测：本项目就是走这条路恢复成功的，无需手工命令

**备选：命令行重建**（仅当项目列表里也没有）：

```bash
docker run -d \
  --name podcast-archiver \
  --restart unless-stopped \
  -p <原端口>:80 \
  -v /volume1/docker/Podcast/data:/data \
  -v /volume1/docker/Podcast/output:/output \
  codeberg.org/janw/podcast-archiver:latest
```

> 端口填你原来访问用的端口（如 8085）。镜像已在第 3 节 load 回来，不需要联网。数据在 `/volume1/docker/Podcast`，容器重建后订阅和历史原样恢复。

---

## 6. 旧池子善后（可推迟数天，不急）

旧数据目录（`/volume1/@docker-bad` 或重置前的 `/volume1/@docker`）约 23GB、1000+ 子卷。它不影响运行，占的 23G 在 14T 盘上也不痛不痒，**可以放着不管**。

有空想清掉时（实战验证的最简流程）：

```bash
# 0. 先重启一次 NAS —— 重启后子卷挂载全部释放，删除不会报 busy（实战验证的关键一步）
sudo -i

# 1. 停 Docker
synopkg stop ContainerManager

# 2. 确认旧目录上没有挂载（输出里不应出现 /volume1/@docker（不带 -new）的行）
mount | grep '@docker'

# 3. 逐个删子卷。注意：btrfs 子卷不能 rm -rf，必须用 btrfs subvolume delete
for sv in $(btrfs subvolume list /volume1 2>/dev/null | awk '$NF ~ /^@docker\// {print $NF}'); do
  btrfs subvolume delete "/volume1/$sv"
done

# 4. 子卷删完后，残壳秒删
rm -rf /volume1/@docker

# 5. 恢复 Docker
synopkg start ContainerManager
```

> 实测（RS2416P + 重启后）：数百个子卷删除比预想快得多，几分钟完成，未再遇到 busy。不需要 `sort -r`，删除顺序无关紧要。

---

## 7. 预防（防止再次发生）

1. **构建缓存的正确清理时机**：
   - 不是每次构建后都清 —— 空池刚构建完的缓存是下次秒级构建的本钱，别急着删；
   - **Build Cache 积到 300 条以上再清**：`docker builder prune -af`；
   - 清完不影响运行，只影响下次构建速度（回到约 12 分钟的空池构建）。
2. **`docker image prune` 只用不带 `-a` 的版本**：
   ```bash
   docker image prune -f    # 只删悬空层，安全
   ```
   **永远不要跑 `docker image prune -a` / `docker system prune -a`** —— `mybooks_base` 和
   `node:20-alpine` 没被容器直接使用，会被标成 Reclaimable（约 68%）然后被它删掉，下次构建就要重新拉 1.7G。
3. **定期体检**（建议每周）：
   ```bash
   docker system df        # Build Cache TOTAL > 300 条就该清
   btrfs device stats /volume1   # 确认仍全 0
   ```
4. **避免在 IO 繁忙时构建**：先看 `top` 的 `wa`，超过 30% 等一等。这台机 RAID5 写放大 4 倍，繁忙期写大层就是坏层来源。
5. **升级站点前先跑 `backup.sh`**，数据备份在 `/volume1/docker/audiobook-backup`。
6. **升级后保留 `audiobook.old`**，确认新版跑通、功能验证过（页脚版本号 + 自动续播 + 迷你条切歌）再删。
7. **内存已升级到 6G**（事故当时是 1.9~2G）。btrfs 子卷多时元数据缓存才装得下，查找不会全部落到磁盘；
   这是本次恢复后构建能稳定在 12.6 分钟的重要条件，不要再按旧机器的 2G 口径估算耗时。
8. **不要删数据卷里的 `update-sync/` 与 `update-backup/`**（r7 新增）：
   - `/volume1/docker/audiobook-data/update-sync/current/` 存着尚未固化到镜像的在线热更新；
   - `/volume1/docker/audiobook-data/update-backup/` 是每次在线更新的回滚备份；
   - `deploy.sh` / `upgrade.sh` 构建前会读前者，删了会让已在线生效的修订被旧包覆盖回去。
9. **不要手工往容器里拷文件改代码**。纯后端修订请在页面 `/admin/version` 点「立即更新」，
   含前端产物的修订按第 8 节重新部署，两者都会留备份、可回滚。

---

## 8. r7 版本检测与在线更新（新增）

### 入口与提示

- 左侧管理树 → **版本与更新**（`/admin/version`），仅管理员可见；右上角与「外观设置」「退出」
  平行处还有「新版本」角标，后台检测到新修订时才会出现。
- 首页登录后自动弹出的「版本变更」对话框、页脚版本号弹窗、消息弹窗里的旧升级文案，
  r7 起统一按本项目 **Gitee 发布清单** 生成，不再沿用上游 mybooks 的 release 提示。

### 检测源

唯一发布源是 Gitee 公开仓库 `wxgoo/audiobook-src` 的 `update/manifest.json`（raw 直链，
不需要 token、不需要容器内装 git）。比对的是修订号 `-rN`，不是固定的 `VERSION`。
包内同一份清单是本地基线；`pack.sh` 出包时强制检查它存在。

### 三种情况

| 清单判定 | 页面给的动作 | 要动 NAS 吗 |
|---|---|---|
| `requires_dist=false`、`hotfixable=true`（只改 `server.py` / `webserver/**/*.py`） | **「立即更新」**：下载 → sha256 + 字节数 + 语法校验 → 备份 → 原子替换 → 自动重启 | 不用，页面点一下即可 |
| `requires_dist=true`（含 `app/dist`、`app/src`、locale、镜像配置等） | 给出可复制的重新部署命令 | 要，按下面的流程 |
| 仅文档 | 提示「无需执行更新操作」 | 不用 |

任一下载项校验不符会直接中止，**线上文件一个字节都不会动**。

### 含前端产物的重新部署（本次 r27 上线用的就是这条）

```bash
cd /volume1/docker
sha256sum -c audiobook-deploy-4.6.0-build.27-r27.tar.gz.sha256
docker compose -f audiobook/docker-compose.yml down 2>/dev/null
mv audiobook audiobook.old-$(date +%m%d-%H%M)
tar -xzf audiobook-deploy-4.6.0-build.27-r27.tar.gz
cd /volume1/docker/audiobook && sh scripts/deploy.sh
```

> 用命令行 `tar -xzf`，别用 File Station / GUI 解压 —— 会把 MyReader 的 119 根符号链接压扁。
> 全新部署用 `deploy.sh`；保留现有目录做升级 / 重装用 `upgrade.sh`。

### 回滚与防倒退

- 页面「备份与回滚」可一键回滚最近 8 次在线更新；Web 进不去时在 NAS 上：
  ```bash
  ls /volume1/docker/audiobook-data/update-backup/
  docker cp /volume1/docker/audiobook-data/update-backup/<备份目录>/webserver/. \
    audiobook-mybooks-1:/var/www/mybooks/webserver/
  docker restart audiobook-mybooks-1
  ```
- 在线热更新改的是容器可写层，重新部署前由 `scripts/sync-hotfix.sh` 把
  `/data/update-sync/current/` 里比包内更新的修订固化进源码目录再构建镜像。
- 页面提示「在线更新尚未固化」时，按本节跑一次 `deploy.sh` / `upgrade.sh` 即可；不跑也不影响当前运行。

完整机制见 `docs/在线更新说明.md`。

---

## 9. 文档索引（r7，别拿错文档）

### 当前有效，均在 r7 部署包 / Gitee 仓库内

| 文档 | 看什么 |
|---|---|
| `docs/README.md` | 全部文档的分类索引（先从这里找） |
| `docs/部署包说明.md` | 完整部署、验收、dist 指纹表（逐版记录见 `docs/archive/部署包版本记录-2026-11.md`） |
| `docs/在线更新说明.md` | 版本检测、分级更新、回滚、防倒退、发布新修订 |
| `docs/NAS-Docker缓存池重置与镜像备份恢复手册.md` | 本手册（缓存池事故、镜像备份、文档索引） |
| `CHANGELOG.md` | 全部修订的变更明细 |
| `README.md` | 快速开始与构建口径（已改为 BuildKit + 脚本部署） |
| `update/README.md` | 发布清单字段、生成命令 |
| `docs/备份与恢复演练.md` | 备份范围、恢复演练、RPO/RTO、NAS 演练清单（原 `交付/NAS备份演练清单.md` 已并入） |
| `交付说明-4.6.0-build.27-r27.md` | 本次交付摘要、sha256、重新部署命令（交付目录） |

### 历史 / 归档，命令不要照抄

| 文档 | 状态 |
|---|---|
| `docs/操作总纲.md` | 早期操作环境说明（4.6.0-15），顶部已加 r7 指向；部分路径与出包流程已被取代 |
| `docs/archive/交付索引.md`、`docs/archive/应用与回滚.md` | build.20 时代的 14 个补丁序列，与 r7 整包部署无关 |
| `docs/archive/*` | 历史变更报告与旧号段资料，**不进部署包**，仅回溯用 |
| `交付说明-4.6.0-build.27-r4/r5/r6.md` | 各版交付快照，仅用于回溯 sha256 与当时的变更 |
| `docs/上游跟进*`、`docs/目录功能说明.md`、`docs/字幕生成与播放.md` | 功能与上游资料，与部署 / 缓存池无关 |

### 源码与包

- Gitee 仓库 `wxgoo/audiobook-src` 是**源码与发布清单的权威来源**，不再单独出 `audiobook-src-*.tar.gz` 源码包。
- 部署包 `audiobook-deploy-4.6.0-build.27-r27.tar.gz` 仍必须完整分发：Gitee 不跟踪
  `app/dist`、`app/node_modules`，且 Windows / GUI 解压会压扁 MyReader 的符号链接。
- 三者口径冲突时，以「当前有效」表里前三份为准。

---

## 附：本次事件时间线（2026-11-08 ~ 11-09）

| 时间 | 事件 |
|---|---|
| 18:46 | build.27 升级开始，backup.sh 完成（5.9G） |
| 18:47 | 构建 Step 11 `COPY app/ /build/` 报 `layer does not exist`（缓存池 1037 条） |
| 19:50 | 重启 ContainerManager，daemon 因扫千级子卷耗时 4 分钟 |
| 20:38 | dockerd 启动时跳过 6 个坏镜像链（not restoring image） |
| 20:57 | 误判需要 builder prune，实际 2.7 子卷/分钟，需 6 小时，中断 |
| 21:36 | BuildKit 构建，与 prune 抢 IO 卡死 17 分钟 |
| 次日 05:50 | 改符号链接 → `docker system df` 全 0，1 分钟完成重置 |
| 05:55 | load 镜像（podcast-archiver / node:20-alpine）后 BuildKit 构建正常推进 |
| 06:10 | 空池构建成功：43 步 12.6 分钟 FINISHED，此前三连败的 `COPY app/` 层 11.7s 通过 |
| 06:15 | 站点上线验证 `VERSION = "4.6.0-build.27"`；podcast-archiver 从 Container Manager 项目界面重建成功 |
| 06:27 | 发现 base 未以标签落盘，`docker pull` 补回（层全命中缓存，秒级）；base 备份落袋 |
| 06:42 | 重启 NAS → 逐个删旧池子卷 → `rm -rf /volume1/@docker`，23G 回收；`builder prune` 又回收 1.159GB，Build Cache 归零 |
| 07~09 时 | 手册首次修订（6 处实战反馈）；NAS 内存升级到 6G |
| 10~13 时 | r4 修 MyReader 119 根符号链接、r5 合并工具箱入口、r6 统一读者组统计口径 |
| 13 时 | r7：版本检测独立成页 + Gitee 清单分级在线更新；全部升级提示改 Gitee 口径；本手册与仓库文档同步到 r7 |

**核心教训：缓存池碎渣是慢性病，清它要用「改指向」而不是「逐个删」；构建口径统一交给脚本，别手工敲 docker build。**
