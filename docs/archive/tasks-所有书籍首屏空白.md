# 任务清单：/all 空白排查 + 列表性能

对应规格：`spec.md`（同目录）。全部改动在 `C:\Users\anan\Documents\audiobook-src-opt`。
提交策略：每项独立一笔提交，便于单独回退；未重新出包、未推送。

- [x] **T1 修复列表页静默失败（P0，对应截图）**
  - `app/src/pages/ListBook.vue`：`this.alert` → `this.$alert`；新增 `load_error`/`loaded`/`errorText`；失败时清空 `books/total` 并置 `page_cnt=1`；模板增加错误卡片（带重试）与非打印书空态；`init()` 增加请求令牌，丢弃过期响应。
  - 验收：`load_error` 有值时渲染红色 `v-alert` + 重试按钮（模板已编译通过，0 error）。

- [x] **T2 详情页错误弹窗收紧（P0）**
  - `app/src/pages/book/_bookid.vue:2136`：改为 `if (this.err && this.err !== "ok")`，`to` 传 `null`，`msg` 为空时用 `message.operationFailed`。

- [x] **T3 告警 store 空值兜底（P0）**
  - `app/src/store/index.js`：`alert` mutation 开头 `if (!v || !v.msg) return;`。

- [x] **T4 `$backend` 超时与“永不 settle”兜底（P0）**
  - `app/src/plugins/mybooks.js`：新增 `options.timeout`（AbortController，默认 0=关闭）；502 与 `server_starting` 的无限 Promise 加 10s 看门狗；`ListBook.vue`/`_bookid.vue` 的 `asyncData` 与 `init()` 传 `{timeout: 20000}`。

- [x] **T5 同类写法全仓扫描脚本（P0）**
  - 新增 `app/scripts/check-vue-method-refs.js`；`package.json` 增加 `lint:refs`。
  - 结果：`node scripts/check-vue-method-refs.js --strict` → 0 处脚本级错误（扫描 100+ `.vue`）。

- [x] **T6 文案（P0）**
  - `app/locales/{zh,zh-TW,en}.json` 与 `delivery/overlay/files/app/locales/{zh,zh-TW,en}.json` 的 `listBook` 下新增 `empty`/`loadFailed`/`retry`。

- [x] **T7 静态回归测试（P0）**
  - 新增 `tests/test_frontend_silent_failures.py`；`pytest tests/test_frontend_silent_failures.py -q` → **8 passed**。

- [x] **T8 列表性能：前端渲染（P1）**
  - `app/src/components/BookCards.vue`：`.book-list-card` 加 `content-visibility: auto` + `contain-intrinsic-size`；`render_books` 不再改写父级书对象，改为返回浅拷贝。

- [x] **T9 page size 与服务端上限对齐（P1）**
  - 新增 `app/src/utils/pageSize.js`；`ListBook.vue`/`folder.vue`/`search.vue` 三处 `page_size`/`pageSize` 统一走 `clampPageSize(..., 60)`，上限 200。
  - 验收：localStorage `defaultPageSize=500` 时按 200 计算 `page_cnt` 与 `start`，不再出现第二页空白。

- [x] **T10 后端 `total` 与实际返回一致（P1）**
  - `webserver/handlers/base.py`：新增 `_adjust_total_excluding_sole` / `_sole_hidden_ids`（一条 SQL + 30s 缓存，缓存上限 64），`get_book_list` 用修正后的 `count`。
  - 边界：阅读范围过滤需要 tags/category，未在 total 中预计算（见 T12 结论），仅在页面层剔除。

- [x] **T11 排序与分页（P2，实测后决定：不做）**
  - 微基准（本机 Python 3）：1000 ids `0.081 ms`、10000 ids `1.252 ms`、100000 ids `18.267 ms`（sort+slice，20 次平均）。
  - 结论：10 万本时全量排序约占单请求 18ms，相比逐行取数与格式化不是主瓶颈；按 `library_version` 缓存降序 id 列表的收益不足，**不实施**。键集游标继续保留给后续深翻页需要时使用。

- [x] **T12 性能实测（只测不改，能测的部分）**
  - 静态确认的 SQL 次数（每请求）：`books_by_id` 走版本缓存 0 次；`_item_maps` 2 次（`Item ... IN page_ids` + `Reader`）；`_sole_hidden_ids` 0-1 次（仅受限用户，30s 缓存）；`isbn()` 为逐书调用，是否再查库需真机确认。
  - 未实测项（需要运行中的实例）：`curl -w '%{time_total} %{size_download}'` 的响应字节数、`PerfMonitor` 的 `fast.*`/`list.*` 阶段耗时、60 张卡片首屏 Long Task。
  - 采集命令已写入 `spec.md` 第 6/8.8 节，等环境可用时补数字。

## 完成标准

- [x] 静态检查：`npx eslint` 改动文件 0 error（1 warning 已修）。
- [x] 模板编译：`vue-template-compiler` 编译 `ListBook.vue`、`BookCards.vue` 0 error。
- [x] 回归测试：`pytest tests/test_frontend_silent_failures.py -q` 8 passed。
- [x] 后端语法：`python -m py_compile webserver/handlers/base.py` 通过。
- [ ] 真机验证（需部署环境）：block `/api/all` 看到错误卡片；停后端 10s 内离开转圈态。
