# 规格：书列表/详情“时空白、时转圈、时正常”的定位与修复

状态：待确认（Spec Mode）
范围：`C:\Users\anan\Documents\audiobook-src-opt`（源码仓库，前端 `app/`，后端 `webserver/`）
不涉及：重新出包、推送 Gitee、改数据库。

## 1. 现场与已确认事实（均为静态证据）

### 1.1 “左侧树”到底是什么

仓内**没有书籍树组件**（全仓 `v-treeview|treeview|el-tree` 0 命中）。与“左侧 + 树/目录”相关的只有三处：

| 界面 | 文件 | 内容 | 点击去向 |
|---|---|---|---|
| 全局左侧导航栏 | `app/src/components/AppHeader.vue:3-142` | `v-list-group` 静态链接（目录/有声书/作者/分类/标签/出版社/丛书），**不含具体书籍** | `:to`，同标签 SPA 跳转 |
| 目录页 | `app/src/pages/folder.vue:100-147` | `tree` 来自 `GET /api/folders`，只渲染文件夹 chip，书籍在下方卡片区 | 卡片走 `BookCards` → `/book/:id` |
| TXT 阅读器左抽屉 | `app/src/pages/book/_bid/readtxt.vue:3-22` | `content` = 章节目录（章节不是书） | `getNovelContent`，无路由跳转 |

书卡统一入口：`app/src/components/BookCards.vue:4` `v-card :to="book.href"`，`href` 在 `BookCards.vue:92-97` 生成 `/book/<id>`（有声书页为 `/audio/<id>`），**同标签**，与会话中已知结论一致。

用户新截图落在 **“所有书籍”页**：`app/src/pages/all.vue` 只是 `export default ListBook`，真实实现在 `app/src/pages/ListBook.vue`。

### 1.2 列表页数据流（/all）

1. `ListBook.vue:195-199` `asyncData` → `app.$backend(route.fullPath)`（SSR 走 `http://127.0.0.1:port/api/all` 并透传 cookie；CSR 走同源）。SSR 已设 `Cache-Control: no-cache`。
2. 后端路由：`webserver/handlers/book.py:5428` `(r"/api/all", RecentBook)`；`RecentBook` 在 `book.py:2754-2759`，`@throttle(write=True)` + `render_book_list` → `base.py:2333-2417` `get_book_list`。
3. `get_book_list` 正常永远返回 `{err:"ok", title, total, books, next_cursor}`；`books` 可能为空数组而 `total` 为 0。
4. 后端异常由 `@js`（`base.py:210-238`）兜住，HTTP **200** + `{err:"exception", msg:...}`。
5. 限流：`@throttle`（`base.py:279-300`）在 `LITE_THROTTLE` 开启且 `HeavyGate` 饱和时返回 **HTTP 503** + `{err:"busy"}`。
6. 目录 id 缓存：`base.py:1777-1783` `books_by_id_async` 按 `library_version()` 缓存；扫描/升级导致版本切换期间可能拿到空 id 列表 → `err:"ok"` + `total:0` + `books:[]`。

### 1.3 三个确定的“静默失败”点

**S1（直接对应截图）** `ListBook.vue:304-309`：

```js
this.$backend(route.fullPath).then(rsp => {
  if (rsp.err != 'ok') {
    this.alert("error", rsp.msg);   // ← 注入名是 $alert，this.alert 不存在
    return;                          // ← 列表保持 []，无任何提示
  }
  ...
})
```

`this.alert` 不是方法/计算属性/数据字段，`.then` 内抛 `TypeError` 被 Promise 吞掉：不弹提示、不写 `load_error`、`books` 保持 `[]`。全仓 `this.alert(` 只有这 1 处（`grep -rn "this\.alert(" app/src`）。

**S2（截图里“页码 1”是假信号）** `ListBook.vue:210`：

```js
this.page_cnt = Math.max(1, Math.ceil(this.total / this.page_size))
```

`total` 初始 0 → `page_cnt = 1`，所以 `‹ 1 ›` 只说明组件已创建，**不能**区分“接口空数据”和“请求失败/未返回”。

**S3（无空态）** `ListBook.vue:29-32` 的空态只对 `isPrintBooksPage`（`/printbooks`）生效；`/all`、`/folder`、`/tag` 等在 `books=[]` 时就是一片空白，没有任何文案。

另：`BookCards.vue:87-101` 对 `books` 做了 `|| []` + 可选链保护，**列表区空白不可能是子组件 render 崩**，只可能是 `books` 就是空的。这一条排除了“BookCards 渲染中断”。

### 1.4 详情页 / 阅读器链路

- `/book/:id`：`app/src/pages/book/_bookid.vue:1724-1729` `asyncData` → `GET /api/book/:id`；`created` 调 `init()`（`:2136-2143`）。`init()` 里的 `var rsp = this` 依赖 `asyncData` 把 `{err,msg,...}` 合并进组件 data，正常时 `err==="ok"` 不弹；非 ok 时 `$alert("error", msg, "/")`，`layouts/default.vue:16` 是 `v-dialog persistent`，OK 会 `$router.push("/")`。
- 阅读器：`switchToAudioPlayer` → `/audio/:id`；TXT 阅读 `readtxt.vue` 先 `GET /api/read/txt/:id` 再轮询 `/api/book/txt/parser`，自身有 `tip` 错误卡片与 30s 起跳的轮询预算，不是本次主因。

### 1.5 全局请求封装的两个“不 settle”点

`app/src/plugins/mybooks.js`：

| 位置 | 条件 | 行为 |
|---|---|---|
| `:70-89` | HTTP 502，CSR | `goStarting()` + 300ms `location.assign('/starting?next=')` + `return new Promise(() => {})`（**永不 settle**） |
| `:107-125` | body `err==="server_starting"` | 同上；SSR 返回 rsp |
| `:91-95` | 其它非 200（含 503 busy） | `$alert` 后 `throw` |

全程 **无 fetch 超时**（`session.js:31-34`、`ReaderGroupEditor.vue:454-465` 才有 `Promise.race` 超时，`$backend` 本身没有）。

## 2. 三种表现 → 失败点映射

| 表现 | 失败点 | 判定依据 |
|---|---|---|
| **列表区空白**（壳/标题/页码都在，无卡片、无空态） | S1：`/api/all` 返回 `err!=='ok'`（`exception` / `busy` / `need_login` 等）→ `this.alert` 抛错 → 静默；或 `err==='ok'` 但 `books=[]`（缓存版本竞态/限流后的空结果） | 页脚版本、侧栏计数来自其它请求，说明 JS/SSR 正常；`BookCards` 对空数组安全 |
| **整页空白**（连壳都没有） | chunk 加载失败（dist 重建后旧页面取新哈希 chunk 404）→ `chunk-reload.js` 冷却 15s 只 reload 一次；若 reload 仍命中旧 index.html 则持续白屏 | `plugins/chunk-reload.js` 注释与 `router.onError` 兜底 |
| **一直转圈** | CSR 导航中命中 502/`server_starting` → 永不 settle 的 Promise；或后端 `HeavyGate` 503 被 `mybooks.js:91-95` 抛错后路由守卫未 next | `mybooks.js:84/124`；无超时 |
| **正常** | 请求抢先成功；或 `total=0` 前页面已由 SSR 带入 `books` | — |

“同一本书重复点结果不同”的两个可解释机制：
1. `HeavyGate`/`LITE_THROTTLE` 下并发（页面 + 侧栏 + 详情子请求）瞬时饱和 → 503 随机出现；
2. `library_version()` 缓存切换（扫描/转换任务运行时）→ `books_by_id` 空表 → `total:0`。
两者都不需要前端 bug 参与就能产生随机性；S1 让它们**看不见**。

## 3. 与上一轮三件事的关系

| 事项 | 是否同源 | 说明 |
|---|---|---|
| `modeText` 修复（读者组设置） | **同类，不同 bug** | 都是“调用了不存在的成员导致异常被吞”。本轮在 `ListBook.vue:307` 找到同类 `this.alert`，需全仓扫描；`modeText` 本身不影响书列表 |
| r25 dist 重建 / 395 个静态资源恢复 | **不同链路，但可解释“整页空白”** | 只影响 chunk 哈希与 404；截图里壳、页脚、侧栏计数都正常，说明 JS 已加载，**本次截图不是 chunk 404** |
| `/starting` 跳转 | **相关但非本次主因** | 它解释“转圈”；截图中 `/starting` 已跳出，属于启动期已结束 |

## 4. 改动方案（P0，静态可定论）

### C1 `app/src/pages/ListBook.vue`

1. `data()` 增加 `load_error: ""`。
2. `init()`（:298）：
   - `this.alert(...)` → `this.$alert("error", rsp.msg || this.$t("listBook.loadFailed"))`；
   - 失败时 `this.books = []; this.total = 0; this.page_cnt = 1; this.load_error = rsp.msg || ""`；
   - 成功时 `this.load_error = ""`；
   - 保留 `if (next) next()`。
3. 新增计算属性 `initial_error()`：`this.err && this.err !== "ok" ? (this.msg || this.$t("listBook.loadFailed")) : ""`，覆盖 `asyncData` 失败、`init` 未被调用的首屏路径。
4. 模板在 `<book-cards>` 之后增加：
   - `v-if="!books.length && (load_error || initial_error)"` → `v-alert type="error" outlined` 显示错误 + 重试按钮（`@click="init($route)"`）；
   - `v-else-if="!books.length && loaded && !isPrintBooksPage"` → 灰色“暂无书籍”。
5. `created()` 增加 `this.loaded = true`（`data` 增 `loaded:false`），保证首屏也能进入空态分支。

### C2 `app/src/pages/book/_bookid.vue:2136-2143`

`init()` 改为显式判空：

```js
if (this.err && this.err !== "ok") {
  this.$alert("error", this.msg || this.$t("message.operationFailed"), null);
}
```

`to` 由 `"/"` 改为 `null`：不在用户点“确定”时强行跳回首页。

### C3 `app/src/store/index.js:108-112`

`alert` mutation 增加空值保护：`if (!v || !v.msg) return;`。这是对 `layouts/default.vue:16` 的 `persistent` 对话框的兜底，避免任何调用点传 `undefined` 时出现“关不掉的白框”。

### C4 `app/src/plugins/mybooks.js`

1. 支持按请求超时：`options.timeout`（毫秒，默认 0=不启用）。实现用 `AbortController` + `setTimeout`，超时返回 `{err:"timeout", msg:"请求超时，请重试"}`（**不 throw**，让页面能渲染错误态）。
2. 502 与 `server_starting` 的 `new Promise(() => {})` 保留 300ms 整页跳转，但增加 10s 看门狗：超时后 `resolve({err:"server_starting", msg:...})`，避免“永久转圈”。
3. 只给两个入口开启超时：
   - `ListBook.vue` 的 `asyncData`：`app.$backend(route.fullPath, {timeout: 20000})`；
   - `_bookid.vue` 的 `asyncData`：`app.$backend('/book/'+params.bookid, {timeout: 20000})`。
   不动 `/book/txt/parser` 这类长轮询（默认 0 = 关闭）。

### C5 同类写法全仓扫描（对应用户第 2 点）

新增 `app/scripts/check-vue-method-refs.js`（Node，无新依赖）：

- 扫描 `app/src/**/*.vue`；
- `<script>` 段：收集 `methods`、`computed`、`data` 返回键、`props`；找出 `this.<name>(` 中既不在上述集合、也不以 `$` 开头、也不是生命周期/内置（`$emit` 等）的标识符；
- `<template>` 段：收集 `@event="x(...)"`、`{{ x(...) }}`、`:prop="x(...)"` 中的顶层标识符，做同样比对；
- 输出 `file:line  name` 报告；默认退出码 0（只报告），`--strict` 时有命中退出 1。

在 `app/package.json` 加 `"lint:refs": "node scripts/check-vue-method-refs.js"`，**不并入 `build`**（启发式，避免误报卡构建）。

### C6 文案

在 `app/locales/zh.json`、`zh-TW.json`、`en.json` 的 `listBook` 下新增 `empty`、`loadFailed`、`retry`；并同步 `delivery/overlay/files/app/locales/*.json`（overlay 是部署用副本，必须同改，否则热更后缺 key）。

### C7 静态回归测试

新增 `tests/test_frontend_silent_failures.py`（pytest，纯文本断言）：

1. `app/src` 下不存在 `this.alert(`；
2. `ListBook.vue` 的 `init()` 含 `this.$alert(` 且含 `load_error`；
3. `ListBook.vue` 模板含 `listBook.empty` 与 `listBook.loadFailed`；
4. `store/index.js` 的 `alert(` mutation 含 `if (!v || !v.msg) return;`；
5. `node app/scripts/check-vue-method-refs.js --strict` 无输出（子进程执行，找不到 node 时 skip）。

## 5. 待证项（不猜、不改）

1. `/api/all` 到底返回 `err:"exception"`、`err:"busy"`(503) 还是 `err:"ok"+books:[]` —— 决定 S1 之外是否还要修后端缓存/限流。
2. chunk 404 是否在本次现场出现过 —— 决定是否要加强 `index.html` 的 `no-cache`（`webserver/handlers/static_files.py` 已对部分路径设 `no-cache`，需按实际命中路径核对）。
3. `LITE_THROTTLE`/`HeavyGate` 在该部署是否开启 —— 决定随机 503 的概率。

## 6. F12 最小采集（一次操作拿一项）

**动作 A（拿失败响应，优先做）**
DevTools → Network → 过滤框输入 `all` → 刷新 `/all` → 点开 `all` 请求 → 复制 Response 前 500 字符。
一次可得：HTTP 状态码 + `err` 字段（`ok`/`exception`/`busy`/`server_starting`）+ `total`/`books.length`。

**动作 B（拿 chunk 404，仅在“整页空白”时做）**
Console 粘贴一行：

```js
performance.getEntriesByType('resource').filter(r=>/_nuxt\//.test(r.name)&&r.responseStatus>=400).map(r=>r.responseStatus+' '+r.name)
```

输出为空 = 排除 chunk 404。

**动作 C（拿服务端异常栈，动作 A 显示 `exception` 时做）**

```bash
docker logs <容器名> 2>&1 | grep -E "Exception|Traceback|/api/all" | tail -40
```

## 7. 验收

1. `cd app && npm run lint` 通过。
2. `node scripts/check-vue-method-refs.js --strict` 0 命中。
3. `pytest tests/test_frontend_silent_failures.py -q` 全通过。
4. 人为制造失败（把 `/api/all` 临时改错或在 Network 里 block 该请求）后刷新 `/all`：应看到红色错误卡片 + 重试按钮，不再是无提示空白。
5. 断开后端（停容器）点侧栏进 `/all`：最多 10s 内离开“转圈”状态（跳 `/starting` 或显示错误），不出现永久转圈。

## 8. 列表性能审计（/all，按“是否随书数增长”判定）

### 8.1 每本书返回什么（问题 1）

`get_book_list` → `self.fmt(b, include_comments=include_comments, strip_comments=True)`（`base.py:2416`）→ `BookFormatter.format`（`formatter.py:197-212`）→ `SimpleBookFormatter.format`（`formatter.py:58-116`）。每本书约 35 个字段，随书数线性增长的部分：

| 字段 | 内容 | 体积 |
|---|---|---|
| `comments` | 简介，`strip_comments=True` 时截到 120 字符 + `...`（`formatter.py:72-73`） | 小 |
| `catalog` | 目录字段，**未截断**（`formatter.py:71`） | 可能较大 |
| `tags` / `authors` / `translators` | 数组 | 小 |
| `img` / `thumb` | 两个 CDN 字符串（带 `?t=` 时间戳） | 小 |
| `files` | `[{format, size: 0}]`，**不读磁盘**（`formatter.py:48-56`） | 小 |

结论：没有把完整 metadata 全塞进去（`with_files=False`、`comments` 截断），但 `catalog` 是全量，且每本书都带两份封面 URL。真实响应字节数需实测（见 8.6）。

### 8.2 分页、排序与总数（问题 2）

- 服务端分页存在：`start`/`size`（默认 `DEFAULT_PAGE_SIZE=60`，上限 `MAX_PAGE_SIZE=200`，`base.py:2346-2357`；`LITE_PAGE_SIZE` 时上限 60）。
- 排序：`/all` 走 `sort_fields="id"`，`ids.sort(reverse=True)`（`base.py:2366-2368`），全量 id 排序后切片；只加载当前页的书（`get_books_for_list_async(ids=page_ids)`），不整表取行。
- 总数：`count = len(ids)`（`base.py:2362`），**不是 `COUNT(*)`**；id 列表由 `books_by_id_async` 按 `library_version()` 缓存（`base.py:1777-1783`）。
- 已知偏差：`total` 在 `_merge_books_full`（`base.py:1327-1332`）剔除独占书/阅读范围外书之前就定了 → 尾页可能为空。

### 8.3 封面与音频标志（问题 3）

- 音频：`AudioBooksCache.get_audio_book_ids_set()`（`audio.py:233-236`）在请求路径上只做 O(1) 过期判断并触发后台扫描，**不扫盘**；`_merge_books_full` 每次请求把这个 set 取一次（`base.py:1301-1308`）。
- 封面：`SimpleBookFormatter` 只拼 URL，无 stat；`fast_get_data_as_dict` 里 `path()` 是 id→路径映射，`formats(verify_formats=False, with_paths=False)` 不做文件校验（`calibre_fast.py:96-120`）。
- 结论：本页**没有**“一本书一次磁盘 stat/读目录”的 N+1。唯一可疑的是 `x["isbn"] = self.isbn(db_id, ...)` 逐书调用（`calibre_fast.py:88`），是否触发逐书 SQL 需实测（T12）。

### 8.4 前端渲染（问题 4）

- `ListBook.vue:34-43` 一次性渲染当前页全部 `books`（默认 60，`LITE_PAGE_SIZE` 时 60，未开时用户可到 200），**无虚拟滚动/分页懒加载**。
- `BookCards.vue:3` 每张卡一个 `v-row/v-col/v-card`，`:src="book.thumb"` 无懒加载，60 张封面同时请求。
- `BookCards.vue:87-101` `render_books` 是 computed，每次重算都 `map` 全页并**直接改写** `b['href']`（改父级对象，副作用）。
- `BookCards.vue:49-56` 每条评论做 `v-html` 与长度判断（每卡一次，量级小）。
- 结论：卡顿主要来自“整页卡片 + 封面同时解码”，不来自数据量计算。

### 8.5 LIKE / 全表 Python 过滤（问题 5）

- `/all` 不做任何匹配：`RecentBook` 直接取全量 id（`book.py:2754-2759`），无 `LIKE '%x%'`、无全表 Python 过滤。
- 全表 Python 过滤只出现在 `_merge_books_full` 的可见性/独占剔除，作用对象是**当前页**，O(size) 不是 O(N)。
- `LIKE`/FTS 只在 `/api/search`（`SearchBook`，`book.py:2762+`），不在本页。

### 8.6 键集分页与 FTS 是否接上（问题 6）

- 键集分页**后端已支持**：`after`/`cursor` 参数 + `next_cursor` 响应（`base.py:2340-2344, 2381-2386, 2399-2401`）。
- 前端**没接**：`ListBook.vue:317-325` 仍用 `start=(page-1)*page_size`，且 `v-pagination` 需要跳页，`next_cursor` 只能顺序翻。这是有意保留 offset 的原因，代价是深翻页要全量排序+切片（内存操作，非 SQL）。
- FTS5 不适用：`/all` 是“全量按 id 倒序”，没有查询词；FTS 只在搜索页生效。

### 8.7 按收益排序的改法

| 优先级 | 改法 | 改动面 | 回退 |
|---|---|---|---|
| 1 | 前端 page size 上限对齐后端 200（`utils/pageSize.js`，所有列表页） | 3-5 个前端文件 | 单笔 revert |
| 2 | `content-visibility: auto` + 卡片 computed 去副作用（`BookCards.vue`） | 1 个组件 | 单笔 revert |
| 3 | `total` 与可见集合一致（`base.py`，仅过滤生效时重算） | 1 个后端文件 | 单笔 revert |
| 4 | 缓存降序 id 列表（按 `library_version`） | `base.py` 1 处 | 单笔 revert |
| 5 | 前端接 `next_cursor`，深翻页不再算 offset | `ListBook.vue` + 分页组件 | 需产品确认“跳页”是否保留 |
| 6 | 虚拟滚动（`v-virtual-scroll` 包卡片网格） | `BookCards.vue` 重构 | 改动大，最后做 |

前 3 条不改变接口契约、可独立验证；第 5/6 条等 T12 实测数字出来再决定。

### 8.8 需要的实测数字（不猜）

1. `GET /api/all?start=0&size=60` 的 `time_total` 与 `size_download`；
2. `PerfMonitor` 阶段：`fast.lock_wait` / `fast.fields` / `fast.formats` / `list.items_execute` / `list.merge_total`；
3. 单请求 SQL 次数（`Item` 1 次 + `Reader` 1 次 + 可能的逐书 `isbn`）；
4. 60 张卡片首屏的 Long Task 数量与图片解码耗时（Performance 面板）。

## 9. 风险与回滚

- C4 的 10s 看门狗只影响“永不 settle”分支，正常请求不受影响；如担心误伤，可先只做 C1/C2/C3，C4 单独一笔提交。
- C5 是启发式脚本，只报告不阻断；误报可在 `IGNORE` 名单里加。
- C6 改 locales 必须同时改 overlay，否则部署包与源码包不一致（上一轮已出现过同类漂移）。
- 全部改动不涉及数据库与后端接口契约，回滚 = revert 对应提交。
