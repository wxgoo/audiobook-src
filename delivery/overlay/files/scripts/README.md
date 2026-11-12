# scripts/ —— 运维脚本

所有跟 NAS 部署、升级、排障有关的 shell 脚本都收在这里。**先看这张表，不要凭名字猜。**

## 日常用哪几个

| 脚本 | 什么时候用 | 会不会动数据 |
|---|---|---|
| [`pack.sh`](pack.sh) | **开发侧出包**。从仓库打部署包并自动验包 | 不改数据 |
| [`upgrade.sh`](upgrade.sh) | **升级 / 重装，唯一入口**。装新出的包就走它 | 会。自动备份数据库，数据目录本身不碰 |
| [`backup.sh`](backup.sh) | **日常备份唯一入口**。数据库在线备份 + 书/音频硬链接快照，默认每日一次、保留 7 天/4 周/6 个月。详见 [备份与恢复演练](../docs/备份与恢复演练.md) | 只读数据，写备份目录 |
| [`check-reader.sh`](check-reader.sh) | 阅读器出问题（打开书空白 / 502）**先跑这个** | 只读，不改任何东西 |
| [`deploy.sh`](deploy.sh) | 首次装机，或怀疑包被解压坏了 | 会。构建并启动容器 |
| [`protect-custom.sh`](protect-custom.sh) | 跟随上游合并前后，保护 BOOK_NAV 与三语文案 | 不改运行环境，只读写源码文件 |
| [`upgrade-upstream.sh`](upgrade-upstream.sh) | 上游 mybooks 发了新版，要跟 | 会。全链路，最后调 `upgrade.sh` 上线 |
| [`watch-upstream.py`](watch-upstream.py) | 日常盯上游改动，**不等发版**。`--tags` 看有没有新版，`--between` 看两版之间改了什么 | 只读，只拉取上游仓库 |
| [`upstream/patch_tool.py`](upstream/patch_tool.py) | **把本地改动按 A/B/C/D 主题导出成上游补丁**：`export A --upstream <上游检出> --out <目录>`；`status` 检查上游是否已修。用法与主题说明见 [docs/上游比对与跟进-4.6.1](../docs/上游比对与跟进-4.6.1.md) 第 8 节 | 只读，写 patch 文件 |
| [`hotfix.sh`](hotfix.sh) | **只改 Python 时用它，省掉十几分钟的镜像重建**。覆盖容器内 `webserver/` 并自动语法预检、可回滚。文件来源是**部署包**，不是源码目录（见下表） | 不动数据，只换代码文件 |
| [`migrate-audio-dirs.py`](migrate-audio-dirs.py) | 有声书音频从 `audios/<id>/` 搬进书目录 `.audio/`。默认预演，`--apply` 才动 | **会**。搬文件不可逆，先看清单再决定 |
| [`test-audio-dirs.py`](test-audio-dirs.py) | 音频路径逻辑自测（假 cache + 临时目录，47 项） | 不改数据，只在 /tmp 里折腾 |
| [`test-integration.sh`](test-integration.sh) | 跑 `tests/test_main.py` 那 63 个真起站点的用例。**它负责搭 calibre 库 + python3.12 环境**，没有它这些用例在任何新机器上都是红的。⚠️ 要完整源码仓库——部署包已把根 `tests/` 裁掉 | 只在临时夹具目录里折腾 |

三个高频命令，照抄即可：

```sh
# 升级到新包
sh scripts/upgrade.sh /volume1/docker/audiobook-deploy-4.6.0-14.tar.gz

# 阅读器打不开书，先诊断（只读）
sh scripts/check-reader.sh

# 上游发新版了，一条龙跟随
sh scripts/upgrade-upstream.sh 4.6.0
```

## 脚本之间的关系

```text
pack.sh               【开发侧】从仓库出包 → 自动验包（下文详述）

upgrade-upstream.sh ──┬─> protect-custom.sh save   合并前存快照
                      ├─> git merge 上游 tag       （冲突时暂停等你）
                      ├─> protect-custom.sh check  打包前校验自定义内容没丢
                      ├─> pack.sh                  出成品包
                      └─> upgrade.sh               上线

deploy.sh            首次装机走这条（upgrade.sh 不存在时用它引导）
check-reader.sh      任何"阅读器不正常"的情况，先跑它再动手
```

`upgrade-upstream.sh` 会在同目录、上一层 `scripts/`、以及 `/volume1/docker` 三处
找 `protect-custom.sh`，所以两个必须一起拷贝，别只拿一个。

## `tools/` 下有两个名字相近的脚本，别拿错

历史上 `tools/` 和 `scripts/` 里存在同名但**用途完全不同**的脚本，容易搞混。
4.6.0-16 起把 `tools/` 侧的两个都改了名，名字自身就说明了适用范围：

| 你手里有什么 | 用哪个 | 它从哪取文件 | 用法 |
|---|---|---|---|
| 部署包 `.tar.gz`，没有源码 | `scripts/hotfix.sh` | 指定的**部署包**里解出来的 `.py` | `sh audiobook/scripts/hotfix.sh <包> [--restart]` |
| 源码仓库（在改代码） | `tools/hotfix-from-src.sh` | **当前源码目录**里 mtime 变过的 `.py` | `sh tools/hotfix-from-src.sh [--frontend] [--dry-run]` |
| 想全自动跟上游最新版 | `scripts/upgrade-upstream.sh` | 上游 GitHub release，全链路自动跑完 | `sh scripts/upgrade-upstream.sh <版本>` |
| 想手工跟上游、逐文件看冲突 | `tools/upgrade-from-upstream-manual.sh` | 上游指定 ref，拉进独立 git 目录由你合并 | `sh tools/upgrade-from-upstream-manual.sh [ref]` |

一句话记：**`scripts/` 面向拿到部署包的运维，`tools/` 面向改源码的开发者。**

## 出包：为什么必须用 pack.sh，不能自己 tar 一下

```sh
sh scripts/pack.sh                 # 版本号自动取 CHANGELOG 顶部
sh scripts/pack.sh 4.6.0-11        # 或手动指定
sh scripts/pack.sh --check 某包.tar.gz   # 只验一个已有包
```

它会做四件事：源码污染自检 → 产物自检 → 打包 → **解压实数链接**再验一遍。

### 坑一：`--transform` 会改坏符号链接

`myreader-dist` 里有 127 个符号链接，内容是**相对路径**：

```
../../../../node_modules/.pnpm/@mozilla+readability@0.6.0/node_modules/@mozilla/readability
```

如果用 `tar --transform 's,^\.,audiobook,'` 来加顶层目录，这个规则会连带作用于
**链接的目标内容**，把它改写成：

```
audiobook./../../../node_modules/.pnpm/...     ← 全废，127 个链接全断
```

表现是：包能解开、文件数也对（2732 条），但 `deploy.sh` 报
「有效链接 0 个」→ 部署后 `/readerx` 全 502。

`pack.sh` 的做法是 `cp -al` 硬链接镜像出一份叫 `audiobook/` 的树，
再 `cd` 到父目录 `tar -czf ... audiobook`，**完全不用 `--transform`**。

### 坑二：产物少一个文件，链接就断一片

`myreader-dist/node_modules/.pnpm/` 是那 68 个包的实际内容（28M），
所有链接都指向它。`.gitignore` 里 `node_modules/`、`media/`、`*.mp3` 这些
通配规则会把产物里的必需内容一起挡掉 —— 文件末尾有专门的例外区解决这个，
改 `.gitignore` 时**不要动那段**，改了 `pack.sh` 第 2 步会立刻报错。

## 为什么用 `upgrade.sh` 而不是 `tar -xzf`

直接在 `audiobook/` 里解压新包会把新文件叠在旧文件上：上游删掉的模块还留在那儿，
旧的数据目录混在源码里，"现在到底跑的哪个版本"说不清。`upgrade.sh` 的做法是
**停容器 → 备份库 → 旧目录改名 → 全新目录解压 → 校验 → 构建 → 启动 → 验证 4 个进程**，
任何一步失败都能退回。详见 [`docs/部署包说明.md`](../docs/部署包说明.md)。

# 只改 Python？用 hotfix.sh，别等镜像

`upgrade.sh` 是「全量重解压 + 重建镜像 + 重启」，NAS 上一次十几分钟。但项目里
**绝大多数修复只动了 `webserver/` 下的 .py**——这部分在 Dockerfile 里就是
`COPY webserver/`，纯 Python，不参与任何编译。

```sh
# 覆盖容器内代码 + 语法预检 + 重启（约 10 秒）
sh audiobook/scripts/hotfix.sh /volume1/docker/audiobook-deploy-4.6.0-14.tar.gz --restart

# 只覆盖不重启（想看 diff 或自己挑时间重启时用）
sh audiobook/scripts/hotfix.sh /volume1/docker/audiobook-deploy-4.6.0-14.tar.gz
```

它做的事：从包里**只解出 `webserver/` + `tools/` + `server.py`**（不解 197M 全包）
→ 备份容器内旧代码 → 覆盖 → 容器内 `python3 -m compileall` 预检 →
编译不过自动回滚并退出 → 通过则按需重启并检查 4 个进程和 HTTP 200。

**什么时候不能用它**（老实跑 `upgrade.sh`）：

| 改了什么 | 需要重建镜像 |
|---|---|
| `webserver/` 下任意 .py | 不需要，用 hotfix.sh |
| `app/` 前端源码 | 需要（要重新 build-spa） |
| `myreader-dist/` | 需要（要重新导出 Next 产物） |
| `Dockerfile` / `requirements` / 系统包 | 需要 |
| `conf/nginx/` `conf/supervisor/` | 不需要镜像，但要 restart 容器或 reload |

## 有声书音频迁移（4.6.0-13 起）

4.6.0-13 把音频从 `audios/<id>/` 改成放在书自己的目录里
（`library/<作者>/<书名> (id)/.audio/`），这样一本书的电子书和音频就在一处。
**新代码两种位置都能读，不迁移也能正常播放**，迁移只是为了目录干净。

`upgrade.sh` 已经接进去了：容器起来、四个进程全绿之后会自动跑一次预演，
把清单打出来问你一句要不要搬。也可以单独跑：

```sh
# 预演，只出清单（不动文件）
docker exec -it audiobook-mybooks-1 python3 /var/www/mybooks/scripts/migrate-audio-dirs.py

# 确认清单没问题再执行
docker exec -it audiobook-mybooks-1 python3 /var/www/mybooks/scripts/migrate-audio-dirs.py --apply

# 只迁某几本
docker exec -it audiobook-mybooks-1 python3 /var/www/mybooks/scripts/migrate-audio-dirs.py --book-id 12 --book-id 34 --apply
```

几条安全设计：

- **默认 dry-run**，必须显式 `--apply`
- 目标已有同名文件时**跳过，不覆盖**，会在日志里列出来
- 字幕 `.srt/.vtt` 和封面图跟着音频一起搬，否则播放器找不到
- 搬空才删源目录；源目录里还有别的东西就留着
- 库里找不到对应书的 `audios/<id>/`（孤儿）**只报告不删**，等你人工确认
- 必须用 **`docker exec` 在容器里跑**：书目录名要靠容器里的 calibre 算
  （`field_for("path")`），宿主机上的 calibre 版本不一定对得上

## 约定

- 所有脚本 POSIX `sh` 可跑（不依赖 bash 特有语法），NAS 上直接 `sh xxx.sh`。
- 路径默认 `BASE=/volume1/docker`，可用环境变量覆盖。
- 破坏性操作前必须打印"将要做什么"并等确认，或提供 `--dry-run`。
- 改脚本时同步更新本文件的表格。
