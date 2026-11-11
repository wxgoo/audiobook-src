# 变更日志（CHANGELOG）

本项目的版本号规则：**`<上游 mybooks tag>-build.<自建构建号>`**，当前版本 **`4.6.0-build.27`**。
上游基线：mybooks tag `4.6.0`（2026-10-25，commit `3c5947c`）。
交付标签 / 包名与运行期版本同值：`4.6.0-build.27`（tag `4.6.0-build.27`，提交 `a5019c6`）。

> 更早的变更记录（`4.6.0-build.21` 及以前、旧编号时代）已精简归档，
> 完整历史见 git 提交记录（`git log`）。

---

## 4.6.0-build.27-r15（2026-11-11，可页内热更）

> 只动前端（`app/src/pages/admin/settings.vue` + 重建 `app/dist`），后端 `.py` 未改；
> 清单 `requires_dist=true` 且 `dist_hotfixable=true`，已在 r14 的实例可直接点「立即更新」
> （r14 之前的页面不认识 `dist_files`，需整包部署一次把后端换新）。

- **友情链接支持拖动排序**：条目一多，「上移 / 下移」要点十几次。现在每行左侧多一个拖拽把手
  （`mdi-drag-vertical`），按住拖到目标位置即可，落点处显示半透明占位行；触屏上长按 120ms
  才起拖，避免滑动页面时误改顺序；上下箭头保留，用于 ±1 的精调。首列宽度 1→2，链接列
  6→5，总宽仍是 12 栅格。
- **拖拽的稳定 key 不能写进配置**：`v-for` 原来用下标当 key，拖动后 Vue 按下标复用元素，
  输入框里正在编辑的文字会「跟着」跑到别的行。改为每条挂一个自增 `_uid`，并用
  `Object.defineProperty` 定义成**非枚举**属性——`Object.assign` / `JSON.stringify` 都看不见它，
  保存时不会被写进 `auto.py`，也不影响「未保存修改」的 JSON 比对。
- **`moveFriend` 改回原地挪动**：上一节那条用 `slice` + `$set` 整体替换数组，绕开了「Vue 2
  侦测不到下标赋值」，但拖拽组件的 `:list` 绑的就是这个数组引用，换成新数组会让它指向旧数据。
  改用 `splice` 摘出再插入：既触发响应式，又保持同一个数组引用。
- **新增 `addFriend()` / `removeFriend()`**：新增时顺带挂 `_uid`，删除走 `splice`。
- **验证**：无头 Chromium 里用克隆页面跑了完整回归（拖首行到末行 / 反拖 / 拖动后改写输入框 /
  上下按钮 / 删除 / 新增），顺序、`_uid`、输入框内容一一对应，无 JS 报错；
  `JSON.stringify(FRIENDS)` 输出里没有 `_uid`。

---

## 4.6.0-build.27-r13（2026-11-11，随包 `audiobook-deploy-4.6.0-build.27.tar.gz`）

**含前端产物**：设置页字段清理随 `app/dist` 下发（`requires_dist=true`），已热更到
r12 的实例也不能页内点更新，需随包或 `git pull && docker compose up -d --build` 重新部署。

- **douban v1 尸体彻底清除**：r12 只做了「注销」，插件本体还留在树里。本条删除
  `webserver/plugins/meta/douban/`（3 文件）、`tests/test_douban.py`、
  `webserver/test/test_douban_search.py`、`TestReferDouban` 类与 `tests/run.py` 引用。
- **修正 r12 误删 `douban_max_count`**：豆瓣V2 的每源返回条数也在读这个键
  （`douban_v2/plugin.py`），删掉后 v2 丢配置入口；现恢复进默认值与保存白名单，
  界面文案去掉「插件」二字（「豆瓣查询结果数量」）。
- **公共函数迁移**：`str2date` / `has_proper_book` 迁至 `webserver/base/meta_helper.py`，
  `baike` / `handlers/book.py` / `ai_fillinfo` 改引公共层——这是删插件目录的前提。
- **前端源码清理**：设置页删 `douban_baseurl` / `douban_apikey` 两个字段与「豆瓣插件」
  说明条；搜索索引 mapping 三语区共约 20 处引用清理；`app/dist` 已重建。
- **三语 locale**：各删 `douban_baseurl` / `douban_api_key` / `douban_plugin_description` /
  `meta_source_douban` 4 键；`douban_max_count` 文案同步去「插件」。
- **文案与 i18n**：ISBN 查询失败提示去掉「配置插件地址」口径，中/英/繁同步。
- **文档**：《在线更新说明》补 8.10 节——rsync 拷贝目录报 "not a git repository" 的
  就地 `git init` + fetch + reset 处理（vDSM 排错现场补充）。

### 当日收尾修复（部署后暴露的五个坑）

- **前端 chunk 全线 404（事故根因）**：`app/.gitignore` 里有**两条**模板自带的 dist 忽略规则
  （Node 模板 `/dist` + Nuxt 模板 `dist`），`app/dist/_nuxt/*.js` 从未入库。仓库里的 dist
  是「有页面、没 JS」的残骸，NAS 走 `git reset --hard` + 重建镜像拿到的就是这套，
  浏览器所有 `_nuxt/*.js`、`css/*.css` 一律 404，怎么重建镜像、怎么强刷都没用。
  已删除两条规则并留注释防复发，dist 完整入库。
- **dist 改用 r13 源码重建**：补回 js 后的 dist 仍是早期构建产物，缺 `admin/version`
  （左侧树「版本与更新」入口）、`toolbox/author_tools`（作者归一 / 清理合并页）、友情链接设置。
  现以当前源码 `nuxt generate --spa` 重建：**757 文件 / 142 个 js chunk**，入口资源
  `06f853b.js / 14efd0e.js / 9d0d704.js / a262561.js`，引用全量自洽。
- **读者组分组规则重建后丢失**：`READER_GROUPS` 曾不在 `PERSISTABLE_KEYS`，而 `dumpfile()`
  是**整份覆盖** `auto.py`——设置页任意一次保存都会把分组规则静默抹掉。已补进白名单，
  并在 `tests/test_setting_saver.py` 加两条断言（键在白名单 + 保存无关键后值不变），已做反向验证。
- **`scripts/pack.sh` 验包必崩**：shebang 是 `sh` 却用了 `set -o pipefail`（bash 专有），
  第 4 步 `sh` 自调用做验包必报 `Illegal option -o pipefail`，md5 打不出来。已改 `#!/usr/bin/env bash`。
- **文档同步**：本文件、《部署包说明》（当前包名 / md5 / dist 自检）、《在线更新说明》8.11
  （chunk 404 排查）、《开发指南》踩坑 9~11、`.claude/memory/MEMORY.md` ②b 与 ⑨。

### 同日追加（r13 包内更新，未升修订号）

- **分类页每个分类带图标**：分类是 calibre 自定义列的纯文本，本身没有图标来源。
  新增 `webserver/base/category_icons.py`，用「关键词 → 图标」规则表映射常见命名
  （演播 / 有声 / 电台 → `mdi-radio-tower`，科幻 → 火箭，文学 → 摊开的书，历史 → 古典建筑……），
  未命中的按分类名 crc32 从备选池稳定取一个（同名不跳变、不同分类不撞脸）。
  `/api/categories` 每项多返回 `icon` / `color`，前端 `pages/categories.vue` 在 tab 名前渲染图标，
  选中态转白适配深蓝底。`tests/test_category_icons.py` 8 条断言锁住规则优先级与兜底稳定性。
- **友情链接上下移动修好**：`moveFriend` 原来用「按下标原地交换」，Vue 2 侦测不到下标赋值，
  点了没反应（保存后顺序也不变）。改为 `slice` 新数组 + `$set` 整体替换。
- **新增 `scripts/hot-update.sh`（热更新，不重建镜像）**：只改了 `app/src`（已出 dist）或
  `webserver/` 下 `.py` 时，用它覆盖运行中容器的 dist 与代码、`compileall` 预检、
  `supervisorctl restart tornado`（nginx 不动），默认把旧文件备份到
  `../audiobook-hotfix-backup/`。用法与回滚见《在线更新说明》8.12。
- **打包脚本清垃圾**：`app/build.sh` 的 `.build-trash` 归档目录与 `app/.nuxt` 构建缓存
  会被当成工作区文件打进部署包（上一版包 246M，多出 4.4 万条无用户）。`pack.sh` 跳过
  `.build-trash`、暂存后删 `app/.nuxt`，验包阶段对这两项直接报错防复发。
- **「版本与更新」页现在也能在线更新前端产物**：以前只要本次含 `app/dist` 变更，
  `requires_dist=true` 就一律只给「请重新部署」指引——因为旧逻辑只替换
  `webserver/**/*.py`，硬更会出现「新 py + 旧 dist」的半新半旧。现在发布清单额外给出
  `dist_hotfixable` / `dist_files`（逐文件 sha256）/ `dist_deleted`，
  后端放开 `app/dist/**` 静态文件（后缀白名单、拒绝 `..` 与绝对路径），
  全部下载校验通过才动线上，`index.html` 最后替换（中途失败也不会白屏），
  删除项走备份可回滚；超过 200 个文件 / 20MB（整包重建）仍退回重新部署。
  `requires_dist` 语义保持不变，老版本页面照旧只显示部署指引，不会半更。
  页面会显示前端产物数量与体积，并提示更新后 `Ctrl+Shift+R`。

---

## 4.6.0-build.27-r12（2026-11-10，未随包，可页内热更）

- **检索索引（FTS5）修复（重点）**：`search_index._fill_index` 引用了 calibre
  books 表**不存在的** `b.publisher` / `b.series`（真实结构走
  `books_publishers_link` / `books_series_link` 链接表），索引自 build.20 引入起
  重建从未成功（syslog 反复报 no such column），中文检索一直静默回退原生检索。
  现按链接表聚合出版社/丛书；评论聚合后按 book 去重——FTS5 对重复 rowid 的
  INSERT 直接 constraint failed，多评论行的老库会炸掉整个重建（已实测钉住）。
  升级后后台 5 分钟内自动重建成功，中文 / 出版社 / 丛书均可检索。
- **刮削超时收敛**：calibre 插件 ISBN 查询 timeout 60→8s；`book_search` 外层
  `future.result` 60→15s。8 源全开的最坏情况从 60s 降到 15s 左右。
- **douban-rs-api 无效默认值去除**：单容器/vDSM 部署没有该伴生容器，默认地址
  永远无效；未配置插件地址时 douban 源直接跳过。已取消勾选无效源的实例不受影响。
- **douban v1 源连同配置全量下线**：`DoubanMetaPlugin` 从聚合搜索与 provider
  路由注销，`douban_apikey` / `douban_baseurl` / `douban_max_count` 三键从默认值
  与两份白名单移除，admin 校验块删除，设置页字段清理（下一版随 dist 下发）。
  ISBN 兜底链改为 douban_v2 → xhsd 两级。v2 直连源不受影响。
- `gen-update-manifest.py` 分类修正：`tests/**` 与维护者侧工具自身的改动归为
  非阻塞（原来一个测试文件就会把纯后端修订顶成「必须重新部署」）。

---

## 4.6.0-build.27-r11（当前包修订）

> 主题：**电台实时流断流修复 + Dockerfile 镜像源修正**。`MiniPlayer.vue` 改为出错自动恢复/重连，
> 不再每十几秒规律暂停；`Dockerfile` 中 node 基础镜像源由 `docker.1ms.run` 改为直连 `node:20-alpine`，
> 规避代理源间歇性 503。改动含前端源码与构建文件，需重建镜像（`docker compose up -d --build`），
> 不可仅热更。运行期版本仍是 `4.6.0-build.27`。

### 变更

1. **电台流出错自动恢复**（`app/src/components/MiniPlayer.vue`）：hls.js 致命错误由「直接暂停」改为
   按错误类型自愈——网络错误 `startLoad()`、媒体错误 `recoverMediaError()`，其余才暂停；原生
   `<audio>` 出错时自动在 2 秒后重连同一源，避免直播流规律断流。
2. **Dockerfile 镜像源修正**（`Dockerfile` / `delivery/overlay/files/Dockerfile`）：`node` 基础镜像由
   `docker.1ms.run/library/node:20-alpine` 改为直连 `node:20-alpine`（`poxenstudio/mybooks_base`、
   `ubuntu` 仍走原源），规避该代理源偶发 503 导致构建失败。
3. **部署影响**：改动涉及前端源码与 Dockerfile，必须重建镜像后生效（`docker compose up -d --build`），
   不能仅替换 .py 热更；修复脚本 `apply_radio_fix.py` 一并入库，便于换环境复用。

---

## 4.6.0-build.27-r10

> 主题：**扩展在线阅读支持的图书格式 + docx 改走 EPUB**。入库白名单从 11 种扩到
> 24 种；`docx` 不再转 PDF，改为转 EPUB 流式阅读（可重排、可全文搜索）；新增
> `lit / pdb / prc / rb / snb / tcr / lrf / rtf / odt / html / htm / azw1 / tpz`
> 等 Calibre 原生可转换格式，打开时自动转 EPUB 后读。仅改后端 Python，**`app/dist`
> 未动**，无需重建前端。运行期版本仍是 `4.6.0-build.27`。详见
> [`docs/支持的图书格式.md`](docs/支持的图书格式.md)。

### 变更

1. **`docx` 改转 EPUB**（`webserver/handlers/book.py` 的 `BookRead`）：旧逻辑是打开只有
   `docx` 的书时自动转 PDF 后用 PDF 阅读器打开（分页扫描式、不可重排/搜索）；现与
   `mobi`/`azw3` 一致，统一转 **EPUB** 后交由流式阅读器打开。若书本身已带 `epub` 直接读
   epub；若同时有 `docx` 和 `pdf`，现在优先转 `docx → epub`（而非读 PDF）。
2. **格式白名单扩展**（`webserver/constants.py`）：`SUPPORTED_EBOOK_FORMATS` 新增
   `lit / pdb / prc / rb / snb / tcr / lrf / rtf / odt / html / htm / azw1 / tpz`，
   新增 `EPUB_CONVERTIBLE_FORMATS` 明确哪些源格式需自动转 EPUB 才能读（排除已有原生
   阅读器的 `epub/pdf/fb2/cbz/djvu` 与专用阅读器的 `txt`）。`ACCEPTED_BOOK_FORMATS` 由
   11 种变为 24 种。
3. **阅读选择逻辑统一**：`BookRead.get` 的「指定格式」分支与「自动选择」循环都改用
   `EPUB_CONVERTIBLE_FORMATS` 决定转 EPUB 阅读；`_epub_conversion_source` 同步覆盖新格式，
   使 `/book/<id>/read` 的 POST 检测能正确触发/判定转换。
4. **配套列表同步**：`reading_stats_service.FORMAT_PREFERENCE_ORDER`、
   `batch_convert.supported_formats` 加入新格式；`converter.py` 注释由 `docx→pdf` 更正为
   `docx→epub`。
5. **边界**：所有自动转换依赖系统已安装 Calibre（`ebook-convert`），未安装或转换失败仍提示
   「暂不支持，请转 EPUB 或 PDF 后阅读」；`uvz` 仅入库不可读、`fb2`/`cbz` 仅 MyReader 阅读器
   原生支持，行为与此前一致，未改动。

---

## 4.6.0-build.27-r9（当前包修订）

> 主题：**读者组目录树计数口径统一**。分组成员登录后，点开「目录」看到的各级
> `(N)` 现在按「他真正读得到的书」重算，不再显示全库规模（与书籍列表同源判定）。
> 仅改后端 Python（`folder_helper.py` + `folder.py`），**`app/dist` 未动、指纹与 r8 一致**，
> 无需重建前端。运行期版本仍是 `4.6.0-build.27`。

### 变更

1. **根因**：`/api/folders`（目录树）一直用全库 `folder_counts()` 逐路径数书，
   而点进目录的书籍列表走 `is_book_visible()` 按读者组过滤——两条链路口径不同，
   于是出现「目录显示 科幻 7 本，点进去只有 3 本可读」。左侧树 `sys.folders`、
   `/categories`、标签云在 r6 已改走 `scoped_counts`，**唯独目录树漏了**。
2. **修复**：新增 `folder_helper.folder_counts_for(cache, visible_ids)`，按可见书集合
   重算逐路径计数（与 `folder_counts` 同口径，按完整路径逐本计数）；`FolderList.get`
   对受限制用户改为取 `scoped_counts(key)["book_ids"]`（与书籍列表同源的判定结果）
   来算计数，`root_count` 也基于可见总数。计数为 0 的目录在 `build_tree` 里被自动丢弃，
   不会出现「读不到却还列在那儿」的空目录。管理员 / 游客 / 未受限用户走原有全库快路。
3. **边界**：`scoped_counts` 聚合异常时降级回全库口径（与 r6 一致），不会让
   `/api/folders` 返回 500；`FolderCandidates`（管理员专属的目录改名候选）保持全库行为不变。

---

## 4.6.0-build.27-r8（当前包修订）

> 主题：**版权下架（书籍停止阅读 / 下载）**。应版权人要求下架的书不删除、不隐藏书目，
> 后端在所有内容出口硬拦，前端在详情页 / 分享页 / WAP 显示版权声明并引导购买正版。
> 本次新增 `/admin/takedowns` 管理页并重建了 `app/dist`，**必须完整部署一次**。

### 变更

1. **标记与留痕**：新增 `book_takedowns` 表（本站 SQLAlchemy 库，`book_id` 主键 +
   书名快照 / 下架原因 / 操作人 / 时间），纳入 `ensure_new_tables()` 幂等补建，
   **零手写迁移**；不动 Calibre `metadata.db`，不删任何书与文件。下架记录用于日后
   应对版权方核查，原因只给管理员看。
2. **统一硬拦截**：`webserver/services/book_takedown.py` + `BaseHandler.prepare()`
   的路径门禁，覆盖下载直链、阅读页、epub 正文分片、TXT 正文、MyReader 文件路径、
   格式转换、邮件 / 设备推送、音频、OPDS 直链。判定发生在设 `X-Accel-Redirect`
   **之前**，nginx `"/_lib/"` 直出也绕不过；MyReader 必须经 `/api/book/<id>/filepath`
   拿物理路径，因此同样被挡。刻意不拦详情页、封面 / 缩略图、编辑与管理接口——
   书目还在，读者需要看到声明。
3. **旁路补齐**：OPDS / WebDAV 目录剔除下架书，WebDAV `get_content()` 再兜一层；
   MCP `download_book`（book_id 在请求体里，路径门禁看不到）显式拦截；
   分享链接 `_payload` 不再下发文件与 `book_id`，并强制 `allow_read/allow_download=false`。
4. **拒绝响应分流**：下载直链 / 阅读页 / 正文分片 / OPDS → **403 + 自包含 HTML 版权声明页**
   （200 JSON 会被 aria2 / IDM / epub.js 当成资源解析成功、存成假书）；
   其余 `/api/*` → 200 + `err=book.copyright_takedown` + 声明文案，前端弹提示。
   默认文案「因版权人要求，已下架处理，请购买正版图书支持原作者！」，
   可由 `CONF["COPYRIGHT_TAKEDOWN_NOTICE"]` 覆盖，输出一律 `html.escape`。
5. **前端**：详情页顶部显示版权声明卡片；阅读 / 下载 / 推送 / 分享按钮改为
   **点了弹声明**，不是静默置灰；管理员在「管理」菜单里可单本下架 / 恢复；
   新增 `/admin/takedowns` 列表页（批量恢复、按 book_id 新增、声明文案预览），
   左侧管理树直达。分享页与 WAP 老设备页同步显示声明，不再给下载直链。
   三语 locale 补齐 `book.copyright*`、`book.takedown*`、`takedown.*`、
   `appHeader.copyrightTakedown`。
6. **管理接口**：`GET /api/admin/takedown/list`、`POST .../set`、`POST .../remove`，
   均仅管理员，支持 `book_id` 单本与 `book_ids` 批量（上限 200），写操作同步刷新缓存，
   下架 / 恢复**立即生效、无需重启**。
7. **文档**：新增 `docs/版权下架说明.md`；README / 部署包说明 / 本日志同步到 r8 口径。
8. **顺带修掉版本检测 `-r0` 误判**（用户装了 r7 却显示「已应用修订 `-r0`」、并提示重装）：
   根因是 `webserver/services/version_check.py` 的 `CODE_ROOT` 少算一级，指向
   `/var/www` 而非 `/var/www/mybooks`，读不到本地基线 `update/manifest.json` 被兜底成
   `-r0`，连带在线热更新也会把文件写到 `/var/www/`。修正为正确的项目根；`read_local_manifest`
   改为打日志而非静默返回空。`book_barn`（后台 8 小时检测）与 `admin.py`（版本弹窗）的
   基线判定同步加上「远端比本地旧则不算有更新」的同口径保护，避免发布清单回滚时倒灌提示。
   页内「复制命令」在非 `https` 下不再只弹「复制失败」，自动降级为「手动选中」提示。

> 本次 r8 含前端改动，发布清单 `requires_dist=true`、`hotfixable=false`，
> 页内「立即更新」会给出重新部署命令；运行期版本仍是 `4.6.0-build.27`。

---

## 4.6.0-build.27-r7（上一修订）

> 主题：**「版本与更新」独立成页 + 分级在线更新**。检测源由上游 mybooks.top 的
> release 接口改为本项目的 Gitee 发布清单；只改后端 Python 的修订支持点一下就更新，
> 含前端产物 / 镜像级文件的修订改为引导重新部署。
> 本次新增了 `/admin/version` 页面并拆了设置页分组，**`app/dist` 必须重建**。

### 变更

1. **入口拆分**：系统设置「系统与性能 → 更新与工具箱」拆成两块——
   「版本与更新」（独立页 `/admin/version`，左侧管理树直接进）和「工具箱」
   （只留开发者模式 / 商店两个开关）。`AUTO_CHECKING_NEW_VERSION` 开关搬到新页，
   语义改为「后台每 8 小时比对 Gitee 发布清单」，关闭不影响页内「立即检测」。
   设置页留一张指路卡片，搜索别名不再指向已移走的旧开关。
2. **检测**：新增 `webserver/services/version_check.py`，以 Gitee 公开仓库
   `wxgoo/audiobook-src` 的 `update/manifest.json` 为唯一发布源（raw 直链，
   无需 token / 无需容器内 git）。比对的是**修订号 `-rN`** 而不是 `VERSION`
   ——运行期版本固定 `4.6.0-build.27`，否则改了代码检测不到。
   包内同一份清单是本地基线，随 Dockerfile `COPY update/` 进镜像。
3. **一键在线更新**：`POST /api/admin/version/apply` 按清单逐个下载
   `server.py` / `webserver/**/*.py`，校验 sha256 + 字节数 + `compile()` 语法，
   先备份旧文件到持久化 `/data/update-backup/`，再原子替换、清 `__pycache__`、
   覆写本地清单，最后复用 `AdminRestartServer` 的 `sys.exit(0)` 让 supervisor 拉起新代码。
   白名单之外的路径、跨版本补丁、`requires_dist=true` 一律拒绝在线更新。
4. **需要 dist 的更新**：页面展示原因、涉及的产物文件与可直接复制的
   `sha256sum -c` → `down` → `tar -xzf` → `deploy.sh` 命令，不偷偷替换半个产物。
5. **回滚与防倒退**：Web 端一键回滚 + 宿主机 `docker cp` 命令；热更新同时把文件
   写到 `/data/update-sync/current/`，`deploy.sh` / `upgrade.sh` 在构建前调用
   `scripts/sync-hotfix.sh`，把数据卷里比包内更新的修订固化进源码目录，
   避免下次重建容器把热更新冲掉。
6. **旧链路下线**：`BookBarnClient.check_latest_release()` 不再请求上游 release
   （那条链路返回与本项目无关的号段、且只发「请重新构建容器」没有可执行动作），
   后台每日检测改走新服务，站内消息直接指向新页面；后台检测与页面同样加了
   `-rN` 倒退防护，远端清单比本地旧时不会误报升级。
7. **打包门禁**：`pack.sh` 校验 `update/manifest.json` 与 `scripts/sync-hotfix.sh`
   必须在包内；新增 `scripts/gen-update-manifest.py` 按 git diff 自动分类变更、
   生成带 sha256 的发布清单。
8. **弹窗与右上角提示全部换成 Gitee 口径**：右上角（与外观设置 / 退出平行）
   新增「新版本」角标按钮，由 `sys.upgrable` 驱动、仅管理员可见、直达 `/admin/version`；
   首页自动弹出的「版本变更」对话框与页脚版本号弹窗，内容由
   `AdminReleaseNotes` 改为依据 Gitee 发布清单动态生成（按 revision 去重、含直达链接），
   **不再读取上游 `release_notes.txt`**（那份写的是 mybooks v4.6.0 变更，与本地修订无关）；
   右上角消息弹窗里残留的旧「请重新构建容器以获取更新」站内消息，在展示层统一改写为
   Gitee 提示；`release_notes.txt` 只作兼容旧构建保留。
9. **文档统一**：`README.md` 里仍写着「必须用 legacy builder」的构建段改为
   BuildKit + `buildx` 探测回退，并指向 `deploy.sh` / `upgrade.sh`；
   `docs/部署包说明.md` 删掉 legacy 兜底命令与无关的上游号段描述；
   `docs/在线更新说明.md`、`CHANGELOG.md` 清理同类旧措辞；
   `INSTALL_GUIDE.md` 五处 legacy 构建命令改为脚本调用并在顶部加 r7 指向，
   `docs/操作总纲.md` / `docs/备份与恢复演练.md` 同步构建口径；
   NAS 运维手册《NAS Docker 缓存池重置与镜像备份恢复手册》纳入 `docs/` 并同步到 r7：
   构建口径、6G 内存现状、在线更新与固化区、文档索引一并更新。

> 本次 r7 自身含前端改动，**首次上线必须完整部署**；此后纯后端修订（r8 起）
> 才可用页内「立即更新」。详见 `docs/在线更新说明.md`。

---

## 4.6.0-build.27-r6（上一修订）

> 主题：**读者组分组权限的统计口径统一**——分组成员登录后，左侧树与分类页
> 里的数字按「他真正读得到的书」重算，不再显示全库规模。
> 运行期版本仍是 `4.6.0-build.27`；**`app/dist` 未改动，指纹与 r5 完全相同**。

### 变更

1. **根因**：`/api/user/info` 的 `sys.*` 统计来自 `_library_stats()` 的全库
   `count(distinct book)`，且按书库版本在类级缓存里被所有用户共享；分类页
   `/categories`、标签/作者/系列列表 `/api/meta/*` 的 `count` 同样出自全库 SQL。
   而书列表走 `is_book_visible()` 按读者组过滤——两条链路口径不同，
   于是出现「标签显示 328 本，点进去只有 12 本」。
2. **同源判定**：新增 `services/reader_group.book_matches_limits()`，
   `BaseHandler.is_book_in_reading_range()` 与所有统计共用这一份逻辑，
   杜绝口径再次漂移。40 组白名单/黑名单/空条件用例与旧判定逐项等价。
3. **可见口径聚合**：`BaseHandler.scoped_counts()` 一次性遍历书库，按当前
   生效限制筛出可见书籍，再聚合 `books/tags/authors/publishers/series/
   categories/folders/audiobooks/physicals` 及各维度逐项计数；按
   `(用户, 生效规则, 书库版本)` 缓存（TTL 120s）。管理员、游客、未受限用户
   一律走原来的全库快路，零额外开销。
4. **接入点**：`get_sys_info()` / `get_sys_info_async()`（左侧树 badge）、
   `/categories`、标签云 `all_tags_with_count*`、元数据列表
   `get_category_with_count*` 全部改用可见口径；计数为 0 的条目不再列出，
   个人口径不写类级 fallback 缓存，避免串给别的用户。
5. **顺手修**：`base._filter_tags()` 以前只读 `user.limit_tags`，绕过了
   读者组（`meta.py` 的 `MetaList` 早已改过，这里漏了），现统一走
   `effective_limits()`。
6. **边界**：首页「藏书规模」统计面板对受限用户仍保持关闭（既有设计），
   本次只把左侧树与列表页的数字改成真实可访问数；聚合异常时降级回全库
   口径，不会让 `/api/user/info` 返回 500。

---

## 4.6.0-build.27-r5（上一修订）

> 主题：**工具箱入口合并**——「作者归一化 + 作者清理」与「格式合并 + 格式精简」
> 各自合并为一个工具，入口全部留在工具箱；左侧管理树不再单列「作者归一化」。
> 运行期版本仍是 `4.6.0-build.27`；本修订**重建了 `app/dist`**。

### 变更

1. **工具箱**：`author_clean_tool.info()` 改名「作者归一 / 清理」、
   `merge_formats_tool.info()` 改名「格式合并 / 精简」，各自加 `page` 指向新增合并页；
   `formats_pruning` 不再单独注册工具卡——工具箱里这四块功能由 4 张卡收成 2 张卡。
   两个后端工具类与 `/api/toolbox/*` 接口全部保留，未做破坏性改动。
2. **合并页**：新增 `app/src/pages/toolbox/author_tools.vue` 与 `format_tools.vue`，
   各用两个 Tab 复用原页面；四个原页面新增 `embedded` prop，嵌入时隐藏独立页头。
   归一化页的「去清理」由跨页跳转改成切 Tab 事件，脏名候选每行新增「带入清理」，
   一键把作者名预填进清理表单，形成「体检 → 别名规则 → 落地改名」闭环。
3. **左侧树**：`AppHeader.vue` 管理员菜单删掉 `/toolbox/author_norm` 独立入口；
   设置页指路项改指 `/toolbox/author_tools`；`zh` / `en` / `zh-TW` 三份 locale
   同步更新旧文案、移除不再使用的 `appHeader.authorNorm`、新增 `authorTools`
   与 `formatTools` 两个命名空间。
4. **兼容与边界**：四个旧页面文件保留，旧链接直达时显示「已并入工具箱」提示与跳转按钮，
   不留死链；`webserver/base/author_norm.py` 归一化引擎保留——它服务于**新书入库清洗**
   与重复判定，与 UI 入口无关，不随本次合并删除。
5. **dist 重建**：本机构建环境补齐缺失的 `hls.js` 后重新执行 `nuxt generate --spa`，
   `app/dist/index.html` 指纹更新为部署包说明中的表格值。各脚本的指纹闸门是
   「包内 vs 镜像内」动态比对，脚本无需改动。

---

## 4.6.0-build.27-r4

> 主题：**MyReader 119 根符号链接清单化自愈**——解决「myreader 显示 Ready、打开书却 500」。
> 代码与 dist 与 build.27 完全相同，运行期版本仍是 `4.6.0-build.27`。

### 事故回顾（2026-11-09 现场）

现场全新部署后 `supervisorctl status` 显示 `mybooks:myreader FATAL`，日志为
`Cannot find module 'next/dist/server/lib/start-server'`；手工补链接后 myreader 变为
`RUNNING`、`✓ Ready in 0ms`，但浏览器打开 `/reader/open?bookid=…` 仍报
`Internal Server Error`。

根因不是 build.27 的代码，而是**产物落地环节**：`myreader-dist` 是 Next.js
standalone 产物，三层 `node_modules` 靠 **119 根相对符号链接**解析依赖。经 Windows
检出（`core.symlinks=false`）、File Station 上传或图形界面解压后，这些链接被压扁成
「内容=目标路径文本」的 0 字节文件 / 空目录：

- `.pnpm` 实体包完好，但顶层与每个 `.pnpm/*/node_modules` 的链接全丢 →
  `require('next')` 找不到 → 启动 FATAL；
- 只补了顶层后，`app/.next/node_modules` 那 24 根带哈希的链接
  （`clsx-531b805f92b6415e` 之类）仍缺失 → Next.js 看似 Ready，首个 SSR 请求就 500。

git 里这些链接的 mode 是 `120000`（仓库本身是对的），**但从 Windows 工作区直接
`pack.sh` 打包会重新压扁**，所以不能靠"重新检出"解决。

### 变更

1. **权威清单**：新增 `scripts/myreader-links.manifest`，从完好部署包导出的
   119 根「相对路径 → 链接目标」（`node_modules` 92 / `app/node_modules` 3 /
   `app/.next/node_modules` 24）。按包名推断不可行——链接名带哈希，且同名包在
   `.pnpm` 里有多版本（`@opentelemetry/api` 1.9.0 与 1.9.1 并存，next 用 1.9.1）。
2. **校验/重建脚本**：新增 `scripts/check-myreader-links.sh`（`--fix` 重建、
   默认只读校验），逐根比对清单，不猜版本；已验证清单 119 根目标在包内全部存在。
3. **部署链路自动自愈**：`deploy.sh` 的 [2/5]、`upgrade.sh` 新增的 [6.2/8]
   在**构建之前**调用 `--fix` 修复宿主机 `myreader-dist`（构建上下文状态会被原样
   COPY 进镜像，事后补容器没用）；`upgrade.sh` 显式调用新解压出来的脚本，
   避免重演「旧目录里的旧脚本跑完整场」。
4. **Dockerfile 构建期兜底**：`COPY myreader-dist/` 之后按清单再校验一次，
   手工 `docker compose build` 绕过部署脚本也能修好。
5. **出包堵源头**：`pack.sh` 打包前与 `--check` 验包时都跑清单校验，缺链接或
   目标不符一律拒收；缺清单/脚本也拒收。Windows 压扁的工作区会在此明确失败，
   提示须在 Linux 上重新检出或以完好包为底重打。
6. 保留 `scripts/fix-pnpm-links.sh` 作为「清单不在时的应急兜底」（按 `.pnpm`
   目录名 peer 后缀推断版本），正常部署不再依赖它。

### 不变

- 代码零改动：`app/dist/index.html` 指纹仍是 `56565065…`；
- 站点运行期版本仍是 `4.6.0-build.27`；-r2/-r3/-r4 都是包修订号。

---

## 4.6.0-build.27-r3（已被 -r4 取代）

> 主题：**构建口径全面切 BuildKit**——脚本与文档统一，代码与 dist 与 build.27 完全相同。

### 变更

1. **脚本弃用 legacy builder**：`deploy.sh` / `upgrade.sh` / `recover.sh` /
   `fix-build-layer.sh` / `check-deployed-version.sh` 的构建命令统一为
   `DOCKER_BUILDKIT=1 docker build --no-cache`（btrfs 上 legacy 每层一子卷，攒千级后
   触发 `layer does not exist` 事故，且已发 deprecation 警告）；`recover.sh` 三轮顺序
   改为「BuildKit 复用缓存 → 清碎片全量重建 → legacy 兜底」，其第二轮的
   `builder prune -af` 改为不带 `-a`。
2. **所有重建路径补内容指纹闸门**：`recover.sh` / `fix-build-layer.sh` /
   `check-deployed-version.sh` 构建后新增镜像内 `index.html` sha256 与包内比对
   （deploy/upgrade 原本就有）。恢复场景常是同一版本反复重建，只有版本门禁抓不到
   「dist 半新半旧」，内容指纹才能拦下上下文快照复用产出的坏镜像。
3. **文档口径统一**：`docs/部署包说明.md` 正文 7 处 legacy 写法全部改 BuildKit，
   「为什么不能用 docker compose build」改写为「为什么是 DOCKER_BUILDKIT=1 docker build」；
   历史 build.23 条目的部署口径标注已被本修订取代。

### 不变

- 代码零改动：`app/dist` 指纹与 build.27 相同（`56565065…`），运行期版本仍是
  `4.6.0-build.27`；-r2（纯文档定版）与 -r3（文档 + 脚本口径）都是包修订号。

---

## 4.6.0-build.27

> 主题：**有声书一集播完自动进下一集**，收起成迷你条之后同样生效；迷你条补上「上一首 / 下一首」。
> 起因是现场反馈：点最小化收起后听完一集就停住，得重新点开播放页才会继续；
> 而播放页里 `onTrackEnded → nextTrack(true)` 一直是好的 —— 差别在于**收起后播放页已销毁**，
> 只剩迷你条的 `onEnded` 在跑，而它只做 `miniPlayer_pause`。

### 变更

1. **store 增加播放列表**：`miniPlayer` 新增 `list` / `index`（整张列表 + 当前序号），
   `miniPlayer_play` 接收 `{list, index}`。**不带 list 的音源（友情链接电台）必须清空旧列表**，
   否则迷你条会拿上一本书的列表去「下一首」，串台。
2. **新增 `miniPlayer_step(delta)`**：收起后播放页已销毁，切集只能由这条 mutation 改
   `url` / `index` / `currentTime`。`currentTime` 取该集的 `base`（整轨起始秒），
   与 `collapseToMini` 的交接口径一致，换集后不会被 `applyStart` 定位回上一集。
3. **迷你条加「上一首 / 下一首」**：`step(±1)`，首页 / 末页自动置灰；`onEnded` 由
   「暂停」改成「推进到下一集并续播」，只有最后一集才停。
   相邻两集指向同一个文件（同轨切片）时 `url` 不变、watcher 不触发，补一次 `attach`，
   否则表现为「点了下一首没反应」。
4. **播放页 `collapseToMini` 交列表**：把整张 `audioFiles` 映射成 `{url, title, base}`
   一起交给迷你条；不带列表，收起后听完一集就没人接手了。
5. **看门狗放过「已播完」**：元素停在末尾不再判定为卡死，交给 `onEnded` 正常推进。
6. **i18n**：`miniPlayer.prev` / `miniPlayer.next`（zh / zh-TW / en）。

### 不变

- 版本门禁全套保留：build.25 的构建期 `--build-arg` + 镜像内 `VERSION` 强校验、
  build.26 的六处 `tr -d '\r'` 与 `check-version-lock.py` 的 LF 写入。
- 后端接口未改。`app/dist` **将在出包时重建**——本版前端有改动，
  前端产物不再与 build.26 逐字节相同（指纹以出包后 `verify` 输出为准）。

## 4.6.0-build.26

> 主题：**修掉版本门禁自己造出来的「假 FAIL」**。build.25 在现场跑 `check-version.sh`，
> 五个版本号打印出来一模一样（都是 `4.6.0-build.25`），却连报三行 `!!` 并 `FAIL`。
> 根因不在部署，在取值：`webserver/version.py` 是 **CRLF** 行尾，而
> `sed -n 's/^VERSION...="\(.*\)"/\1/p'` 只替换到收尾引号，**行尾那个 `\r` 留在变量里**。
> `echo` 到终端时 `\r` 被当成「光标回行首」吃掉，肉眼完全看不出差别，
> 但 `pkg_version` 比 `image/container/api_version` 多一个字节，三次比较全不等。
> 反过来推：若运行期那三个也带 `\r`，它们就会相等而不报错 —— 所以那三处恰恰证明
> 镜像、容器、接口返回值本来就是干净的。

### 变更

1. **六处取值统一 `| tr -d '\r'`**：`scripts/check-version.sh`（4 处）、
   `scripts/deploy.sh`、`scripts/upgrade.sh`（2 处），以及交付侧的
   `check-deployed-version.sh` / `fix-build-layer.sh` / `recover.sh`。
   这条不只是显示问题：`deploy.sh` 若把带 `\r` 的值当 `--build-arg` 传下去，
   镜像里会写进一个看不见的控制符。
2. **断掉源头**：`scripts/check-version-lock.py --set` 原来用 `Path.write_text()`，
   在 Windows 上按 `os.linesep` 换行，**每次改版本号都把 version.py 写成 CRLF**（真凶就在这）；
   改为 `open(..., newline="\n")`。`webserver/version.py` 本身也已归一为 LF。
3. **修 `recover.sh` 的重启口径**：DSM 7.2 上套件叫 `ContainerManager` 而不是 `Docker`，
   `synopkg restart Docker` 直接失败；改为按 `ContainerManager → Docker → synoservice → systemctl`
   候选逐个试，并保留 180s 等待守护进程就绪。
4. **修 `recover.sh` 的两处小坑**：`PROJ` 支持从 `scripts/` 目录运行（自动回退到上级）；
   兜底 `curl | grep` 的模式补上冒号后的空格（`"version":"…"` 匹配不到
   Flask 的 `"version": "…"`，原来会静默空输出）。
5. **三个现场脚本入包**：`scripts/recover.sh`（镜像丢失 / `layer does not exist` 恢复）、
   `scripts/check-deployed-version.sh`（六步定位页脚版本断点，带 `--fix`）、
   `scripts/fix-build-layer.sh`（七步诊断构建层）。以前它们只在交付目录里散放，
   解压新包就找不到了。
6. **文档**：`docs/部署包说明.md` 新增「常见构建失败」一节，收录 build.25 现场踩到的三类问题
   （`layer does not exist`、`synopkg` 重启口径、`compose up` 误拉镜像导致站点中断）。

### 不变

- 前端代码未改，`app/dist` 与 build.25 **逐字节相同**（738 文件 / 71 入口页，
  `index.html` 仍是 `f8771fea…`，入口脚本 `fa08a4c/73f398b/f4ce4e7/7d03e7e`）。
- 最小化播放相关修复（build.23/24）全部保留，未回退。
- 版本锁九处载体 `--set 4.6.0-build.26` 一次改齐并复检通过。

## 4.6.0-build.25

> 主题：**把「页脚版本还是旧号」挡在部署阶段**。build.24 交付后现场出现一个问题：
> 镜像、容器、`dist` 都是新的，页脚却仍显示 `4.6.0-build.22`。根因是
> `webserver/version.py` 由 **构建期的 `GIT_VERSION`** 覆写，而现场保留了自用的
> `docker-compose.yml`（PUID/PGID、路径本地化），里面 `GIT_VERSION` 还是旧号 ——
> 用 compose 构建就把旧号写进了镜像。旧门禁只比对 `app/dist/index.html`，
> 完全看不到版本串，所以一路绿灯。

### 变更

1. **构建时显式传版本号**（`scripts/deploy.sh` / `scripts/upgrade.sh`）：
   `docker build --build-arg GIT_VERSION=<包内 version.py 的值>`。
   从此不再依赖 `docker-compose.yml` 里的 `GIT_VERSION`，现场那行写错也影响不到镜像。
2. **新增版本门禁**（两脚本构建后立刻执行）：`sh scripts/check-version.sh --image`，
   镜像内 `webserver.version.VERSION` 必须等于包内版本，不等即 `exit 1`，
   **容器不会启动**（站点保持旧版本可用，不会出现半新半旧）。
3. **启动后再次全链路自检**：容器内 `version.py` + `GET /api/user/info` 的 `sys.version`
   都必须是包内版本，否则 `exit 1` 并打印排查入口。
4. **新增 `scripts/check-version.sh`**：可单独运行，一次打印
   `pkg_version` / `compose_version` / `image_version` / `container_version` / `api_version`，
   带 `!!` 的行就是断点。支持 `--image` 只看镜像。
5. `scripts/upgrade.sh` 增加提示：compose 的 `GIT_VERSION` 与包内不一致时明确告知
   「本脚本会覆盖，但别手工 `docker compose build`」。

### 不变

- 前端代码未改，`app/dist` 与 build.24 **逐字节相同**（738 文件 / 71 入口页，
  `index.html` 仍是 `f8771fea…`，入口脚本 `fa08a4c/73f398b/f4ce4e7/7d03e7e`）。
- 最小化播放相关修复（build.23/24）全部保留，未回退。
- 版本锁九处载体 `--set 4.6.0-build.25` 一次改齐并复检通过。

## 4.6.0-build.24

> 本版只动「最小化播放」这条链路：把回页接管、被打断的 play、移动端挂起这三条静默失败路径补上自愈，
> 并重建 dist。build.23 已实装的常驻 `<audio>`、可拖动进度条、切源互斥保持原样，只做加固。

1. **回页接管改走页面的播放意图链路**（`app/src/pages/audio/_id.vue` · `adoptFromMini`）：
   原实现是 `player.currentTime = at; player.play().catch(() => {})`——位置写在 `loadedmetadata`
   前后都有可能，`play()` 一旦被判成 AbortError 就被 `catch` 静默吞掉，而本页看门狗只认
   `_wantPlay`（此时为 false）不会救，表现是「从迷你条回到播放页没声音，点一下播放才恢复」。
   现在改为 `_wantPlay = true` + `_playWhenReady()`（等 canplay、最多 40×250ms 重试，AbortError
   走 `safePlay` 的重新武装），并把接管到的位置同步回 `currentTime/progress`。
2. **接管期间服务端进度让路**：新增 `_adoptedFromMini` 标记，`tryRestoreFromServer()` 在接管后直接
   返回，并置 `_positionAppliedFor` 让 `loadTrack` 的定位重试链不再把位置改回 localStorage 的旧值
   （原实现两条链各写一次 `currentTime`，进度条会跳）。
3. **迷你条看门狗 + 回前台续播**（`app/src/components/MiniPlayer.vue`）：每 2s 检查
   「store 说在播、元素却停在 paused」的静默失败（被打断的 play、移动端切后台/锁屏挂起、seek 后
   停住），自动补一次 `play()`；连续 10 次救不起来就退回「暂停」，不再空转。
   `visibilitychange` / `pageshow` 回到可见时同样补一次，避免切后台再回来「条在播没声音」。
4. **`resume()` 的 AbortError 不再直接丢弃**：改为最多 3 次、间隔 250ms 的重试（成功后清零），
   覆盖「换源那一拍 play 被打断就永久静音」的情况。
5. **拖动到最右不再触发 ended**：`onSeekEnd` 的目标位置夹到 `duration - 0.5`（原来夹到 `duration`，
   拖到底会立刻 `ended` → 自动暂停）。
6. **dist 重建**：`eslint`（0 error / 4 条既有 camelcase warning）+ `nuxt build --spa`，
   738 文件 / 71 个入口页；`app/dist/index.html` 新指纹见交付说明。
7. **版本号**：九处载体由 `python3 scripts/check-version-lock.py --set 4.6.0-build.24` 一次改齐并复检通过。

## 4.6.0-build.23

> 本版只做「版本号与包名统一」：取消 `rebuiltN` 交付命名，运行期版本、包名、dist 指纹三者同号。

1. **版本号统一**：运行期版本统一为 `4.6.0-build.23`，九处载体一次改齐
   （`webserver/version.py`、`docker-compose.yml` 的 `GIT_VERSION`、`Dockerfile` 的 `ARG GIT_VERSION` 默认值、
   `app/package.json` / `package-lock.json`、`Makefile` 的 `VERSION_LOCK`、
   `scripts/check-version-lock.py`、`tests/test_version_lock.py`），由
   `python3 scripts/check-version-lock.py --set 4.6.0-build.23` 写入并复检通过。
2. **包名取消 `rebuilt`**：交付包统一为 `audiobook-deploy-4.6.0-build.23.tar.gz` 与
   `audiobook-src-4.6.0-build.23.tar.gz`；源码包内第一层目录同步为 `audiobook-src-4.6.0-build.23/`。
3. **dist 重建**：因 `app/package.json` 版本变更重新构建（eslint + `nuxt build --spa`），
   新 `app/dist/index.html` 的 sha256 与文件数见交付说明，部署后按该指纹验收。
4. **两包同源**：部署包与源码包对应文件逐字节一致（`Dockerfile`、`app/dist`、设置页、白名单、
   locale、`favicon.ico` 等）；源码包 `SHA256SUMS` 重算并与包内实际文件一致。
5. **迷你播放条「第二次收起无声」修复**：`<audio>` 元素移出 `v-if` 改为常驻（原来条隐藏时元素被销毁，
   再展开的新元素没有 src，而 url watcher 已按旧值跑过，于是第二次起无声）；`attach()` 增加 ref
   缺失时的 nextTick 兜底，`resume()` 在无 src 时自动补 attach；`loadedmetadata` 补写 `duration`
   （新 mutation `miniPlayer_duration`），刚展开即可拖动。
6. **迷你条真正切源（有声书 ⇄ 友链电台）**：切源前先 `hls.destroy()` 再换 `src`；`miniPlayer_play`
   覆盖源时旧音源先停再放；有声书页监听 `miniPlayerSig`，迷你条切到别的音源时页面立即停声并清掉
   播放意图；页面开始播放时反向关闭迷你条里的电台；从迷你条回播放页时只有「还在放这本书」才
   adopt 并 seek，否则页面保持静音、迷你条继续放。
7. **迷你条进度条可拖动**：整条 41px 为拖拽热区（按钮层级更高，不误触），拖动中 `timeupdate`
   不再覆盖显示值，松手才 seek 并写回 store；触屏用 pointer events + `touch-action:none`；
   电台/时长未知（NaN/Infinity）退化为静态线并显示「直播」，不出现无意义可拖动条。

## 4.6.0-build.22

> 相对 build.21 的增量：**交付前换行修复（CRLF→LF 全包 3644 文件）、dist 语言包补 4 键
> （作者归一化指引 openClean、设置页归堆标签）、上游 develop（至 fdf982a6）按主题移植 6 组**。

1. **换行纪律**：全包文本 CRLF→LF（修复 build.21 交付包容器 `start.sh` shebang 带 `\r`
   无法启动的交付事故）；新增 `.gitattributes` 强制 LF；`pack.sh --check` 增加换行检查
   与 dist/src 同步抽查（`openClean` 键）。
2. **EPUB 修复页 i18n 修复**（上游 `d7dd8af1`）：扁平点键→嵌套结构（`op.*`/`stage.*`），
   修复整页语言失效；检测结果/阶段文案分隔符不再硬编码；检测完成后进度条复位；
   后端新书上标 `（精修）` 走 i18n。
3. **OPDS 两处**（上游 `8ccab741`/`c0245c78` 适配）：必须登录时 `from=opds` 下载直链回
   401 挑战（原 200 JSON 会被阅读器存成假书）；`ENABLE_OPDS_SERVICE` 关闭后 OPDS 直链
   一并 404。
4. **「即将读完」三项修复**（上游 `606a5031`/`26509dd7`/`2b231705`）：手动标记读完的书
   不再占名额；排除用相关 NOT EXISTS（避免全表扫已读集合）；明细查询复查堵并发窗口。
5. **依赖升级**：tornado 6.5.9→6.6、social-auth-core 5.0.0→6.2.0（需重建镜像生效）。
6. **设置页**：新增「作者重名 / 别名归一」指路条目（三语）；dist 语言包补
   `authorNorm.openClean` 与设置页归堆标签（作者归一化功能本体 build.21 已有）。
7. **源码包内层缺陷修复**：`audiobook-nas-release.tar.gz` 的 overlay MANIFEST 有 27 行
   引用了内层未携带的文件（CHANGELOG.md、Dockerfile、app/locales/*、settings.vue 等，
   它们只在外层 overlay/files 里）——无 git 覆盖部署会漏掉这 27 个文件。本轮已从外层
   overlay 补齐进内层，内层三份清单（SHA256SUMS / overlay 两件）随之全量重生成；
   overlay 现在与清单逐行对账 0 差异。
8. **作者归一化指路升级**（用户反馈"一直说作者清理很突兀"）：设置页指路条目改为
   **可点击直达**（subtitle 字段新增 `to` 支持）；归一化页内链接文案标明
   「工具箱 → 作者清理」；设置页 tips 说明两个入口的分工。
9. **反馈弹窗内容管理员可改**：新增 `FEEDBACK_QR_URL` / `FEEDBACK_NOTICE` /
   `FEEDBACK_GITHUB_URL` 三个设置项（站点信息组），siteinfo 下发，反馈弹窗读配置；
   默认值保持上游行为，管理员可换自己的二维码/文案，仓库链接填 `-` 可隐藏按钮
   （不再指向上游）。
10. **实体书导入入口合并**：导入图书页的「批量导入实体书」按钮与弹窗下线
    （后端 `/admin/batch_add/run` 接口保留），实体书导入统一走「实体书」页的
    「导入实体书」（模板下载 + 逐行错误反馈）。
11. **工具箱新增「音频转写文稿」**（srt_tool）：选书直接转写 `.audio/` 里的音频，
    生成同名 `.srt`（faster-whisper，与 PC 版 srt-tool 同一识别内核 srt_core）；
    后台任务可取消（取消点前的识别结果写入），已有字幕跳过；依赖 faster-whisper
    （requirements-optional.txt），未安装时页面降级提示改用 PC 版。此前 srt-tool
    与网页转写接口都没有任何 UI 入口（用户发现的"大 bug"），本条补齐。
    **交付热修**：首版在 NAS 上启动循环——Dockerfile 未 COPY srt-tool/ 导致容器内
    `import srt_core` 失败拖垮 tornado。已修：srt-tool 目录移入 `webserver/toolbox/`
    （与既有工具同目录，随 webserver/ 整体 COPY 进镜像，不再需要单独 COPY）；
    srt_transcribe 的 srt_core 导入改为容错（缺失时工具降级，不再拖垮启动）。
12. **友情链接类型改为显式选择**（本次 rebuilt 新增）：原先前端按 URL / 名称推断
    友链类型，导致大量普通链接被猜成「电台」，点一下就意外开始播放。现在：
    - 后端 `FRIENDS[].type` 持久化；新增 `webserver/friend_links.py` 统一 canonical
      取值（`radio / website / bbs / video / news / book / link`）、历史别名
      （`stream→radio`、`forum→bbs`、`site→website`、`other→link`）与非法值清洗；
      保存时清洗，非法值不会写进配置；读取时容错非 list / 非 dict / 字段类型异常。
    - 后台设置页友情链接编辑新增「类型」下拉（七类），沿用原有增删改与上下移；
      老数据缺 `type` 时归一化为「网站」，可正常编辑、删除、前后新增、排序。
    - 前台图标按 `type` 显示（`mdi-web` 新增进 MDI 子集）；**只有「电台」类型
      点击触发底部迷你播放条，其余类型一律普通外链跳转**，不再按 URL 猜测。
    - 三套 locale（zh / en / zh-TW）补齐 `friend_type` 与七个类型名、提示文案。
    - `app/dist` 已重建（入口指纹见 `docs/部署包说明.md`「本次构建产物指纹」）。
13. **反馈弹窗设置修复 + 二维码后台上传 + 部署口径修正**（rebuilt8 新增）：
    - `FEEDBACK_QR_URL` / `FEEDBACK_NOTICE` / `FEEDBACK_GITHUB_URL` 此前只出现在
      `settings.py` 默认值与前端表单，未登记进 `webserver/base/setting_saver.py` 的
      `ADMIN_SETTING_KEYS`，导致后台保存被 `AdminSettings.post` 的白名单丢弃、刷新后
      回退默认值。三个键已补齐，保存即落盘、刷新生效（`PERSISTABLE_KEYS` 由其派生，自动跟随）。
    - **反馈二维码改为后台上传**：设置页「反馈二维码图片地址」下方新增选图 + 上传
      （`v-file-input` → `POST /api/feedback_qr`），复用作者头像上传的同一套基础设施
      （`@is_admin`、multipart、JPG/PNG/WEBP 校验）；写入容器 `/data/books/logo/feedback_qr.<ext>`
      （宿主 `/volume1/docker/audiobook-data/books/logo/`），目录不存在自动创建，
      返回 `/logo/feedback_qr.<ext>?v=<时间戳>` 自动回填输入框并即时预览。保留手填
      URL / 外链能力；不写镜像内路径，不需要重启容器；换扩展名时清理旧的其它格式文件。
    - 三语 `feedback_qr_url_tips` 由错误的 `app/public/logo/` 改为生产真实路径
      `/data/books/logo/`（宿主 `/volume1/docker/audiobook-data/books/logo/`），并说明可在页面上传。
    - 构建口径：`docker compose build` 在本机会走 compose 内嵌 BuildKit，其上下文快照
      按 `(mtime,size)` 判重，会复用旧 `dist`（表现为「新 `_nuxt` + 旧 `index.html`」，
      页面一直转圈）。统一改为 `DOCKER_BUILDKIT=0 docker build --no-cache`，
      启动用 `docker compose up -d --force-recreate --no-build`；
      `scripts/deploy.sh` / `scripts/upgrade.sh` 已同步，并在构建后比对镜像内
      `dist/index.html` 与包内文件。
    - 包内所有文件 mtime 常量换新（`1794019300` → `1794019500`），避免再次命中旧上下文快照。

    - `app/dist` 已按新前端重建：`index.html` sha256 `f698cb5b…`、入口脚本 `71819e1.js`。
    - **站点图标收敛为一张**：`app/public/logo/` 与 `app/dist/logo/` 删除全部
      `favico*`（`favicon_0.ico` ~ `favicon_8.ico` 一并移除），只保留新的 `favicon.ico`；
      后台「网站图标」下拉相应收敛为「沿用当前图标」，不再指向不存在的文件。
      `favicon.ico` 与默认反馈二维码 `link_gongzhonghao.jpg` 采用「缺失才补」：
      全新部署由 `deploy.sh` / `upgrade.sh` 写入 `/volume1/docker/audiobook-data/books/logo/`，
      存量站点一律不覆盖，需要更换由管理员手工覆盖或后台选图上传。

版本锁九处载体已由 `check-version-lock.py --set` 同步升号；CHANGELOG 本条为人工补写。
