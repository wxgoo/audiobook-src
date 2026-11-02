# scripts/ —— 运维脚本

所有跟 NAS 部署、升级、排障有关的 shell 脚本都收在这里。**先看这张表，不要凭名字猜。**

## 日常用哪几个

| 脚本 | 什么时候用 | 会不会动数据 |
|---|---|---|
| [`pack.sh`](pack.sh) | **开发侧出包**。从仓库打部署包并自动验包 | 不改数据 |
| [`upgrade.sh`](upgrade.sh) | **升级 / 重装，唯一入口**。装新出的包就走它 | 会。自动备份数据库，数据目录本身不碰 |
| [`check-reader.sh`](check-reader.sh) | 阅读器出问题（打开书空白 / 502）**先跑这个** | 只读，不改任何东西 |
| [`deploy.sh`](deploy.sh) | 首次装机，或怀疑包被解压坏了 | 会。构建并启动容器 |
| [`protect-custom.sh`](protect-custom.sh) | 跟随上游合并前后，保护 BOOK_NAV 与三语文案 | 不改运行环境，只读写源码文件 |
| [`upgrade-upstream.sh`](upgrade-upstream.sh) | 上游 mybooks 发了新版，要跟 | 会。全链路，最后调 `upgrade.sh` 上线 |
| [`watch-upstream.py`](watch-upstream.py) | 日常盯上游改动，**不等发版**。`--tags` 看有没有新版，`--between` 看两版之间改了什么 | 只读，只拉取上游仓库 |

三个高频命令，照抄即可：

```sh
# 升级到新包
sh scripts/upgrade.sh /volume1/docker/audiobook-deploy-4.6.0-10.tar.gz

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

## archive/ —— 已归档，别再新建同类

> **这一节只对源码仓库有效。`scripts/archive/` 不随部署包下发**，
> NAS 上的 `audiobook/scripts/` 里只有上面那 6 个脚本。
> 打包时由 `pack.sh` 排除，`--check` 也会验这一条。

这九个都是**一次性脚本**：使命已完成，不修、不跟版本更新。留着的价值是"当时是怎么解决的"。

| 脚本 | 干什么的 | 为什么归档 |
|---|---|---|
| [`archive/merge-4.6.0-9.sh`](archive/merge-4.6.0-9.sh) | v9 那趟合并（23 个文件） | 依赖的补丁包与 v8 基准包都已不在，跑不起来 |
| [`archive/build-v3.sh`](archive/build-v3.sh) | 组装 4.6.0-9 v3 成品包 | v9 最终就是它出的，v10 起改出完整包 |
| [`archive/build-v2.sh`](archive/build-v2.sh) | 组装 4.6.0-9 v2 包 | 已被 build-v3 取代（当时产物残缺需拼凑） |
| [`archive/make-base-4.6.0-8.sh`](archive/make-base-4.6.0-8.sh) | 从 -9 包反推 -8 基准包 | 只为喂给 merge-4.6.0-9.sh，同批归档 |
| [`archive/rescue-from-248.sh`](archive/rescue-from-248.sh) | 从 248M 的 v8 包里挖完整产物 | 一次性救火，产物早已进仓库 |
| [`archive/export-myreader.sh`](archive/export-myreader.sh) | 从容器里导出 `myreader-dist` | 产物重建过一次之后没再用过 |
| [`archive/find-myreader.sh`](archive/find-myreader.sh) | 翻 NAS 找完整产物在哪 | 功能被 export-myreader 覆盖 |
| [`archive/rollback-to-8.sh`](archive/rollback-to-8.sh) | 退回 4.6.0-8 | 现役 4.6.0-10，跑它等于丢掉全部新功能 |
| [`archive/push-to-gitee.sh`](archive/push-to-gitee.sh) | 推 v9 改动到 Gitee | 现在直接 `git push` |

需要类似能力时**新写一个**放 `scripts/` 根，别在这些文件上打补丁 —— 它们记录的是当时的状态，
改了就不再是"当时的解法"，反而误导人。

## 约定

- 所有脚本 POSIX `sh` 可跑（不依赖 bash 特有语法），NAS 上直接 `sh xxx.sh`。
- 路径默认 `BASE=/volume1/docker`，可用环境变量覆盖。
- 破坏性操作前必须打印"将要做什么"并等确认，或提供 `--dry-run`。
- 改脚本时同步更新本文件的表格。
