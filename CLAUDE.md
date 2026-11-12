# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

MyBooks (formerly Talebook) is a personal Calibre-based ebook management webserver. It's a monorepo with two main parts:

- `webserver/` — Python/Tornado backend, built on top of Calibre's library DB (and PyQt5, since Calibre depends on it)
- `app/` — Vue 2 frontend (Nuxt.js + Vuetify), compiled to a static SPA served by the backend

Other top-level directories: `tests/` (backend unit tests), `tools/` (standalone scripts: spiders, converters, metadata scrapers), `conf/` (nginx/supervisor config templates), `docker/` (image entrypoints and prebuilt library), `extensions/` and `third-party/epub.js` (git submodules), `webserver/epub_to_audio` (git submodule for EPUB→audiobook conversion).

## ⚠️ 生产部署必读（每次都看，踩过多次）

生产环境：群晖 NAS `RS2416P`，容器 `audiobook-mybooks-1`，代码在容器内 `/var/www/mybooks`（镜像内置，无源码挂载），数据在 `/volume1/docker/audiobook-data`。宿主机**没有 python3.12 / npm**，相关命令必须在容器内跑。

```bash
# supervisor 程序名必须带 mybooks: 组前缀（写 mybooks / tornado 都报 no such process）
docker exec audiobook-mybooks-1 supervisorctl restart mybooks:tornado
# 查全部状态时不要带程序名
docker exec audiobook-mybooks-1 supervisorctl status
```
程序名只有四个：`mybooks:tornado`、`mybooks:nginx`、`mybooks:logrotate`、`mybooks:myreader`。
**只改前端不需要重启** —— `_nuxt/*.js` 由 nginx 直接发，浏览器 Ctrl+Shift+R 即可。

```bash
# 前端热更不要用 docker cp src/. 目标/（容器里 dist/avatar 是文件，宿主是目录 → 类型冲突）
tar c -C /tmp/audiobook/app dist | docker exec -i audiobook-mybooks-1 tar x -C /var/www/mybooks/app
# 验证：列出新构建的哈希 chunk 才算成功
docker exec audiobook-mybooks-1 ls /var/www/mybooks/app/dist/_nuxt/ | grep <chunk前7位>
```

给用户的命令**一律单行、编号列出、一次一条**——NAS 终端粘贴多行会把 `\` 续行吃掉。

更多踩坑记录见 [`.claude/memory/MEMORY.md`](.claude/memory/MEMORY.md)（calibre `custom_columns` 没有 `colnum`、实体书双写、上传权限口径、上游分支陷阱等）。

## 代码地图（简版）

> 完整架构、路由顺序、常用命令、开发任务与踩坑清单以 [`docs/开发指南.md`](docs/开发指南.md) 为准，
> 本文件只留索引级信息，不重复维护。

- **入口**：`server.py` → `webserver.main.main()`；路由由 `webserver/handlers/*.py` 的 `routes()` 按固定顺序拼接，
  `static_files.routes()` 含 `r"/(.*)"` 必须最后。
- **请求**：`webserver/handlers/base.py` 的 `BaseHandler`（`@js` 统一异常/JSON、`db_lock` 串行化 Calibre 访问）；
  重业务放 `webserver/services/`。
- **配置**：`webserver/settings.py` 默认值 + `settings_path`（默认 `/data/books/settings/`）下的 `auto.py` / `manual.py`；
  统一读 `webserver.loader.get_settings()`（别名 `CONF`）。
- **数据**：Calibre 库（`legacy`/`cache`）+ 应用 SQLAlchemy 库（`webserver/models.py`，`user_database`），两库并存。
- **前端**：`app/src/**` → `app/dist/`（预构建进包，NAS 不构建）；`myreader-dist/` 是 Next.js standalone 阅读器。
- **i18n**：后端 `webserver/i18n.py`，前端 `app/locales/`。

### toolbox
Refer to [Toolbox Design](document/toolbox_design.md) for details to add new tool in MyBooks.

## metadata plugin
Refer to [Metadata Plugin](document/meta_plugins.md) for details to add new meta data plugin.

## 维护约定（硬约束）

以下三条是 r28→r29 复盘后定下的硬约束，动手改代码前先对照，违反任何一条都按回归处理。

1. **同步 IO 不进 ioloop。** 本项目是 Tornado 单进程单 IOLoop，`@js` 直接在主线程跑同步 handler，sqlite 查询、calibre 子进程、文件读写、jieba 分词等阻塞调用会卡住整个 loop，表现为页面偶发转圈；改法：这类调用放进 `run_in_threadpool` / `run_sqlite_async` 一类工作线程（历史案例：读者组接口卡顿）。
2. **任何会转圈的 await 必须有超时 + 可见错误出口。** 只给 loading 不给失败路径，用户只能一直等、也看不到原因；超时必须落到具体文案和可重试的出口（历史案例：`server_starting` / `modeText` / `this.alert` 那组三连）。
3. **Vue 2 里模板带参调用的方法只能留在 `methods`。** 挪到 computed / setup 会丢掉 `this` 绑定或拿不到参数，页面直接报错；`tests/test_reader_group_frontend_contract.py` 会拦住，改完先单独跑一遍。

## Code style

- Python: flake8-checked (config in `.style.yapf` and `.flake8`; `E501` line-length ignored), formatted with yapf using a Google-based style (`column_limit=240`). Pylint config disables several docstring/logging warnings.
- TypeScript/JS (frontend): see `.claude/rules/typescript.md` — never use `any`; strict mode; ES2022 target; `_`-prefixed unused vars allowed.
- UI/Vuetify (frontend): see `.claude/rules/ui.md` — shared dialog structure/colors and other cross-page UI conventions.
