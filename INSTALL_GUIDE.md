# MyBooks（audiobook 功能移植版）安装使用说明书

> 版本：4.6.0-15（基于上游 mybooks tag 4.6.0）
> 本版变化：新增「**音频批量转码**」工具箱（见第七节附）；修复有声书播放卡死/进度不动（nginx 缓存头 + 后端 HEAD/Range + 前端 seek 时序三处）；详情页「有声书」改为直接进入播放页。「读者组分级权限」「音频转写文稿」「有声书挂靠」见第五~七节；内嵌阅读器见第八节。

---

## 目录

1. [系统要求](#一系统要求)
2. [Windows 部署](#二windows-部署)
3. [NAS 部署（群晖 / 威联通 / 其他 Linux）](#三nas-部署)
4. [初始化设置](#四初始化设置)
5. [新功能一：读者组分级权限](#五新功能一读者组分级权限)
6. [新功能二：音频转写文稿](#六新功能二音频转写文稿)
7. [新功能三：有声书挂靠到已有电子书](#七新功能三有声书挂靠到已有电子书)
8. [**内嵌阅读器 MyReader（502 排查看这节）**](#八内嵌阅读器-myreader502-排查看这节)
9. [日常使用速览](#九日常使用速览)
10. [数据备份与升级](#十数据备份与升级)
11. [**构建加速（慢的话先看这节）**](#十一构建加速慢的话先看这节)
12. [常见问题排查](#十二常见问题排查)
13. [**排查命令速查表（实战积累）**](#十三排查命令速查表实战积累)
14. [音频批量转码（4.6.0-15）](#十四音频批量转码460-15)
12. [常见问题排查](#十二常见问题排查)

---

## 一、系统要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 10/11（64 位）、macOS、Linux、群晖 DSM 7+、威联通 QTS 5+ |
| Docker | Docker Desktop 4.x（Windows/macOS）或 Docker Engine 20.10+（Linux/NAS） |
| 内存 | 建议 **4 GB 以上**（音频转写功能建议 8 GB+） |
| 磁盘 | 镜像约 1.5 GB；另按藏书量预留空间 |
| 网络 | 首次构建需要联网拉取依赖 |
| Node.js | **无需本机安装**——前端在镜像内用 Node 20 构建（已内置，勿改低版本） |

> 音频转写（Whisper）是**可选功能**：有 NVIDIA 显卡的机器体验最好；纯 CPU 也能跑但速度慢。

---

## 二、Windows 部署

### 第 1 步：安装 Docker Desktop

1. 打开 <https://www.docker.com/products/docker-desktop/>，下载并安装 Docker Desktop。
2. 安装过程中保持勾选「Use WSL 2 based engine」（默认）。
3. 安装完成后启动 Docker Desktop，等右下角图标变成绿色（running）。
4. 验证：打开 PowerShell，输入 `docker --version`，能显示版本号即成功。

### 第 2 步：获取项目

把交付的 `audiobook-deploy-4.6.0-build.26.tar.gz` 解压到一个**路径里不含中文和空格**的目录，例如：

```
D:\audiobook\
```

解压后目录里应能看到：`Dockerfile`、`docker-compose.yml`、`webserver/`、`app/`、`README.md` 等。

### 第 3 步：构建并启动

打开 PowerShell，执行：

```powershell
cd D:\audiobook
$env:DOCKER_BUILDKIT="0"; docker build --no-cache -t mybooks-local:latest .
docker compose up -d --force-recreate --no-build
```

说明：
- 本机 compose 内嵌 BuildKit 会按 `(mtime,size)` 复用旧上下文快照，因此**不要**用
  `docker compose build` / `up -d --build`；必须 legacy 构建 + `--no-build` 启动。
- 首次构建约 5～15 分钟，取决于网络；`--no-cache` 是规定动作。
- `docker-compose.yml` 中同时写了 `build: .` 和 `image: mybooks-local:latest`：有 `build:` 时 Compose 会从当前目录源码构建并把结果打上该标签，**不会**再去拉取远程镜像。如果只写 `image:` 不写 `build:`，Compose 只会拉取远程同名镜像、忽略本地改动——本包已修复此问题。
- 看到 `Started` 字样即启动成功。

### 构建慢 / 报错的排查（v4.7.1 已修复的坑）

如果你之前遇到「构建很慢，最后报一堆错」，通常是这两类原因，本包都已修好：

**① 前端依赖装成了 Nuxt 4（最常见）**

`app/package.json` 里 `nuxt` 曾写作 `^4.6.2`，而本项目是 **Nuxt 2 + Vue 2**。`npm install` 会按 `^` 解析到真实的 Nuxt 4（Vue 3），于是用 Vue 3 编译器去编译 Vue 2 模板，报：

```
RollupError: <template v-for> key should be placed on the <template> tag.
SyntaxError: <template v-for> key should be placed on the <template> tag.
  at app/src/pages/login.vue:31:51
```

同时它会去解析 Nuxt 4 的整套依赖（`@vue/shared@^3.5.44` 等），耗时极长、最后 `ETARGET` 失败。

已修复：`nuxt` 改为 `^2.18.1`；Dockerfile 改用 `npm ci` 严格按 `package-lock.json` 安装；
并把 20 处 `<template v-for>` 的 `:key` 统一移到 `<template>` 标签上（两种编译器都合规）。
本地实测 `npm ci`（5 秒）→ `npm run build-spa`（36 秒，`Compiled successfully`）全通过。

**② 用了国外源**

`app/.npmrc` 已指向 `registry.npmmirror.com`；`docker-compose.yml` 默认传入 `BUILD_COUNTRY: CN`，apt/pip 也走国内源。

> 重要：`app/package.json` 的 `nuxt` 千万不要改回 `^4.x`，否则上面那堆错误会立刻重现。

**③ Node 16 太旧（`util.styleText` 报错）**

如果 ESLint 显示 `0 errors` 之后，真正构建时又冒出：

```
import { styleText } from 'node:util';
SyntaxError: The requested module 'node:util' does not provide an export named 'styleText'
  at file:///build/node_modules/@nuxt/cli/bin/nuxi.mjs:78:21
```

这是 **Node 版本太旧**，不是代码问题。Nuxt 2 的 CLI 链依赖 `@clack/core`，它需要 `node:util` 的
`styleText`，而该 API **Node 20.12 才引入**。原来的 `node:16-alpine` 早已 EOL，运行到 `import` 就抛错。

已修复：builder 基础镜像换成 `node:20-alpine`，并加了版本断言（低于 20 会直接提示，不再给出含糊的模块错误）。

> 注意 `@nuxt/cli` 这类包的 `engines` 声明并不能拦住这个问题——它写的是 `^16.14.0`，
> 但实际依赖要求 ≥ 20.12，所以 npm 不会阻止安装，只在运行时炸。

### 第 4 步：访问

浏览器打开：

```
http://localhost:9800
```

### 停止 / 重启 / 删除

```powershell
docker compose stop      # 停止（数据不丢）
docker compose start     # 再次启动
docker compose restart   # 重启
docker compose down      # 删除容器（data 目录里的数据仍在）
```

---

## 三、NAS 部署（群晖 / 威联通 / 其他 Linux）

### 一键部署（推荐，v4.8.1 起）

SSH 登录 NAS 后，**三行命令**完成部署：

```bash
cd /volume1/docker
tar -xzf audiobook-deploy-4.6.0-build.26.tar.gz
cd audiobook && sh scripts/deploy.sh
```

`scripts/deploy.sh` 会自动做五步：

1. **关键文件校验**——Dockerfile、docker-compose.yml、myreader-dist 产物、
   supervisor/nginx 配置、回填脚本，缺一个直接报错停止；
2. **符号链接抽查**——`app/node_modules` 首层应为 3 个链接（next/react/react-dom）、
   全产物合计应为 127 个，数量异常说明被解压工具压扁，会给出正确解压命令；
3. `DOCKER_BUILDKIT=0 docker build --no-cache -t mybooks-local:latest .`（legacy builder 构建镜像）；
4. `docker compose up -d --force-recreate --no-build`（启动容器）；
5. 等 20 秒后自动输出 supervisor 各进程状态和 myreader 日志尾部，一眼确认
   `myreader RUNNING`、日志无 `SyntaxError`。

只构建不启动：`sh scripts/deploy.sh build-only`。
手动部署与脚本等效，见下面的分步说明。


### 群晖 DSM

1. **套件中心**安装 **Container Manager**（DSM 7）或 Docker（DSM 6）。
2. 用 File Station 把解压后的项目文件夹上传到 NAS，例如 `/docker/audiobook/`。
3. 打开 Container Manager → **项目** → 新增：
   - 路径选择 `/docker/audiobook/`（它会自动读取里面的 docker-compose.yml）
   - 点击「构建」→ 等待完成 →「启动」。
   - 也可以 SSH 进 NAS 在项目目录直接执行：
     `sudo env DOCKER_BUILDKIT=0 docker build --no-cache -t mybooks-local:latest .`
     `&& sudo docker compose up -d --force-recreate --no-build`。

### 威联通 QTS

1. App Center 安装 **Container Station**。
2. SSH 进 NAS，进入项目目录执行 `DOCKER_BUILDKIT=0 docker build --no-cache -t mybooks-local:latest . && docker compose up -d --force-recreate --no-build`。

### 纯 Linux 服务器

```bash
# 若未装 docker compose 插件：
sudo apt install docker-compose-plugin

cd /path/to/audiobook
sudo env DOCKER_BUILDKIT=0 docker build --no-cache -t mybooks-local:latest .
sudo docker compose up -d --force-recreate --no-build
```

### NAS 专属注意事项

编辑 `docker-compose.yml`，把用户/组 ID 改成你自己的，避免数据目录权限问题：

```yaml
    environment:
      - PUID=1000     # 换成你的 UID（SSH 里输入 id 命令查看）
      - PGID=1000     # 换成你的 GID
```

改完执行 `docker compose up -d --force-recreate` 重建容器。

局域网访问：`http://NAS的IP:9800`（端口在 docker-compose.yml 的 `ports` 里改，冒号左边是宿主机端口；本包默认 9800，8080 留给官方版 mybooks）。

---

## 四、初始化设置

首次访问会进入安装向导：

1. **管理员账号**：设置管理员用户名和密码（务必记牢）。
2. **访问模式**：可开启「必须登录」（私人图书馆模式）或允许游客访问。
3. **书库目录**：默认 `/data/books`，对应 docker-compose.yml 挂载的 `./data` 目录。把电子书放入该目录即可导入。

登录后，点击右上角头像 → **系统设置** 进入管理后台。

---

## 五、新功能一：读者组分级权限

**用途**：像 audiobook 那样按「年级/分组」批量限制每个用户能看哪些书，不用逐个用户设置。

### 位置

管理后台 → 系统设置 → **用户** → **读者组分级权限**

### 使用步骤

1. **开启总开关**：先在「阅读范围」相关设置里启用阅读范围限制（`ALLOW_READ_RANGE_SETTING`）。
2. **创建组**：可以点 **「从模板创建」** 选一套预置模板（见下节），也可以自己填。
   - **白名单**：该组用户只能看到匹配的分类/标签的书
   - **黑名单**：该组用户看不到匹配的书
   填分类和标签（逗号分隔，如 `绘本`；标签 `童话,绘本`），点「添加」。
3. **分配用户**：在下方「批量分配用户到组」，填用户名（逗号或空格分隔），选组，点「分配」。
   - 不选组（留空）再分配 = 把用户**退出**当前组。
   - 不存在的用户名会提示数量。
4. **验证**：用组内用户的账号登录，首页/搜索/详情/下载都只会出现允许范围内的书。

### 预置模板（v4.8.2 起）

点「从模板创建」下拉，选一套即可填入表单，**改完再点「添加」才真正落库**，不会自动凭空建组。

| 模板 | 限制方式 | 标签数 | 效果 |
|---|---|---|---|
| **儿童** | 白名单 | 16 | 绘本/童书/少儿文学/国学诗词/少儿科幻 |
| **访客** | 白名单 | 33 | 人文社科 + 科普，挡掉财经与心理养生 |
| **成人家属** | 白名单（空） | 0 | 不限权，全库可读 |
| **会员** | 黑名单 | 56 | 全库可读，仅屏蔽心理励志 + 医学养生 |

模板值直接改 `webserver/services/reader_group.py` 的 `PRESET_GROUPS` 即可，改完重建镜像生效。

> **分类字段 vs 标签字段，别搞混**（这是我踩过的坑）：
>
> - **标签**（`tags`）匹配 `tags` 表里的标签名，是模板的主力；
> - **分类**（`categories`）匹配 `#category` 自定义列的值，即书入库时的分类路径。
>
> 而「书籍分类」设置里的 `BOOK_NAV`（经济金融/文学/历史那一大坨）**只负责前端把标签分组显示成导航**，完全不参与权限判断。所以别拿 BOOK_NAV 的分类名往 `categories` 里填 —— 不会报错，但也不生效。
>
> 另外，多数书库的 `#category` 列是空的（可以用管理后台 → 统计 里的「未分类」数量确认）。这种情况下分类字段填什么都无效，老老实实用标签。

### 生效规则（重要）

| 用户状态 | 实际限制 |
|---|---|
| 用户自己设置过阅读范围（个人设置） | **用户自己的设置优先** |
| 用户没设置过 | 使用所属组的配置 |
| 用户不在任何组、也没自己设置 | 不受限（管理员不受任何限制） |

### 数据存哪里

- 组定义存在站点设置里（`READER_GROUPS`），随设置持久化，无需数据库迁移。
- 用户归属存在每个用户的 `extra.reader_group` 字段。
- 删除组时，成员的归属会一并自动清除。

---

## 六、新功能二：音频转写文稿

**用途**：移植自 audiobook 的 Whisper 转写——把有声书音频（mp3/m4a/m4b/wav/flac/ogg/aac/wma）转成**可阅读的文字稿**（同名 .txt）。

### 位置

管理后台 → 系统设置 → **阅读** → **音频转写文稿**

### 安装（可选功能，默认未启用）

Whisper 体积很大（约 2 GB），没有打进默认镜像。需要时执行：

```powershell
# Windows PowerShell（容器运行中执行）
docker exec -it mybooks pip install -r /var/www/mybooks/requirements-optional.txt
```

```bash
# NAS / Linux
sudo docker exec -it mybooks pip install -r /var/www/mybooks/requirements-optional.txt
```

装完重启一次容器：`docker compose restart`。

> 有 NVIDIA 显卡的机器可先在容器内装对应 CUDA 版 torch 再装 whisper，速度能快一个数量级。
> **不安装也不影响任何其他功能**——面板会显示「未安装」并隐藏操作。

### 使用步骤

1. 展开「音频转写文稿」面板，确认没有「未安装」提示。
2. 选择要转写的音频，两种方式：

   **方式一：浏览服务器目录（推荐）** —— 点「浏览服务器目录」按钮，逐级进入
   文件夹，文件点「加入」、目录点「加整个目录」，路径自动填入列表。
   前提：需在管理后台开启「服务端目录浏览与导入」设置（浏览器只能看 /data 范围）。

   **方式二：直接粘贴路径** —— 文件和目录都可以，混着填也行：

   ```
   /data/books/有声书/第一季        ← 整个目录（自动递归收集其中全部音频，含子目录）
   /data/books/有声书/第99集.mp3   ← 单个文件
   ```

   提交后会返回实际找到的音频文件数；非音频文件、隐藏文件自动跳过，重复路径自动去重。

3. 选择模型与语言：
   - 模型：`tiny`（最快最糙）→ `small`（推荐）→ `medium`/`large`（最准最慢）
   - 语言：`auto` 自动判断，或指定 `zh` / `en`
4. 点「开始转写」。进度条实时显示（完成 / 失败 / 总数），任务在后台跑，页面关了也能继续跑。
5. 转写完成后，**在音频同目录生成同名 `.srt` 字幕（播放时高亮跟随）**；若勾选了
   「同时生成 .txt 文稿」，再多写一份纯文本。
6. 想中途停止：点「取消」，当前这一段音频转完就停（已生成的文稿保留）。

### 转写进度也可用 API 查看

`GET /api/admin/transcribe/status`（管理员），返回 running/进度/完成数等。

---

## 七、新功能三：有声书挂靠到已有电子书

### 问题从哪来

mybooks 里电子书和有声书是**两套目录**：

| 类型 | 物理路径 | 挂靠方式 |
|---|---|---|
| 电子书 | `data/books/library/<作者>/<书名>/` | Calibre 书库记录 |
| 有声书 | `data/books/audios/<book_id>/` | 靠 **book_id** 指向 Calibre 书籍 |

`audios/<book_id>/` 这个目录名就是书籍 ID，有声书本身**没有独立数据表**。

原版逻辑（上游 bug）：导入音频时只看「这本书有没有 `audios/<id>/` 目录」，
没有就**新建一本书**。于是你先把 epub 导入书库（它在 `library/` 里，没有音频目录），
后来再导入同名音频 → 判定「没有音频」→ 又建一条新记录 → **同一本书出现两条**。

### 现在的行为

导入音频时，若发现**同名书籍已存在**，直接把音频挂到那本书上（共用同一个 book_id），
不再新建记录：

- 一条记录、一个封面、一套元数据，音频仍在 `audios/<book_id>/` 下
- 书库里**不会**多出重复条目
- 挑选优先级：① `library/` 里真有格式文件的那本 → ② 都没有则取最早的 book_id

> 「目录合并」在本项目里的正确含义是**共用 book_id**，不是把音频文件搬进 `library/`。
> 物理路径搬了会连带弄坏播放器扫描、字幕配对和 Calibre 书库结构。

### 开关在哪

后台 → **系统设置** → **阅读与浏览** 标签 → 「有声书导入」区域：

| 设置项 | 默认 | 含义 |
|---|---|---|
| 同名电子书存在时，音频挂到该书而非新建 | 开 | 关闭则恢复上游旧行为（同名就新建书） |

在设置页顶部搜索框里搜「有声书」「挂靠」「重复」「合并」都能直接定位到这一项。

### 怎么确认生效

导入后看容器日志，出现这一行说明挂靠成功：

```
[AUDIO_IMPORT] 同名书籍已存在(book_id=42)，音频将挂到该书而非新建：《书名》
```

扫描结果弹窗里会多一项 **「已挂靠」** 计数（`linked`），与「新增」分开统计。

### 已经产生的重复记录怎么办

不必手动删。用内置的**同名重复书清理**工具一次搞定：

> 后台顶部菜单 → **管理** → **重复书清理**（或直接访问 `/toolbox/book_dedup`）

操作就两步：

1. 点「**扫描重复书**」——只读，不改数据。列出所有同名组，并给出每组的处置方案
2. 确认无误后点「**合并选中的 N 组**」

工具会自动完成这些事：

| 动作 | 说明 |
|---|---|
| 音频搬目录 | `audios/<重复id>/` → `audios/<保留id>/`，封面和 `.srt` 字幕一起搬，**不覆盖**目标已有同名文件 |
| 关联数据迁移 | 阅读进度、收藏、书单、评论、分享、浏览记录全部改指到保留书，**不是删掉** |
| 删除重复记录 | 从 calibre 书库删掉只有音频的那条 |
| 修正扫描记录 | `ScanFile` 里指向旧 id 的行改指到保留书，否则下次扫描会误判"已导入" |
| 备份 | 执行前把用户库完整拷贝到 `data/backup/dedup_<时间戳>.db` |

**哪些组不会自动处理**（只报告、不改动，需你自己判断）：

| 情况 | 原因 |
|---|---|
| 两本**都有**电子书文件 | 可能是同名的不同版本（上下册、不同译本），删错就麻烦了 |
| 一本电子书都**没有** | 全是音频记录，无法判断该留哪一本 |
| 同名超过 8 本 | 超出自动处理上限，多半不是"导入 bug"造成的 |

这些组会在列表里以黄色左边框标出，附一行原因说明。

**合并前请确认**：
- 勾选了「合并前备份用户库」（默认勾选）
- 清单里的「保留 / 删除」符合你的预期——保留的永远是**有电子书文件**的那本

**出错了怎么办**：备份文件在 `data/backup/dedup_<时间戳>.db`。
停服后把它拷回原位置（`data/books/settings/` 下对应的 sqlite 文件，具体文件名见
`docker-compose.yml` 的挂载），重启即可回到合并前状态。
calibre 书库的删除无法从该备份恢复，但音频文件仍在 `audios/` 目录里，重新扫描可挂回来。

---

## 八、内嵌阅读器 MyReader（502 排查看这节）

MyBooks 里的 epub / pdf / cbz / fb2 可以交给内嵌的 **MyReader** 打开，而不是用内置的
epub.js 或浏览器 PDF 阅读器。MyReader 是一个独立的 Next.js 服务，跑在容器内的
127.0.0.1:9100，由 supervisor 看管，nginx 把相关路径反代过去。

### 它是怎么接进来的

```
浏览器  →  nginx (/readerx/open?bookId=1&format=epub)
                   │  upstream myreader → 127.0.0.1:9100
                   ▼
             node app/server.js   ← 目录 /var/www/myreader
                   │  目录内容来自构建上下文里的 myreader-dist/
                   ▼
             向 Tornado (127.0.0.1:8000) 取书和用户身份
```

对应三处配置：

| 位置 | 作用 |
|---|---|
| `Dockerfile` 的 `COPY myreader-dist/ /var/www/myreader/` | 把产物放进镜像 |
| `conf/supervisor/mybooks.conf` 的 `[program:myreader]` | 起 `node app/server.js`，`PORT=9100` |
| `conf/nginx/mybooks.conf` 的 `upstream myreader` | 反代 `/readerx/`、`/reader/`、`/_next/`、`/api/mybooks/` 等 |

### 遇到 502 Bad Gateway 怎么判断

现象是访问 `/readerx/open?bookId=…&format=…` 返回
`502 Bad Gateway nginx/1.x.x`。502 的含义是 **nginx 连不上 upstream**，不是页面本身出错，
所以先确认 9100 到底有没有在听：

```bash
# 1. 容器里 9100 有没有监听（没有 → 服务没起来）
docker compose exec mybooks sh -c 'netstat -ltnp 2>/dev/null | grep 9100 || ss -ltnp | grep 9100'

# 2. 服务自己的日志（supervisor 把它写在 /data/log/myreader.log）
docker compose exec mybooks tail -50 /data/log/myreader.log

# 3. 产物在不在（正常应该是 app/server.js + app/.next + node_modules）
docker compose exec mybooks ls -la /var/www/myreader /var/www/myreader/app

# 4. 绕过 nginx 直连服务，缩小范围
docker compose exec mybooks sh -c 'curl -sS -o /dev/null -w "%{http_code}\n" \
  "http://127.0.0.1:9100/readerx/open?bookId=1&format=epub"'
```

按日志对号入座：

| 日志/现象 | 原因 | 处理 |
|---|---|---|
| `ls /var/www/myreader` 只有 `.keep` 或为空 | 构建时 `myreader-dist/` 是空的 | 见下面「怎么生成产物」 |
| `Cannot find module 'next'` | 产物里的 `node_modules` 没进镜像 | 检查 `.dockerignore` 的 `!myreader-dist/...` 放行规则 |
| `Cannot find module 'js-md5-<hash>'` | `.next/node_modules` 那层被 `.dockerignore` 排掉了 | 同上 |
| `EADDRINUSE` | 9100 被占 | `docker compose restart` |
| 日志正常、`curl` 也 200，但浏览器 502 | nginx 没重载配置 | `docker compose restart` |

### 怎么生成产物（需要自己重建时）

产物不入库（`.gitignore` 里有 `myreader-dist/`），因为它有 92MB、2600 多个文件，且内含
Next 裁剪好的 `node_modules`。源码包里已内置一份可用的产物；只有在升级 MyReader 或
产物损坏时才需要重新生成：

```bash
# 1. 取 MyReader 源码（注意 tag 名是 0.9.1，没有 v 前缀）
git clone --branch 0.9.1 https://github.com/PoxenStudio/MyReader.git
cd MyReader

# 2. 初始化必需的 submodule（不初始化会直接构建失败）
git submodule update --init \
    packages/foliate-js packages/simplecc-wasm packages/js-mdict packages/qcms \
    app/src-tauri/plugins/tauri-plugin-turso \
    app/src-tauri/plugins/tauri-plugin-webview-upgrade

# 3. 装依赖（仓库声明 pnpm@11.1.1）
corepack enable && corepack prepare pnpm@11.1.1 --activate
pnpm install --frozen-lockfile

# 4. 把 pdfjs / simplecc / jieba 的 wasm 拷进 public/vendor（这一步生成的文件不入库，
#    跳过会报 pdfjs 类型错误）
pnpm --filter @poxenstudio/myreader setup-vendors

# 5. 构建 standalone 产物并装配成 myreader-dist/
pnpm --filter @poxenstudio/myreader build-docker-dist

# 6. 拿回 MyBooks
rsync -a --delete app/myreader-dist/ <mybooks 路径>/myreader-dist/
cd <mybooks 路径>
DOCKER_BUILDKIT=0 docker build --no-cache -t mybooks-local:latest .
docker compose up -d --force-recreate --no-build
```

> 第 5 步的脚本输出目录结构就是 MyBooks 的 `Dockerfile` 期望的
> `myreader-dist/app/server.js` + `myreader-dist/node_modules`，**不要拍平或重新组织**。
> 三层 `node_modules` 之间是相对符号链接（`app/node_modules/next -> ../../node_modules/.pnpm/…`），
> 任意合并/搬动一层都会启动即失败。

### 不想用它？

在 **设置 → 阅读器** 里把 EPUB 阅读器从 `MyReader` 改回 `epubjs.html`，PDF 则会走浏览器
内置阅读器。改完 `/readerx` 不再被使用，即使 9100 没起来也不影响阅读。

> 顺带说明：MyReader 的 GitHub Release 页面上那些 `.deb` / `.dmg` / `.apk` / `.exe` 是
> 桌面端和移动端安装包，**不能**放进 `myreader-dist/`。容器要的是 web 产物，只能按上面的
> 步骤从源码构建。

---


### 八之补、v4.8.1 增量修复（已包含在本包中）

1. **封面修复**：MyReader 嵌入流的 `applyCloudMetadata` 现在会把同源封面
   `/get/cover/<bookId>.jpg` 写入 `metadata.coverImageUrl`，从桌面版同步过来、
   持久化封面地址丢失的书也能显示真实封面（此前只显示书名兜底帧）。
2. **扫描器屏蔽**：`conf/nginx/mybooks.conf` 新增两组 `return 444` 规则，
   `.php`/`.env`/`wp-admin`/`phpmyadmin` 等扫描请求静默断开且不写 access log。
   注意 `/api/mcp` 是 MyBooks 真实功能端点，刻意未拦。
3. 交付物 `myreader-dist.tar.gz` 必须用命令行 `tar -xzf` 解压（符号链接事故的完整
   复盘见 `CHANGELOG.md`「修复：仓库里的 myreader-dist 是残骸，直出的包必然 502」，
   打包侧要点见 [`docs/操作总纲.md`](docs/操作总纲.md)），**不要用图形化解压工具**。

### 八之补二、v4.8.2 增量（书籍分类重整 + 读者组模板）

1. **书籍分类从 9 类重整为 13 类**（`settings.BOOK_NAV`，中英繁三处默认值已同步）。
   原来 `文学`(128)、`历史`(100)、`社科`(80) 三个巨型分类占了一半标签，
   且同类内还有 6 个重复项、跨类重复 2 个。重整后 **493 个标签零遗漏零重复**：

   | 分类 | 标签数 | | 分类 | 标签数 |
   |---|---|---|---|---|
   | 经济金融 | 56 | | 科技 | 57 |
   | 哲学社科 | 73 | | 艺术设计 | 11 |
   | 历史 | 98 | | 心理励志 | 44 |
   | 文学 | 71 | | 教育 | 12 |
   | 小说 | 31 | | 医学养生 | 12 |
   | 推理悬疑 | 17 | | 传记纪实 | 5 |
   | 科幻小说 | 6 | | | |

   主要动作：把 `小说`/`推理悬疑` 从 `文学` 里独立出来（原来「恐怖」「犯罪」
   和「儿童文学」挤在同一类，做白名单时无法切分）；把 `艺术设计` 从 `社科` 拆出；
   `心理励志` 从 `心理学` 改名以贴合实际收录；`量子力学`/`博弈论` 归入科技。
2. **读者组预置模板**：管理后台读者组编辑区新增「从模板创建」，四套模板见第五节。
3. **空规则不再等于全屏蔽**：白名单组若分类和标签都为空，现在按「不限权」处理。
   此前会被展开成空集合 → 屏蔽全库，是最容易被误判为「系统坏了」的形态。

### 打包自己的交付包时注意（踩过的坑）

`tar` 的 `--exclude` 是**路径任意位置匹配**，不是锚定开头。写
`--exclude='app/node_modules'` 会连 `myreader-dist/app/node_modules`
一起排掉，而那一层恰好是 Next standalone 的符号链接入口，缺了它解压后
docker build 就少了 `next`/`react`/`react-dom` 三个链接，容器起来后 myreader
会 FATAL。要用带前缀的写法：

```bash
tar --numeric-owner \
    --exclude='./mybooks/.git' \
    --exclude='./mybooks/app/node_modules' \
    --exclude='./mybooks/app/.nuxt' \
    -czf audiobook-deploy-vX.Y.Z.tar.gz \
    --transform 's,^mybooks,audiobook,' mybooks
```

打包后务必验证（正确值：首层 3、全产物 127）：

```bash
tar -tzvf audiobook-deploy-vX.Y.Z.tar.gz | awk '$1 ~ /^l/ {n++} END {print "链接总数:", n}'
# 建议再实际解压到 /tmp 抽查一次，确认三个链接不是断链
```


### 读者组分类回填脚本（tools/category_backfill.py）

读者组分级权限的「分类」匹配的是每本书的 calibre 自定义列 **#category**
（不是「阅读与浏览」里的书籍分类导航 BOOK_NAV）。书没填这一列时，
白名单模式下会被全部挡掉。v4.8.1 起镜像内置回填脚本，用法：

```bash
# 1. 预览（dry-run，不写数据）
docker exec -it audiobook-mybooks-1 python3 /var/www/mybooks/tools/category_backfill.py

# 2. 确认无误后真正写入
docker exec -it audiobook-mybooks-1 python3 /var/www/mybooks/tools/category_backfill.py --apply

# 可选：只处理含某些标签的书；join 模式把全部标签拼成一个分类值
docker exec -it audiobook-mybooks-1 python3 /var/www/mybooks/tools/category_backfill.py --only 绘本,教材 --apply
```

要点：只回填 `#category` 为空且有标签的书，已有的分类绝不覆盖；
走 calibredb CLI 写入，与运行中的服务并发安全，无需停服；
回填后读者组判定实时生效。若书库连 #category 列都没建，脚本会明确报错提示先建列。

### 从上游 mybooks 迁移数据（tools/migrate_from_upstream.sh）

**适用场景**：上游 mybooks（9000 站）的书、音频、用户想整体搬到本改版站（9800），
搬完之后上游容器和镜像一并退役。

#### 第 1 步：找到上游目录

```bash
# 上游容器把宿主机哪个目录挂到了 /data，输出的左边就是
docker inspect <上游容器名> --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
# 本例：/volume1/docker/mybooks -> /data
```

#### 第 2 步：改脚本配置（通常不用改）

```bash
cd /volume1/docker/audiobook
vi tools/migrate_from_upstream.sh
```

开头四个变量：`UPSTREAM_DIR`（上游目录）、`OUR_DIR`（本站目录）、
`UPSTREAM_CONTAINER`（上游容器名）、`OUR_CONTAINER`（本站容器名）。
默认值就是上面的例子，路径一致时直接跳过这步。

#### 第 3 步：dry-run 预览（不写任何数据）

```bash
sh tools/migrate_from_upstream.sh
```

看三样东西：书库总字节数（与上游 `du -sh 上游目录/books` 对得上）、
用户库是否找到（找不到会自动扫描列候选）、模式提示。

#### 第 4 步：真正迁移——两种模式选一

| 模式 | 命令 | 原理 | 上游目录结局 |
|---|---|---|---|
| **--move（推荐）** | `sh tools/migrate_from_upstream.sh --move` | 同一文件系统内 `mv` 是瞬间 rename，11GB 不用逐字节拷 | books 被腾空（只留空壳） |
| --apply（保守） | `sh tools/migrate_from_upstream.sh --apply` | rsync 逐文件复制，3~10 分钟 | 上游原样保留，可回退 |

同一块盘上选 `--move`；两块盘/跨卷时 mv 等效复制，选哪个耗时差不多，
选 `--apply` 更稳（上游还在）。

脚本自动做的事（两种模式相同）：

1. `--move` 模式先停上游容器（搬走后上游不能再写数据）
2. 备份本站现有数据到 `../audiobook-backup-<时间戳>/`
3. 停本站容器 → 移动/同步 `books/`（书文件 + `metadata.db` + `audios/` 有声书音频）+ `calibre-webserver.db`（用户/权限库）→ 修属主 1026:100 → 起容器
4. 自检：书数、标签数、supervisor 四进程状态

#### 第 5 步：验证

```bash
# 进程全 RUNNING（tornado / nginx / logrotate / myreader）
docker exec audiobook-mybooks-1 supervisorctl status
```

浏览器打开 9800：用**上游的管理员账号**登录（用户库已被上游覆盖，本站原
账号不在了），核对书籍总数、封面、有声书播放。`#category` 空缺的书随后跑
`category_backfill.py` 回填（见上文）。

#### 迁移后有声书没有「文稿 + 声音高亮」？

机制：播放有声书时，系统扫描 `audios/<book_id>/` 里**与音频同名的 `.srt` 字幕**
按时间轴高亮文稿（`.txt` 全稿也在同目录）。`.srt`/`.txt` 是音频目录的一部分，
**随迁移整体过来，不会丢**。迁移后没同步，几乎都是上游本来就没生成过字幕。验证：

```bash
# 对上游（或退役改名后的）目录数一下：srt 数 vs 音频数
find /volume1/docker/mybooks*/books/audios -name "*.srt" | wc -l
find /volume1/docker/mybooks*/books/audios \( -name "*.mp3" -o -name "*.m4b" -o -name "*.wav" \) | wc -l
```

两个数字接近 → 字幕在，浏览器强刷（Ctrl+Shift+R）再看；srt 明显少或为 0 →
上游没跑过转写，用第六节的转写功能补：详情页 → 转写文稿（需开启
`WITH_WHISPER`，本包默认已开）。这是数据补齐，与迁移脚本无关。

#### 第 6 步：上游退役（确认迁移无误后再做）

```bash
# 1. 停并删上游容器（含 compose 项目）
cd /volume1/docker/mybooks && docker compose down

# 2. 删上游镜像（先看名字）
docker images | grep -i mybooks
docker rmi <上游镜像名:tag>

# 3. 上游目录先改名保留一段时间，彻底确认没问题再删
cd /volume1/docker && mv mybooks mybooks-retired-$(date +%Y%m%d)
# 观察 1~2 周后：
# rm -rf mybooks-retired-YYYYMMDD
```

> 退役顺序有讲究：先 `docker compose down`（容器不用了）→ 再 `docker rmi`
> （镜像占空间最多，几 GB）→ 目录最后删（数据无价，多留一阵没坏处）。

### 上游版本更新后怎么升级（tools/upgrade-from-upstream-manual.sh）

> **和 `scripts/upgrade-upstream.sh` 别搞混**
> - `scripts/upgrade-upstream.sh` —— **自动**：查上游最新 release，拉取 → 合并 → 重建 → 迁移全链路跑完，无人值守。适合「我就想跟到上游最新版」。
> - `tools/upgrade-from-upstream-manual.sh` —— **手工**（本节讲这个）：把上游某个 ref 拉进独立 git 目录，冲突由你自己解决、逐文件确认补丁层没被抹掉。适合「跟版本，但我要看清改了哪些」。

**不要直接用上游新代码覆盖本站**——本站是带十几个文件改动的 fork（封面修复、
nginx 扫描屏蔽、读者组模板、分类重整、MyReader 接入……），直接覆盖等于把移植
价值全部抹掉。正确做法是 git 补丁层：

#### 脚本参数怎么填（重点，容易搞错）

参数是**上游 git 仓库的分支名**，不是我们改版的版本号，也不是裸数字。

上游 PoxenStudio/mybooks 的版本以**分支**形式发布，命名是三段式带 `v` 前缀：
`v4.6.0`、`v4.5.1`、`v3.27.0`……截至本手册编写时最新正式分支是 **`v4.6.0`**。

```bash
sh tools/upgrade-from-upstream-manual.sh              # 不带参数 = 自动探测上游最新 v*.*.* 正式版分支（推荐）
sh tools/upgrade-from-upstream-manual.sh v4.6.0       # 指定跟上游 v4.6.0（推荐：正式版）
sh tools/upgrade-from-upstream-manual.sh v4.5.1       # 也可以跟任意历史版本
```

三种常见写错：

| 错误写法 | 为什么错 |
|---|---|
| `sh ... 4.6` | 少了 `v` 前缀和第三段，上游没有这个分支名 |
| `sh ... 4.61` | 上游版本是 v4.6.0 / v4.6.1 三段式，没有 4.61 |
| `sh ... v2.0.0` | 上游从未发布过这个版本 |

**每次升级前先查上游最新分支号**（一条命令）：

```bash
git ls-remote --heads https://github.com/PoxenStudio/mybooks.git \
  | grep -oP 'refs/heads/v[\d.]+' | sort -V | tail -3
# 输出最新三个版本分支，拿最新的当参数即可
```

#### 升级节奏建议

- **首次部署后先别急着升级**：分类重整、读者组模板等改版刚落地时，马上 merge
  上游新版本容易冲突（上游也常改 `settings.py` 的 BOOK_NAV），把几件事搅在一起。
  先把迁移、回填这些基础操作做稳，再跟版。
- 跟版前先看上游该版本的更新内容（GitHub Releases 页），确认没有与我们改动
  正面相撞的功能（如上游重写了 BOOK_NAV / 权限体系），再执行。

#### 脚本做的事

fetch 上游 → merge 到本站 → 无冲突直接 legacy 构建 + `docker compose up -d --force-recreate --no-build`；
有冲突则停下列出冲突文件，处理原则写在提示里（`webserver/`、`app/src/` 下
优先保我们的改动，纯上游新文件直接 add）。

#### 详细步骤

```bash
cd /volume1/docker/audiobook

# 1. （首次）脚本会自动初始化 git 仓库并提交基线
#    ★ 仓库不在站点目录里，而在 /volume1/docker/audiobook-git/（站点外）★
sh tools/upgrade-from-upstream-manual.sh

# 2. 日常升级：不带参数即自动跟上游最新正式版分支；也可显式指定（写法见上文「参数怎么填」）
sh tools/upgrade-from-upstream-manual.sh              # 自动探测最新 v*.*.* 分支
sh tools/upgrade-from-upstream-manual.sh v4.6.0       # 显式指定版本分支
sh tools/upgrade-from-upstream-manual.sh develop      # 明确要跟开发进度时才用（不稳定）

# 3. 有冲突时（脚本会停下并列出文件），逐个处理：
git status                          # 看冲突清单（需要在 audiobook-git 目录，或带 GIT_DIR，见下）
vi <冲突文件>                        # 找 <<<<<<< 标记手工融合
git add <解决完的文件>
git commit
# 然后手工收尾：
DOCKER_BUILDKIT=0 docker build --no-cache -t mybooks-local:latest .
docker compose up -d --force-recreate --no-build
```

#### git 仓库放在哪、为什么、怎么防删

| 问题 | 答案 |
|---|---|
| 仓库文件在哪 | **`/volume1/docker/audiobook-git/`**（站点目录外面），站点目录内不留 `.git` |
| 为什么放外面 | 重装流程是 `rm -rf audiobook` 再解压新包——`.git` 放里面会被连根删掉。放外面后，重装完跑一次升级脚本，git 自动接回原历史，所有提交都在 |
| 里面存了什么 | 只有**代码 + 配置 + 文档**。构建产物（`app/dist`、`myreader-dist/`、`node_modules`）被排除；书/音频/用户库在 v4.8.2 起已整体外置到 `audiobook-data/`，本来就不在站点目录里 |
| 怎么确认历史还在 | `git -C /volume1/docker/audiobook-git log --oneline` 能看到基线提交 |
| 想删了重来 | 直接 `rm -rf /volume1/docker/audiobook-git`，下次跑脚本重建（代价只是丢失历史提交线） |

冲突处理、查看历史等手工 git 命令，两种写法任选：

```bash
git -C /volume1/docker/audiobook-git log --oneline      # 看历史
cd /volume1/docker/audiobook
GIT_DIR=/volume1/docker/audiobook-git GIT_WORK_TREE=/volume1/docker/audiobook git status
```

（脚本内部已自动设好这两个环境变量，只有你自己敲 git 命令时才需要带。）

#### 升级前后的检查点

| 时机 | 检查 |
|---|---|
| 升级前 | `git status` 干净（没有未提交的手工改动）；磁盘余量 ≥ 5GB（构建需要） |
| 构建后 | `docker compose exec mybooks supervisorctl status` 四进程全 RUNNING |
| 访问验证 | 首页出书、点一本能进阅读器、有声书能播、管理后台读者组模板还在 |
| 回滚（有问题时） | `git reset --hard ORIG_HEAD && DOCKER_BUILDKIT=0 docker build --no-cache -t mybooks-local:latest . && docker compose up -d --force-recreate --no-build` |

#### 配套使用习惯

- 每次手工改过本站代码后 `git add -A && git commit`，让"我们的补丁层"保持成一条干净的提交线；
- 升级出问题 24 小时内都能秒回：`git reset --hard ORIG_HEAD && DOCKER_BUILDKIT=0 docker build --no-cache -t mybooks-local:latest . && docker compose up -d --force-recreate --no-build`；
- 长期不跟随上游也没关系，本站自洽；想同步时再跑一次脚本即可，git 历史永远在。

### 一次性：把数据目录分离出源码目录（v4.8.2 布局，强烈建议）

v4.8.1 及以前，数据直接落在源码目录里（挂载 `audiobook:/data`），`rm -rf audiobook`
重装时书和数据库会一起陪葬。v4.8.2 起 compose 改挂 `audiobook-data:/data`，
源码和数据彻底分手。**已按旧布局跑起来的环境**做一次搬迁（几分钟，纯 rename）：

```bash
cd /volume1/docker

# 1. 停容器（保持源码目录不动）
docker compose -f audiobook/docker-compose.yml stop   # 或 docker stop audiobook-mybooks-1

# 2. 建数据目录，把 /data 下所有运行数据搬过去（同盘 mv 是 rename，秒级）
mkdir -p audiobook-data
for d in books sync models cache logs log reader toolbox workspace; do
    [ -e "audiobook/$d" ] && mv "audiobook/$d" "audiobook-data/$d" || true
done

# 3. 确认 books 三个核心都在
ls audiobook-data/books/        # library/ audios/ calibre-webserver.db ...

# 4. 换新包（compose 已写好 audiobook-data:/data）或手工改旧 compose 的 volumes 行
#    - /volume1/docker/audiobook:/data   →   - /volume1/docker/audiobook-data:/data

# 5. 起容器并验证
cd audiobook && docker compose up -d && sleep 25
docker exec audiobook-mybooks-1 supervisorctl status
docker exec audiobook-mybooks-1 python3 -c \
  "import sqlite3;print('书数:',sqlite3.connect('/data/books/library/metadata.db').execute('select count(*) from books').fetchone()[0])"
```

搬迁后：`rm -rf audiobook` 重装源码 = 只是换代码，书、音频、用户、模型缓存全在
`audiobook-data/` 里毫发无损。备份也只需盯住这一个目录。

### 长期保持源码目录干净：升级时必须"原子替换"

这是最容易踩的坑：**直接在 `audiobook/` 里 `tar -xzf` 新包**，新包会覆盖旧文件，
但旧包里已被删掉的文件会残留下来。历史上（v4.8.1 及以前）数据也落在源码目录里，
于是旧 `books/` 残留 + 新包叠加，就出现了"`audiobook` 下冒出 `books`"的现象。

**v4.8.2 起提供 `scripts/upgrade.sh`，从根上避免这件事：**

```bash
cd /volume1/docker
sh audiobook/scripts/upgrade.sh /volume1/docker/audiobook-deploy-4.6.0-build.26.tar.gz
```

它做的事（详见 [`docs/部署包说明.md`](docs/部署包说明.md) 的步骤表）核心只有一句：
**先把 `audiobook` 整个改名成 `audiobook.old`，再 `mkdir` 一个全新目录解压。**
全新目录里不可能有任何历史残留，也就谈不上"污染"。

#### 三条铁律

| 铁律 | 说明 |
|---|---|
| **1. 不在旧目录上叠加解压** | 永远 `mv` 走旧的 → `mkdir` 新的 → 解压到新目录 |
| **2. 数据只存在 `audiobook-data/`** | 源码目录里出现 `books/`、`data/`、`library/`、`audios/` 一律视为异常 |
| **3. compose 挂载只指向 `audiobook-data`** | `grep ":/data" docker-compose.yml` 必须得到 `- /volume1/docker/audiobook-data:/data` |

#### 每次升级后的 30 秒自检

```bash
cd /volume1/docker

# ① 源码目录应看不到任何数据目录（无输出 = 正常）
ls -d audiobook/books audiobook/book audiobook/data audiobook/library audiobook/audios 2>/dev/null

# ② 挂载必须指向 audiobook-data
grep ":/data" audiobook/docker-compose.yml

# ③ 容器实际挂载确认
docker inspect audiobook-mybooks-1 --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'

# ④ 数据仍然在（书数应与升级前一致）
docker exec audiobook-mybooks-1 python3 -c \
  "import sqlite3;print('书数:',sqlite3.connect('/data/books/library/metadata.db').execute('select count(*) from books').fetchone()[0])"
```

`scripts/deploy.sh` 与 `scripts/upgrade.sh` 已把 ① ② 固化为脚本开头的强制检查，失败即中止，
不会在"脏目录"上继续构建出镜像。

#### 万一发现源码目录里已有数据目录

不要直接 `rm -rf`，先判断数据是否还在 `audiobook-data` 里：

```bash
cd /volume1/docker
docker compose -f audiobook/docker-compose.yml down

# 体积对比：源码目录里的 vs 数据目录里的
du -sh audiobook/books audiobook-data/books 2>/dev/null

# 若 audiobook/books 里有 audiobook-data/books 没有的东西，先合并（-n 不覆盖已有）
command -v rsync >/dev/null && rsync -avn audiobook/books/ audiobook-data/books/   # 先 dry-run
command -v rsync >/dev/null && rsync -av  audiobook/books/ audiobook-data/books/

# 确认数据齐全后，再清掉源码目录里的副本
rm -rf audiobook/books audiobook/data audiobook/library audiobook/audios
```

清理完重跑一次 `scripts/upgrade.sh`，即可得到完全干净的源码目录。

## 九、日常使用速览

以下为 mybooks 原有功能，简单列出入口：

| 功能 | 入口 |
|---|---|
| 上传书籍 | 首页右上角「+」或拖拽上传（epub/mobi/azw3/pdf/txt 等） |
| 批量导入 | 管理后台 → 导入（可监听目录自动导入） |
| 在线阅读 | 书籍详情 → 阅读（EPUB/PDF 内置阅读器） |
| 下载 / 推送 Kindle | 书籍详情 → 下载或推送（需配置 SMTP） |
| 有声书（EPUB→音频） | 书籍详情 → 转音频（edge-tts，本项目原有功能） |
| 豆瓣刮削 / AI 补全信息 | 管理后台 → 图书信息刮削 |
| WebDAV | `http://IP:9800/books`（Windows 资源管理器映射网络驱动器） |
| OPDS | `http://IP:9800/opds/`（供阅读器 App 订阅） |
| 用户管理 | 管理后台 → 用户（含本版新增的读者组） |

---

## 十、数据备份与升级

### 目录布局（v4.8.2 起：数据与源码分离）

| 目录 | 内容 | 生命周期 |
|---|---|---|
| `/volume1/docker/audiobook/` | 源码 + 部署脚本 | 可随意 `rm -rf` 重装 |
| `/volume1/docker/audiobook-data/` | **全部运行数据**（books 书库+音频+用户库、models 模型缓存、logs 日志等） | 独立于源码，重装不动它 |
| `/volume1/docker/audiobook-git/` | 升级脚本的 git 历史 | 同上 |

docker-compose.yml 的挂载是 `audiobook-data:/data`。删除容器、删除镜像、重装源码，
数据都安然无恙；**唯一要怕的是 `rm -rf audiobook-data`**。

### 备份

**只需要备份一个目录**：`/volume1/docker/audiobook-data/`（书库、音频、用户库、
模型缓存、日志全在里面）。停服备份最稳：

```bash
cd /volume1/docker/audiobook
docker compose stop
cp -a /volume1/docker/audiobook-data /volume1/backup/audiobook-data-$(date +%Y%m%d)
docker compose start
```

只关心书和库的话，最小集是 `audiobook-data/books/`（书文件 + metadata.db +
calibre-webserver.db + audios 音频）。

### 升级到新版

1. 备份 `audiobook-data`。
2. 源码目录随便换：`rm -rf audiobook` 后解压新包即可（数据在 `audiobook-data`，不受影响）。
3. `sh scripts/deploy.sh` 重建。

### 改一行代码不想等构建：热更新（`tools/hotfix-from-src.sh`）

> **和 `scripts/hotfix.sh` 别搞混**——两个脚本功能相似但**文件来源不同**：
> - `tools/hotfix-from-src.sh`（本节讲这个）：从**当前源码目录**（git 仓库）挑改过的 `.py` 推容器。你手里有源码、在改代码时用它。
> - `scripts/hotfix.sh`：从**指定部署包** `.tar.gz` 解出后挑 `.py` 推容器。只有部署包、没有源码时用它，用法 `sh audiobook/scripts/hotfix.sh <包> [--restart]`。

完整镜像构建（`DOCKER_BUILDKIT=0 docker build --no-cache`）最慢的一步是 `npm run build-spa`（前端编译，CPU 密集）。
如果只改了 **Python 后端**，没必要为它等构建，用热更新把改动直接推进运行中的容器：

```bash
cd /volume1/docker/audiobook
sh tools/hotfix-from-src.sh --dry-run    # 先看会推哪些文件（对比容器内 mtime）
sh tools/hotfix-from-src.sh              # 推送 + 只重启 tornado，1 分钟内生效
```

脚本做的事：扫描 `webserver/`、`server.py`、`tools/` 下所有 `.py`，比对源码与容器内的
mtime，只把**改过的**用 `docker cp` 推进去 → `chown mybooks` → 清 `__pycache__`
→ `supervisorctl restart mybooks:tornado`（nginx / myreader 不动，阅读器不掉线）。

**能热更什么、不能热更什么：**

| 改动位置 | 能否热更 | 说明 |
|---|---|---|
| `webserver/**.py`、`server.py`、`tools/*.py` | ✅ 能 | 脚本自动处理 |
| `app/**/*.vue`、`app/locales/*.json` | ❌ 不能 | 已编译进静态 `dist/`，必须 `DOCKER_BUILDKIT=0 docker build --no-cache` 重建镜像 |
| `conf/nginx/*`、`conf/supervisor/*` | ❌ 不能 | 需重建镜像或手工 `docker cp` + reload |

**关键提醒**：热更新**不持久**——容器重建、镜像重建、`docker compose down` 之后就回到
镜像里的旧代码。所以它的定位是「先验证，再固化」：

```bash
sh tools/hotfix-from-src.sh --frontend   # 验证后端（同时提醒前端未生效）
DOCKER_BUILDKIT=0 docker build --no-cache -t mybooks-local:latest .   # 验证通过后固化进镜像
docker compose up -d --force-recreate --no-build
```

`--no-cache` 会重建全部层（含 npm 依赖安装与 `npm run build-spa`），这是为了避免新旧
`dist` 混装的规定动作；不要为了省时间改成带缓存的构建。

---

## 十一、构建耗时（慢的话先看这节）

构建慢的主要原因仍是基础镜像与依赖安装；但**本机的构建口径固定为 legacy + `--no-cache`**，
不再提供层缓存加速。优化重点只能放在网络（镜像加速）与磁盘速度上。

### 为什么会慢：三块耗时

| 耗时来源 | 体积/时长 | 能否避免 |
|---|---|---|
| ① 拉 `mybooks_base` 基础镜像（Ubuntu 24.04 + Calibre 7.6 + FFmpeg + Node） | 约 **1.5 GB** | 首次必拉，之后命中本地缓存 |
| ② 前端 `npm ci` + webpack 打包 | 约 **3～6 分钟** | 每次全量重跑（规定动作） |
| ③ Python 依赖 `pip install` | 约 **2～5 分钟** | 每次全量重跑（规定动作） |

**首次构建 5～15 分钟是正常的**，因为 ①②③ 全都要跑。

### 正确命令（规定动作，没有缓存捷径）

本机的 compose 内嵌 BuildKit 会按 `(mtime, size)` 复用旧上下文快照，导致「新 `_nuxt` +
旧 `index.html`」。因此构建一律走 legacy builder + 全量重建：

```bash
DOCKER_BUILDKIT=0 docker build --no-cache -t mybooks-local:latest .
docker compose up -d --force-recreate --no-build
```

- 不要用 `docker compose build` / `docker compose up -d --build` / `make fast-build`：
  它们会回到带缓存的路径，正是事故来源。
- `--no-cache` 会让 ①②③ 全量重跑，这是为了产物一致，不是可优化项。
- 清理旧镜像用 `docker image prune -f`；**禁止 `docker system prune -a`**（会删基础镜像）。

### 唯一可做的加速：配好 Docker 镜像加速（国内必做）

`docker.1ms.run` 已在 Dockerfile 里内置。若拉镜像仍然慢，说明本机 Docker 没配加速，
在 Docker Desktop → Settings → Docker Engine 里加：

```json
{
  "registry-mirrors": [
    "https://docker.1ms.run",
    "https://docker.m.daocloud.io",
    "https://hub.rat.dev"
  ]
}
```

然后 `Apply & Restart`。这三个源实测都通（HTTP 200/401，响应 0.04～0.27 秒）。

### 实测数据（本机 Node 20 / Linux）

```
npm ci              → 1448 packages, 5s
npm run build-spa   → Compiled successfully in 36s   （含 ESLint）
```

也就是说优化后前端打包本身只要 36 秒，剩下的时间都在拉基础镜像和装 Python 依赖上。

---

## 十二、常见问题排查

### 构建很慢或失败
- 本机 `docker compose build` 会走 compose 内嵌 BuildKit，且会复用旧上下文快照
  （表现为「新 `_nuxt` + 旧 `index.html`」），**不要用**；统一用
  `DOCKER_BUILDKIT=0 docker build --no-cache -t mybooks-local:latest .`。
- 网络问题。国内给 Docker 配镜像加速（见上）；重试同一条 legacy 构建命令。
- legacy builder 没有 `--progress=plain`，直接看 `docker build` 的 `Step N/M` 输出即可；
  想只看末尾报错：`DOCKER_BUILDKIT=0 docker build --no-cache -t mybooks-local:latest . 2>&1 | tail -50`。
- `--no-cache` 是**规定动作**，不是可选项：本机曾因缓存/上下文判重吃过「新旧 dist 混装」，
  交付与升级一律全量重建。

### 构建卡在 `Step N/M` 某一层很久
多半是在拉 `mybooks_base`（1.5GB）。看进度：另开一个窗口执行
`docker stats`，若网络流量在动就是在下载，耐心等；完全不动则是网络问题，配镜像加速。

### `Step 7/65 : RUN npm ci` 失败 / 卡住

**先分清是哪一类**，两类问题修法完全不同：

| 现象 | 原因 | 怎么办 |
|---|---|---|
| 几秒就报 `ERROR: npm registry 不可达` | NAS 出不了网、DNS 不通 | 见下面的排查命令 |
| 跑很久后 `ETIMEDOUT` / `ECONNRESET` / `socket hang up` | 网络慢或抖动 | 直接重跑一次；已内置自动重试一次 |
| `npm ERR! ` + `EUSAGE` / `lock file` 字样 | `package-lock.json` 与 `package.json` 不一致 | 源码包被改过，重新解压完整包 |

**v4.8.0 已加固**（如果你还在用旧包，先换成新的）：

- 构建开始先做一次 **15 秒连通性探测**，registry 不通就立刻失败并打印排查步骤，
  不会让你干等十几分钟
- `fetch-timeout` 设为 120 秒、重试 5 次；`npm ci` 失败还会自动用
  `--prefer-offline`（复用已下载缓存）再试一次

**自己排查（在 NAS 的 SSH 里执行）**：

```bash
# 1. NAS 本身能上网吗
curl -sI https://www.baidu.com | head -1

# 2. DNS 能解析 npm 镜像吗
nslookup registry.npmmirror.com

# 3. 镜像源本身通不通
curl -sI https://registry.npmmirror.com | head -1
```

1 通、3 不通 → 是 npm 镜像被拦，改用官方源试试：把 `docker-compose.yml` 里
`build.args` 的 `BUILD_COUNTRY: CN` 改成别的值（比如 `US`），或整行删掉。

1 就不通 → NAS 整体没网。检查群晖「控制面板 → 网络 → 常规」的网关/DNS，
或给 Docker 配代理（群晖：`/var/packages/Docker/etc/dockerd.json` 里加
`"proxies": {"http-proxy": "...", "https-proxy": "..."}`）。

**想定位到具体包**：legacy builder 不支持 `--progress`，用
`DOCKER_BUILDKIT=0 docker build --no-cache -t mybooks-local:latest . 2>&1 | tail -50`
看末尾报错。`--target production` 仍依赖 builder 阶段的产物，不是绕过前端的捷径。

```bash
DOCKER_BUILDKIT=0 docker build --no-cache -t mybooks-local:latest . 2>&1 | tail -50
```

### `COPY failed: no source files were specified`（myreader-dist）
已修复（v4.7.4）。`myreader-dist` 目录始终存在（内置 `.keep` 占位），`COPY myreader-dist/`
始终有源可拷，构建不会中断（v4.7.3 的通配符方案在 Docker 中零匹配仍会报错，已废弃）。

### `/readerx/open?...` 返回 `502 Bad Gateway`
nginx 连不上 9100 上的 MyReader 服务。根因通常是 `myreader-dist/` 是空的（只有 `.keep`），
或者产物里的 `node_modules` 被 `.dockerignore` 排除掉了。完整排查步骤见
[第八节](#八内嵌阅读器-myreader502-排查看这节)。

### 微信读书批注导入不可用 / `foliate-js` 子模块为空
`third-party/foliate-js` 是 git submodule，源码包里可能是空目录。构建时会打印
`WARN: foliate-js 子模块为空`，但不影响其他功能。需要该功能就执行：

```bash
git submodule update --init third-party/foliate-js
```

然后重新执行规定构建命令：

```bash
DOCKER_BUILDKIT=0 docker build --no-cache -t mybooks-local:latest .
docker compose up -d --force-recreate --no-build
```

### 访问不了 9800
- `docker compose ps` 看容器是否 Up；`docker compose logs mybooks | tail -50` 看日志。
- 端口被占用：改 docker-compose.yml 里 `"9800:80"` 左边的数字（9800 若被占用可换 9801 等）。

### Windows 提示「驱动器未共享」
Docker Desktop → Settings → Resources → File Sharing，把项目所在盘符勾上。

### NAS 上文件权限错误
把 PUID/PGID 改成自己的 ID 后 `--force-recreate`；或 `sudo chown -R 1000:1000 data/`。

### 读者组设置了但不生效
1. 确认管理员设置里**阅读范围限制总开关**已开启。
2. 确认用户已分配到组（组列表的「成员」列能看到用户名）。
3. 确认该用户自己没有设置过个人阅读范围（用户设置优先于组）。
4. 管理员本人不受限制，用普通用户账号验证。

### 转写面板显示「未安装」
镜像**默认已内置** `faster-whisper`（构建参数 `WITH_WHISPER=1`）。若显示未安装，通常是
当初构建时把参数关掉了。检查：

```bash
sudo docker exec audiobook-mybooks-1 python3 -c "import faster_whisper; print('OK', faster_whisper.__version__)"
```

有版本号输出说明装好了。若报 `ModuleNotFoundError`，把 `docker-compose.yml` 里的
`WITH_WHISPER: "1"` 确认无误后重新构建：

```bash
sudo env DOCKER_BUILDKIT=0 docker build --no-cache -t mybooks-local:latest .
sudo docker compose up -d --force-recreate --no-build
```

若报 `av 版本过高`，说明镜像里的 `av` 被升到 16+ 了（faster-whisper 不兼容），执行：

```bash
sudo docker exec audiobook-mybooks-1 pip install --break-system-packages "av<16"
```

### 转写很慢
正常现象，Whisper 在纯 CPU 上是重活。参考耗时（1 小时音频）：

| 模型 | Atom C2538（低端 NAS） | 普通 x86 四核 | 带 CUDA 的机器 |
|---|---|---|---|
| `tiny` | 约 1.5~2 小时 | 约 20~40 分钟 | 实时或更快 |
| `base` | 约 3~4 小时 | 约 1~1.5 小时 | 实时 |
| `small` | 不建议 | 约 2~3 小时 | 实时 |

提速办法：① 系统设置里把模型改成 `tiny`；② 只转短音频（单集、播客）；
③ **在 PC 上转好 `.srt`，拷到音频同目录同名，播放器会自动加载并逐句高亮**
（不用在本机跑 Whisper，这是低端 NAS 最实用的方案）。

模型缓存位置：`/data/models/whisper`（容器重建不丢）。首次转写自动下载：
`tiny` 75MB / `base` 145MB / `small` 484MB。下载源为 `hf-mirror.com`（国内可达）。

### 转写产出了什么文件
同目录下生成**两个**文件（与音频同名）：

| 文件 | 用途 |
|---|---|
| `书名.srt` | 带时间轴字幕。播放页的音频会自动配对同名 `.srt`，**播放时逐句高亮跟随** |
| `书名.txt` | 纯文本全稿。用于全文搜索、复制做笔记、手机离线阅读 |

只想保留字幕不要 `.txt`：转写面板上取消勾选「同时生成 .txt 文稿」，或在系统设置里关掉
`TRANSCRIBE_KEEP_TXT`。`.srt` 字幕始终生成——它是高亮跟随的唯一来源。

### 加了音频后书库里多出一条同名书

v4.8.0 已修复。若仍出现，检查两点：

1. 后台 → 系统设置 → 阅读与浏览 → 「同名电子书存在时，音频挂到该书而非新建」是否为开
2. 两条记录的书名是否**完全一致**（多一个空格、全角/半角括号不同都算不同书）

查看挂靠是否发生：

```bash
sudo docker logs audiobook-mybooks-1 2>&1 | grep AUDIO_IMPORT
```

出现 `同名书籍已存在(book_id=N)，音频将挂到该书而非新建` 即生效。
历史遗留的重复条目用后台「管理 → 重复书清理」一次合并，见[第七节](#七新功能三有声书挂靠到已有电子书)。

### 忘记管理员密码
```bash
docker exec -it mybooks python /var/www/mybooks/manage.py reset_admin_password 新密码
# 若无此脚本，可删库重建（会丢用户数据，慎用）：
# 停服后删除 data/books/settings/ 下的用户库文件，重启重新初始化
```

---

## 十三、排查命令速查表（实战积累）

本节是历次真实故障（502 三连、孤儿容器、端口冲突、符号链接压扁）的排查
命令汇总。**排查顺序从外到内：先看容器，再看进程，再看日志**。

### 1. 容器层：在不在、占没占端口

```bash
# 看全部容器状态 + 端口映射（最常用的一条）
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

看什么：
- 目标容器是 `Up` 还是 `Exited`（后者 `docker logs <容器名> --tail 50` 找原因）；
- 端口映射是不是预期的 `0.0.0.0:9800->80/tcp`；
- 是否出现**带哈希前缀的怪名字**（如 `57e4a67cf8a0_audiobook-mybooks-1`，
  项目列为 `-`）——这是 Compose 的孤儿容器：旧目录删了但容器还在，重建时
  为避免重名加的哈希。GUI 点开可能报「No such container」，用下面的命令
  按名字或 ID 清掉即可，**不要**因为看到一个名字里有 audiobook 就手抖删了
  正在运行的实例：

```bash
docker rm -f 57e4a67cf8a0_audiobook-mybooks-1      # 按名字删
docker rm -f <docker ps -a 里查到的 ID>             # 名字报不存在时按 ID 删
```

- **端口冲突**：`Exited` 且 `docker logs` 里有 `bind() to 0.0.0.0:xxx failed`，
  就是端口被占。查谁占了：

```bash
netstat -tlnp | grep 9800          # 看监听进程
docker ps --format '{{.Names}}\t{{.Ports}}' | grep 9800
```

### 2. 进程层：supervisor 管的四个服务

```bash
docker exec -it audiobook-mybooks-1 supervisorctl status
```

正常应四行全 RUNNING：

```
logrotate                        RUNNING
myreader                         RUNNING
nginx                            RUNNING
tornado                          RUNNING
```

三种异常对照：

| 显示 | 含义 | 下一步 |
|---|---|---|
| `myreader: ERROR (no such process)` | supervisor 配置里根本没有这个程序段（旧镜像），或新配置还没加载 | `docker restart <容器>` 重新加载配置；仍不行则镜像里 conf 是旧版，需重建 |
| `FATAL` / `EXITED` | 进程反复崩溃退出 | 看第 3 步日志，按报错对照表处理 |
| `unix:///var/run/supervisor.sock no such file` | supervisord 还没起来（启动脚本要先 syncdb 等）或起失败 | 等 30 秒重试；还不行 `docker logs <容器> --tail 50` 看启动脚本输出 |

手动干预进程（改配置后让 supervisor 重新加载，不用重启整个容器）：

```bash
docker exec -it audiobook-mybooks-1 supervisorctl reread    # 读新配置
docker exec -it audiobook-mybooks-1 supervisorctl update    # 应用变更
docker exec -it audiobook-mybooks-1 supervisorctl restart myreader
```

### 3. 日志层：MyReader 为什么崩

```bash
docker exec -it audiobook-mybooks-1 tail -50 /data/log/myreader.log
```

报错对照表（历史真实案例）：

| 日志特征 | 根因 | 修法 |
|---|---|---|
| `SyntaxError: Unexpected token '.'` + 路径指向 `app/node_modules/next` | 符号链接被解压工具压成文本文件（127 个 pnpm 链接全灭） | 删目录，**命令行** `tar -xzf` 重新解压 |
| `Cannot find module 'xxx'` | 产物依赖被裁掉（构建/传输环节丢文件） | 重新用完整 myreader-dist 覆盖，重建镜像 |
| `EADDRINUSE: 9100` | 容器内有残留 node 进程占端口 | `docker restart <容器>` |
| `Ready in 0ms` 反复出现 | 不是正常启动，是崩溃后被 supervisor 拉起的循环 | 属于上面三类之一，看完整日志找首次报错 |

**旁证检查**：产物里符号链接的实际数量（压扁后文件数会变多、链接数为 0）：

```bash
docker exec -it audiobook-mybooks-1 sh -c \
  "find /var/www/myreader -type l | wc -l; ls -la /var/www/myreader/app/node_modules/"
# 全部链接应为 127；app/node_modules 下应能看到 next/react/react-dom 三个 lrwxrwxrwx 链接
```

### 4. 服务层：nginx / 页面状态码

```bash
# 容器内直接测（绕过一切外层代理）
docker exec -it audiobook-mybooks-1 curl -s -o /dev/null -w '%{http_code}\n' \
  'http://127.0.0.1:9100/readerx/open?bookId=589&format=epub'
```

| 返回 | 结论 |
|---|---|
| 200 | MyReader 本身正常，问题在 nginx 或浏览器侧 |
| 502 | 9100 没人监听 → 回到第 2/3 步 |
| 000 连不上 | myreader 没起来或没监听回环 |

nginx 配置改过后先测语法再重载（**不要**直接 restart 容器）：

```bash
docker exec -it audiobook-mybooks-1 nginx -t
docker exec -it audiobook-mybooks-1 nginx -s reload
```

浏览器端二分定位：如果 `/read/589` 302 到 `/readerx/open` 正常但 502，说明
Tornado 正常、MyReader 挂了；如果 `/` 首页都打不开，先看 tornado 和 nginx。

### 5. 数据层：读者组分类回填

```bash
# 预览（不写数据），确认后加 --apply
docker exec -it audiobook-mybooks-1 python3 /var/www/mybooks/tools/category_backfill.py
docker exec -it audiobook-mybooks-1 python3 /var/www/mybooks/tools/category_backfill.py --apply
```

### 5.5 读者组是否被"隐形个人设置"架空

背景：用户级阅读范围（read_limit/limit_categories/limit_tags）永远优先于
读者组；而「默认权限与配额」的阅读范围在**注册时**会被复制进每个新用户的
个人字段。一旦种了值，这些用户划进任何读者组都不会生效。

只读检查（不改任何数据）：

```bash
docker exec -it audiobook-mybooks-1 python3 -c "
import sqlite3, json
db = sqlite3.connect('/data/books/calibre-webserver.db')
n = 0
for un, rl, cats, tags, extra in db.execute(
        'select username, read_limit, limit_categories, limit_tags, extra from readers'):
    has = (int(rl or 0) > 0) or (cats or '').strip() or (tags or '').strip()
    try:
        grp = (json.loads(extra) or {}).get('reader_group', '-')
    except Exception:
        grp = '-'
    if has:
        n += 1
        print(f'{un:20s} 组={grp:10s} 自身: limit={rl} cats={cats!r} tags={tags!r}')
print(f'共 {n} 个用户带个人设置（这些人组配置不生效）')
"
```

判读与处置：
- `共 0 个` → 读者组对全员生效，无需任何操作；
- 有列出的用户 → 在 admin/users.vue 把他的阅读范围改回"无限制"并清空
  分类/标签，即落回组配置；
- **预防**：「默认权限与配额」的阅读范围保持无限制，批量管控一律走读者组。

### 6. 通用心法

1. **先 `docker ps -a` 再猜**——一半的问题在状态列就露馅了；
2. **一层一层剥**：浏览器 502 → nginx 到 9100 不通 → supervisor FATAL → 日志 SyntaxError，
   每层只回答「这一层通不通」，不通就停在这一层查，不要跳到别的层改东西；
3. **改配置类操作**（nginx conf、supervisor conf）都在镜像里，容器内手改
   只是临时生效，`DOCKER_BUILDKIT=0 docker build --no-cache` + `up -d --no-build` 重建才是根治；
4. **写脚本要实测阈值**：deploy.sh 的符号链接检查就曾把「正确的 3 个」
   误判为异常（链接大头在根层 node_modules），任何自动检查先在好的环境
   上跑一遍校准再上线。

---

## 十四、音频批量转码（4.6.0-15）

**用途**：把书 `.audio/` 目录里的 mp3 批量转成 m4a（AAC）。转码时
`-map_metadata -1` 洗掉 mp3 内嵌的杂乱标签（老有声书的 ID3 artist 常是
播音员而不是作者，会让导入逻辑建错书），`-movflags +faststart` 让浏览器
秒开、拖动快。

### 位置

侧栏 **管理 → 音频转码**，或直接访问：

```
http://<你的地址>/toolbox/audio_transcode
```

仅管理员可见。

### 单本转码

1. 打开书详情页，看地址栏 `/book/215`，记下 **215**
2. 工具页输入 `215` → 点「**扫描单本**」→ 显示书名和 mp3 数量
3. 选码率 → 「开始转码」→ 确认
4. 页面实时显示进度与正在转的文件

### 批量转码

1. 点「**扫描全库（批量）**」→ 列出所有含 mp3 的书（已默认全选）
2. 取消勾选不想转的 → 选码率 → 「开始转码」
3. 按队列逐本处理，进度条显示「第 N/M 本」

> 没有 mp3 的书会被自动跳过（比如已经全转成 m4a 的书），不会卡住队列。

### 码率怎么选

| 码率 | 适用 |
|---|---|
| 64k | **有声书/播客（默认推荐）**，体积最小，语音听感无差别 |
| 96k | 有背景音乐的广播剧 |
| 128k | 音乐类、要求较高 |

### 安全行为

- **只有 m4a 成功生成后才会删除对应 mp3**；失败的 mp3 原样保留，
  并在结果区列出失败原因，修好后可重跑
- 已有同名 m4a 会被新转的覆盖
- 已经是 m4a 的文件不会出现在扫描结果里
- 同一时刻只允许一个转码任务，避免两个任务改同一目录
- 页面可以关掉，后台继续跑；重新打开工具页即可看进度

### 耗时参考

65 集、每集约 20 分钟的音频，64k AAC：NAS（网络盘读写）约 **15–30 分钟**。
转码是 CPU 密集的单线程 ffmpeg，NAS 弱的话会更慢，建议夜间跑。

### 转完怎么验证

回书详情页点「有声书」→ 直接进入 `/audio/<id>` 播放页 → 列表里应能看到
新生成的 m4a（文件名与 mp3 同名）→ 点播放确认能出声、能拖进度。

### 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 点扫描报「书籍不存在」 | ID 填错，或者这本书不在 calibre 库里 |
| 扫描结果 0 个 mp3 | 这本书已经全是 m4a，或本来就没音频 |
| 进度卡在某本书不动很久 | 该书文件特别大或网络盘读慢；看 `docker logs -f audiobook-mybooks-1` 里的 `[audio_transcode]` 行 |
| 某几个文件失败 | 结果区会列出具体原因（多半是源文件损坏）；原 mp3 保留，可单独处理后再重跑 |
| 想中途停止 | 当前版本不支持停止，只能等队列跑完（失败不会影响已有文件） |

---

## 附：本次移植内容一览

| 模块 | 文件 | 说明 |
|---|---|---|
| 读者组服务 | `webserver/services/reader_group.py` | 组定义/成员/生效规则 |
| 读者组 API | `webserver/handlers/reader_group.py` | `/api/admin/reader_groups*`（含 `options` 候选值） |
| 转写服务 | `webserver/services/transcribe.py` | faster-whisper/openai-whisper 双后端，输出 `.srt` + `.txt` |
| 转写 API | `webserver/handlers/transcribe.py` | `run/status/cancel/available` |
| 有声书挂靠 | `webserver/services/audios_import.py` | 同名电子书存在时复用 book_id，不再新建重复书 |
| 重复书清理 | `webserver/services/book_dedup.py`、`handlers/book_dedup.py`、`pages/toolbox/book_dedup.vue` | 已产生的重复记录一次性合并：搬音频、迁数据、删冗余、自动备份 |
| TTS 朗读 | `webserver/handlers/tts.py` | edge-tts，含词级高亮数据 |
| 权限接线 | `handlers/base.py` | 书籍可见性接入读者组生效规则 |
| 前端组件 | `app/src/components/ReaderGroupEditor.vue`、`TranscribePanel.vue`、`ServerFileBrowser.vue` | 设置页管理界面、目录浏览选音频 |
| 前端集成 | `app/src/pages/admin/settings.vue`、`locales/*.json` | 分节注册与中英文案 |
| 内置依赖 | `third-party/{foliate-js,edge-tts}`、`prebuilt/wheels/` | 已 vendored，不再依赖 git submodule |
| 移除 exe | `installer/` 已删除 | Docker 唯一部署方式 |
| 测试 | `tests/test_reader_group.py`（14）、`tests/test_transcribe_service.py`（24）、`tests/test_audio_link_existing.py`（17）、`tests/test_book_dedup.py`（43） | 98 个全通过（用例在源码仓库，部署包不含 `tests/`） |
| 上游跟进 | [`docs/上游跟进清单.md`](docs/上游跟进清单.md) | **改动清单 + 合并指引，升级前必看** |
