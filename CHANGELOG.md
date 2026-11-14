# 变更日志（CHANGELOG）

本项目的版本号规则：**`<上游 mybooks tag>-build.<自建构建号>`**，当前版本 **`4.6.0-build.27`**。
上游基线：mybooks tag `4.6.0`（2026-10-25，commit `3c5947c`）。
包名与运行期版本同值：`4.6.0-build.27`；**修订号 `-rN` 才是「哪一次交付」**，见下方各节。

> **发布标签（别拉错）**：`4.6.0-build.27` 这个 tag 停在 2026-11-08 的首版交付点（`a5019c6`，
> 相当于 `-r0`），**不含 r8~r15 的任何修复**（含 `_nuxt/*.js` 全 404 那次事故的根因修复）。
> 要取当前交付点，用 tag **`4.6.0-build.27-r27`**（指向 `edcc9f2`；r18 作废，勿用）；若该 tag 之后 master 还有提交，
> 以 `master` 为准（tag 只在发布时打，文档类提交不会跟着挪）。
> 已合并的历史工作分支 `r7-fix`、`opt/p0-p1` 已于 r15 删除（无独有提交，内容都在 master 历史里），
> 早期文档里若出现 `git diff master..opt/p0-p1`，请改用 tag `4.6.0-build.27` 与当前 master 比对。

> 更早的变更记录（`4.6.0-build.21` 及以前、旧编号时代）已精简归档，
> 完整历史见 git 提交记录（`git log`）。

---

## 4.6.0-build.27-r34（2026-11-14，**修复详情页修改分类报错**，纯后端，可热更）

### 根因：`_` 被当成局部变量，盖掉了 i18n 翻译函数

`a1d6055`「取书权限前置收口」重构引入了 `_, err = self.require_book(book_id)`。
Python 只要在函数内给 `_` 赋过值，**整个函数里的 `_` 都是局部变量**，于是
`_("分类更新成功")` 调的是 `require_book` 返回的 book dict →
`TypeError: 'dict' object is not callable`；异常分支里又调了一次 `_()`，
所以 traceback 里出现两段同样的错误（这也是 `@js` 包装器 `base.py:213` 的来由）。

**这不是版本问题，是仓库里一直存在的既存 bug，任何版本点该功能都会复现。**

### 受影响的 5 个接口

| 接口 | 触发动作 | 报错形态 |
| --- | --- | --- |
| `/api/book/<id>/category` | 详情页修改分类 | `'dict' object is not callable`（本次实测） |
| `/api/book/<id>/location` | 修改位置 | 同上 |
| `/api/book/<id>/catalog` | 重新提取目录 | 同上 |
| `/api/book/<id>/ai-fill` | AI 填充书籍信息 | 同上 |
| `/api/admin/token` | 生成 MCP token | `for _ in range(32)` → `UnboundLocalError` |

「上次好像也有一次这个错误」就是同一个根因落在另一个接口上。

### 修复

- `webserver/handlers/book.py` 4 处 `_, err = ...` → `_book, err = ...`
- `webserver/handlers/admin.py` 的 `for _ in range(32)` → `for _i in ...`
- 新增 `tests/test_i18n_underscore_shadowing.py`：AST 扫描全仓 `webserver/`，
  凡 import 了 `webserver.i18n._` 的模块，禁止在任何还调用 `_()` 的函数里把 `_`
  用作赋值目标 / 循环推导变量 / 参数名。含 3 个「扫描器必须能抓到坏例」自测，
  防止测试退化成永远通过。4 例全绿。

### 部署方式

纯 `webserver/**/*.py` + `tests/`（归 docs），`hotfixable=true` / `requires_dist=false`：
页内 `/admin/version` →「立即更新」即可，装完强刷浏览器，**不需要重新部署**。

> ⚠️ 但**「有声书」页没有分类 tab 是另一件事**：r31 才引入前端组件
> `CategoryTabs.vue` 与 `ListBook.vue` 改动，产物在 `app/dist` 里；热更只替换 py，
> 不碰 dist。若你的站点前端还停在 r30 之前，请用
> `audiobook-deploy-4.6.0-build.27-r34.tar.gz` **整包重新部署一次**，
> 可同时拿到「分类 tab」和本修复。判断是否旧 dist：
> `sha256sum <源码目录>/app/dist/index.html` 应为 `2c02df40…`（768 个文件）。

---

## 4.6.0-build.27-r33 联网全新安装支持（2026-11-14，**第二次同 revision 重出**）

给第三方装机多一条「联网 git clone」路径，不必传 153MB 包。仍是 r33，
`update/manifest.json` 字节未变，已装站点无需任何操作。

### 实证

匿名 clone `b8fdcf4` → 5764 个文件；`app/dist` 768、`myreader-dist` 2724 条 /
119 根软链、断链 0；`docker compose config` 通过；builder 阶段真实构建日志
`预构建 dist：有（跳过 npm ci / generate）`、768 个文件。
所以联网只用于 clone 与拉基础镜像 / apt / pip，**不装前端依赖**。

### 改动

- `docker-compose.yml` 变量化：`DATA_DIR` / `PUID` / `PGID` / `HTTP_PORT` /
  `HTTPS_PORT` / `TZ` 支持 `.env` 覆盖，默认值与原来完全一致（现有 NAS 无感）。
  新增仓库根 `.env.example`。
- 新增 `scripts/install-fresh.sh`：clone 后一条龙（校验 dist 与 119 根软链 →
  打印清单基线 → 生成 `.env` 并排除提交 → 建数据目录 → 调 `deploy.sh`）。
  `CHECK_ONLY=1` 实测通过；`.env` 被写进 `.git/info/exclude`，且 `pack.sh` 只打
  `git ls-files` 跟踪文件，本地配置不会混进部署包。
- `Dockerfile` 更正过时注释：`myreader-dist` 是**完整入库**的（2724 条 / 119 根软链），
  不是「不入库、只有 .keep 占位」；clone 必须 `core.symlinks=true` 且只在 Linux 上做。
- `docs/部署包说明.md` 重写「第三方全新安装」：三条路径对比、删掉
  「出包会自动从 Gitee raw 拉清单覆盖包内那份」这句与 r33 闭环矛盾的 r8 旧口径、
  版本号统一 r33、补「数据目录必须先建」与 PUID 说明。
- `docs/部署方式速查.md` 新增 §5.5 与 §0 决策行。

> ⚠️ `docker-compose.yml` / `Dockerfile` 属于镜像级文件，下次用
> `gen-update-manifest.py` 生成清单时会判 `blocking` → `mode=redeploy`。
> 这是预期的（别人装机本来就要重新构建镜像），不影响当前 r33 的判定。

---

## 4.6.0-build.27-r33 重出（2026-11-14，**仅脚本加固，revision / 清单字节不变**）

r33 包**同 revision 重出**（只有包 md5 变了）：`update/manifest.json` 一个字节没改，
`app/dist` 基线 768 / `index.html` 指纹 `2c02df40…` 也没变，所以**不需要再走一次
redeploy**，已装 r33 的站点不受影响。本轮改动全在 `scripts/` 与文档，按
`gen-update-manifest.py` 的 `classify()` 归为 `docs`，不阻塞热更。

### 发布清单闭环（r27 / r33 事故的根治）

- `scripts/pack.sh` **删掉从 Gitee raw 拉清单的历史逻辑**——出包链路零网络请求；
  包内清单唯一来源是仓库工作区 `update/manifest.json`（前面已断言 `revision == $VER`）。
  首次修复只做到「远端落后就跳过 + 暂存区断言」，断言仍没覆盖**最终 .tar.gz**，闭环没合上。
- 新增 `scripts/verify-pkg-manifest.sh`：直接从最终 `.tar.gz` 解出清单，校验
  `revision` 格式、与本次版本一致、整份字节 `sha256` 与仓库清单一致。
- `pack.sh` 打包后门禁强制调用它，不一致就**删包退出**；`pack.sh --check` 也调用它。
- `scripts/upgrade.sh` §5.5 / `scripts/deploy.sh` 解压后反向校验包内 `revision`
  与包文件名的 `-rN` 一致，坏包在构建前被拦。
- 新增 `tests/test-pkg-manifest-guard.sh`：重演「r32 清单打进 r33 包」等 13 个用例，全绿；
  `scripts/check-remote-manifest.sh` 作为发布**后置**只读检查，不进出包链路、不覆盖产物。

### compose 部署

- `docs/部署方式速查.md` 新增 §2.5：仓库自带 compose 已是 `9800:80` / `8443:443` /
  `/volume1/docker/audiobook-data:/data`；明确**源码目录不能挂 `/data`**、证书路径与自签说明。
- `scripts/pack-image.sh` 的交付 compose 模板补 `8443:443` 与 `HTTPS_PORT`、证书说明。

---

## 4.6.0-build.27-r33（2026-11-14，**打包口径收敛 + 部署文档整理**，需重新部署）

### 打包：默认排除 `app/node_modules`

- `scripts/pack.sh` 默认 `SLIM=1`，包体 **215MB → 153MB**；新增 `--full` 显式保留，
  `--slim` 作为兼容别名（等价于默认，不再产生 `-slim` 后缀，默认包就是正式包）。
- 依据：Dockerfile v3 只要 `app/dist` 齐全就跳过 `npm ci / generate`，生产镜像里的
  `app/` 来自 `/app-static`（只含 dist 与几个配置文件），从来不含 node_modules；
  `.dockerignore` 也本来就排除它。
- 真机证据：**r29**（TraeCode CN 出的包就没带这一层）→ 热更 r30 后站点一直正常；
  本次又在沙箱用 `docker build --target builder` 复验，日志明确
  「检测到预构建 dist，跳过 npm ci 与 generate」，768 个 dist 文件全部带上。
- 早期「删了会出运行异常」的说法来自 r11 时代的旧构建链路，且常伴随误伤
  `myreader-dist` 依赖；相关注释、真机清单前提、失效文档引用（`docs/真机验证清单.md`
  早已归档并入 `部署包说明.md`）全部改写或去除。
- `myreader-dist` 下三层 `node_modules`（119 根相对符号链接）任何模式都不动，门禁不变。
- **修复包内清单基线被 Gitee raw 缓存污染**：旧逻辑出包前从 raw 拉清单覆盖包内那份，
  r33 首次打包时 raw 还停在 r32，导致「包名 r33、包内清单 r32」，装完页面会一直
  误报有新版本 / 反复要求重新部署（r27 同类事故重演）。首次修复只做到
  「远端落后就跳过 + 暂存区断言」，**断言没覆盖最终 .tar.gz**，闭环仍未合上；
  完整根治见上方「r33 重出」。

### 文档：一份按场景给命令的速查表 + 全仓口径对齐

- 新增 [`docs/部署方式速查.md`](docs/部署方式速查.md)：页内热更、整包离线部署
  （带 dist，连 `npm ci` 都不执行）、改了前端却没重新出 dist（builder 现场
  `npm ci + npm run generate`，需联网）、镜像 tar 交付、源码包、回滚、通用自检，
  每种情况给可直接复制的命令、判据与易误判项。
- `scripts/pack-image.sh` 收进仓库（此前只在交付目录），镜像交付命令有对应文件。
- dist 基线统一到 **768**；清掉 `Dockerfile`、`.dockerignore`、`README.md`、
  `INSTALL_GUIDE.md`、`docs/部署包说明.md`、`docs/操作总纲.md`、NAS 手册里的
  757/766、`build-spa`、「默认保留 node_modules」、「断链 8」、容器内
  `/app-static` 路径等过时描述。历史修订摘要中的 757/766 保留原样（描述当时事实）。
- `docs/README.md` 把速查表列为「每次部署前先看」的第一份文档。

### 部署方式

`scripts/pack.sh` 与 `Dockerfile` 变更落 `blocking` → 清单判定 `mode=redeploy`，
**必须用整包重新部署**，页内「立即更新」不会出现。命令见 `docs/部署方式速查.md` §2。

---

## 4.6.0-build.27-r32（2026-11-14，**修正：分类 tab 与分类浏览页同源**，仅后端 3 个 py，可热更）

按验收反馈「跟分类里面的分类一致，进行分类最合适」，把 r31 里各算各的分类改成同一套：

- 分类骨架下沉为 `BaseHandler.catalog_categories()`，`/api/categories` 与
  `/api/audiobooks/categories` 共用同一份（同一 SQL、同一可见性口径、同一套
  `category_icons` 图标规则）。有声书页只把 count 换成「该分类下的有声书数」，
  **顺序照抄分类页，不按有声书数重排**。
- 有声书数为 0 的分类默认不显示（点进去只能是空页）；`?all=1` 可保留，
  用于核对两页分类是否完全一致。
- 修复既存 bug：读者组成员打开「分类浏览」页时分类列表整段为空。
  原代码 `for name, _ in categories` 遍历的是 dict 列表，解包到的是键名
  `"name"`/`"count"`，`counts.get()` 永远取不到值，所有分类被当作 0 剔除。
- 新增 `tests/test_catalog_categories.py`（11 例）锁分类骨架契约；
  `tests/test_audiobooks_category_handler.py` 补「顺序照抄」「0 计数隐藏」两例。

> **r31 去哪了**：`update/manifest.json` 仓库里只有一份，永远指向最新修订，
> 所以 r32 推上去后页面「最新版本」直接显示 r32，不会逐个列出中间修订；
> r31 的清单与代码仍在 git 历史里（`7f41756` / `acadb43` / `034d256`）。
> **r32 整包已包含 r31 的全部改动（含前端 dist），不需要先装 r31。**
>
> 部署方式：**r31 → r32** 可在页面「立即更新」热更（3 个 py，装完强刷）；
> **r30 及更早** → 清单 `base_revision` 与本地不匹配，页面判定 `redeploy`，
> 请用 `audiobook-deploy-4.6.0-build.27-r32.tar.gz` 整包重新部署。

---

## 4.6.0-build.27-r31（2026-11-14，**功能：有声书页分类 tab**，含前端产物，可热更）

### 有声书页支持按分类浏览（与「分类浏览」页同款交互）

左侧菜单点「有声书」进入后，列表顶部新增一排分类 tab（首个是「全部」），
点击只看该分类的有声书；分类与数量来自 calibre 自定义列 `#category`。

- 后端：`/api/audiobooks` 新增 `category` 参数（先过滤后分页，游标兼容）；
  新端点 `/api/audiobooks/categories` 返回 tab 数据（name/count/icon/color）。
- **分类与「分类浏览」页完全一致**：tab 的分类名、顺序、图标全部取自
  `BaseHandler.catalog_categories()`——与 `/api/categories` 同一份骨架（同一 SQL、
  同一可见性口径、同一套 `category_icons` 命名规则），只是把 count 换成
  「该分类下的有声书数」。有声书数为 0 的分类默认不显示（点进去只能是空页），
  带 `?all=1` 可保留，用于核对两页分类是否一致。
- **口径一致**：tab 的 count 与列表的 total 用同一个可见性判定
  （`book_matches_limits`，读者组白/黑名单同一函数）——tab 显示几本，点进去就是几本。
- 顺带修复 ①：受限用户此前在有声书页看到的 `total` 是全量数，
  与每页实际书数对不上，现在 total 同样按可见口径计算。
- 顺带修复 ②：**读者组成员打开「分类浏览」页时分类列表整段为空**。
  原代码 `for name, _ in categories` 遍历的是 dict 列表，解包到的是键名
  `"name"`/`"count"` 而不是分类名，`counts.get()` 永远取不到值、所有分类
  被当作 0 计数剔除。改为按 `item["name"]` 取值，`test_catalog_categories`
  的 `test_scoped_counts_*` 锁定该行为。
- 性能：分类聚合（书 × `#category`）收敛到共享模块 `webserver/base/audio_category_agg.py`，
  podcast 的分类/标签/作者聚合改为复用同一份（消灭两份各自失效的缓存）；
  书集合小变更在请求线程增量补齐（毫秒级），冷启动/全库扫描后转后台线程重建，
  请求路径零阻塞。podcast 原有的 180s TTL 语义由共享层节流承担，行为不变。
- 前端：tab UI 抽成公共组件 `CategoryTabs.vue`，「分类浏览」页与有声书页共用
  （原来模板与样式各写一份）；有声书页的选中状态走路由 query（`?category=`），
  刷新、分享、翻页都能保持；「全部」tab 的数字直接用列表实时 total。

### 新增测试

- `tests/test_audio_category_agg.py`：聚合形态口径（含 "A/B" 不拆分的历史锚）、
  版本短路、增量补齐、全量节流、meta 与分桶同源；
- `tests/test_audiobooks_category_handler.py`：category 过滤、未知分类空页、
  过滤集上游标翻页、**tab count ≡ 列表 total**、受限用户同步削减、空分类剔除、
  **tab 顺序照抄分类页（不按有声书数重排）**；
- `tests/test_catalog_categories.py`：分类骨架契约（无自定义列、SQL 顺序、
  访客/管理员/白名单/黑名单、scoped 可见口径替换与 0 剔除、书库版本失效缓存、
  两个 handler 共用同一条缓存）；
- `tests/test_audio_books_cache.py` 补缓存版本号随三个变化入口递增。

---

## 4.6.0-build.27-r27（2026-11-12，**安全修复 + 文档**，无运行期代码变更，检测仅提示）

> 本版**没有前端/后端运行期代码变更**，只改运维脚本与文档；已重出 deploy 与 src-full 两张整包。

### 安全修复：跟随上游脚本不再内置 Gitee 令牌

`scripts/upgrade-upstream.sh` 原先在第 23 行把私人令牌写成默认值（`TOKEN="..."`），
等于让凭据随仓库和部署包一起分发。现在脚本里不留任何令牌：

| 文件 | 改动 |
| --- | --- |
| `scripts/upgrade-upstream.sh` | 删除硬编码 `TOKEN`，改为 `TOKEN="${GITEE_TOKEN:-}"`；有值时仍拼 `https://wxgoo:${TOKEN}@…`（无人值守行为不变），无值时退回无凭据地址 `https://gitee.com/wxgoo/audiobook-src.git` 并打印一行提示（`export GITEE_TOKEN=...` 或 `~/.netrc`，600 权限），**不再直接报错退出**；clone 与 push 统一走同一个 `GITEE_URL` 变量 |

> 令牌失效时改环境变量或 `~/.netrc` 即可，**不要写回脚本、URL 或文档**。
> 全仓复扫 `https://<user>:<32位十六进制>@gitee.com` 与历史令牌字面量：工作树 0 命中。

### 文档：凭据口径统一为「环境变量或 `~/.netrc`」

| 文件 | 改动 |
| --- | --- |
| `delivery/overlay/files/docs/操作总纲.md` | 推送示例里的 `<令牌>` 占位符改为无凭据地址；令牌说明与报错表（`could not read Username` / `403`）统一为「用 `GITEE_TOKEN` 或 `~/.netrc` 提供，不要写进文档或提交」 |
| `docs/开发指南.md` | 「发布一个修订」小节补同一口径 |
| `docs/部署包说明.md` | 脚本清单后补同一口径，并写明未读到 `GITEE_TOKEN` 时脚本退回无凭据地址 |

### 归档：首屏空白那轮的规格与任务清单

`docs/archive/` 新增 `spec-所有书籍首屏空白.md`（274 行）与 `tasks-所有书籍首屏空白.md`（55 行），
按原样归档，与 r26 的 [`docs/故障复盘-所有书籍首屏空白.md`](docs/故障复盘-所有书籍首屏空白.md) 配套查阅。
`docs/README.md` 本就没有 docs/archive 的索引表，本次不新建索引。

### 发布物

| 包 | 说明 |
| --- | --- |
| `audiobook-deploy-4.6.0-build.27-r27.tar.gz` | 部署整包（不切片），附 `.md5` / `.sha256` |
| `audiobook-src-4.6.0-build.27-r27-full.tar.gz` | 源码整包（含 `app/dist`，不含 `app/node_modules` 构建依赖），附 `.md5` / `.sha256` |

> 出包后按流式方式（`tar -tzf` / 逐成员读取，未把整包解压到磁盘）复核包内
> `delivery/overlay/files/docs/操作总纲.md` 与 `scripts/upgrade-upstream.sh`：32 位十六进制令牌明文 0 处；
> 包内 `SHA256SUMS` 全量重算 0 不符、0 缺成员。

## 4.6.0-build.27-r26（2026-11-12，**前端 + 服务端**，须重建镜像）

> 完整复盘：[`docs/故障复盘-所有书籍首屏空白.md`](docs/故障复盘-所有书籍首屏空白.md)
> —— 现象与证据 / 被推翻的 7 个判断 / 决定性证据与机理 / `ssr_loaded` + 请求令牌去重 /
> 68 页全站审计（4 处命中）/ 同批次 `this.alert` 与页大小修复 / id 排序实测 / 复现与校验命令。

### 修复：列表页数据失败只留空白壳（`this.alert` 静默 TypeError）

现场截图是「所有书籍」页：标题、翻页、页脚版本、左侧栏计数全部正常，中间网格空白，
**连空态文案都没有**。这不是接口慢，也不是 chunk 404。

根因在 `ListBook.vue` 的错误分支：调用了不存在的 `this.alert(...)`。
Vue 插件用 `inject('alert')` 暴露的是 **`this.$alert`**，`this.alert` 是 `undefined`，
`this.alert(...)` 抛 `TypeError: this.alert is not a function`；它发生在 `$backend().then(...)`
回调里，异常被 Promise 链吞掉，`books` 停在 `[]`，界面既没书也没提示 —— 正是截图表现。
`modeText` 那次（r24）是同一个模式：**调用了不存在的成员，render/回调抛错被吞**。

| 文件 | 改动 |
| --- | --- |
| `app/src/pages/ListBook.vue` | 错误分支改 `this.$alert`；新增 `load_error` / `errorText` 与「加载失败 + 重试」「暂无书籍」两种可见状态；`init()` 加请求令牌（旧响应不覆盖新页面）；`asyncData` 走 `$backend(fullPath, {timeout: 20000})`；页大小改用 `clampPageSize` |
| `app/src/pages/book/_bookid.vue` | `init()` 的错误弹窗同样改为 `this.$alert`，并带 `msg` 兜底 |
| `app/src/store/index.js` | `alert` mutation 对空 `msg` 直接返回，避免弹窗组件拿到空对象 |
| `app/src/plugins/mybooks.js` | `$backend` 新增 `options.timeout`（`AbortController` + 定时器）；502 与 `server_starting` 分支不再返回永不 settle 的 Promise，改为 10s 看门狗返回可展示错误 |
| `app/src/utils/pageSize.js`（新增） | `clampPageSize(value, fallback, max=200)`：页大小封顶 200（LITE 60），对齐后端 `MAX_PAGE_SIZE` |
| `app/src/components/BookCards.vue` | `render_books` 不再改写父级 `book` 对象（`{...b, href}`）；卡片加 `content-visibility: auto` + `contain-intrinsic-size`，降低长列表一次性渲染开销 |
| `app/locales/{zh,zh-TW,en}.json`、`delivery/overlay/files/app/locales/*` | `listBook` 新增 `empty` / `loadFailed` / `retry` |
| `app/scripts/check-vue-method-refs.js`（新增）+ `npm run lint:refs` | 静态扫描 `app/src/**/*.vue`（129 个）：脚本段比对 `this.NAME()` 是否真实存在（methods/computed/data/props/inject/运行时赋值），模板段只提示；`--strict` 有脚本级错误即退出 1 |
| `tests/test_frontend_silent_failures.py`（新增） | 12 条：禁止 `this.alert(`、ListBook 必须用 `$alert` 且带 `load_error/errorText`、模板三 key 存在、store 空文案保护、三语与 overlay key 齐全、`lint:refs --strict` 退出 0、ListBook/ListMeta 的 `mounted` 必须触发 `init` 且用 `ssr_loaded` 去重 |

### 修复：直接进入 / 强刷列表页不发请求（首屏永久空白）

现场决定性证据：强刷 `/all` 后 Network 里**没有任何取书请求**，Console 无报错；
而 `app/dist/all/index.html` 是构建期预渲染的壳，payload 为 `data:[{}]`。

根因不在接口，而在**取数入口**：`ListBook.vue` 只在 `asyncData` 与 `beforeRouteUpdate` 里取数。
静态产物（`nuxt generate --spa`）的 `asyncData` 只在构建期跑一次，运行时首屏不会重跑；
`beforeRouteUpdate` 又只在**同组件**切路由/翻页时触发。于是：
直接打开/强刷 → 两个入口都不触发 → 永远不发请求 → 空白；
从侧栏其它列表页点进来 → 组件复用 → `beforeRouteUpdate` 触发 → 正常出书。

| 文件 | 改动 |
| --- | --- |
| `app/src/pages/ListBook.vue` | 新增 `mounted()`：`!ssr_loaded && !inited` 时 `init($route)`，保证首屏必取一次；`asyncData` 仅在 `rsp.err === 'ok'` 时打 `ssr_loaded`，避免 dev/SSR 下重复请求；切路由/翻页仍走 `beforeRouteUpdate`，请求令牌去重 |
| `app/src/pages/ListMeta.vue` | 同一问题（`created` 里的 `init` 被注释、只剩 `asyncData` + `beforeRouteUpdate`）；同样补 `mounted` 兜底与 `ssr_loaded` 去重，覆盖 /tag、/series、/rating、/author、/publisher、/language |

其余同构页已核对：`search.vue`、`folder.vue`、`booklist/_id.vue` 在 `mounted` 里取数，
`_bookid.vue`、`author.vue`、`tag.vue`、`series.vue` 在 `created` 里调用 `init`，首屏都会发请求，不受影响。

### 全站首屏取数审计（6 类形态）

`lint:refs` 增加「首屏取数审计」：`pages/**` 里若只有 `asyncData`，或只在 `$route` 的 `watch`
里取数且缺 `immediate`、又没有生命周期兜底，`--strict` 直接失败。扫描 68 个自有页面
（`all/audiobooks/favorites/reading/printbooks/soledbooks/visits/wants/read-done` 等是
`export default ListBook` 的薄壳，自动继承修复；`tag/series/rating/author/publisher/language`
同理继承 ListMeta）。

| 页面 | 命中形态 | 直接进入的结果 | 处理 |
| --- | --- | --- | --- |
| `ListBook.vue`（+ 9 个薄壳） | 只有 `asyncData` + `beforeRouteUpdate` | 不发请求，空白 | 已修：`mounted` + `ssr_loaded` |
| `ListMeta.vue`（+ tag/series/rating/author/publisher/language） | `created` 里的 `init` 被注释，只剩 `asyncData` | 不发请求，空列表 | 已修：`mounted` + `ssr_loaded` |
| `admin/syslog.vue` | 只有 `asyncData` | 日志区永远「暂无日志」 | 已修：`mounted → fetchLog` |
| `toolbox/_id.vue` | 只有 `asyncData` | 永远显示「工具不存在或已禁用」 | 已修：`mounted → loadTool` |
| `welcome.vue` | 只有 `asyncData` | 安装引导页，无列表数据；`err` 缺失只是不跳转 | 不改，lint 白名单 |
| `s/_token.vue` | `asyncData` + `mounted`（`err` 默认 `ok` 时会 `verify()` 重新取数） | 能自愈，不受影响 | 不改 |
| `search/folder/booklist/_id/booklists/*/history/memos/expected/admin/*` | `created` 或 `mounted` 取数 | 正常 | 不改 |
| `author/tag/series/_bookid/readtxt/index/audio/_id` | `created`/`mounted` 取数（`watch` 只做二次响应） | 正常 | 不改 |
| `starting.vue` | `mounted → poll()` | 正常 | 不改 |

误报控制：`watch` 规则只在「handler 里出现取数调用 + 没有 `immediate: true` + 没有生命周期取数」
时命中；`starting.vue` 的 `poll()` 已计入取数，不再误报。薄壳页（`export default ListBook`）不做独立判定。

### 服务端：列表 `total` 与可见集合一致

`webserver/handlers/base.py` 的 `ids` 分支原来直接 `total = len(ids)`，但渲染时会过滤掉
对当前用户隐藏的独享书，可能出现「总数有值、items 为空」。改为 `len(ids)` 后再扣除隐藏项，
隐藏集合按 `(user_id, library_version)` 缓存 30s。

### 验证

- `pytest tests/test_frontend_silent_failures.py -q` → **16 passed**（含首屏取数 8 条）
- `node app/scripts/check-vue-method-refs.js --strict` → **0 处脚本级错误，0 处模板级待确认**，
  首屏取数审计 **0 处隐患**（68 个页面）
- 改动文件 `npx eslint` → 0 error；`python -m py_compile webserver/handlers/base.py` 通过
- `npx nuxt generate` 后 `scripts/check-dist.sh` → **757 个文件**，pdfjs 369 / 字体 3 / 壁纸 4 / 图片 4 齐全
- `app/dist/index.html` sha256 = `b7c49b20c2e9042538dcdd9038e0c43557a18d7449922e159569e8ee509a1ebc`（23273 字节）

> `app/public` 是 `dir.static` 的真实来源（`srcDir: src/` + `../public`）。本轮重建前它在工作树里被删过，
> generate 只会产出 301 个构建产物；重新从 HEAD 取回 456 个非构建资源后才恢复到 757。**重编前先确认 `app/public` 存在。**

> 本次改的是 `app/src`，**必须重建镜像才生效**；`docker cp app/dist` 进容器只是临时，重启/重建即回到旧产物。

## 4.6.0-build.27-r25（2026-11-11，**服务端 + 构建期**，须重建镜像）

### 构建期硬门禁：dist 缺 pdfjs viewer 直接中止

`aa457b8`~`bc39f47` 那次重建暴露出「`nuxt generate` 先清空 dist」这个坑，靠人记没用，改成构建期断言：

| 文件 | 改动 |
| --- | --- |
| `Dockerfile` | builder 阶段 `/app-static/dist` 生成之后、生产阶段 `COPY --from` 之前，断言 `static/pdfjs/web/viewer.html` 存在，否则 `exit 1` 并打印原因与校验方法；`mkdir -p logo/avatar` 兜底不变 |
| `scripts/check-dist.sh` | 新增：关键路径存在性 + 各目录数量下限 + 整目录文件数必须等于基线 `757`（可用 `BASELINE` 覆盖） |
| `scripts/pack.sh` | 出包前 `[1b/4]` 调 `check-dist.sh`；`--check` 验包时再查 viewer.html 与 757 |
| `docs/开发指南.md`、`docs/部署包说明.md`、`docs/故障复盘-读者组转圈.md` | 写明「前端重编后必须整目录校验 dist，不能只数构建产物」，附三道防线与白名单 `comm` 清理法 |

### 修复：元数据更新 500（`NameError: name 'douban' is not defined`）

线上 `webserver/handlers/book.py` 第 1310 行 `if provider_key == douban.KEY:` 抛 `NameError`。
豆瓣 v1 插件在 build.27-r12 已整体移除，但 `BookRefer.post` 里还留着 v1 分支；该比较表达式
**对所有 provider 都会先求值**，所以任何 provider 的元数据更新都会 500，与是否用豆瓣无关。
因为它是「更新元数据」这条较少使用的路径（不是页面加载），一直没被发现。

| 文件 | 改动 |
| --- | --- |
| `webserver/handlers/book.py` | 抽出 `_resolve_refer_mi`，删掉 v1 分支；所有 provider 统一走「v2 占位注释修正 → 表单 metadata / 现有 mi → 补封面」 |
| `tests/test_book_meta_provider_branch.py` | 新增 8 条：`douban`/`douban_v2`/`xhsd`/`bookbarn` 分支在无豆瓣模块时也返回；封面开关；AST 静态检查禁止未绑定的 `douban.` 引用；v1 模块确已删除 |

> `delivery/overlay/files/webserver/handlers/book.py` 是 `opt/p0-p1` 分支的历史快照（冻结产物），
> 不参与运行，也不改它——它的 MANIFEST/SHA256SUMS 依赖原始字节。

> 本次含 Dockerfile 变更，**不能页内热更**，必须 `docker compose build mybooks` 重建镜像。

> 完整证据链与残留清单见 [`docs/故障复盘-豆瓣v1残留500.md`](docs/故障复盘-豆瓣v1残留500.md)。

## 4.6.0-build.27-r24（2026-11-11，可页内热更，**只有前端产物**）

### 更正：r20 对「读者组一直转圈」的归因是错的

r20~r23 一直认定是「服务启动期 `server_starting` → `$backend` 返回永不 settle 的 Promise」，
并据此加了整页跳转和 20s 超时兜底。**这个归因不成立**：用户抓包显示 `GET /api/admin/reader_groups`
返回 `200`、正文 548 字节、两组数据完整；r21 部署后仍无限转圈。

**真实原因**：`ReaderGroupEditor.vue` 把 `modeText(mode)` 写在了 `computed` 里，而模板写成
`{{ modeText(groups[name].mode) }}` 按方法调用。

- Vue 2 的 computed **按属性求值、不接收参数**：`modeText` 被无参执行一次，得到一个**字符串**；
- 模板再对这个字符串加括号调用 → `TypeError: e.message / e.modeText is not a function`；
- 异常发生在 `_render` 期间，整个组件渲染中断，DOM 停在初始 `v-if="!loaded && loading"` 的 spinner 上；
- `reload()` 里 `loaded = true` 其实**执行了**，但组件已经渲染失败，状态无人消费；
- 保存（POST）不走这条渲染路径，所以「保存能用、列表不显示」。

结论：**接口 200 + 数据正常 + 页面转圈，不等于请求有问题**，也可能是渲染期抛异常把 DOM 冻在了 spinner。

### 修法

| 文件 | 改动 |
| --- | --- |
| `app/src/components/ReaderGroupEditor.vue` | `modeText` 从 `computed` 移到 `methods` 首位（逻辑不变） |
| `tests/test_reader_group_frontend_contract.py` | 新增 3 条契约测试：computed 不得在模板里带参调用；`modeText` 必须在 methods；dist 必须含 src 独有文案 |
| `app/dist/**` | 用 `app/src` 重编（`nuxt generate`），确认新 chunk 里 `modeText` 位于 `methods` |

### 附带修复：重编把 dist 里的非构建资源清空了

`nuxt generate` 会**先清空 dist**，而 dist 里除了构建产物，还有一批手工放入的静态资源。
r22/r23 按「构建产物」口径清点（348 / 362 个文件），漏掉了 **395 个非构建资源**（15,346,411 B）：
`static/pdfjs` 369 个（PDF 阅读器，后端 `PDF_VIEWER` 指到 `web/viewer.html`）、
`static/fonts` 3、`static/wallpaper` 4、`static/images` 4、`static/js/jquery-1.11.1.min.js`、
`static/toolbox-bridge.js`、`icons/*.svg` 11、`robots.txt`、`static/pdfjs/web/viewer.html`。

对账基准：**r20（原始 build.27）dist 757 个文件，r23 只有 362 个**。这些资源不会让构建失败
（Dockerfile 只强依赖 `dist/logo`、`dist/avatar`），线上表现是图标/字体/壁纸静默 404、PDF 打不开。

处理：从 r20 包原样取回 395 个文件写入 `app/dist`，同一批写入 `public/`（`dir.static`），
以后 `generate` 自动带出；`_nuxt` 仍以新产物为准，不与旧包混用。

> 教训见《开发指南》踩坑 #18、#19；完整证据链见 `docs/故障复盘-读者组转圈.md`。
> 本版仍**只换前端产物**，装后 `Ctrl+Shift+R` 强刷。

## 4.6.0-build.27-r20（2026-11-11，可页内热更，**只有前端产物**）

> ⚠️ **本节对根因的判断已被 r24 推翻**：真实原因是 `modeText` 误入 `computed` 导致渲染中断，
> 与 `server_starting` / 永不 settle 的 Promise 无关。下面的兜底仍然有价值（它们是独立的防护），
> 但**不要**再拿「服务启动期」解释「页面一直转圈」。详见上方 r24 一节。

### 「读者组分级权限一直转圈」的根本原因（归因已被更正）

现象：设置页展开「读者组分级权限」，组列表位置一个圈一直转，不报错、不超时、刷新才好。

原因不在读者组接口本身（本地实测秒回），而在**服务启动期**：

1. 服务启动/重启（含在线更新后的重启、数据库升级）期间，端口由一个临时应答服务占着，
   它把**所有** `/api/*` 一律回成 `{"err": "server_starting"}`（`webserver/startup_status.py`）；
2. 前端 `$backend` 对这种响应 `return new Promise(() => {})` —— 一个**永不 settle 的 Promise**，
   本意是「启动期间别弹一堆错误框」，等 `/starting` 页跳转接管；
3. 但请求如果是在**导航结束之后**发出的（展开面板、mounted 补拉），`redirect()` 已经是空操作，
   页面不会跳走 —— 于是 `await` 永远挂起，`loading` 永远是 `true`，圈子转到底。

也就是说：**只要在服务启动的那几分钟里点开这个面板，就必然无限转圈**。r19 在线更新后
服务重启，用户正好在这个窗口里操作，就是本次现象。

### 修法（两层，缺一不可）

| 层 | 改动 | 效果 |
| --- | --- | --- |
| 全局 | `app/src/plugins/mybooks.js` 的 `server_starting` 分支补上与 502 分支一致的整页兜底：300ms 后 `location.assign("/starting?next=…")` | 不再默默挂起，直接进启动进度页；启动完成后自动跳回原页 |
| 面板 | `ReaderGroupEditor.reload()` 的请求加 20s 超时（`Promise.race`），超时/失败时停止转圈，显示原因 + 「重试」按钮 | 任何原因导致的「不响应」都不会再变成无限转圈 |

顺手把这个坑写进《开发指南》踩坑 #17：**用 `new Promise(() => {})` 表达「无需回调」时，
必须同时给出可见出路；任何会显示 spinner 的 `await` 都要带超时兜底。**

本版**不含后端改动**，只换前端产物；装完请 `Ctrl+Shift+R` 强刷。

## 4.6.0-build.27-r19（2026-11-11，可页内热更，**base 是 r17**）

> r18 是坏版本，**跳过它**：那版清单里的 `webserver/services/reader_group.py` 被 Gitee
> 内容审核判定违规（451），在线更新下到第二个文件就断，因此没有任何实例成功装上 r18。
> 本版 base 指回 r17，r17 实例点一次即可直上 r19（含 r18 的全部内容）。

### 在线更新报裸 `HTTP 451` 的原因与修法

现象：点「立即更新」，页面抛出一段 traceback，末尾只有 `Exception: HTTP 451`，
不知道是哪个文件、也看不出该做什么。

**451 = Gitee 的内容审核拒绝分发**（响应体：`The content may contain violation
information`）。r18 给「家庭共用」模板写的那行黑名单标签里有几个露骨/暴力词，
整份 `reader_group.py` 被判违规，raw 直链 451；`git clone` 不受影响，只有在线更新的
下载链路会断——所以这版代码在仓库里"好好的"，却谁都装不上。

实测（临时分支逐词探测，测完即删）：「血腥暴力」连排即触发，写成 `血腥,暴力`
不触发；`情色` / `色情` / `性爱` 单独出现也不触发，但叠加整段后整份文件仍被判违规。
这类判定是模型黑箱，**没法靠试词表穷举**，只能约定一条规矩：

> 仓库里任何会被 raw 下载的文件（`webserver/**`、`app/dist/**`），
> 正文里不写露骨、暴力、涉政的词组；必须出现时用中性词代替，或让管理员自己填。

同时把这条链路上的失败做成可读的：

| 以前 | 现在 |
| --- | --- |
| 报 `Exception: HTTP 451`，没有文件名 | 报「下载被 Gitee 拦截（451，内容审核）：`webserver/services/reader_group.py`」 |
| 只有一句状态码 | 附「这是发布侧问题，与本机网络无关，重试无效」+ 两条可执行出路 |
| 4xx 也重试 3 次（空等 90 秒） | 4xx（除 408/429）立刻失败；5xx/超时照旧重试 |
| 异常抛到页面，显示 traceback | `POST /api/admin/version/apply` 返回 `{err, msg}`，页面弹提示 |

发布前自检也补了一步：把清单里 86 个文件（4 个 py + 82 个前端产物）逐个用
`MyBooks-VersionCheck/1.0` 的 UA 下载并核对 sha256，确认没有 451 再打 tag。

### 本版内容（即 r18 的全部内容）

读者组模板从 4 套扩到 17 套并分两栏、「成人家属」改用「不限」模式、
黑名单空条件不再被判成读不到书、模板与本库标签的匹配度提示——详见下一节。
与 r18 的唯一差别是「家庭共用」模板的标签换了中性词。

## 4.6.0-build.27-r18（2026-11-11，可页内热更）

> 前后端都有改动（`reader_group.py` + 前端产物）。清单 `requires_dist=true`、
> `dist_hotfixable=true`，已在 r14 及以上的实例可直接点「立即更新」。

### 读者组模板扩到 17 套（分两栏），并修掉一个「模板本身是坏的」问题

**「成人家属」模板以前不能用**：它的说明写着「留空即不限权，等于全库可读」，
但实际是 `whitelist` + 空条件 —— 严格模式（默认开启）下等于**一本书都看不到**。
照着模板建组，全家账号立刻啥都读不了，而界面上只显示「白名单」，看不出问题。

修法不是改文案，是补一个真正能表达「不受限」的模式：

| 模式 | 含义 | 分类/标签 |
| --- | --- | --- |
| 白名单 | 只能读匹配项 | 留空 = 读不到任何书（严格模式） |
| 黑名单 | 屏蔽匹配项 | 留空 = 什么都不屏蔽 = 全库可读 |
| **不限（新增）** | 全库可读，不参与任何限制 | 填了也会被清空（留着只会让人误判） |

- `ReaderGroupService.save_group()` 接受 `mode="open"`；`effective_limits()` 对
  `open` 直接返回 `read_limit=0`（`source="group-open"`）。
- 前端限制方式下拉多了「不限（全库可读）」，选中后分类/标签输入禁用并给出说明，
  组列表的模式列改为三态映射。
- 老数据里已经建坏的「成人家属」（白名单空条件）**不会自动变**：打开该组，把限制方式
  改成「不限」再保存即可。

顺带修掉一个同源的语义错误：**黑名单空条件以前也被判成「读不到书」**。
`book_matches_limits()` 里 `if not 条件: return False` 对两种名单一起生效，可黑名单空条件
的语义恰恰相反（什么都不屏蔽 = 全放行）。现在按 `read_limit` 区分，白名单空条件仍然读不到书。

### 模板从 4 套扩到 17 套，按「给谁用 / 读什么」分两栏

模板菜单不再是一条长长的平铺列表：后端每条带 `group` 字段，前端按首次出现顺序
分栏渲染（`v-subheader`），菜单限高 70vh 可滚动。加模板只改后端常量，前端不用动。

**家庭与账号**（按账号身份挑）

| 模板 | 模式 | 场景 |
| --- | --- | --- |
| **婴幼儿亲子**（新） | 白名单 | 绘本、睡前故事、儿歌童谣 |
| 儿童 | 白名单 | 绘本童书、少儿科幻、国学诗词 |
| **青少年**（新） | 白名单 | 中小学必读、科普、历史、名著；比儿童宽、比访客窄 |
| **长辈听书**（新） | 白名单 | 戏曲评书、养生健康、历史散文 |
| 访客 | 白名单 | 人文与科普，屏蔽经济金融、心理励志、医学养生 |
| **家庭共用**（新） | 黑名单 | 全库可读，只挡成人向与恐怖血腥 |
| **会员**（新） | 黑名单 | 全库可读，仅屏蔽心理励志与医学养生 |
| 成人家属 | **不限** | 全库可读 |

**兴趣主题**（按内容方向挑）

| 模板 | 模式 | 场景 |
| --- | --- | --- |
| **公版经典**（新） | 白名单 | 公版名著与人文经典，对外展示的「公开书架」 |
| **人文社科**（新） | 白名单 | 哲学、社会学、法律、思想史 |
| **经管职场**（新） | 白名单 | 经济金融、管理投资、职场成长 |
| **理工科普**（新） | 白名单 | 数理化生、天文地理与科普 |
| **技术编程**（新） | 白名单 | 编程语言、算法、AI 与系统工程 |
| **历史爱好者**（新） | 白名单 | 中外通史、断代史、人物传记、军事史 |
| **科幻迷**（新） | 白名单 | 硬/软科幻、太空歌剧、赛博朋克 |
| **悬疑推理**（新） | 白名单 | 本格/社会派、日系欧美推理；不含惊悚恐怖 |
| **武侠奇幻**（新） | 白名单 | 武侠、仙侠、玄幻、网络文学 |

> 「家庭共用」和「会员」都是黑名单，区别在屏蔽面：前者挡成人向与恐怖，适合一家
> 老小共用一个号；后者挡心理励志与医学养生，适合对外订阅用户。要「完全不限制」
> 用「成人家属」的「不限」模式，别拿空白名单凑。

### 模板适配性自检：填了却看不到书，先看这里

模板里的标签名是照着一套通用书库写的，换到别的库很可能大半对不上；白名单组只认
**真实存在**的标签，对不上就是「填了也看不到书」，而且界面上毫无提示。

r18 起，载入模板后会立刻比对 `/reader_groups/options` 返回的真实标签/分类，显示：

- 「本库当前没有这些标签/分类：… （N/M 项）」+ 一键「剔除这 N 项」；
- 未命中过半时转橙色并提示「这套模板可能不适合你的书库」。

保留未命中的标签本身无害（以后导入相关书会自动生效），提示的目的只是让人知道
「现在为什么看不到书」。

测试：`TestReaderGroupService` 加 3 条（不限组全库可读且不留条件、黑名单空条件全放行、
白名单空条件仍挡书）；`TestPresets` 11 条，除模式/名字/标签归一等基础项外，还锁了三件
容易悄悄坏掉的事：模板数不少于 14、`group` 只能是后端定义的两个常量（写错字会让那一条
单独成一栏）、同栏模板必须连续（前端按首次出现分栏，中间插一条别栏的会把栏拆成两段）。

---

## 4.6.0-build.27-r17（2026-11-11，可页内热更）

> 前后端都有改动：3 个 `.py` + 重建 `app/dist`。清单 `requires_dist=true`、
> `dist_hotfixable=true`，已在 r14 及以上的实例可直接点「立即更新」。

### 悬空引用「一键重建空分组」

r16 说「打开读者组页看悬空引用告警，按组名重建分组，成员自动归位」——这句话当时是错的：
`GET /api/admin/reader_groups` 在返回列表**之前**就调了 `clear_members_of()`，把
`Reader.extra["reader_group"]` 抹掉了，告警永远为空，而唯一能恢复归属的线索也当场删了。

r17 把两件事一起改掉：

- **只报告，不清除**：`collect_groups()` 先统计悬空引用再返回，不碰 `Reader` 数据。
  留着它不是风险——`effective_limits()` 对 `group-missing` 一律按「读不到书」兜底，
  不会静默放行全库。
- **一键重建**：告警里每个组名右侧有「重建此组」，底部有「一键重建全部 N 个组」
  （`POST /api/admin/reader_groups/revive`，body `{"names": [...]}` 或缺省为全部）。
  重建出的是**白名单 + 空条件**的组，成员归属因为一直没被删，立刻自动回位。

> **重建不等于恢复可读**：空条件白名单在严格模式下等于「一本书都看不到」（有意为之，
> 宁可先挡住也不在规则没配好时放行全库）。重建后必须补填分类/标签，界面上也这么提示。
>
> **如果 r16 期间已经打开过读者组页面**，那些引用已经被当时的清逻辑删掉了，重建出来的是
> 空组，需要在「批量分配」里重新选人。这一点无法自动挽回——DB 里没有 `Reader.extra` 的历史。

顺带修掉：`POST /api/admin/reader_groups`（保存组）的响应里补上 `orphans`。原来只回
`groups`，前端 `this.orphans = rsp.orphans || {}` 会把告警清空——即使后端还有悬空引用。

测试：`tests/test_reader_group.py::TestReviveOrphanGroups` 7 条，锁住「查询不动数据」
「重建后成员仍在组里」「只重建指定组」「名字不在悬空集合里不凭空建组」
「重建的空白名单仍挡书」。反向验证过：把 `collect_groups` 改回清引用，立刻变红。

---

## 4.6.0-build.27-r16（2026-11-11，可页内热更，**只改后端**）

> 只改了 `webserver/*.py` 三个文件，`app/dist` 未动：`requires_dist=false`、
> `hotfixable=true`，可直接在「版本与更新」点在线更新并重启服务。

### 读者组分组「又没有了」的真正原因

r13 把 `READER_GROUPS` 加进了 `PERSISTABLE_KEYS`，也加了断言，为什么还丢？因为那套白名单
只在 `save_partial()` 里用来「播种」，而**设置页保存走的是另一条路**：

`handlers/admin.py: AdminSettings.post` 自己 `SettingsLoader()` + `clear()`，然后只填入
**前端提交的键**（还要再过一遍 `ADMIN_SETTING_KEYS`）。`dumpfile()` 是**整份覆盖**写
`auto.py` ——args 里没有的键，文件里就不再有。

于是「在 `PERSISTABLE_KEYS`、但不在 `ADMIN_SETTING_KEYS`」的键，每次点保存都会消失。
实测受影响的有 5 个：

| 键 | 丢了会怎样 |
| --- | --- |
| `READER_GROUPS` | 读者组分组全没了（本次报障） |
| `READER_GROUP_STRICT` | 白名单空条件是否当作「什么都读不到」回退成默认 |
| `ENABLE_KOREADER_SERVICE` | KOReader 服务被关掉 |
| `scan_hash_workers` | 扫描并发数被打回默认 |
| `site_theme` | 站点主题被打回默认 |

r13 的断言之所以「全绿但线上照丢」：它在 `save_partial` 路径上验证，而丢数据的是 `POST` 路径。

**修复**：在 `save_extra_settings()` 入口统一补齐——`CONF` 里有、`args` 里没有的持久化键
原样带回，这样 `save_partial`、设置页 POST、在线更新后写版本号、自动检测开关五条调用路径
一起覆盖。首次安装接口显式 `carry_over=False`（那里本来就该按默认值重建整份配置）。

### 顺手补上：`auto.py.bak`

`dumpfile()` 覆盖前先把上一版复制成 `auto.py.bak`（只留最近一份）。这次分组丢了没处捞，
就是因为设置文件从来没有备份——以后再被误抹，至少能从 `.bak` 恢复上一次的内容。

### 已经丢的分组怎么救

数据层没丢：`Reader.extra["reader_group"]` 里存的还是组名字符串。打开「读者组」页面，
顶部的**悬空引用告警会列出「哪些组名已经不存在、各挂了几个人」**——照着这些名字重建分组
（同一个名字），组员归属立刻自动回来，只需要把白名单的标签/分类重填一遍。
如果 NAS 开了快照（Btrfs Snapshot Replication），也可以从快照里取回上一版 `auto.py`。

> **更正（r17）**：r16 的悬空引用告警实际不会显示——列表接口在返回前就把引用清掉了。
> 真正可用的是 r17 的「只报告 + 一键重建」，见上一节。

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
