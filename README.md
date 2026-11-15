# MyBooks · audiobook 定制版

基于 [PoxenStudio/mybooks](https://github.com/PoxenStudio/mybooks) 的私人图书 / 有声书服务器定制版。
在 Calibre 书库之上提供 Web 阅读、听书、权限分级、元数据刮削、格式转换等能力。

> **当前镜像：`ghcr.io/wxgoo/audiobooks:4.6.0-build.28-r42`**（Public，匿名可拉）
> 装完即最新：镜像内含 r42 全部代码与 r42 发布清单，`/admin/version` 基线就是 r42。

> **仓库**：Gitee [`wxgoo/audiobook-src`](https://gitee.com/wxgoo/audiobook-src) 是**主仓库**，
> GitHub [`wxgoo/audiobook-src`](https://github.com/wxgoo/audiobook-src) 是自动镜像（每半小时单向同步 `master` 与标签）。
> 请只往 Gitee 推代码；在线热更清单 `update/manifest.json` 的 raw 源也以 Gitee 为准。

---

## 安装（只有一种方式：拉镜像就跑）

和上游一致：**成品镜像 + 只有 `image:` 的 compose**。不构建、不 clone、不传大包。
老 NAS 上 `layer does not exist`（legacy builder + btrfs）因此根本不会出现。

### 需要哪些文件

| 文件 | 干什么用 | 必须吗 |
| --- | --- | --- |
| `docker-compose.yml` | 启动配置：用什么镜像、数据挂哪、端口开多少 | 是 |
| `.env.example` | 启动配置模板，改完改名成 `.env` | 是 |
| 镜像 | 程序本体。**GitHub 上直接拉，或用离线包 `docker load` 导入** | 是（来源二选一） |

> **`docker load` 只装镜像，不启动任何东西。** 启动永远要靠上面那两个配置文件。
> 所以不管走哪条路线，`docker-compose.yml` 和 `.env.example` 都要跟着一起拿走
> （离线包里就有，一起传过去即可）。

### 路线 A：从 GitHub 拉（推荐）

```sh
cp .env.example .env
vi .env                     # 只改 DATA_DIR / PUID / PGID
docker compose up -d
```

`docker compose up -d` 会自动从 GitHub Container Registry 拉取镜像，公开包匿名可拉，
不需要登录或令牌。浏览器打开 `http://<机器IP>:9800`。**首次启动要初始化数据库，
1~3 分钟内 502 / 空白是正常的**（`docker logs -f mybooks` 看进度）。

### 路线 B：离线导入（连不上 ghcr.io 时）

第 1 步导入镜像。`gunzip -c ... | docker load` 是「解压 + 导入」一步做完，
别先 `gunzip` 出 2.4GB 中间文件白占磁盘：

```sh
gunzip -c mybooks-image-4.6.0-build.28-r42.tar.gz | docker load
```

第 2 步**照常**改 `.env`（这一步不能省），第 3 步照常 `docker compose up -d`：

```sh
cp .env.example .env
vi .env
docker compose up -d
```

包里已带好 `ghcr.io/wxgoo/audiobooks:4.6.0-build.28-r42` 与 `latest` 两个标签，
**不用再 `docker tag`**；本地有同名 tag，Docker 就不再联网拉，
compose 和 `.env` **一个字都不用改**（还是写着那个 GHCR 名字，但走的是本地镜像）。

### `.env` 只改三项

| 项 | 填什么 |
| --- | --- |
| `DATA_DIR` | 数据目录的**绝对路径**，空目录即可；不能是程序目录本身 |
| `PUID` / `PGID` | SSH 里 `id 你的用户名` 查到的 uid/gid；填错会「上传不了书 / 设置存不下 / 封面不显示」 |
| `IMAGE_TAG` | **别动**，已是 `ghcr.io/wxgoo/audiobooks:4.6.0-build.28-r42` |

端口冲突改 `HTTP_PORT`（默认 9800）；不需要 HTTPS 就删掉 compose 里 8443 那行。

### 没有 `docker compose` 命令时

老版本群晖 DSM、部分精简 Linux、只装了 Docker CLI 的机器上，`docker compose` 会报
`command not found`。这时用等价的 `docker run`，**不需要 compose，也不需要 `.env`**——
参数一行行写在命令行上：

```sh
docker run -d --name mybooks --restart always \
  --security-opt seccomp:unconfined \
  -v /你的/数据目录:/data -p 9800:80 -p 8443:443 \
  -e PUID=$(id -u) -e PGID=$(id -g) -e TZ=Asia/Shanghai \
  ghcr.io/wxgoo/audiobooks:4.6.0-build.28-r42
```

参数与 compose 一一对应：`-v ...:/data` ↔ `volumes`、`-p` ↔ `ports`、`-e` ↔ `environment`。

> `docker run` 和 `docker compose` **不要混用**：同一台机器上若已用 compose 起了容器，
> 再用 `docker run` 会因容器名 `mybooks` 重复而失败。先 `docker compose down` 再换方式。
### 装完必做

1. **改管理员默认密码**（初始化会建默认账号，不改等于把站敞开）。
2. 进「设置 → 基本」改站点名称与对外地址。
3. 上传 / 导入第一本书，确认能读、能听。

---

## 数据在哪、怎么备份

**所有东西都在 `DATA_DIR` 一个目录**（容器内 `/data`）：书库、每本书的 `.audio/`、
数据库（账号 / 进度 / 书架）、设置、日志、SSL 证书。备份 = 打包这一个目录；
换机器 = 搬它 + 用同一个镜像 tag 启动。删容器、重建容器都不伤数据。

```sh
docker compose stop
tar -czf mybooks-data-$(date +%F).tar.gz -C "$DATA_DIR" .
docker compose start
```

热备（不停服）需要数据库一致性处理，别直接 tar 正在写的 sqlite。

---

## 升级

| 情况 | 做法 |
| --- | --- |
| 日常小改动（含前端） | 管理 → 版本与更新 → **立即更新**，然后 Ctrl+Shift+R 强刷。不用重发大包 |
| 页内热更之后 | 改的是容器可写层，**别 `--force-recreate` / 别重建容器**，否则热更会被冲掉 |
| 换正式大版本 | 把 `.env` 的 `IMAGE_TAG` 换成新 tag，`docker compose up -d`。数据目录不动 |

---

## 主要功能

- **Web 阅读与听书**：EPUB / PDF / TXT / DOCX 等在线阅读，有声书章节播放，内嵌 MyReader 阅读器。
- **有声书管理**：自动导入、章节替换 / 删除单集 / 上传新章节；上传时可「插入为第 N 集」，删哪集补哪集，不改文件名。
- **读者组分级权限**：按分组限制可读范围与功能，17 套预置模板。
- **实体书（类型互转）**：可把选中图书在电子书 ⇄ 实体书之间互转。入口在管理 → 图书管理 → 选中若干本书 → 工具栏橙色「图书类型互转」按钮（实体书功能需开启）。转换规则：无 ISBN 或已有电子书格式的文件默认跳过；若希望不做这些检查直接转，在设置里打开「允许直接转换类型」。
- **音频转写文稿**：Whisper 转写（模型首次联网下载，离线环境用不了）。
- **元数据刮削与归一化**：豆瓣 V2 / 百科 / NeoDB 等多源，作者名归一化、重复书清理。
- **友情链接**：管理员在设置里配置，前台侧边栏对**所有用户**一致显示（独立开关 `ENABLE_FRIEND_LINKS`，默认开）。
- **OPDS / WebDAV / 书单 / 站内留言 / AI**：均可在设置中按需开启。

---

## 和上游的区别

在干净的通用图书服务器之上，做了四类工作：

| 类别 | 内容 |
|---|---|
| **功能移植** | 读者组分级权限、音频转写（Whisper）、TTS 朗读（edge-tts）、微信读书批注导入、有声书章节管理 |
| **修上游 bug** | 有声书重复入库、权限判定散落、同名书误合并、epub 坏字体拖慢打开、阅读统计写库失败 |
| **大量打磨** | 刮削源补清洗、作者名归一化、弱网缓存策略、中文文件名容错 |
| **运维口径** | 成品镜像 + 纯 `image:` compose，与上游安装方式一致；Gitee 主仓库 + GitHub 镜像；页内热更 |

相对上游的**逐条改动、原因与排障记录**统一见 [`CHANGELOG.md`](CHANGELOG.md)（历史变革）。

---

## 项目结构

```
audiobook-src/
├── webserver/          Python / Tornado 后端，架在 Calibre 库之上
│   ├── handlers/       HTTP 接口（书籍、音频、阅读器、播客、WebDAV…）
│   ├── services/       业务逻辑（转换、刮削、去重、自动导入…）
│   ├── base/           基础设施（格式化、元数据、侧边栏归一化…）
│   └── plugins/        元数据刮削源
├── app/                Vue 2 + Nuxt + Vuetify 前端（编译为 SPA，产物在 app/dist）
├── myreader-dist/      内嵌阅读器 MyReader 构建产物
├── conf/ docker/       镜像入口与 nginx / supervisor 配置模板
├── tools/ third-party/ 独立工具与 vendored 依赖
├── update/             在线热更清单 manifest.json
├── scripts/            打包与版本校验脚本
└── tests/              后端单元测试
```

**铁律：源码和数据永远分开。** 数据只在 `DATA_DIR`（容器内 `/data`）。源码目录里一旦出现
`books/`、`data/`、`audios/`，就是挂载配错了。

---

## 开发

```sh
# 后端
pip3 install -r requirements.txt && python3 server.py     # 默认 :8083

# 前端（另开终端）
cd app && npm ci && npm run dev                            # 默认 :3000，代理到后端

# 检查
pytest tests/                          # 后端测试
cd app && npm run lint                 # 前端 lint
```

前端改完**必须重新构建**，否则后端服务的还是旧的 `app/dist`：

```sh
cd app && npm run generate
```

版本号规则、发布流程、历史变更与排障记录统一在 [`CHANGELOG.md`](CHANGELOG.md)。

---

## 安全

安全问题请勿公开提交 issue，按 [`SECURITY.md`](SECURITY.md) 的方式报告。
