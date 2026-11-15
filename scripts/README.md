# scripts/ —— 运维与发版脚本

> **先看这张表，不要凭名字猜。** 每个脚本都标明「什么时候用」「会不会动数据」。
>
> 装机器本身**不需要**这些脚本——那是 [`README.md`](../README.md) 里的
> 「拉镜像 + `docker compose up -d`」三步。下面这些是给**维护这套系统的人**用的。

---

## 现存脚本一览

| 脚本 | 什么时候用 | 会不会动数据 |
|---|---|---|
| [`pack.sh`](pack.sh) | **开发侧出包**。从仓库打部署包并自动验包（含四道门禁） | 不改数据 |
| [`pack-image.sh`](pack-image.sh) | 把本机已构建好的镜像打成「可直接分发给他人」的离线包（`docker save` + 校验和） | 不改数据 |
| [`gen-update-manifest.py`](gen-update-manifest.py) | 生成 Gitee 发布清单 `update/manifest.json`，决定「点一下能更新」还是「必须重建镜像」 | 不改数据 |
| [`check-version-lock.py`](check-version-lock.py) | 版本锁自检：八处版本载体不许回退。改版本号用它统一改（`--set`） | 不改数据 |
| [`check-version.sh`](check-version.sh) | 运行期版本全链路自检（容器内外版本是否一致） | 只读 |
| [`check-dist.sh`](check-dist.sh) | 前端产物完整性校验（文件数 / chunk / 关键页面） | 不改数据 |
| [`check-myreader-links.sh`](check-myreader-links.sh) | 内嵌阅读器的符号链接体检 | 不改数据 |
| [`verify-pkg-manifest.sh`](verify-pkg-manifest.sh) | 出包终验：包内清单字节必须与仓库清单一致 | 不改数据 |
| [`backup.sh`](backup.sh) / [`backup_run.py`](backup_run.py) | **日常备份唯一入口**：数据库在线备份 + 书/音频硬链接快照，默认每日一次、保留 7 天/4 周/6 个月 | 只读数据，写备份目录 |
| [`upgrade.sh`](upgrade.sh) | **升级 / 重装，唯一入口**。装新出的包走它 | 会。自动备份数据库，数据目录本身不碰 |
| [`deploy.sh`](deploy.sh) | 首次装机，或怀疑包被解压坏了 | 会。构建并启动容器 |
| [`install-from-tar.sh`](install-from-tar.sh) | 解压部署包后的全新安装入口（不需要 git、不需要 clone） | 会 |
| [`install-fresh.sh`](install-fresh.sh) | 全新安装统一入口（上面那个的薄封装，逻辑收口在此） | 会 |
| [`hotfix.sh`](hotfix.sh) | **只改 Python 时用它，省掉十几分钟的镜像重建**。覆盖容器内 `webserver/` 并自动语法预检、可回滚 | 不动数据，只换代码文件 |
| [`hot-update.sh`](hot-update.sh) | 用**仓库当前工作区**热更正在运行的容器（前端 dist + 后端 Python） | 不动数据，只换代码文件 |
| [`sync-hotfix.sh`](sync-hotfix.sh) | 部署前把「在线热更新」固化进宿主机，避免下次部署版本倒退 | 会（写宿主机源码目录） |
| [`deploy-cert.sh`](deploy-cert.sh) | Let's Encrypt 证书签发 + 装进容器（全自动续期） | 会（写证书、reload nginx） |
| [`migrate-audio-dirs.py`](migrate-audio-dirs.py) | 有声书音频从 `audios/<id>/` 搬进书目录 `.audio/`。默认预演，`--apply` 才动 | **会**。搬文件不可逆，先看清单再决定 |
| [`test-audio-dirs.py`](test-audio-dirs.py) | 音频路径逻辑自测（假 cache + 临时目录） | 不改数据，只在 /tmp 里折腾 |
| [`test-integration.sh`](test-integration.sh) | 跑 `tests/test_main.py` 那批真起站点的用例。**它负责搭 calibre 库 + python3.12 环境** | 只在临时夹具目录里折腾 |
| [`search_index.py`](search_index.py) | 中文检索索引的命令行入口（不依赖 Web 服务） | 只读 |
| [`upstream/follow-upstream.py`](upstream/follow-upstream.py) | **跟随上游**。`fetch` 拉上游 → `assess` 评估规模 → `compare` 逐文件三方比对出冲突矩阵 | 只读（报告写到 `--out`） |
| [`upstream/patch_tool.py`](upstream/patch_tool.py) | **把本地改动按主题导出成上游补丁**：`export <主题> --upstream <上游检出> --out <目录>`；`status` 检查上游是否已修 | 只读，写 patch 文件 |

---

## 三个高频命令，照抄即可

```sh
# 出包（开发侧）
bash scripts/pack.sh

# 升级 / 重装（运维侧）
sh scripts/upgrade.sh /volume1/docker/audiobook-deploy-4.6.0-build.28-r42.tar.gz

# 阅读器打不开书，先诊断（只读）
sh scripts/check-reader.sh
```

---

## 脚本之间的关系

```text
pack.sh          【开发侧】从仓库出包 → 自动验包（下文详述）
  └─ pack-image.sh      把已构建好的镜像打成离线包（给别人）

deploy.sh        首次装机走这条（upgrade.sh 不存在时用它引导）
upgrade.sh       升级 / 重装走这条（内部会调 sync-hotfix.sh 固化热更）

check-reader.sh  任何「阅读器不正常」的情况，先跑它再动手
```

---

## 出包：为什么必须用 pack.sh，不能自己 tar 一下

`pack.sh` 里有四道门禁，少一道都可能交付出坏包：

1. **符号链接不被压扁**——`--transform` 会把符号链接改成普通文件，阅读器直接报 500；
   所以只能 `tar -xzf`（不要加 `--transform`）。
2. **产物一个文件都不能少**——链接断一片比整包坏更难查。
3. **包内 `update/manifest.json` 与仓库那份字节一致**——挡住「包名新版、包内清单旧版」
   这类事故（装完 `/admin/version` 永远误报有新版本）。
4. **版本锁自检**——`scripts/check-version-lock.py` 必须在出包前跑过。

### 坑一：`--transform` 会改坏符号链接

`tar --transform` 会在打包时重写路径，**顺带把符号链接变成普通文件**。
内嵌阅读器（MyReader）依赖 `app/node_modules` 下的一批符号链接，压扁后阅读器打不开书。
所以打包时不要加 `--transform`。

### 坑二：产物少一个文件，链接就断一片

前端 `dist` 是多目录结构，缺一个目录里的文件不会报错，只会表现为「某个页面空白」。
`pack.sh` 因此在打包后逐目录核对，而不是只数文件总数。

---

## 为什么用 `upgrade.sh` 而不是 `tar -xzf`

直接在 `audiobook/` 里解压新包会把新文件叠在旧文件上：上游删掉的模块还留在那儿，
旧的数据目录混在源码里，「现在到底跑的哪个版本」说不清。`upgrade.sh` 的做法是
**停容器 → 备份库 → 旧目录改名 → 全新目录解压 → 校验 → 构建 → 启动 → 验证 4 个进程**，
任何一步失败都能退回。历史细节见 [`CHANGELOG.md`](../CHANGELOG.md)。

---

## 只改 Python？用 hotfix.sh，别等镜像

`upgrade.sh` 是「全量重解压 + 重建镜像 + 重启」，NAS 上一次十几分钟。但项目里
**绝大多数修复只动了 `webserver/` 下的 .py**——这部分在 Dockerfile 里就是
`COPY webserver/`，纯 Python，不参与任何编译。

```sh
# 覆盖容器内代码 + 语法预检 + 重启（约 10 秒）
sh audiobook/scripts/hotfix.sh /volume1/docker/audiobook-deploy-4.6.0-build.28-r42.tar.gz --restart

# 只覆盖不重启（想看 diff 或自己挑时间重启时用）
sh audiobook/scripts/hotfix.sh /volume1/docker/audiobook-deploy-4.6.0-build.28-r42.tar.gz
```

---

## 有声书音频迁移

```sh
# 预演，只出清单（不动文件）
python3 scripts/migrate-audio-dirs.py

# 确认清单没问题再执行
python3 scripts/migrate-audio-dirs.py --apply

# 只迁某几本
python3 scripts/migrate-audio-dirs.py --apply --ids 12,34
```

---

## 约定

- 命令**单行**给，编号列表，一条一条来（NAS 终端粘多行会吃掉续行符）。
- 涉及数据的脚本一律**默认预演、显式 `--apply` 才动手**。
- 改版本号只用 `scripts/check-version-lock.py --set <版本>`，不要手工改单个文件。
- 相对上游的全部改动记录在 [`CHANGELOG.md`](../CHANGELOG.md)。
