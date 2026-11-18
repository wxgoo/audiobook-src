# 历史变革（CHANGELOG）

> 本文件是项目的**唯一历史与排障档案**：逐版变更、修复原因与验证方式在正文（按修订号倒序），
> 历史排错文档的完整证据链在文末「附录：排障实录」。当前安装方式与功能见 [`README.md`](README.md)。

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
> 完整历史见 git 提交记录（`git log`）。---

## 4.7.0-build.07（2026-11-17，**SRT 识别内核升级 v1.3.0**，网页转写与 PC 版同源受益，须重建镜像）

主题：附属工具 srt-tool 整包升级到 v1.3.0（借鉴 OneAsr 的「测时间/排版分离」流水线设计）。
网页版「音频转写文稿」与 PC 版 make_srt_gui.exe 共用同一识别内核（srt_core.py），
本版同步后两者同源受益。网页 API 未变，词级时间轴是内核默认行为，升级后自动生效。

### 识别内核（srt_core.py，301 → 667 行）

- **词/字级时间轴**（`word_timestamps=True` 默认开启）：识别结果以 timeline 缓存，
  断行贴合朗读节奏；无词级时间时按字符均分，不崩。
- **断行预设** short / standard / loose：按字数、句末标点、静音间隔、最大时长断行。
- 幻觉剔除、字幕排版沿用 v1.1/v1.2 机制并随内核整体增强。

### 新增配套（PC 版）

- `srt_tools.py`：后期工具 CLI——`render` 不加载模型按 timeline 重出字幕
  （改预设/美化不用重新识别）、`transcript inspect/split/beautify`、`status --json`。
- `srt_align.py`：音视频 + 自己的文稿 → 字幕（whisper 词级时间 + SequenceMatcher 对齐）。
- `--script original|simplified|traditional`（opencc 可选，未装原样返回）、
  `--txt` / `--ass`（卡拉 OK 逐词扫光）、`--hotwords` 热词、`--events-json` 机器可读进度。
- `make_srt_gui.py`、`make_srt.py`、`build.py`、README、测试同步升级。

### 服务端兼容性

- `srt_transcribe.py` 仅调用 `transcribe_audio` / `write_srt`，v1.3 两接口均为
  旧参数严格超集、返回格式向后兼容，服务端代码零改动。
- `srt_core` 仅依赖标准库（faster-whisper / opencc 均惰性导入），容器导入冒烟通过。
- v1.3 自带 pytest 套件 58 passed + 1 skipped。

## 4.7.0-build.06（2026-11-17，**发版改号彻底一键化**，消除最后一处手工步骤，须重建镜像）

主题：build.05 取消了 `-rN`，但 `--set` 仍有一处手工遗留——`CARRIERS` 把
`docker-compose.yml` 的预期版本串写死为 2 处（旧「GIT_VERSION + 注释示例」形态），
而当前 compose 已是与上游一致的纯镜像形态、只有 1 处 image tag，`1 != 2` 导致
`--set` 拒绝盲改 compose，每次发版还得手工改它。本次把该预期改为「不限次数、
全量替换」，改号真正变成一条命令、零手工。

### 改动

- `scripts/check-version-lock.py`：`CARRIERS["docker-compose.yml"]` 预期次数 `2 → None`。
  compose 的版本串数量随形态而异（纯镜像 1 处 image tag / 本地构建 2 处
  GIT_VERSION + 注释示例），故不限次数全量替换；build 号一致性仍由校验器独立的
  compose 段强校验，放宽次数不降低防护。
- `tests/test_version_lock.py`：新增端到端用例——复刻全部载体后跑 `--set`，
  验证 compose 的 image tag 被自动改写、且改完版本锁复检直接通过（零手工闭环）。

### 验证

- 版本锁测试 13 项全绿；临时目录实测 `--set 4.7.0-build.06` 一条命令改写全部
  10 个载体（含 compose），脚本常量自动同步、复检通过。
- 本版无运行期代码/前端产物改动，改的是发版工具链，但因改了版本号，按惯例重建镜像。

## 4.7.0-build.05（2026-11-17，**取消版本号 `-rN` 后缀**，首个无 r 版本，须重建镜像）

主题：永久取消版本号里的 `-rN` 交付修订号后缀。此前每次发版 build 号由 `--set` 自动改，
但 `-rN` 要手工 r46→r47 到处补（.env / compose / README / 测试夹具 / 清单），反复残留出错。
既然 `build.N` 已在同上游基线内唯一标识每次交付，`-rN` 语义冗余，本次彻底去掉。

### 版本号简化
- 版本格式：`<上游 tag>-build.<N>`（如 `4.7.0-build.05`），不再有 `-rN`。本版 build 号由 04 递增到 05。
- 升级检测比较器 `webserver/services/version_check.py` 新增 `_ver_key()`：解析成
  `(major, minor, patch, build)` 四元组比较，正确处理跨基线 build 重置
  （4.6.0-build.27 → 4.7.0-build.01 仍判为新版本）；容忍读旧 `-rN` 串但忽略其值，
  防御 Gitee raw 旧清单缓存。`status()` / `need_persist` / admin.py / book_barn.py 四处调用点统一改用。
- 出包门禁断言：`pack.sh` / `verify-pkg-manifest.sh` 的 revision 格式断言由 `-rN` 改为
  `-build.<N>`；`sync-hotfix.sh` 的 `rev_of()` 改抽 build 号。
- `check-version-lock.py` 的 `--set` 旧值识别正则补可选 `-rN`，确保残留旧号能被整体替换。
- 新增 `tests/test_version_check_rev_key.py`（版本比较零覆盖的补齐）；相关测试夹具与 shell 测试同步改无 r。

### 影响与兼容
- 按全新安装处理，**不承担历史升级兼容负担**：老部署重装即可，无需平滑升级。
- 版本锁 `/admin/version`、清单 revision / base_revision、镜像 tag 全部改为无 r 口径。
- 历史 CHANGELOG 条目、文档示例里的 `-rN` 作为历史记录保留，不改写。
- 本版无前端产物改动，dist 保持 771 基线、index.html 哈希不变。

---

## 4.7.0-build.04-r47（2026-11-17，**WebDAV 书目树完全隔离 + 阅读范围判定收口**，纯后端+测试+文档，须重建镜像）

主题：按"尽量与上游一致"收敛——放弃 EPUB 详情页内嵌等定制，聚焦一件事：堵住 WebDAV
的越权读漏洞，并把散落两处的阅读范围判定收口成全站唯一来源。不新增任何 per-user 数据模型
或定制权限层，仍是上游 4.7.0 的"全库视图 + 用户阅读范围字段"语义，只是强制在所有出口一致执行。

### ① 公共判定模块 reading_range.py（唯一口径来源）

- 新增 `webserver/services/reading_range.py`：只依赖 `webserver.constants`，无 Tornado/wsgidav 依赖。
  把判定本体 `book_matches_limits` 从 `handlers/base.py` 迁出；`is_admin` / `reading_range_of`
  成为豁免与范围字段读取的唯一实现。
- `handlers/base.py._book_matches_limits` 改为转调公共模块（保留函数壳，既有调用点/测试不变）；
  `services/access_control.py.AccessControl.is_admin/reading_range_of` 也转调，门面与纯模块同一份语义。
- 这样网页列表 / 网页统计 / WebDAV 书目树三处共用一份判定，杜绝 r46 那种"两份口径靠人肉同步"的漂移。
  顺带修掉上游内联版的一个边界：白名单空条件不再错误放行全库。

### ② WebDAV 书目树完全隔离（高危越权读修复）

- **问题**：r46 及以前，阅读范围过滤只作用在建表枚举/列表；8 个"直接定位单本书"分支
  （category/tags/authors/recent/favorite/wants/reading/read_done 的 book_id 直链）与下载出口
  `get_content()` 完全不判定，用户凭 book_id 可读到白名单外/他人私藏的书。
- **修复**：新增 `_can_access_book()` 作为所有出口唯一校验点，顺序为：无用户拒绝(fail-closed) →
  管理员全放行 → 下架拒绝 → 他人私藏拒绝 → 全局开关关闭放行 → 阅读范围判定（重取完整元数据后
  转调公共模块）。8 个直链分支在构造资源前校验（越界返回 404），`get_content()` 在下载配额扣费前
  校验（越界 403 且不误扣费），9 个资源构造点全部传 provider 引用，无 fail-open。
- 统一 `environ` 用户解析：优先 `mybooks.user`（auth 写入的 Reader 对象），回退用户名查库，
  消除"对象/字符串混淆→误判无用户→全放行"隐患。
- `handle_authors` 只枚举可见书作者，避免作者名泄露越界书；虚拟路径层加 `normpath` + 拒绝 `..` 段。
- 与"跟上游一致"兼容：不引入任何新机制，仅把上游既有的"阅读范围"语义在 WebDAV 全出口强制一致执行。

### ③ 测试与文档

- 新增 `tests/test_reading_range.py`（判定全矩阵，dict/元数据对象两种入参）；
  扩展 `tests/test_webdav_user_isolation.py`（fail-closed、8 分支全校验、扣费前校验、路径穿越、
  作者过滤等源码核对）。新增+相关测试 53 项全绿。
- 更新 `document/WebDAV_Reader_Sync_Provider.md`：补 r47 完全隔离设计与口径单一来源说明。

### 验证与影响

- WebDAV 恒要求认证（require_authentication=True、is_share_anonymous=False），fail-closed 语义成立。
- 本版**无前端源码改动**，dist 保持 771 基线、index.html 哈希不变，pack 门禁无需改。
- 全量 pytest 的 19 个 collection error 与 r44/r45/r46 基线一致（缺 social_tornado），非本版引入。

---

## 4.7.0-build.03-r46（2026-11-17，**借鉴 anx-calibre-manager 的 4 项能力**，含前端产物，须重建镜像）

主题：把考察 `anx-calibre-manager` 后确认有价值的 4 项能力移植进来——登录失败锁定、
PWA、浏览器内 EPUB 朗读、WebDAV 用户隔离补齐。均复用项目既有基础设施，最小侵入。

### ① 登录失败锁定（LOGIN_MAX_ATTEMPTS / LOGIN_LOCK_SECONDS）

- 新增 `webserver/services/login_guard.py`：仿 `book_share_service.verify` 的失败计数，
  状态存 `Reader.extra`（JSON 列）——跨进程共享、重启不丢、免 ALTER TABLE 迁移。
  按 (IP, 用户名) 计数，达阈值写 `login_locked_until` 临时锁定，成功清零。
  密码比较改用 `hmac.compare_digest`。剩余秒数用 `math.ceil` 避免 0.x 秒被截成 0 而误放行。
- 只拦交互登录：`handlers/user.py` 的 `SignIn` 与 `handlers/wap.py` 的 `WapLogin`；
  设备凭据类入口（Basic/token/MCP/WebDAV/社交）不接入，避免合法设备被误锁。
  用户不存在与密码错误统一文案，缓解用户枚举。
- 配置贯穿：`settings.py` 默认值（5 次 / 600 秒）、`setting_saver.py` 白名单、
  管理设置页两个 number 字段、三语文案。设置页改完动态生效（无需重启）。
- 测试 `tests/test_login_lockout.py`：锁定/到期/成功清零/按 IP 隔离/配置钳制，8 项全绿。

### ② PWA（轻量手写，零新依赖）

- 新增 `app/public/manifest.json` + `app/public/sw.js` + 192/512 标准图标（从 logo 生成）。
  **图标放 `app/public/pwa/` 而非 `logo/`**：Dockerfile 构建时把 `app/dist/logo` 替换成
  指向用户数据 `/data/books/logo` 的软链，放 logo 目录的图标进镜像后会丢失导致 404
  （容器实测发现并修正）。
  sw 只缓存应用静态壳（`/`、`/_nuxt/`、`/static/`、`/logo/`、`/icons/` 等），
  **绝不缓存 API 与书籍数据**（`/api`、`/read`、`/get`、`/books`、`/s` 等），
  避免缓存私有数据/读到过期书目/串登录态。network-first 导航 + cache-first 静态资源。
- `nuxt.config.js` head 加 manifest link / theme-color / apple-touch-icon；
  新增 client-only 插件 `plugins/pwa-register.js`，仅生产环境注册 sw（配合 chunk-reload 做发版刷新）。

### ③ 浏览器内 EPUB 朗读（内置阅读器，与 MyReader 解耦）

- 默认阅读器**仍是 MyReader**（自带 TTS，不动）；只增强内置 `epubjs.html` 链路：
  注入 `static/epubreader/js/tts.js`，悬浮朗读控件（播放/暂停/停止、声音、语速）。
- 复用后端 `/api/tts/edge` 代理（GET 列声音 / POST 合成 audio/mpeg）与 word boundary 头。
  朗读文本取当前选区或可见 iframe 正文，分段合成播放；三语文案内置于 tts.js。
- 新版 dist 的 index.html head 变更导致其 sha256 变化，pack.sh 基线同步更新。

### ④ WebDAV 用户隔离补齐

- 现状已按 `reader_id` 分物理目录（`/data/reader/<id>/`，对外统一 `/reader/`），本次补齐口径：
  `dav_provider.py` 的 `_get_user_reading_range()` 增加 `ALLOW_READ_RANGE_SETTING` 全局开关判断，
  关闭时全放行，与 web 侧 `is_book_visible` 一致（此前 WebDAV 不看开关，两边对不上）。
- `settings.py` 补 `WEBDAV_SYNC_FOLDER_NAME="reader"` 默认值（此前靠 None 兜底）。
  不改设置页白名单（内部目录名，改错会导致数据目录失联）。
- 测试 `tests/test_webdav_user_isolation.py`（纯函数复刻 + 源码核对，沙箱无 wsgidav），9 项全绿。
  恢复设计文档 `document/WebDAV_Reader_Sync_Provider.md`。

### 验证

- 新增 4 组测试 31 项全绿；设置白名单契约 14 项全绿；前端 lint 0 error。
- `npm run generate` 成功，dist 771 文件（基线 766 + 5 个新静态资源），check-dist 通过。
- 全量 pytest 的 19 个 collection error 均为沙箱缺 `social_tornado`，与 r44/r45 基线一致，非本次回归。
- 基线更新：check-dist.sh / install-fresh.sh / pack.sh 的 dist 文件数 768→771，
  pack.sh 的 index.html sha256 更新为 r46 新值。

## 4.7.0-build.02-r45（2026-11-16，**移除读者组定制层 + 统一权限判定**，含前端产物，须重建镜像）

主题：把权限体系从「6 套机制并行、口径靠人肉同步」收敛到与上游 4.7.0 一致，
并消除历史上反复出现的「计数与列表口径不一」「管理员豁免这边写那边漏」类 bug。

### ① 关键前提：读者组是我们独有的定制，上游 4.7.0 根本没有

实测上游 4.7.0 的 `handlers/__init__.py` 路由与 `services/` 目录都没有 `reader_group`，
但**上游有完整的「按用户阅读范围限制可见书籍」能力**：`Reader.read_limit/limit_tags/
limit_categories` 字段 + `BaseHandler.is_book_visible()/is_book_in_reading_range()` +
`ALLOW_READ_RANGE_SETTING` 开关。两者逐行等价。所以本次精确区分：

- **删掉「组」这一层**（我们加的封装）：`READER_GROUPS`/`READER_GROUPS_ENABLED`/
  `READER_GROUP_STRICT` 三个设置键、`services/reader_group.py` + `handlers/reader_group.py` +
  `ReaderGroupEditor.vue`、17 套预置模板、`Reader.extra["reader_group"]` 成员归属、
  `effective_limits()` 的组回退逻辑。
- **保留「阅读范围限制」**（上游也有的正式功能）：每个用户自己的三个字段 + 全局开关，
  判定回退到直接读用户字段（与上游逐行等价）。

### ② 数据迁移（保住靠组继承的限制）

新增 `scripts/migrate_reader_group_to_fields.py`：遍历 Reader，删除前调 `effective_limits()`
算出生效限制，仅对「自身无显式设置」的用户写回 `read_limit/limit_tags/limit_categories`
（有自身设置的保持原值；`group-missing` 哨兵也固化，避免删组后权限静默全开）。
支持 `--dry-run` 预览、执行前自动备份 sqlite、交互确认。随镜像发布，升级后可选执行。

### ③ 判定回退上游口径（base.py + 4 个调用点）

- `webserver/handlers/base.py` 7 个判定块（`is_book_visible` / `is_library_restricted` /
  `is_book_in_reading_range` / `_filter_tags` / `_filter_categories_by_reading_range` /
  `_scope_key` / `_build_scoped_counts`）从 `effective_limits()` 改直读用户字段。
- 判定本体收口到模块级 `_book_matches_limits()`（从被删的 reader_group 搬入）：比上游内联版
  更严谨——白名单空条件=什么都看不到、黑名单空条件=全库可读、分类与标签「或」关系。
  书列表与统计共用同一函数，根治「树里 328 本点进去 12 本」。
- `audio.py` / `meta.py` / `podcast_provider.py` / `dav_provider.py` 的调用点同步改上游口径。

### ④ 统一权限门面 AccessControl（用户选的"统一判定入口"）

现实核查：5 套机制里，`BookAccessService`（访客/分享）、`modules`+`ModuleGateMixin`（模块）、
`Reader.can_*`（操作权限位）**本身已是门面**，再包一层只是换名字、零收益且冒回归风险。
所以门面只做两件有价值的事：

- **真正散落的管理员豁免收口**：新建 `webserver/services/access_control.py`，
  `is_admin()` 成为单一口径来源；`BaseHandler.is_admin()` 内部转调门面——
  **74 处调用点一行不改**即获得一致口径（零回归风险）。
- **统一 import 入口**：re-export `BookAccessService` / `modules` 的判定（纯别名，不复制逻辑），
  新代码从一个模块 import 即可。

### ⑤ 顺手修的口径不一致（用户同意"顺手修+加回归测试"）

- `is_library_restricted()` 原来没检查 `ALLOW_READ_RANGE_SETTING` 全局开关：开关关闭时
  用户实际能看全库，却被误判"受限"、错误隐藏统计页。现加开关前置，与 `is_book_visible`
  同前提；加回归测试 `test_is_library_restricted_respects_global_switch`。

### ⑥ 清理与验证

- 删除 5 个读者组测试；改写 5 个引用 `effective_limits` 的测试为直读用户字段口径
  （audiobooks category/list、catalog_categories、setting_saver、version_dist_paths）。
- 三语文案删 130+ 个读者组键；前端 settings.vue 删读者组设置区块与组件；重编 dist
  （reader_group/读者组命中 0 个 chunk）。
- 新增 `docs/权限判定对照表.md`：5 套机制 × 典型场景逐格预期，作为回归与验收依据。
- 验证：权限相关单测 115 passed；可执行全量 2187 passed / 18 failed（18 个均为
  `social_tornado` 缺失的环境问题，与 r44 基线逐条一致）；前端 lint 0 error、generate 成功；
  容器实测三条主链路见下方发布记录。


---

## 4.7.0-build.01-r44（2026-11-16，**跟随上游 4.7.0**，含前端产物，须重建镜像）

> **版本号随上游基线整体改号**：我们按主题合入了上游正式发布的 `4.7.0`，
> 因此运行期版本从 `4.6.0-build.28` 改为 **`4.7.0-build.01`**（新基线上的第一次构建）。
> 交付修订号 `r43` → `r44`（镜像 tag 变了，等于新的交付点）。
> `scripts/check-version-lock.py` 随之改造为**基线可配置**：基线段与构建号段分开判定，
> 换基线时构建号允许重置为 1，同一基线内构建号只能递增。

这是本项目第一次**按「跟随上游」的流程**走完整一轮：拉上游 → 规模评估 → 逐文件三方比对
→ 逐条判定 → 移植。工具与判定报告见
[`docs/跟随上游-4.7.0-判定报告.md`](docs/跟随上游-4.7.0-判定报告.md) 与
`scripts/upstream/follow-upstream.py`。

### ① 上游现状（脚本实测）

上游已发 **`4.7.0`**（我们基线 `4.6.0`），`4.6.0..4.7.0` = **114 提交 / 176 文件**
（+18999 / −8133 行）。三方比对结果：**可自动吸收 111 / 需人工判定 58 / 仅我们有 7**，
禁止整体合并 1（`webserver/settings.py`，上游默认值与键名有破坏性变更）。

> **关键前提**：我们与上游**没有共同祖先**（仓库是「导出上游源码」建的，
> 上游 git 历史不在本仓库里），所以 `git merge` / `rebase` / `cherry-pick` 全部不可行。
> 跟随上游只能「文件级三方比对 + 逐条手工移植」。

### ② 安全类逐条核对：**这一轮上游没有安全漏洞需要我们补**

| 上游提交 | 内容 | 我们的状态 | 判定 |
|---|---|---|---|
| `755b4f08` / `ef30fa83` | 封面背景图库路径穿越、并发写 | 无此功能（无 `cover_background.py`） | 不跟（无攻击面） |
| `8f629701` / `8142ee83` | 图库上传权限与文件类型校验 | 同上 | 不跟 |
| `c0245c78` | 匿名 OPDS 收紧登录闸 | `opds_anonymous_allowed()` 未接线 → 匿名入口不存在 | 不跟 |
| `8ccab741` | 必须登录时下载直链回 401 挑战 | **已有**（`opds.py` 设了 `WWW-Authenticate` + 401） | 已吸收 |
| `f3fde9ff` / `fd1c605f` | 社交注册新用户漏默认权限 | 无社交注册路径 | 不跟 |

### ③ 已吸收：上游修了我们早就修过的问题

- `63cab1d7`（dev 模式首页落到「服务正在启动中」）：我们的 `AppHeader.vue` 早已用
  `commit("sync_sys", rsp.sys)` + `language !== 'auto'` + footer 不回写 `rsp.sys`（r35 修的同一处）。
- `bac37687`（侧边栏登录按钮样式）：我们已有 `.login-button` 高亮样式。

### ④ 移植一：模块化门控接线（**本轮最大项**）

**发现**：我们早就有 `webserver/base/modules.py`（模块表 + `ModuleGateMixin` 全套实现），
但**一个 handler 都没接**——设置里的模块勾选框存在，开了没用。这是典型的「有能力、
无接线」半成品。

按上游口径接了 **47 处**：

| 文件 | 处数 | 模块 |
|---|---|---|
| `handlers/audio.py` | 14 | `MODULE_AUDIO`（含我们比上游多的 Replace / ChapterDelete / ChapterUpload 等） |
| `handlers/booklist.py` | 13 | `MODULE_SHARED_READING` |
| `handlers/share.py` | 5 | `MODULE_SHARED_READING` |
| `handlers/scan.py` | 4 | `MODULE_AUDIO` / `MODULE_PHYSICAL` |
| `handlers/toolbox.py` | 4 | `MODULE_AUDIO` |
| `handlers/admin.py` | 4 | `MODULE_MULTIUSER` / `MODULE_SHARED_READING` / `MODULE_AI` |
| `handlers/book_review.py` | 2 | `MODULE_SHARED_READING` |
| `handlers/tts.py` | 1 | `MODULE_AUDIO` |

（上游 57 处比我们多 10 处：那些类我们没有，不是漏接。）

配套改动：

- `handlers/base.py` 5 处：下发 `sys.modules` 快照；`socials` 受多用户模块影响；
  `ai_enabled` / `mynexus_enabled` 受 AI 模块影响；**统计缓存 key 带上模块状态**
  （否则关模块后计数不刷新）。
- 前端 `AppHeader.vue` 9 处：新增 `moduleOn(id)`（**默认开启、只有显式 `false` 才关**，
  防首屏入口闪没），用于有声书入口、书单、留言、友情链接、用户管理、期望书单、AI 按钮、留言对话框。
- 设置页新增「功能模块」区块（6 个勾选框）+ 三语 15 个文案；模块开关进
  `PERSISTABLE_KEYS` / `ADMIN_SETTING_KEYS`。
- 新增 `tests/test_module_gate_wiring.py`（7 例）：门控接线、文件流走 404、
  漏写 `module_id` 即炸、开关可逆且**不删数据**。

### ⑤ 移植二：扫描导入忽略目录 `SCAN_IGNORE_DIRS`（上游 `0d7dc96b`）

我们刚做完自动导入，「哪些目录不参与扫描」是刚需，上游这一轮正好补上。

- 后端 `services/scan_service.py`：`_scan_ignore_dir_names()` 归一化 +
  `_is_ignored_scan_subpath()` 路径判断；**双防线**——遍历层在 `os.walk` 的 `dirnames`
  里直接剔除（不进入该目录，后代自然排除），路径层挡住「显式扫描路径」与
  「并入待处理记录」两条绕过路径。
- 服务端清洗 `handlers/admin.py` 的 `sanitize_scan_ignore_dirs()`：与前端校验同口径，
  形成双重保障。
- 前端新增 `components/ScanIgnoreDirsEditor.vue`（非法名/重名阻止保存）+
  设置页「导入规则」区块接入 + 三语 7 个文案。
- 新增 `tests/test_scan_ignore_dirs.py`（18 例）：归一化、路径判断、服务端清洗。

### ⑥ 工具：重建「跟随上游」能力

- 新增 `scripts/upstream/follow-upstream.py`：`fetch` 拉上游 → `assess` 评估规模 →
  `compare` 逐文件三方比对出冲突矩阵。只读本仓库、只用标准库、冲突判定真做三方合并、
  CRLF 归一、硬约束 `webserver/settings.py` 始终进「禁止整体合并」。
- 新增 `tests/test_follow_upstream_tool.py`（7 例）锁工具契约。
- 上一笔清理删掉的「跟随上游」方法论（原 `docs/上游比对与跟进-4.6.1.md`，25KB）
  已全文并入本文件「跟随上游：方法论与实况」一节，并更新为当前实况。

### ⑦ 暂不移植的（判定理由见报告）

访客按 IP 每日下载配额、阅读历史按书/按天删除、书籍字数统计、AI 聊天对话框
（与我们 `MyNexusChatDialog` 重叠）、封面背景图库（含安全面，要跟得连安全修复一起带）、
PDF 阅读器切换（待比对是否等价）。另：`app/pnpm-lock.yaml` 不手工合并（重新 `npm ci`）、
`app/src/assets/fonts/*.woff2` 与 favicon 是素材不是功能。

### 验证

- 受影响用例 **95 passed**（门控 7 + 忽略目录 18 + 友链 4 + sys_info + sidebar + 版本锁 + 清单 + 安装入口）；
- 前端 `npm run lint` 0 error；`npm run generate` 重新出 dist（`moduleOn` / `scan_ignore_dirs` /
  `shared_reading` 均在产物中）；
- 全部 shell 与 py 文件语法通过。


---

## 4.6.0-build.28-r42（2026-11-16，**镜像级变更，须重建镜像**，含文档重构）

本次是**安装口径与文档体系的一次性对齐**，加上两个 bug 修复与一个功能显性化。
运行期版本升到 `4.6.0-build.28`（八处版本载体由 `scripts/check-version-lock.py --set` 统一改写）。

### ① 文档体系收敛为两份（本次最大动作）

**只保留**：

| 文件 | 定位 |
| --- | --- |
| [`README.md`](README.md) | **唯一安装 / 使用文档**：GHCR + 纯 `image:` compose、`.env` 三项、数据与备份、升级、功能清单 |
| [`CHANGELOG.md`](CHANGELOG.md) | **唯一历史与排障档案**：逐版变更（倒序）+ 文末「附录：排障实录」 |

**已删除**（内容要么过时、要么已并入上面两份）：

- `docs/` 整个目录（38 个文件）：部署包说明、部署方式速查、操作总纲、在线更新说明、备份与恢复演练、
  NAS-Docker 缓存池手册、开发指南、上游比对与跟进、待修复项、目录功能说明、支持的图书格式、
  版权下架说明、字幕生成与播放、HTTPS 真证书申请、MCP/Skill 上手卡、`docs/archive/` 全量；
- `INSTALL_GUIDE.md`（1526 行）：Windows 部署、源码构建、legacy builder 避坑等内容已过时，
  其**功能章节**（读者组、音频转写、有声书挂靠、MyReader）与**排错章节**分别并入 README 与本文件附录；
- `delivery/` 旧 NAS 交付目录（all-in-one.patch、各 zip、overlay 冻结快照）：上一代「构建包」体系产物，
  与现在的成品镜像方式无关；
- `scripts/watch-upstream.py`（引用的 `docs/upstream-baseline.json` 从未存在，功能已废）；
- `scripts/install-online.sh` + 其契约测试（「从 Gitee 在线取包再本地构建」路线，与 GHCR 拉镜像冲突）；
- `apply_radio_fix.py`（一次性修复脚本，无引用）。

**排错内容并入历史变革**：原三篇独立排错文档（`故障复盘-所有书籍首屏空白`、`故障复盘-读者组转圈`、
`故障复盘-豆瓣v1残留500`）全文并入本文件文末「附录：排障实录」，**保留完整证据链与走过的弯路**，
按现象检索即可。

### ② 安装口径改为与上游一致（纯 image，无 build）

`docker-compose.yml` 与 `.env.example` 从「本地 build + `mybooks-local:latest`」改为
**成品镜像 + 只有 `image:`**（`${IMAGE_TAG:-ghcr.io/wxgoo/audiobooks:4.6.0-build.28-r42}`）：

- 交付给别人时不需要 clone 源码、不需要在本机构建，也就不再出现
  `layer does not exist`（legacy builder + btrfs 的老 NAS 事故）；
- 仓库根 compose 此前是「作者本机自建」口径，与实际给别人的交付包口径**长期不一致**——本次统一；
- `scripts/check-version-lock.py` 的 compose 检查随之分两种形态：
  有 `build:` 段 → 查 `GIT_VERSION` 与运行期版本一致；只有 `image:` → 查镜像 tag 的构建号段一致。

### ③ 修 bug：非管理员看不到友情链接

- **根因**：前端用 `showItem("friends")` 决定友链分组显隐，它依赖 `sys.sidebar_items`；
  而 `SIDEBAR_ITEMS` 在「管理员保存过设置页 + 存下的列表恰好是旧默认（缺 friends/authors/booklists）」时，
  会被 `SIDEBAR_ITEMS_MIGRATED` 标记判成「管理员主动取消勾选」而原样返回，**friends 被永久吞掉**。
  这与用户身份无关，前台所有用户都看不到。
- **修法**：友链显隐**解耦**出 `SIDEBAR_ITEMS`，改由独立站点开关 `ENABLE_FRIEND_LINKS`（默认 True）
  决定，经 `sys.allow.friend_links` 下发；前端用
  `allow.friend_links ?? showItem("friends")` 判显隐——新后端走独立开关，老后端回退旧逻辑（兼容）。
- 设置页新增「显示友情链接」开关（站点与外观区），三套 locale 同步补文案；
  `ENABLE_FRIEND_LINKS` 已进 `PERSISTABLE_KEYS` / `ADMIN_SETTING_KEYS` 白名单，不会被无关保存抹掉。
- 新增 `tests/test_friend_links_visibility.py`（4 例）锁定：缺省为真、显式关为假、
  与 sidebar 迁移彻底解耦、前端走独立开关。

### ④ 图书类型互转（电子书 ⇄ 实体书）显性化

- 该功能**其实早已完整存在**（后端 `BookExchangeType` + `/api/book/exchange_type`、
  前端对话框与批量处理菜单入口、`ENABLE_BOOKS_TYPE_CONVERT_DIRECT` 开关），
  但入口藏在「批量处理」折叠菜单里、且需先勾选书才能点，因此一直像「没引用」。
- 本次在图书管理页工具栏**新增独立橙色按钮**「图书类型互转」（选中书后出现，实体书功能开启时显示），
  与菜单入口复用同一对话框与方法；README 已写明入口位置与「无 ISBN / 已有电子书格式默认跳过」的规则，
  以及想直接转就去设置里打开「允许直接转换类型」。

### ⑤ 镜像 OCI label 改回自己的口径

`Dockerfile` 的 `org.opencontainers.image.*` 原本指向**上游** `PoxenStudio/mybooks`
（`vendor=PoxenStudio`、`source=https://github.com/PoxenStudio/mybooks`），
GHCR 包页面 Details 里有一部分字段就是取自它，会误导看包的人。现在改为：

- `vendor=wxgoo`、`source`/`url`/`documentation` → `https://github.com/wxgoo/audiobook-src`
- `title=mybooks (audiobook 定制版)`，补 `description`；`Author` 改为 wxgoo，`Thanks` 保留上游致谢。

> label 只能在**构建时**写入，所以这次随新版镜像一起生效；不必为它单独重建已有镜像。

### ⑥ 顺手清掉的口径残留

- `version_check.py` / `gen-update-manifest.py` 里「请重新执行 deploy.sh / upgrade.sh」的提示
  改为「把 `.env` 的 IMAGE_TAG 换成新 tag 后重新 `docker compose up -d`」；
- `gen-update-manifest.py` 的 `DOCS_EXACT` 去掉已删的 `INSTALL_GUIDE.md`；
- `tools/category_backfill.py`、`scripts/upstream/patch_tool.py`、`scripts/README.md`、
  `.claude/memory/MEMORY.md`、`CLAUDE.md` 里指向已删文档的链接全部改指 README / CHANGELOG。

### 验证

- `pytest tests/`：**2282 passed**（另有 22 failed + 224 errors 属**基线环境问题**：
  缺 `social_tornado` / calibre / MCP 依赖，与本次改动无关；装 `social-auth-app-tornado` 会与项目
  models 的 `social_auth_usersocialauth` 表定义冲突，制造 224 个假 error，**不要装**）；
- 新增与受影响的针对性用例 **60 passed**（友链可见性、sidebar 迁移、sys_info、安装入口契约、清单白名单）；
- `app` 前端 `npm run generate` 重新出 dist（768 文件 / 143 个 `_nuxt` chunk），
  `npm run lint` 0 error；dist 关键路由页与友链开关均在产物中；
- `scripts/check-version-lock.py` 八处载体全绿。

---

---

## 交付补充（2026-11-15，**不新增 revision**，同 `r38` 重出整包 + 新增镜像离线包）

改动只在**部署方式**，站点运行代码一行没动，所以 `/admin/version` 仍是 r38、不需要热更、线上站点无感。`update/manifest.json` 字节不变。

- 新增 `scripts/install-from-tar.sh`：解压部署包后的**一键全新安装入口**，不需要 git、不需要 clone。
- `scripts/install-fresh.sh` 收敛为**唯一一份安装逻辑**：去掉「缺 git 就退出」的硬依赖（tar 包机器可能没装 git），只有存在 `.git` 时才要求 git；`.git/info/exclude` 写入改为条件执行；升级提示从 `git pull` 改为页内「立即更新」/换包。
  两个入口是「薄封装 → 统一入口」关系，避免两套逻辑以后改一处忘另一处（r36/r38 的教训）。新增 `tests/test_install_entrypoints_contract.py` 12 例锁定这个关系。
- `scripts/pack.sh --check` 增加**成对校验**：包里只要出现两个安装入口之一，就必须两个都在；老包两个都没有照样放行，不会误报。
- `scripts/pack-image.sh`：`docker save -o` 受 umask 影响常生成 `600` 权限，拷给别人（尤其经 Windows/网盘）会读不到，压缩后钉成 `644`。

**两条全新部署路线（新老兼顾）**：

| 路线 | 给谁 | 交付物 | 是否构建 |
| --- | --- | --- | --- |
| A 镜像离线包 | 老 NAS（btrfs/legacy builder）、离线、想最省事 | `mybooks-image-4.6.0-build.27-r38/`（923MB：`docker load` 即用 + 只有 `image` 没有 `build` 的 compose + `.env.example` + README + SHA256SUMS） | **零构建、零联网** |
| B 整包一键安装 | 新 NAS / 普通 Linux、可联网 | `audiobook-deploy-4.6.0-build.27-r38.tar.gz`（153MB，含新入口）+ `sh scripts/install-from-tar.sh` | 走预构建 dist 快路，仍需拉基础镜像 |

两条路线装完，r39+ 都走页内「立即更新」，不必重发大包。镜像离线包已在本机做过端到端自检：删 tag → `docker load` → 用交付 compose 起容器 → 4 个进程 RUNNING / 首页 200 / API 200 / 数据目录自动初始化。

---

## 4.6.0-build.27-r38（2026-11-14，**修「明明改成教育了却没进教育分类」**，纯后端，可热更）

- 症状：详情页把一本有声书的分类改成「教育」，有声书页的 tab 仍是
  `全部(100) / 教育(2) / 文学(1) / 科幻小说(4) / 社科(1)`；点进「教育」
  也看不到那本书。强刷、重开页面无效，**重启容器才自愈**。
- 根因（**不是前端、不是 dist、不是分类接口没数据、不是书没写进库**）：
  `audio_category_agg` 的模块级快照只跟随
  `AudioBooksCache.get_version()` 失效，而那个 version 表示「**有音频的书
  集合**」是否变化。改 `#category` 是 calibre 元数据写入，集合一本没变，
  version 纹丝不动 → 快照一直旧。分类 tab 的 count
  （`build_audio_tab_categories`）与 `?category=X` 的列表过滤
  （`AudioBooks.get` 里的 `allowed`）**都读这份快照**，所以两处同时不更新。
  反差佐证：分类名骨架 `catalog_categories()` 用 `library_version()` 做缓存
  key，是实时的——所以 tab 名字/顺序对，只有数字和归属旧。
  实证：缓存 10 本时教育为 `[1,2]`；DB 改成教育后 tab 仍 `教育(2)`；
  强制重算一次立刻变 `教育(3)`，证明 DB 已写入、只是缓存没失效。
  另有一处隐患：即使 version 变了但集合没变，原「集合增量」分支
  `added/removed` 都为空，会**什么都不重算却把 version 推到最新**，
  把旧元数据永久钉死。
- 修复（**不动 `app/dist`，纯 py 可热更**）：
  - `audio_category_agg.on_category_changed()` / `on_categories_changed()`：
    改分类成功后**按调用方手上的新值直接挪桶**，O(1)、不读 calibre 元数据
    （绕开 `new_api` 在 `set_field` 之后未必即时反映新值的缓存层），保留
    该书 `tags`/`authors`（受限用户可见性 `_visible_audio_ids` 读的就是这份
    `book_meta`）。只处理已在有声书集合里的书，集合未建好/该书无音频时忽略。
  - `library_version()`（metadata.db + -wal 的 mtime）兜底 + `invalidate()`：
    漏通知的写入（`set_metadata`、外部 calibre 工具、导入脚本、独立进程的
    AI 填信息）会推进库版本，触发**后台全量重建**（单飞 + 20s 节流），
    保持「请求路径零阻塞」的既定约定，秒级自愈。
  - 元数据脏时**禁止**走集合增量空转分支；`force` 同步重建与后台重建都会
    写回 `lib_version`、清 `meta_dirty`，不会反复重算。
  - 全仓 9 处 `set_field(#category, ...)` 入口全部接线：详情页改分类、
    批量改分类、清空分类、批量元数据编辑、MCP 改书信息、AI 自动填信息、
    导入按目录名设分类、重命名分类目录、移动文件。
  - 新增 AST 契约测试 `tests/test_category_change_notify_contract.py`：
    强制**每个**写分类的函数内必须出现 `audio_category_agg` 的通知调用，
    以后新增入口忘了通知会直接让测试失败，而不是等用户在 NAS 上发现。
- 边界：只有**带音频的书**才会出现在有声书分类 tab；无音频的书改成任何
  分类都不会进（这是口径，不是 bug）。独立进程写入靠库版本兜底，允许秒级
  滞后；站内改分类走即时通知，零延迟。
- 测试：新增 `tests/test_audio_agg_category_change.py`（14 例）与契约测试
  （3 例）；音频/分类/设置/扫描相关回归 **316 passed / 4 skipped**。
  （`test_scan_p0.py` 的全角折叠语义用例在 r37 之前 HEAD 基线上同样失败，
  与本次改动无关；2 个测试文件因沙箱缺 `social_tornado` 无法收集。）

---

## 4.6.0-build.27-r37（2026-11-14，**修「监控导入目录勾了不响应」+ 有声书目录自动导入 + 两个死开关**，纯后端，可热更）

- 症状：设置页「导入与存储 → 自动导入」勾了「监控导入目录，自动进行导入」，
  经 SMB 往 `\\<NAS>\docker\audiobook-data\books\imports\audiobooks\` 放整本
  有声书（每个子目录一本书、几十个音频分片），书库毫无反应。
  现场诊断：`auto.py` 里 `IMPORT_BY_INOTIFY=True`、`scan_upload_path` 正确、
  导入目录存在、`inotify_simple` 已装、日志有 `[Monitor] started`，
  但**日志里一条 `[Monitor] Event:` 都没有**，且明确有一行
  `[Monitor] Skipping imports folder: /data/books/imports/audiobooks`。
- 根因（**勾选本身是生效的，是开关覆盖不到用户放的那个目录**）：
  1. `monitor_service` 只管电子书，`_add_watch_recursive` 明确跳过
     `constants.AUDIO_BOOK_IMPORTS`（即 `audiobooks`）目录；且事件过滤只认
     `CLOSE_WRITE` / `MOVED_TO`，`CREATE` 一律不入队，3 秒防抖对经 SMB
     拷贝几分钟的整本有声书也太短。有声书归 `AudioBookImporter` 管，
     而它**只有管理页「导入有声书」按钮一个触发入口**（`AudioImportRun`），
     既无定时也无文件事件 —— 所以「自动导入」对有声书从来不存在。
  2. 审计设置页 51 个勾选框发现 **2 个死开关**：
     `AUDIO_LINK_TO_EXISTING_BOOK`、`ENABLE_KOREADER_SERVICE` 未登记进
     `ADMIN_SETTING_KEYS`。`AdminSettings.post` 用 `KEYS=list(ADMIN_SETTING_KEYS)`
     过滤提交，漏登记的键被**静默丢弃**；前者连 `PERSISTABLE_KEYS` 都没登记，
     保存设置时 `dumpfile()` 整份覆盖还会把手写进 `auto.py` 的值抹掉。
     实测：前者根本不在 `auto.py` 里，后者在但永远是改不动的旧值 `True`。
  3. r36 遗留：`settings.py` 里 `AUDIO_CACHE_REFRESH_SECONDS = 6*3600` 会被
     `loader` 灌进 `CONF`，**覆盖** `audio.py` 里改成 300 的 fallback —— r36
     声称的「兜底 6 小时 → 5 分钟」实际没生效（主修复 `sync_from_scan` 不受影响）。
- 修复（**不动 `app/dist`，纯 py 可热更**）：
  - 新增 `webserver/services/audio_auto_import.py`：跟随 `IMPORT_BY_INOTIFY`
    启停的轮询服务。指纹覆盖 `imports/audiobooks/` 一级子目录内所有音频文件的
    `(相对路径, size, mtime_ns)`，忽略封面/字幕/`@eaDir`/临时文件；
    **指纹连续两轮一致**才触发 `AudioBookImporter.do_import`，避开慢拷贝中途；
    触发前检查导入互斥，忙时**不「消费」这次变化**，下一轮补触发；
    幂等由 `AudioBookImporter` 自身的 `audiodir:` + 路径 MD5 判重保证，
    已导入目录只补同步新增音频、不会重复建书（最终一致）。
  - `main.py` 启动接线；`setting_saver._apply_dynamic_settings()` 让开关改动
    **即时启停**，不用重启容器。
  - 把 `AUDIO_LINK_TO_EXISTING_BOOK`、`ENABLE_KOREADER_SERVICE` 补进白名单，
    并登记 `AUDIO_AUTO_IMPORT_ENABLED` / `AUDIO_AUTO_IMPORT_INTERVAL`（暂无 UI，
    可手工写进 `auto.py` 且不会被保存设置抹掉）。
  - `settings.py`：兜底间隔对齐 r36 意图改为 **5 分钟**，并注明「改间隔要改这里，
    它会覆盖 audio.py 的 fallback」；新增两个自动导入配置。
  - 契约测试 `tests/test_settings_checkbox_whitelist.py`：强制设置页**所有**
    `type: "checkbox"` 的键都在 `ADMIN_SETTING_KEYS` 里，防止再漏。
- 行为与配置：默认开启、轮询 60 秒、稳定 2 轮 ⇒ **放完文件约 2 分钟内自动入库**。
  想只保留电子书监控，在 `auto.py` 加 `'AUDIO_AUTO_IMPORT_ENABLED': False,`
  后重启；调间隔改 `AUDIO_AUTO_IMPORT_INTERVAL`（最小 20 秒）。
  本轮**没做设置页状态显示**（会动 `app/dist`，需重新构建，留待下一轮），
  运行状态看日志 `[AUDIO_AUTO]` / `[AUDIO_IMPORT]`。
- 测试：新增 `tests/test_settings_checkbox_whitelist.py`（3 例）与
  `tests/test_audio_auto_import.py`（10 例，覆盖指纹稳定性、噪声文件忽略、
  忙时不消费、禁用开关、启停幂等）；设置/音频/扫描相关回归
  **350 passed / 4 skipped**。另有 1 例
  `test_scan_p0.py::TestTitleDedupIndex::test_semantics_parity_with_icu_lower`
  （全角字符折叠语义）在 **r37 之前的 HEAD 基线上同样失败**，与本次改动无关；
  2 个测试文件因沙箱缺 `social_tornado` 无法收集，亦与本次改动无关。
- 部署：r36 → r37 为纯 `webserver/**/*.py` + `tests/**`，页内「立即更新」→ 强刷；
  `app/dist` 与 r34/r35/r36 同指纹，`hotfixable=true` / `requires_dist=false`。

---

## 4.6.0-build.27-r36（2026-11-14，**修「手工加音频后统计 +1 但分类 tab 不更新」**，纯后端，可热更）

- 症状：r35 装好后分类 tab 正常出现（默认「全部」+ 已有分类）。用户手工往某本书的
  `.audio/` 目录补了音频后，**左侧菜单「有声书 N」立刻 +1**，但页面右侧的分类 tab
  纹丝不动，新加那本书所属的「文学」分类始终不出现。强刷、重开页面都无效。
- 根因（**不是前端、不是 dist、不是分类接口**）：站内「有声书」这个维度有两套互不知晓的口径。
  左侧菜单计数来自 `BaseHandler.get_audio_books_count()`，它**每次请求都
  `find_audios_by_scanning_library()` 实时全库扫盘**，所以手工塞文件立刻 +1；
  而 `/api/audiobooks` 的书列表、分类 tab 读的是 `AudioBooksCache` +
  `audio_category_agg`（**事件驱动 + 兜底扫描**）。手工往书目录塞文件不经过任何应用
  事件（`mark_has_audio` 只在导入 / TTS / 扫描服务里调用），缓存最长要等
  **6 小时**兜底扫描才更新。于是「统计实时、列表与 tab 陈旧」——用户看到的
  「统计加了 1、文学还是不出来」正是这两套口径的差值。
  （对照实证：缓存 11 本时 tab 为 教育2/科幻小说3/演播3/科幻1；把实时扫盘的
  12 本同步进缓存后，`audio_category_agg` 随 version 增量补齐，tab 立刻多出「文学 1」。）
- 修复（**不动 `app/dist`，纯 py 可热更**）：
  - `AudioBooksCache.sync_from_scan(book_ids)`：把一次实时扫盘结果喂进缓存，
    集合**真变化**才 `+version`，下游 `audio_category_agg` 自动增量补齐；空结果
    不同步（避免偶发 `listdir` 失败清空缓存），坏 id 忽略。
  - `BaseHandler.get_audio_books_count()`：盘既然已经扫过了，扫完顺手调
    `sync_from_scan(found.keys())`；同步失败只 `logging.debug`，绝不影响统计本身。
  - 全库兜底扫描间隔默认值 **6 小时 → 5 分钟**（`AUDIO_CACHE_REFRESH_SECONDS`，
    仍可配置、`0` 可关闭），兜住「既没有统计请求、也没有事件」的极端情况。
  - 净效果：手工加音频后**刷新一次页面**即可看到新分类；不必再等 6 小时或重启容器。
- 测试：新增 `tests/test_audio_stats_cache_sync.py` 6 例，锁定「统计扫盘同步 → tab
  立刻出现新分类」「重复同步不抖动 version」「空扫盘不清空缓存」「坏 id 忽略」
  「统计入口确实调用同步」「同步失败不影响统计」。
- 部署：r35 → r36 为纯 `webserver/**/*.py`，页内「立即更新」→ 强刷即可；
  `app/dist` 与 r34/r35 同指纹，`hotfixable=true` / `requires_dist=false`。

---

## 4.6.0-build.27-r35（2026-11-14，**修复有声书页分类 tab 一直不显示**，纯后端，可热更）

- 症状：r34 热更 / `deploy.sh` / `upgrade.sh` 全试过，左侧「有声书」页右侧始终没有分类 tab。
  但 **Console 无红字**、书列表正常（11 本、每本都带 `category`）、手动访问
  `/api/audiobooks/categories` 也返回 4 个分类。前端 `46bb55f.js` 里
  `fetchAudioCategories` 存在、HTTP 200、runtime 映射 `0:"46bb55f"` 也正确。
- 根因（**与 dist 新旧、浏览器缓存、后端接口都无关**）：本前端是 SPA 模式，
  `asyncData` 在客户端每次导航都会执行，成功返回 `err:ok` 后把 `ssr_loaded=true`
  merge 进组件 data；`mounted()` 的守卫是 `if (!this.ssr_loaded && !this.inited) init()`，
  于是 **`init()` 被整个跳过**。而 `fetchAudioCategories()` 只写在 `init()` 里 →
  分类请求一次都没发 → `audioCategories` 恒为 `[]` → `audioTabs.length === 1` →
  `v-if="isAudioPage && audioTabs.length > 1"` 静默不成立。
  这正是「版本新、功能旧」里最难查的一种：所有排查项都是绿的，就是不发请求。
  r31 引入 tab 时只覆盖了站内跳转（`beforeRouteUpdate → init`），首屏直入 / 强刷
  这条 `asyncData` 路径从没走通过。
- 修复（**不动 `app/dist`，纯 py 可热更**）：
  `AudioBooks.get()` 改为 `async def`，在书列表响应里随 `books` 一起下发
  `audioCategories` 与 `audioTotal`——`asyncData` 会把这两个 key merge 进组件 data
  （两者都在 `data()` 里声明），tab 首屏就有数据，不再依赖 `init()` 那条链路。
  抽出模块级 `build_audio_tab_categories()`，`/api/audiobooks` 与
  `/api/audiobooks/categories` 共用同一份实现，保证两处 tab 顺序 / 计数 / 图标一致。
  `audioTotal` 用**过滤前**的全量可见数，`?category=X` 时「全部」tab 不会缩水。
- 实证：真实 r34 `app/dist` + 无头 Chromium + mock 后端，
  **现状**分类请求 0 次 / tab 0 个；**书列表带分类数据后** tab 5 个
  （All + 教育 + 科幻小说 + 播音:李慧敏 + 科幻），Console 无报错。
  新增 `tests/test_audiobooks_list_tab_categories.py` 5 例，连同既有
  `test_audiobooks_category_handler.py` 共 16 例全绿。
- 部署：`hotfixable=true` / `requires_dist=false`，只需 2 个 py，
  **页内 `/admin/version` →「立即更新」→ 强刷**即可（当前须为 r34）。
  dist 768 文件与 `index.html` 指纹 `2c02df40…` 一个字节没动，不需要重新部署。
  同时提供 r35 整包，供全新安装 / 想把源码目录固化到 r35 的站点使用。
  热更改的是容器可写层，之后别 `--force-recreate`；真要重建先跑 `sh scripts/sync-hotfix.sh`。

---

## 4.6.0-build.27-r34 后续修复（**upgrade.sh 数据挂载误报**，仅脚本，revision / 清单字节不变）

- 症状：`sh scripts/upgrade.sh <r34 包>` 在 `[6/8]` 报
  `!! docker-compose.yml 里没有 'audiobook-data:/data' 挂载` 并退出，
  此时旧源码已归档、新包已解压，但**镜像未重建、容器未启动**，处于半升级状态。
- 根因：`r33` 把 `docker-compose.yml` 变量化成
  `${DATA_DIR:-/volume1/docker/audiobook-data}:/data`，而 `upgrade.sh` L219 仍按字面量
  `grep -q "audiobook-data:/data"` 校验，中间多一个 `}` 就匹配不上。属上一轮变量化引入的回归。
- 修复：改用 `docker compose config` 解析实际挂载源（自动合并 `.env` 与默认值），
  解析不到再退回文本兜底（兼容 `变量形式` / `旧字面量`）；并新增语义检查——
  必须是**源码目录之外的绝对路径**，防止把 `/data` 挂进会被归档的源码目录。
  实测 4 种 compose 形态解析正确，挂错目录 / 缺 `: /data` 两种坏例被拦。
- **不需要重新部署、不需要重出包**：只改 `scripts/upgrade.sh`，清单与 dist 一个字节没动。
  已装 r34 的站点无感；当前卡在半升级的机器只需
  `cd /volume1/docker/audiobook && sh scripts/deploy.sh` 完成构建与启动即可。

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


---

## 跟随上游：方法论与实况

### 跟随上游：方法论与上轮比对实况（mybooks `4.6.0` → `develop`/4.6.1）

> **这一节是「以后怎么跟上游」的操作手册。** 下面 §0~§7 是 2026-11-05 那轮
> `4.6.0 → develop(4.6.1)` 的**实况记录**（可作参照）；§8 是补丁生成方式。
> **注意**：上游此后已发布 `4.7.0`（见本节末尾「当前上游状态」），
> 下一轮跟进请按同样的方法重跑比对，结论不要照抄旧的。

> 对象：上游主库 `PoxenStudio/mybooks`（`develop`，head `fdf982a6`，2026-11-05）、
> 上游母库 `talebook/talebook`（`master`）；本仓库基线 `4.6.0-build.27-r27`（2026-11-12）。
>
> 本文是「上游跟进」的**唯一在用手册**。缺陷明细（原《上游跟进清单》A~G）与四主题补丁包
> （原 `上游跟进/`）已于 2026-11-13 归档到 [`archive/上游跟进清单.md`](archive/上游跟进清单.md)
> 与 [`archive/上游跟进/`](archive/上游跟进/)；需要查历史条目从那里进，本文负责当前版本级比对、
> 优先级与补丁生成方式（见 §8）。
>
> 口径：**只读上游**。数据取自 GitHub compare API（`4.6.0...develop`）+ `git clone --filter=blob:none
> --shallow-since=2026-10-20`（临时目录，已删除，未落到本仓库）。冲突判定不是估的：对每个「上游改过且
> 本地也改过」的文件做了 `git merge-file` 三路合并（base = `4.6.0` 原文件、ours = 当前工作区、theirs = 上游
> `develop` 对应文件，CRLF 归一后比对），冲突块数即下表数字。

### 0. 结论摘要

| 项 | 结果 |
|---|---|
| 上游提交数（`4.6.0..develop`） | **70**（14 个 merge + 45 个独立工作提交 + 11 个被 cherry-pick 带入的重复提交） |
| 上游改动文件 | **95**（77 改 + 18 新增，0 删除），+12807 / −7541 行（含 `pnpm-lock.yaml` 等大文件） |
| 相对上次跟进（R13 清单 G 节，head 同为 `fdf982a6`） | **新增 0 个提交**；develop 自 2026-11-05 未再推进 |
| 本地也改过的重叠文件 | 68 个 → 实测 **32 可自动合并 / 28 会冲突 / 3 上游新增 / 3 本地已删 / 2 无 patch** |
| 安全相关条目 | 3 个（1 个在我们现状下**无风险**，2 个只存在于我们不打算移植的新功能里） |
| 建议立即移植 | **1 项**（AI 会话调用上限） |
| 需要决策 | **2 项**（模块门控接线；封面背景图库） |
| 禁止整体合并的文件 | `webserver/settings.py`（默认值/键名有破坏性变更，见 §4） |

一句话：**这一轮上游没有安全漏洞需要我们补**，值得动手的只有 AI 会话那个阻塞问题；其余要么我们早已等价吸收，要么是和我们二次开发正面撞车的新功能。

### 1. 分类与逐条状态

状态列口径：`已吸收` = 本地已有等价实现（即使不是同一份代码）；`未吸收` = 本地确实没有；
`不跟` = 已裁决不移植；`无关` = 本地删掉了该目录或该功能不适用。

#### 1.1 安全修复（3）

| 提交 | 日期 | 内容 | 涉及文件 | 本地状态 |
|---|---|---|---|---|
| `755b4f0` | 11-01 | 封面背景图库：**路径穿越**、并发写、对话框规范（PR 审查） | `webserver/base/cover_background.py`、`handlers/cover_background.py` | 不跟（新功能未移植，无该攻击面）；**若将来移植图库，此修复必须一起带** |
| `8142ee8` | 10-31 | 图库上传：权限判断、开关锁定、文件类型校验 | 同上 + `admin/settings.vue` | 同上 |
| `c0245c7` | 11-03 | 匿名 OPDS **收紧登录闸**：只旁路封面/缩略图，`/get/extract` 等仍走登录 | `handlers/base.py`、`opds.py`、`module-gate.js` | 无风险也无该功能：本地 `base/modules.py` 有 `opds_anonymous_allowed()`，但 `handlers/base.py` **未接线**，等于匿名入口不存在。要用这个能力必须连同此提交一起移植 |

> 补充：`8ccab74`（必须登录时 OPDS 下载直链回 401 + `WWW-Authenticate`，而不是 200 JSON）属安全相邻的协议正确性修复，本地已吸收（`base.py` 有 `is_opds_acquisition`，注释标了上游 sha）。

#### 1.2 性能 / 阻塞（2）

| 提交 | 日期 | 内容 | 涉及文件 | 本地状态 |
|---|---|---|---|---|
| `5b270c0` | 10-30 | **AI 会话超出 LangGraph 调用限制**：`recursion_limit` 16→40（可配 `AI_RECURSION_LIMIT`）、单轮工具调用硬上限 `AI_MAX_TOOL_CALLS`=12、相同参数重复调用直接回放上次结果、工具错误回显 | `assistant/ai_assistant_agent.py`、`assistant/mcp_client.py`、`mcp/mcp_service.py`、`settings.py` | **未吸收**（本地仍 `recursion_limit: 16`，无上限、无去重）→ 见 §5 P0-1 |
| `ab73382` | 10-26 | 图书管理支持**取消批量任务**（长任务不能中止 = 阻塞） | `admin/books.vue`、`batch_add.py`、`autofill.py`、`book.py` | 已吸收（本地 `cancel_requested` 已在用） |

#### 1.3 缺陷修复（17）

| 提交 | 内容 | 本地状态 |
|---|---|---|
| `928841e` | 阅读统计两处未按站点时区切天（月统计 + 日统计） | 已吸收（`site_month_bounds_server_local()` + `site_time.site_today()`） |
| `606a503` / `26509dd` / `2b23170` | 「即将读完」排除已标记读完的书：先修语义 → 改 `NOT EXISTS` → 明细查询复查堵并发窗口 | 已吸收（本地注释与实现一致） |
| `d7dd8af` | EPUB 修复页 i18n 全失效 + 检测进度条常驻 100% | 已吸收 |
| `8ccab74` | OPDS 下载直链 401 挑战（见 1.1） | 已吸收 |
| `bbdd87e` | dev 环境首页必然落到「服务正在启动中」 | 已自行吸收（`store/index.js` 走 mutation，本地实现更细） |
| `98bce8f` | OPDS 一级目录名跟随站点语言 | 已吸收（`category_display_name()` / `default_feed_title()` 均在） |
| `c3bebc0` / `999b6ca` / `58c2814` / `c0d0eae` / `f48040a` | 模块门控的 5 轮审查修复（权限、i18n、闸门边界） | 无关（门控未接线，见 §5 P1-1） |
| `cc962e4` / `4091b8b` / `390b0ce` | 封面图库：类属性读取、图标子集、勾选竞态 | 不跟（新功能未移植） |
| `587dde7` | 修正 skill 里测试的问题 | 无关（本地已删 `skills/`） |

#### 1.4 新功能（17）

| 提交 | 内容 | 文件规模 | 本地状态 |
|---|---|---|---|
| `70fcf7a` `eb06820` `82d4cb1` `12f3525` `d0b5bff` `d954175` `ef67b65`（+5 个审查修复） | **功能模块门控**：有声书/社区/共享阅读/实体书/AI/多用户 6→5 个可整块关闭的开关，后端 `ModuleGateMixin` + 前端 `module-gate.js`/`ModuleSettingsDialog` | 约 60 文件 | 半移植：`base/modules.py`、`settings.py` 6 个默认键、`setting_saver` 白名单**已存在且与上游逐字节相同**，但 **handlers 与前端全部未接线**（`git grep ModuleGateMixin` 无命中）→ 见 §5 P1-1 |
| `2faddbe` `badb2ad`（+4 个修复） | **封面背景图库**：管理员上传背景图，并入首页动态封面展开区 | 新增 3 文件 | 不跟（与我们的首页自定义实现是两套） |
| `92d15b4` `ac17658` `a504877` | 首页动效：区块进场、封面书脊、换一批洗牌、统计数字滚动 | `index.vue`、`BookCards.vue`、`mdi-subset.css`、locales | 不跟（首页已按自己需求重写；动效会与分节排序/权限渲染打架） |
| `54f0357` `2aecc55` | 设置页时区选项改为 −12~+12 偏移 + 城市，并归一化旧值 | `admin/settings.vue` | 不跟（设置页已自定义）；后端兜底本地更强（`FALLBACK_REGION_OFFSETS` 按大区前缀猜测，优于上游扩充的固定表） |
| `4f72e23` | 工具箱默认展示顺序按处理流程分组 | `toolbox/toolset.py` | 不跟（本地工具箱顺序与新增工具已另排） |
| `b6f1fd7` | skill：无名图书检索 + 整库补齐 | `skills/` | 无关（本地已删该目录） |
| `1fc15cb` | AI 会话样式（`AiChatDialog.vue`） | 新增 1 文件 | 不跟（我方未使用该组件） |

#### 1.5 依赖升级（4）

| 提交 | 内容 | 本地状态 |
|---|---|---|
| `2df5731` | `social-auth-core` 5.0.0 → 6.2.0 | 已吸收（`requirements.txt` 已是 6.2.0） |
| `cc474f9` | `tornado` 6.5.9 → 6.6 | 已吸收（已是 6.6） |
| `78f4728` | `undici`（`cfi_gen` 子包） | 未跟进（仅影响 cfi 生成子进程的 Node 依赖，风险低） |
| `c120663` | **`nuxt` 2.18.1 → 4.6.2** | 不跟：跨两个大版本，上游 `app/` 已按 Nuxt 4 重排；我们的前端是深度定制的 Nuxt 2，合并等于重写 |

#### 1.6 破坏性 / 行为变更（从上面各类里单列）

1. **`REQUIRE_LOGIN` 默认值 `False` → `True`**（`webserver/settings.py`）。全新安装、或配置里缺这个键时，站点默认变成"必须登录"。我们依赖访客阅读/读者组分流，**不能连默认值一起合并**。
2. **`ENABLE_BOOKLIST_COVER_SCROLL` → `ENABLE_HOME_MOTION` 重命名**（单向迁移：旧键为 False 时强制关新键）。前端 `sys.booklist_cover_scroll` 同步改名 `sys.home_motion`。我们的设置页/首页仍读旧键，直接合并会静默失效。
3. **OPDS 匿名访问语义收紧**：新增 `OPDS_ALLOW_ANONYMOUS`（默认 False），此前"必须登录"时连封面都被拦。启用需配合 `c0245c7`。
4. **安装页新增模块勾选参数**：`/admin/install` 会按未勾选模块写入安全默认值（如关多用户 → 同时写必须登录、关访客权限）。脚本直接调接口的默认行为变了（缺省视为全开）。
5. `nuxt` 4 升级（见 1.5）。

### 2. 与我们二次开发的冲突矩阵（实测）

判定方法见文首。**会冲突** = `git merge-file` 报冲突块；**可自动合并** = 三路合并零冲突；**无关** = 上游这一轮没碰这个文件。

#### 2.1 你点名的 10 个文件

| 本地文件 | 上游本轮是否改动 | 实测 | 说明 |
|---|---|---|---|
| `webserver/handlers/book.py` | 改（+98/−25） | **会冲突（5 块）** | ① `MediaDetail` 的 `audios`：上游套模块闸门，我们已改成带 `db=self.calibre_db_cache` 的签名 → 需人工改写成"闸门 + db 参数"；② 「本月」时区边界：两侧是同一结论的不同实现（我们有 `site_month_bounds_server_local`），保留我方；③ `BookReadingStats`：上游拆成两条 count，我们重构成一次 `group_by` 聚合 → 保留我方（性能更好）；④⑤ 相邻行（推荐/分享）上下文冲突 |
| `webserver/handlers/base.py` | 改（+105/−27） | **会冲突（6 块）** | ① `is_opds_acquisition` 与我们 CORS/同源判断同区域；② OPDS 401 注释块（同文不同措辞）；③ 匿名 OPDS 旁路 vs 我们的 `path.startswith("/opds")` 判定 → **语义级**，只在移植匿名模式时才需要裁决；④⑤⑥ `_library_stats`/`_sys_info_with`/`allow_flags`（`sys.home_motion`、`module` 字段） |
| `app/src/components/BookCards.vue` | 改（+13/−4） | **可自动合并** | 上游只加 `home-motion` 相关类名/过渡；我们的卡片结构改动不在同一行 |
| `webserver/handlers/reader_group.py` | 未改 | 与我们改动无关 | — |
| `webserver/services/reader_group.py` | 未改 | 与我们改动无关 | — |
| `webserver/services/version_check.py` | 未改 | 与我们改动无关 | 上游没有自建更新检测，这是 fork 专有 |
| `app/src/pages/ListBook.vue` | 未改 | 与我们改动无关 | — |
| `app/src/components/ReaderGroupEditor.vue` | 未改 | 与我们改动无关 | — |
| `scripts/pack.sh` | 未改 | 与我们改动无关 | — |
| `Dockerfile` | 未改 | 与我们改动无关 | — |

#### 2.2 其余会冲突的文件（28 个全量）

| 文件 | 冲突块 | 性质 | 处置 |
|---|---|---|---|
| `app/src/pages/admin/settings.vue` | 10 | 语义 | 设置页已重写（分节/搜索/拖动排序/时区列表/我们的专有项）。上游加了 `ModuleSettingsDialog`、时区归一化、图库设置。**不做行级合并**，只按需抄功能 |
| `app/src/pages/book/_bookid.vue` | 6 | 语义（含死代码） | 上游用 `v-if="audioModuleOn"` 包住转换弹窗等；我们已下线详情页弹窗（C11 裁决）→ 上游这段若合并进来是死代码，跳过 |
| `webserver/handlers/base.py` | 6 | 语义 | 见 2.1 |
| `app/src/components/AppHeader.vue` | 5 | 语义 | 上游加 `moduleOn("multiuser"/"audio"/...)`、权限页入口；我们重排了菜单（更新检测独立页、版权下架）。保留我方结构，不接门控 |
| `webserver/handlers/book.py` | 5 | 语义 | 见 2.1 |
| `app/src/assets/css/mdi-subset.css` | 4 | 文本（行插入） | 纯图标行追加，取并集即可（注意我们也在维护子集，需重算 woff2） |
| `app/locales/en.json` / `zh.json` / `zh-TW.json` | 3 / 2 / 2 | 文本 | 键插入位置冲突；只按需补 `home_motion`、模块/图库文案，其余不补 |
| `webserver/main.py` | 3 | 语义（轻） | `names` 列表：上游加 `cover_background`，我们有 `reader_group/book_dedup/author_norm/search_index/version` → 保留我方并追加 |
| `webserver/mcp/mcp_service.py` | 3 | **纯注释**（上游把中文注释改英文） | 保留中文，零风险 |
| `webserver/handlers/audio.py` | 2 | 语义（轻） | 上游 `class AudioFile(ModuleGateMixin, BaseHandler)` + `module_gate_json=False`（模块关时给 404 而不是 JSON）。不接门控则跳过；接门控时必须照做，否则 `<audio>` 播放器会收到 JSON |
| `webserver/services/ai_fillinfo.py` | 2 | 语义（追加） | 上游在批次边界检查 `AI 模块已关` → 属门控配套，未接线则不跟 |
| `webserver/handlers/admin.py` | 1 | 语义 | 安装接口的模块勾选。**我们的 `carry_over=False` 修复必须保留**（否则首装会把旧配置键搬进来） |
| `webserver/handlers/assistant.py` | 1 | 语义（轻） | 上游加 `module_enabled(MODULE_AI)`；P0-1 移植时只需要其 import 位置 |
| `webserver/handlers/opds.py` | 1 | 文本（同内容） | 两侧 `hidden_categories` 完全一致，冲突来自相邻 docstring 差异；取我方 |
| `webserver/handlers/toolbox.py` | 1 | 语义（相邻类） | 上游在 `AdminMimoTTSConvert` 上加门控；我方在该位置插了自己的转码扫描类 → 手工拼接 |
| `webserver/base/setting_saver.py` | 1 | 文本（同内容） | 双方都已把 6 个模块键加入白名单（我方先行移植），取我方 |
| `webserver/site_time.py` | 1 | 语义（函数位置） | 上游加 `site_day_start_server_local()`，我方加 `site_month_bounds_server_local()`。二者可共存，但日统计我们已经用 `site_today()` 解决，无需补 |
| `webserver/services/reading_dashboard_service.py` | 1 | 文本（同结论） | 同一段注释的两种写法；逻辑等价，取我方 |
| `webserver/toolbox/toolset.py` | 1 | 语义 | 上游改注册顺序；我方已自排顺序并注释掉 `FormatsPruningTool`。不跟 |
| `app/src/pages/index.vue` | 1 | 语义 | 上游加 `home-motion-reduced` 类 + `homeMotionEnabled`；我方分节渲染加了统计权限判断。不跟动效则跳过 |
| `app/src/pages/admin/books.vue` | 1 | 语义（轻） | 上游 `if (!this.aiModuleOn || this.ai_scraping)`；不接门控则保留我方 |
| `app/src/pages/admin/imports.vue` | 1 | 文本（相邻） | 与导入页按钮/开关上下文相邻，手工取并集 |
| `app/src/pages/toolbox/epub_fixer.vue` | 1 | 纯注释（我方标了上游 sha） | 取我方 |
| `app/src/store/index.js` | 1 | 纯注释 | 同一修复（dev 下 mutation）的两种注释；取我方 |
| `tests/test_book_access_service.py` | 1 | 文本 | 上游把 `handlers/base.py` 加入允许名单；我们不接门控则不加 |
| `README.md` | 1 | 文本 | 上游加了贡献者图；我们 README 已重写，不跟 |

#### 2.3 可自动合并的 32 个（零冲突，含真正有用的）

`app/nuxt.config.js`、`app/package.json`、`requirements.txt`、`webserver/settings.py`（**注意 §1.6 的默认值**）、
`webserver/handlers/scan.py`、`share.py`、`user.py`、`podcast.py`、`webserver/i18n.py` + 三份 i18n、
`webserver/assistant/ai_assistant_agent.py`、`assistant/mcp_client.py`、`handlers/mcp.py`、`mcp/api_tools.py`、
`services/autofill.py`、`services/batch_add.py`、`app/src/components/BookCards.vue`、`BookListCard.vue`、
`HomeCustomCard.vue`、`HomepageCardsEditor.vue`、`ReadingTimeBackfillDialog.vue`、`AppFooter.vue`、
`pages/admin/all-expected.vue`、`admin/toolbox.vue`、`pages/book/_bid/edit.vue`、`pages/install.vue`、
`utils/homepage.js`、`tests/test_reading_dashboard_service.py`、`thanks_to.txt`、`webserver/services/cfi_gen/package-lock.json`。

> 这 32 个是"能直接 `git cherry-pick` 或整文件取上游"的，但**只有 P0-1 涉及的 4 个值得动**。

#### 2.4 其他

- 上游新增但本地已有同内容文件：`webserver/base/modules.py`、`tools/opds/list_opds.py`（逐字节相同 → 说明半移植状态是既成事实）。
- 上游新增、本地也新增但内容不同：`tests/test_modules.py`。
- 本地已删除、上游本轮又改：`.claude/rules/ui.md`、`skills/mybooks/SKILL.md`、`skills/mybooks/scripts/mybooks_api.py`（保持删除）。
- 无 patch（未能逐行比对）：`app/pnpm-lock.yaml`（超大）、`app/src/assets/fonts/materialdesignicons-subset.woff2`（二进制）。

### 3. 与 talebook 的同期比对

`talebook/talebook` `master` 在 2026-10-24 之后只有 **2 个提交**（1 个 merge + 1 个工作提交 `070e0c58`，2026-11-01）：
新增"微信读书插件（weread）的 skill 版本上报"，涉及 `plugins/weread/*` 与 `scripts/` 少量文件。

**结论：母库这一窗口没有与本仓库重叠的改动**（无 tz/统计/OPDS/权限相关），不存在"两边都改、需要合流"的情况。

### 4. 合并策略上的硬约束

1. `webserver/settings.py` 虽然实测零冲突，但**不能整文件取上游**：会把 `REQUIRE_LOGIN` 默认值改成 True、把 `ENABLE_BOOKLIST_COVER_SCROLL` 改成 `ENABLE_HOME_MOTION`，前者会让新装站点默认不让访客阅读，后者让我们现有首页/设置页静默失效。若只要 `require_login_effective()` 的语义，逐行摘即可。
2. `webserver/handlers/base.py` 是 CORS/同源/OPDS 三条安全线的交汇点（我们 A1/D8 的修复都在这里）。**任何上游改动必须逐块过一遍**，不能按"冲突少"就整块接受。
3. 模块门控不要"半边接线"长期挂着：现在 `modules.py` + 默认键 + 白名单在位、`ModuleGateMixin` 不在，等于埋了一套没人用的开关；要么接完（P1-1），要么在 `modules.py` 顶部注明"仅占位，勿引用"。

### 5. 优先级与动作

排序依据：① 是否安全相关；② 是否正好是我们踩过的坑；③ 合并成本（实测冲突块数）。

#### P0-1 直接移植：AI 会话调用上限（`5b270c0`）· 成本 ≈ 1 小时

- 为什么：上游这是**解阻塞**而非新功能——LangGraph 把每次"模型/工具往返"算约 2 步，旧值 16 只够 ~7 轮工具调用，正常的多步提问会直接 `GraphRecursionError`。本地 `ai_assistant_agent.py:291` 仍是 `recursion_limit: 16`，且没有单轮工具上限，模型犯糊涂时会一直循环。
- 涉及改动：`AI_RECURSION_LIMIT`(默认 40)、`AI_MAX_TOOL_CALLS`(默认 12)、相同参数重复调用回放上次结果、`_tool_result_text` 把 `error` 也回给模型。
- 冲突成本：`ai_assistant_agent.py` / `mcp_client.py` / `handlers/mcp.py` / `mcp/api_tools.py` **全部零冲突**；`mcp_service.py` 3 块是纯注释英文化（保留我方）；`handlers/assistant.py` 1 块只是 import 位置。`settings.py` 只加两个键，不要顺手带别的。
- 验收：找一个需要 3~5 轮工具调用的提问（如"把某作者的书按年份统计"），不再报超限；同一工具同参重复调用时模型能收到"已调用过"的提示。

#### P0-2 结论性确认（无需改代码）：OPDS 匿名能力

- 现状安全：`modules.py` 有 `opds_anonymous_allowed()`，但 `handlers/base.py` 未接线 → 该能力对访客**不可达**，`755b4f0`/`c0245c7` 的风险面都不在我们这。
- 若哪天要给"不能输入账号的阅读设备"开口子：必须同时移植 `c0245c7`（只旁路封面/缩略图，`/get/extract`、`/get/progress`、`/get/tool` 仍走各自授权）+ `8ccab74`（401 挑战），并把 `is_opds_acquisition` 的判定顺序一起改。**单独打开 `OPDS_ALLOW_ANONYMOUS` 就等于把正文下载暴露出去**。

#### P1-1 需要决策：模块门控到底接不接（17 个提交）

- 现状：后端地基已在（`base/modules.py` 与上游逐字节相同、6 个默认键、持久化白名单），缺 `handlers` 的 `ModuleGateMixin` 与前端 `module-gate.js`/`ModuleSettingsDialog`。所以"关掉有声书模块"现在**没有任何效果**。
- 接的收益：给 NAS 用户一个"整块关掉某功能"的开关（尤其 AI、社区），减少误触与资源占用（模块关时 `book.py` 不再扫音频目录）。
- 接的成本：`base.py`(6) + `book.py`(5) + `audio.py`(2) + `AppHeader.vue`(5) + `settings.vue`(10) + 三个 locales(7) + `admin.py`(1) + `toolbox.py`(1) + `ai_fillinfo.py`(2) ≈ **40 个冲突块**，且要与我们读者组/权限体系叠加（关"多用户"会和读者组分流规则打架）。
- 建议：**先不接**。如果接，按"多用户模块永不接入"处理（我们本来就靠读者组），只接有声书/AI 两个模块，成本降到约 15 块。

#### P1-2 不建议跟：首页动效 / 封面背景图库 / 时区选项 UI / 工具箱排序

- 首页动效（3 提交）：收益是观感，成本是 `index.vue` 语义冲突 + `BookCards.vue` 与本地的卡片改动叠加；我们首页已按分节排序 + 权限渲染重写。
- 封面背景图库（6 提交，含 2 个安全修复）：新增 3 个文件零冲突，但它是"另一套首页"，与我们的 `HomeCustomCard` 并存会两套逻辑；且必须连同 `755b4f0` 的路径穿越修复一起进。
- 时区选项 UI：后端兜底本地更强（大区前缀回退），纯设置页观感问题。
- 工具箱排序：本地工具箱已重排且抑制了 `FormatsPruningTool`。

#### P2 仅需知其存在

- `nuxt 2.18.1 → 4.6.2`：跨大版本，我们前端深度定制，明确不跟。
- `undici`（cfi_gen 子包）升级。
- OPDS 目录名 i18n（`98bce8f`）：本地已等价实现，无需动作。
- skill 工具包、贡献者图、locale 扁平键测试：与我们的目录/流程无关。

### 6. 执行清单（可勾选）

- [ ] **P0-1** 摘 `5b270c0`：`ai_assistant_agent.py` 的上限/去重/错误回显 + `settings.py` 两个新键 + `mcp_service.py` 仅取逻辑改动（保留中文注释）
- [ ] **P0-1** 补一条回归：多轮工具提问不报 `GraphRecursionError`
- [ ] **P0-2** 在 `modules.py` / `handlers/base.py` 附近留一句注释，写明"匿名 OPDS 未接线，启用须带 c0245c7 + 8ccab74"（避免后人误开）
- [ ] **P1-1** 决策记录：接 / 不接模块门控；不接则在 `modules.py` 顶部标"占位"
- [ ] **§4-1** 在任何合并脚本里给 `webserver/settings.py` 加白名单排除（或改后逐项复核 `REQUIRE_LOGIN`、`ENABLE_HOME_MOTION`）
- [ ] 下次跟进时先看 `develop` 是否越过 `fdf982a6`

### 7. 未能获取 / 需人工确认

| 项 | 原因 |
|---|---|
| `app/pnpm-lock.yaml`、`materialdesign-subsets.woff2` 的逐行差异 | compare API 对大文件/二进制不返回 patch；只按"文件级有改动"记录 |
| 上游 PR/Issue 的讨论正文与 review 意见 | 本轮只取提交信息与代码 diff（未逐 PR 抓取评论） |
| `8142ee8`/`755b4f0` 的完整修复语义 | 仅在 compare patch 粒度上确认"权限判断/路径穿越/并发"三类改动落在图库相关文件；未读其测试断言细节 |
| talebook 是否存在与 mybooks 同源的未合并补丁 | 只比对了 `master` 近期提交，未追 `dev` 等分支 |

> 本报告生成时的临时克隆与 API 缓存（`_tmp_upstream/`）已在使用后删除，本仓库工作区与 git 历史未做任何改动。

### 8. 补丁包生成（原 `上游跟进/` 迁入）

缺陷明细与四主题包（A 安全与元数据 / B 扫描与导入 / C 音频与播放 / D 功能与权限）已归档到
[`archive/上游跟进清单.md`](archive/上游跟进清单.md) 与 [`archive/上游跟进/`](archive/上游跟进/)。
本节保留仍然可用的生成方式；脚本本身没有动，仍在 `scripts/upstream/patch_tool.py`。

```sh
# 1) 准备上游检出（浅克隆即可）
git clone --depth 1 --branch 4.6.0 https://github.com/PoxenStudio/mybooks.git /tmp/mybooks-4.6.0

# 2) 生成某个主题的补丁（左侧=上游，右侧=本仓库）
python3 scripts/upstream/patch_tool.py export A --upstream /tmp/mybooks-4.6.0 --out upstream-patches/

# 3) 查看上游是否已修（按条目的 grep 检查点）
python3 scripts/upstream/patch_tool.py status --upstream /tmp/mybooks-4.6.0
```

- 导出结果 `upstream-patches/A.patch` 等，`git apply --check` 可直接验证；
- `status` 逐条打印 `fork-only`（上游没有）或 `upstream-has-marker`（上游已出现修复标记），
  后者说明该条可从主题包里剔除，避免补丁永久堆积；
- 为什么按主题而不是按文件拆：`webserver/handlers/base.py`、`handlers/book.py` 同时承载 A/C/D 的改动，
  按文件拆会把不相关改动捆进同一个 PR；主题包只声明「文件清单 + 条目清单」，导出后仍可逐条 cherry-pick；
- 补丁是从**本仓库当前代码**相对上游生成的，天然包含 `opt/p0-p1` 的改动。提 PR 前必须跑
  `python -m pytest tests/ -q` 与 `./scripts/test-integration.sh`，并把归档清单里的检查点逐条对照上游 Release Notes；
- 默认决策：只生成、不自动 `git apply`（合并策略需人工判断）；不引入第三方 diff 库（只用标准库 `difflib`）；
  每个主题包一个 PR，主题内部条目再按「独立可复现」拆小提交。
---

#### 当前上游状态（2026-11-16 实测）

| 项 | 值 |
|---|---|
| 上游最新 tag | **`4.7.0`**（我们基线 `4.6.0`） |
| `4.6.0..4.7.0` 规模 | **114 个提交、176 个文件**（+18999 / −8133 行） |
| 我们的基线 | `4.6.0-build.28`（`webserver/version.py`） |
| 双方重叠改动面 | `webserver/` 81 处、`tests/` 58 处、`app/` 54 处 —— 正是我们改得最多的地方 |

#### ⚠️ 关键约束：**没有共同祖先，不能 git merge**

我们的仓库是用「导出上游源码」的方式建的（根提交 `5748959 audiobook v4.8 源码`），
**上游的 git 历史不在本仓库里**（`git cat-file` 查上游 `4.6.0` 的 commit 会报
`could not get object info`）。所以：

- ❌ `git merge upstream/4.7.0` / `git rebase` —— 没有 merge base，**直接失败**
- ❌ `git cherry-pick` 上游提交 —— 上游对象不存在于本仓库
- ✅ **唯一可行路径**：拉上游到临时目录 → 做文件级三方比对（base=上游旧版、
  ours=我们工作区、theirs=上游新版）→ 逐文件判定「吸收 / 移植 / 不跟」→
  手工把该移植的改动搬进来 → 重新出镜像

这就是下面 §8 的 `scripts/upstream/patch_tool.py` 存在的原因：它把
「按主题导出补丁」和「检查上游是否已修」这两件事标准化，避免每次手工重来。

#### 工具：`scripts/upstream/follow-upstream.py`（新增，替代已删的三个脚本）

把「跟随上游」里机械可重复的部分标准化，三个子命令：

```sh
# 1. 拉上游（浅克隆到临时目录，不落进本仓库）
python3 scripts/upstream/follow-upstream.py fetch --upstream-dir /tmp/up

# 2. 评估这一轮规模
python3 scripts/upstream/follow-upstream.py assess --upstream-dir /tmp/up --base 4.6.0 --target 4.7.0

# 3. 逐文件三方比对 → 冲突矩阵（只读本仓库，报告写到 --out）
python3 scripts/upstream/follow-upstream.py compare --upstream-dir /tmp/up \
    --base 4.6.0 --target 4.7.0 --out /tmp/compare-report.json
```

**`4.6.0 → 4.7.0` 实测输出**（2026-11-16，脚本可复现）：

| 项 | 数量 |
|---|---|
| 上游提交 / 改动文件 | 114 / 176 |
| **可自动吸收** | **111** |
| **需人工判定（冲突）** | **58**（TOP：book.py 197 块、audio.py 141 块、settings.vue 123 块、imports.vue 102 块） |
| 仅我们有 | 7 |

> 冲突计数的口径：**上游在「我们改过的同一段」也改了才算冲突**；上游没动那段不算。
> （第一版实现把「上游没动」也算冲突，导致 80 个冲突虚高；修正后是 58。）
| 禁止整体合并 | `webserver/settings.py` |

> 与「已删的三个脚本」相比：原先的 `upgrade-upstream.sh` 走的是**在 NAS 上从源码
> 构建镜像**的旧路线（`docker compose up -d --build`），现在改成 GHCR 拉成品镜像，
> 那条路线整体退役；`protect-custom.sh` / `watch-upstream.py` 的职责并入本工具的
> 比对矩阵（不再需要「先存快照再合并」，因为我们**不合并**，只做逐文件移植）。

#### 跟一轮上游的检查清单

```sh
# 1. 拉上游（临时目录，不落进本仓库）
git clone --filter=blob:none --no-checkout https://github.com/PoxenStudio/mybooks.git /tmp/up
cd /tmp/up && git fetch --tags && git checkout 4.7.0

# 2. 规模评估
git rev-list --count 4.6.0..4.7.0
git diff --stat 4.6.0..4.7.0 | tail -1

# 3. 逐文件三方比对，判定冲突（下面 §2 的矩阵做法）
#    base=上游 4.6.0、ours=本仓库工作区、theirs=上游 4.7.0，CRLF 归一后比对

# 4. 按判定结果移植：吸收 / 移植 / 不跟，逐条写清理由

# 5. 移植完跑测试 + 重新出镜像（GHCR 拉取方式，见 README）
pytest tests/ && python3 scripts/check-version-lock.py --set <新版本>
```

#### 硬约束（历次跟进得出的，别踩）

- **`webserver/settings.py` 禁止整体合并** —— 上游的默认值 / 键名有破坏性变更，
  整体合并会改掉我们的模块门控与默认值。
- **冲突判定不许估**：每个「上游改过且我们也改过」的文件都要真做三方合并，
  冲突块数才是数字。上轮实测 68 个重叠文件里 **32 可自动合并 / 28 会冲突**。
- **安全修复优先级最高**：即使功能不移植，若该修复覆盖的是「我们已移植功能的攻击面」，
  必须一起带过来。

---

## 附录：排障实录（历史排错文档并入）

> 以下为历史上三篇独立排错文档的原文，按用户要求并入「历史变革」。

> 保留完整证据链与排查弯路，供以后遇到同类现象时对照。按问题现象查找即可。



---

### 故障复盘：所有书籍首屏空白（预渲染壳 + `asyncData` 只在构建期执行）

> 一句话：页面壳、标题、页码、页脚、侧栏计数全都正常，只有书籍网格是空的；
> 强刷无效、Console 干净、Network 里**压根没有取书请求**。
> 真因不是接口、不是缓存、不是旧 chunk，而是**取数入口**：静态产物里 `asyncData` 只在构建期执行，
> `beforeRouteUpdate` 只在同组件切路由/翻页时触发，直接进入 `/all` 时两个入口都不触发。

- 发生环境：用户 NAS 上的 `4.6.0-build.27-r25`（及更早）镜像，浏览器强刷 `/all`
- 表现页面：`/all`「所有书籍」（`ListBook.vue`，`all.vue` 是它的薄壳）
- 引入时间：不是某次提交引入的「新 bug」，而是静态预渲染架构下一直存在的入口缺口；
  r24 重建 dist、r25 加构建门禁之后仍能复现，说明与 dist 完整性无关
- 修复提交：`02ad7a9`（`this.alert` / 页大小 / 卡片开销）、`0070cb5`（首屏取数 + 全站审计）、
  `52648d9`（`lint:refs` 首屏取数规则）；文档另起一笔
- 交付版本：`4.6.0-build.27-r26`

---

#### 0. 摘要

| 项 | 结论 |
| --- | --- |
| 直接原因 | 直接进入 `/all` 时没有任何客户端取数入口被调用：`asyncData` 在静态产物运行时不执行，`beforeRouteUpdate` 只在同组件切换时触发 |
| 为什么「有时正常」 | 从侧栏其它列表页点入时组件复用（都是 `ListBook`），`beforeRouteUpdate` 被触发 |
| 为什么 Console 干净 | 没有异常，也没有未捕获 rejection；只是「没人发请求」 |
| 为什么强刷无效 | 强刷只是重新下载同一个预渲染壳，壳里 payload 是 `data:[{}]`，不会触发生成期逻辑 |
| 影响面 | `/all`、`/audiobooks`、`/favorites`、`/reading`、`/printbooks`、`/read-done`、`/soledbooks`、`/visits`、`/wants`、`/meta/*`；`/rating`、`/publisher`、`/language`（`ListMeta` 同构）；`/admin/syslog`、`/toolbox/:id` |
| 修复 | `mounted` 首屏兜底 + `ssr_loaded` 去重 + 请求令牌；同类页一并修；`lint:refs` 加规则防回归 |
| 是否已上线 | 代码在本地 `52648d9`，包在 r26；**必须重建镜像**，`docker cp` 只临时 |

---

#### 1. 现象与截图证据

用户提供的现场截图与 Network 记录（同一时刻）：

**页面壳完整**

- 顶部标题「所有书籍」、翻页控件 `‹ 1 ›`、页脚「系统版本: 4.6.0-build.27」都在；
- 左侧栏计数正常：目录 2、有声书 11、实体书 2、作者 35、分类 11、标签 74、出版社 30、丛书 6；
- 右侧悬浮按钮（翻译 / 上传等）存在；
- **中间书籍网格完全空白，没有卡片，也没有空态提示文案**。

**Network（强刷后约 21 条）**

| 请求 | 状态 | 大小 | 时间 |
| --- | --- | --- | --- |
| `all`（文档） | 200 | 5.2 kB | 14 ms |
| `f53b51f.js` | 200 | 4.0 kB | — |
| `47409de.js` | 200 | 91.3 kB | — |
| `c5b7bb7.js` | 200 | 78.0 kB | — |
| `ad3c9ea.js` | 200 | 51.6 kB | — |
| `e7cd90c.js` | 200 | 7.6 kB | — |
| `e61364c.js` | 200 | 512 B | — |
| CSS / 字体 | 200 | — | — |
| `info` | 200 | 2.2 kB | — |
| `messages?after_id=0` | 200 | 272 B | — |
| `running` ×2 | 200 | 251 B | — |
| 图标 / 头像 / favicon | 200 | — | — |

**关键否定事实**：列表里**没有任何取书请求**——既没有 `/api/all`，也没有其它书籍接口；
`Console` 无报错、无警告。

截图 + Network 的组合把故障范围压到了「请求从未发出」，而不是「请求失败」或「渲染失败」。

---

#### 2. 关键排查过程与被推翻的判断

排查是按「先排除外层，再往调用链里走」推进的。下面每一条都记录了**当时为什么看起来成立**、
**被什么证据排除**，避免下次重复走弯路。

| # | 被推翻的判断 | 当时为什么像 | 排除证据 |
| --- | --- | --- | --- |
| 1 | 接口返回空数组 | 页面空白、无卡片；`total` 可能为 0 | Network 里**没有该请求**；空数组至少会有一次 200 与响应体 |
| 2 | 浏览器缓存 / Service Worker / CDN | 强刷前空白，怀疑拿到旧 HTML 或旧 JS | `Ctrl+Shift+R` 后仍空白；`all` 文档本身 200、5.2 kB；且请求根本没发 |
| 3 | 旧 chunk 404（dist 重建后 index 与 chunk 不匹配） | r24 刚重建过 dist，历史上确实出过 362/757 的残缺包 | 所有 chunk 全部 200；chunk 404 会在 Console 留错，且整页白而不是「壳正常、网格空」 |
| 4 | 事件循环阻塞 / `HeavyGate` 503 / `server_starting` | 之前有过「转圈」「busy」的故障 | 阻塞或 503 会先有请求（pending 或 5xx）；这里是零请求 |
| 5 | nginx / 反向代理 / 鉴权把请求吞了 | 只有 `/api/*` 受影响时很像代理 | 代理只能影响「已发出的请求」；Network 里没有请求记录 |
| 6 | `modeText` 同类：render 抛错被吞 | r24 刚修过「方法误入 computed」的空白/转圈 | render 抛错必在 Console 留 `TypeError`；本次 Console 干净 |
| 7 | `this.alert` 静默失败 | 同一页面确实存在这个 bug，且表现也是「空白无提示」 | 它只会在**请求失败**的错误分支触发；强刷时请求根本没发，所以不是本次主因（但与本次同批修掉） |

**结论**：1~7 全部排除后，只剩下「取数函数没有被调用」这一种解释。随后用户补的两条现场事实
（Console 干净、从侧栏点入正常）进一步把它锁定为**入口差异**，而不是数据或网络问题。

---

#### 3. 决定性证据

三条证据互相印证，缺一不可：

1. **Network 无取书请求**。如果是接口、代理、渲染、缓存问题，至少会有一次请求或一条 Console 报错。
2. **从侧栏其它列表页点入 `/all` 正常，直接打开/强刷失败**。同一份 JS、同一套接口，
   唯一差别是路由进入方式——这说明取数挂在「路由变化」而不是「组件创建」。
3. **`app/dist/all/index.html` 是预渲染壳**：23,273 字节，`data-server-rendered`，
   payload 里是 `data:[{}]`（构建期后端不可达，`asyncData` 拿到空对象），
   线上 gzip 后约 5.2 kB，与 Network 的 `all` 文档大小一致。
   也就是说：**壳里没有书，运行时也不会再去取**。

对照代码（修复前）：

```js
// ListBook.vue（修复前）
async asyncData({route, app, res}) {
  if (res !== undefined) res.setHeader('Cache-Control', 'no-cache');
  return app.$backend(route.fullPath);       // ← 只在构建期/SSR 执行
},
beforeRouteUpdate(to, next) {
  this.init(to, next);                       // ← 只在同组件路由更新时执行
},
```

`mounted` / `created` 里没有取数；`watch` 也没有兜底。

---

#### 4. 真因（机理）

`app/package.json` 的构建脚本是 `nuxt generate --spa`，`target: 'static'`。它的产物有两层含义：

1. **构建期**：Nuxt 用 SSR 把每条路由渲染成 HTML，`asyncData` 在这里执行一次，
   结果序列化进 `window.__NUXT__.data`；
2. **运行期**：浏览器加载这个 HTML 并 hydrate，**不会**再执行 `asyncData`。
   之后的客户端路由切换（`nuxt-link` / `router.push`）也不会执行 `asyncData`。

而 `beforeRouteUpdate` 的触发条件是「**同一个组件实例**被复用，路由参数或 query 变化」。
跨组件导航（例如从首页到 `/all`）是新组件挂载，不触发它。

两条路径叠起来就是：

| 进入方式 | `asyncData` | `beforeRouteUpdate` | 结果 |
| --- | --- | --- | --- |
| 直接打开 / 强刷 `/all` | 构建期跑过，运行时不跑 | 不触发（首次挂载） | **零请求** |
| 侧栏在列表页之间点击 | 不跑 | 触发（同一 `ListBook` 复用） | 正常 |
| 在 `/all` 上翻页 `‹ 1 ›` | 不跑 | 触发（query 变化） | 正常 |

这也解释了「同一本书重复点结果不一定一样」的历史观感：差别不在书，而在**上一次停留的页面**
是否与目标页共用同一个列表组件。

---

#### 5. 修法与去重机制

### 5.1 首屏补一次取数

`ListBook.vue` / `ListMeta.vue`：

```js
mounted() {
  if (!this.ssr_loaded && !this.inited) {
    this.init(this.$route);
  }
},
```

- `mounted` 保证「组件首次挂载」一定执行一次；
- `beforeRouteUpdate` 保留，负责同组件切路由/翻页；
- `init()` 内已有请求令牌（`_reqToken`）：
  每次发起自增，回调里比对令牌与 `$route.fullPath`，旧响应直接丢弃，不会覆盖新页面。

### 5.2 不产生重复请求

`asyncData` 只在**真的取到数据**时打标记：

```js
const rsp = await app.$backend(route.fullPath, { timeout: 20000 });
if (rsp && rsp.err === 'ok') {
  return Object.assign({}, rsp, { ssr_loaded: true });
}
return rsp || {};
```

- `nuxt dev` / 未来 SSR 部署：`asyncData` 成功 → `ssr_loaded=true` → `mounted` 跳过，只有一次请求；
- 静态产物直入：构建期 `asyncData` 拿到的是错误/空对象 → 不标记 → `mounted` 补一次；
- 构建期失败也算「没取到」，所以不会把构建时的空结果当成运行时已加载。

### 5.3 同类页一并修

| 文件 | 改动 |
| --- | --- |
| `ListMeta.vue` | `created` 里的 `init` 被注释掉，只剩 `asyncData`；补 `mounted` + `ssr_loaded` |
| `admin/syslog.vue` | 只有 `asyncData`；补 `mounted → fetchLog()` + `ssr_loaded` |
| `toolbox/_id.vue` | 只有 `asyncData`；补 `mounted → loadTool()` + `ssr_loaded` |

---

#### 6. 全站审计（68 个自有页面，4 处命中）

口径：`app/src/pages/**/*.vue`，跳过只做 `export default ListBook/ListMeta` 的薄壳（行为继承）。
按 6 类形态检索：

1. `watch` 路由取数但无 `immediate` 且无生命周期兜底；
2. 只在 `routeChanged` / `$nuxt.$on` / `nuxt-link` 事件里取数；
3. 只有 `activated`，无 `created`/`mounted` 兜底；
4. 取数被首屏不成立的判断（登录态 / store 字段 / query 默认值）提前 `return`；
5. 依赖上一页传参，缺失时静默 `return`；
6. `asyncData` 在静态产物运行时不会执行。

| 页面 | 命中形态 | 直接进入的结果 | 处理 |
| --- | --- | --- | --- |
| `ListBook.vue` + 9 个薄壳（`all`/`audiobooks`/`favorites`/`reading`/`printbooks`/`read-done`/`soledbooks`/`visits`/`wants`）+ `_meta/_name` | 6 | 不发请求、永久空白 | 已修 |
| `ListMeta.vue` + `rating`/`publisher`/`language` | 6（`created` 里的 `init` 被注释） | 空列表 | 已修 |
| `admin/syslog.vue` | 6 | 永远「暂无日志」 | 已修 |
| `toolbox/_id.vue` | 6 | 永远「工具不存在或已禁用」 | 已修 |
| `welcome.vue` | 6 | 安装引导页，无列表数据；只是不跳转 | 不改，lint 白名单 |
| `s/_token.vue` | 6 | `err` 默认 `ok`，`mounted` 的 `verify()` 会重新取数，自愈 | 不改 |
| `search` / `folder` / `booklist/_id` / `booklists/*` / `history` / `memos` / `expected` / `admin/*` | —（`created` 或 `mounted` 取数） | 正常 | 不改 |
| `author` / `tag` / `series` / `_bookid` / `readtxt` / `index` / `audio/_id` | —（`created`/`mounted` 取数，`watch` 只做二次响应） | 正常 | 不改 |
| `starting.vue` | —（`mounted → poll()`） | 正常 | 不改 |

**判定依据**：逐个读 `<script>` 段，确认 `created`/`mounted`/`activated` 的钩子体内有取数调用
（`this.init(` / `fetchX(` / `loadX(` / `$backend` / `poll(` / `verify(`）；
`watch: {'$route…': …}` 只在「handler 内取数 + 缺 `immediate` + 无生命周期取数」时才算命中。

**防回归**：`app/scripts/check-vue-method-refs.js` 现在同时做两件事：

1. 原有：扫描 129 个 `.vue`，发现 `this.NAME()` 调用了不存在的成员（`this.alert` / `modeText` 这类）；
2. 新增：`pages/**` 的「首屏取数审计」——只有 `asyncData`、或只靠路由 `watch` 且缺 `immediate`
   又没有生命周期兜底时，`--strict` 直接退出 1。

当前结果：**脚本级错误 0、模板待确认 0、首屏隐患 0（68 页）**。

---

#### 7. 同批次另两处修复

### 7.1 `this.alert` → 不存在成员导致静默失败

`ListBook.vue` 的错误分支原来写的是 `this.alert("error", msg)`。
Vue 插件用 `inject('alert')` 暴露的是 **`this.$alert`**，`this.alert` 是 `undefined`：
调用即 `TypeError: this.alert is not a function`，而它发生在 `$backend().then(...)` 回调里，
异常被 Promise 链吞掉，`books` 停在 `[]` —— 界面既没书、也没提示。

修法：

- 改成 `this.$alert(...)`（`_bookid.vue` 的 `init()` 同步修，并给 `msg` 兜底）；
- 新增 `load_error` / `errorText` 与两种可见状态：
  「加载失败 + 重试」卡片、`loaded && !books.length` 时显示「暂无书籍」；
- `store` 的 `alert` mutation 对空 `msg` 直接返回，避免弹窗组件拿到空对象；
- 三语（zh / zh-TW / en）与 `delivery/overlay` 副本新增 `listBook.empty / loadFailed / retry`。

### 7.2 页大小不封顶 → 第二页必空

`page_size` 从 `localStorage` / `store.default_page_size` 直接读，没有上限；
用户或被污染的值可能是 500、1000。后端 `MAX_PAGE_SIZE = 200`（LITE 60）会截断返回，
但前端仍按「每页 1000」计算 `start`：

- 第一页：`start=0&size=1000` → 后端只回 200 条；
- 第二页：`start=1000` → 越过总数 → **空列表**。

修法：新增 `app/src/utils/pageSize.js` 的 `clampPageSize(value, fallback, max=200)`，
`ListBook` 读取页大小时统一走它；后端 `MAX_PAGE_SIZE` 仍是最终闸门。

### 7.3 卡片渲染开销

`BookCards.vue` 的 `render_books` 原来直接改父级 `book` 对象（`b.href = ...`），
在长列表里会造成无谓的响应式触发；改为返回新对象 `{ ...b, href }`。
卡片样式增加：

```css
.book-list-card {
  content-visibility: auto;
  contain-intrinsic-size: 260px 120px;
}
```

让浏览器跳过视口外卡片的布局/绘制。配合页大小封顶，几十本到几百本的列表不再一次性付全量渲染成本。

---

#### 8. 性能实测与「暂不做」的决定

对「列表接口是否随书数线性变慢」做了静态审计与微基准：

- 无 `LIKE '%x%'`、无全表 Python 过滤；封面/音频标志不逐书 `stat`（走 `AudioBooksCache`）；
- `total` 有版本缓存，不是每次 `COUNT(*)`；
- 主瓶颈在前端一次渲染几十~几百张卡（已用 `content-visibility` 缓解）。

id 排序微基准：

| 规模 | 耗时 |
| --- | --- |
| 1,000 条 | 0.081 ms |
| 10,000 条 | 1.252 ms |
| 100,000 条 | 18.267 ms |

结论：排序本身不是瓶颈，**本轮不做**键集分页前端接入与 id 排序缓存——
后端 `after` / `next_cursor` 已支持，但前端改造面大、收益要等到万级书库才明显。
真到万级再按「先接游标、再谈缓存」的顺序做，避免为假想规模增加复杂度。

---

#### 9. 测试与静态检查

`tests/test_frontend_silent_failures.py`（16 条，实测 `16 passed`）：

| 用例 | 覆盖 |
| --- | --- |
| 全仓禁止 `this.alert(` | `this.alert` 这类「调用不存在成员」不再出现 |
| ListBook 必须用 `$alert` 且带 `load_error` / `errorText` | 错误必须有可见出口 |
| 模板含 `empty` / `loadFailed` / `retry` | 空态与失败态不能缺 |
| store `alert` 空文案保护 | 空消息不弹窗、不写坏状态 |
| 三语 + overlay 的 key 存在（3 个参数化） | 文案不漏语言 |
| `lint:refs --strict` 退出 0 | 成员引用 + 首屏取数审计 |
| 4 个页面（ListBook / ListMeta / syslog / toolbox）`mounted` 必须触发取数 | 守住「首屏必取一次」 |
| 同上 4 页必须用 `!this.ssr_loaded` 去重 | 守住「不重复请求」 |

---

#### 10. 教训

1. **预渲染壳页不能把 `asyncData` 当唯一取数入口。** 静态产物里它只属于构建期；
   任何「运行时必须最新」的数据都要有客户端入口（`mounted` / `created` / 路由 `watch` + `immediate`）。
2. **静默 catch 会把「报错」伪装成「空白」。** `this.alert` 的 `TypeError` 被 Promise 吞掉后，
   页面既不提示也不报错；错误分支必须有可见出口（错误卡片 / 空态 / 全局 errorHandler）。
3. **同类写法要全仓扫，不要单点修。** `modeText`（r24）、`this.alert`、`asyncData-only`
   是同一类问题的三种外衣；用静态扫描把它们变成规则，比每次靠用户报障便宜得多。
4. **区分「没发请求」和「请求失败」是排查分水岭。** 前者查生命周期与入口，后者查接口与网络；
   看一眼 Network 有没有那条请求，能省掉大半猜测。
5. **`dist` 的非构建资源来自 `public/`。** `app/public` 被删时 `generate` 只出 301 个文件，
   包看着能装、页面却缺 pdfjs/字体/图标；出包前必须整目录校验 757。

---

#### 附录 A：实测 / 推断 / 误判

**实测**

- 强刷 `/all` 的 Network 清单（21 条，无取书请求）与 Console 干净（用户现场提供）
- 从侧栏点入正常、直接进入失败（用户实测确认）
- `app/dist/all/index.html`：23,273 B、`data-server-rendered`、payload `data:[{}]`、gzip 约 5.2 kB
- 修复前 `ListBook.vue` 只有 `asyncData` + `beforeRouteUpdate` 两个取数入口
- 全站扫描 68 个自有页面，命中 4 处；修复后 `lint:refs --strict` 0 隐患
- `pytest` 16 passed；`npx eslint` 改动文件 0 error
- `npx nuxt generate` → 757 文件；`index.html` sha256 `b7c49b20…`

**推断**

- 「以前偶发正常」源于进入方式差异（是否与列表页共用组件），依据是 `beforeRouteUpdate` 的触发条件，
  没有逐次操作日志佐证。
- 构建期 `asyncData` 返回空对象，是因为构建环境没有可用后端；依据是 payload `data:[{}]`。

**误判（保留记录）**

- 一度把 `asyncData` 返回视为「运行时会重新执行」，于是先去查接口与缓存；
  实际静态产物只 hydrate，不重跑。
- 一度认为 `this.alert` 是本次主因；它确实是真 bug，但只能解释「请求失败后的空白」，
  解释不了「Network 零请求」。

---

#### 附录 B：复现与验证命令

```sh
### 1) 复现：直接打开 / 强刷（预期修复前零请求、修复后一次取书请求）
###    浏览器打开 /all → Ctrl+Shift+R → Network 过滤 Fetch/XHR

### 2) 确认 dist 是预渲染壳（payload 为空）
python - <<'PY'
import re
s = open('app/dist/all/index.html', encoding='utf-8').read()
print(len(s), '__NUXT__' in s, re.findall(r'data:\[[^\]]*\]', s)[:1])
PY

### 3) 静态扫描（成员引用 + 首屏取数审计，必须 0 错误 0 隐患）
cd app && node scripts/check-vue-method-refs.js --strict

### 4) 回归测试
python -m pytest tests/test_frontend_silent_failures.py -q

### 5) dist 完整性（757 + pdfjs 等非构建资源）
sh scripts/check-dist.sh

### 6) 容器内核对（升级后）
docker exec <容器> sh -c 'find /app-static/dist -type f | wc -l'          # 期望 757
docker exec <容器> sha256sum /app-static/dist/index.html
### 期望 b7c49b20c2e9042538dcdd9038e0c43557a18d7449922e159569e8ee509a1ebc

### 7) 构建期别把 app/public 弄丢（丢了只会出 301 个文件）
test -f app/public/static/pdfjs/web/viewer.html && echo "public ok"
```


---

### 故障复盘：读者组页面一直转圈

> 故障对象：后台「设置 → 读者组分级权限」面板
> 影响版本：`4.6.0-build.27-r18` ~ `r21`（引入提交 `aa457b8`，修复提交 `bc39f47`）
> 修复交付：`4.6.0-build.27-r24`（前端产物，dist 757 文件）
> 复盘日期：2026-11-11
> 证据等级：本文每条结论都标注「实测」或「推断」，被推翻的判断集中记在附录 A，**不要**再把它们当结论引用。

---

#### 0. 摘要

页面一直转圈、接口返回 `200` 且数据完整——**问题不在请求，在渲染**。

`ReaderGroupEditor.vue` 把 `modeText(mode)` 定义在 `computed` 里，模板却按方法调用
`{{ modeText(groups[name].mode) }}`。Vue 2 的 computed 是**无参属性**，求值得到字符串；
模板再对字符串加括号 → `TypeError: e.modeText is not a function`。

异常发生在 `_render` 期间，组件渲染中断，DOM 停在初始的
`<div v-if="!loaded && loading"><v-progress-circular></div>`；`reload()` 里
`loaded = true` 其实执行了，但已没有人能把它画出来。

| 维度 | 结论 |
| --- | --- |
| 直接原因 | `modeText` 误入 `computed`，模板带参调用 → 渲染期 TypeError |
| 引入 | `aa457b8`（读者组模板扩到 17 套，顺手把内联三元改成 `modeText(...)`） |
| 修复 | `bc39f47`：`modeText` 移入 `methods`；新增前端契约测试；按 `app/src` 重编 dist |
| 现场验证 | 用户 NAS 上用 r24 的 `app/dist` 覆盖运行中容器 → 读者组列表恢复（**实测**）；随后 `docker compose build` 重建镜像固化（见 §7.3） |
| 被排除 | 同步 IO 压住 ioloop、`calibre_pool` 饥饿、代理截断、旧镜像未重建、`prepare()` 同步 SQLite、8 秒护栏 |
| 附带事故 | 重编前端时 `app/dist` 丢了 395 个非构建资源（15,346,411 B），r23 只剩 362 / 应有的 757 |

---

#### 1. 现象

**实测**（用户环境 + 本地复现）：

1. 打开设置页，展开「读者组分级权限」：
   - 组列表区域只有一个无限旋转的 `v-progress-circular`；
   - 「分组权限」下拉框（模式选择）同时不出现——两者在同一个 `v-if` 分支里；
   - 不报错、不超时、没有「重试」入口，刷新后照旧。
2. DevTools → Network：`GET /api/admin/reader_groups` **200**，正文 **548 字节**，
   两个组的数据完整（组名、模式、分类、标签、成员都在）。
3. 保存（POST）能成功，只有「读出来展示」这一半是坏的。
4. 服务端日志无异常、无慢查询、无 5xx。

**关键矛盾**：接口好、数据好、页面不显示。这个矛盾贯穿了整个排查过程，也是早期所有
后端侧假设全部走空的原因。

---

#### 2. 时间线

| 阶段 | 动作 | 观察到的证据 | 当时的判断 |
| --- | --- | --- | --- |
| T1 | 用户报障：读者组不显示、一直转圈 | 接口 200、548 B、数据完整 | 先怀疑后端慢/卡（后来被推翻） |
| T2 | 查 Tornado 单线程、同步 IO | 其它 `/api/admin/*` 同时段正常；`reader_groups` 毫秒级返回 | ioloop 未被占（**实测**，见 §3.1） |
| T3 | 查 `calibre_pool` 线程池 | 响应在池排队前就完整返回 | 池饥饿不成立（**实测**，见 §3.2） |
| T4 | 查 handler `prepare()` 的同步 SQLite | 响应体完整、无慢日志 | 不成立（**实测**，见 §3.5） |
| T5 | 怀疑 nginx / 外层代理截断 | Response 面板 548 B 完整，无 JSON 解析错误 | 不成立（**实测**，见 §3.3） |
| T6 | 怀疑旧镜像未重建 | 部署后 `index.html` 指纹已变；报错栈指向新 chunk `a8c2eb4.js` | 不成立（**实测**，见 §3.4） |
| T7 | r20 加 `server_starting` 整页兜底 + 20s 超时 | 部署 r21 后**仍然转圈** | 归因错误（见 §3.6 与附录 A） |
| T8 | 用户贴出浏览器 Console | `TypeError: e.modeText is not a function`，`a8c2eb4.js:1:17741` | **决定性证据**（见 §4） |
| T9 | 对源码 + 对产物 | `modeText` 定义落在 `computed` 区间内；调用点列号 17741 与源码一致 | 根因确认（**实测**） |
| T10 | 修复 `bc39f47`，重编 dist，加契约测试 | 新 chunk `fa190f8.js` 中 `modeText` 已在 `methods` | 修复完成（**实测**） |
| T11 | 用户 NAS 现场替换 dist | 页面恢复，不再转圈 | 闭环（**实测**） |
| T12 | 复核部署包 | 发现 r23 dist 只有 362 / 应有 757，漏 395 个资源 | 副线事故（见 §8） |

---

#### 3. 走过的弯路：每条被排除的假设

> 写这一节的目的是：这些假设在提出时都有「像那么回事」的依据，事后看全是把
> 「页面不显示」误当成「请求不回来」。每条都给出**推翻它的那条证据**。

### 3.1 同步 IO 压住 ioloop

- **提出依据**：后端是 Tornado 单进程；「页面等很久」最经典的原因就是事件循环里有同步
  阻塞调用（文件 IO、`requests`、`subprocess`），把整个 loop 卡住，所有请求一起变慢。
- **推翻证据**（**实测**）：同一时间段其它 `/api/admin/*` 正常返回；`reader_groups`
  本身毫秒级返回 200、正文 548 B 完整。若 ioloop 被占，不可能只坏这一个面板，
  更不可能坏在「数据已经返回之后」。
- **更强的反证**：把修好的 `app/dist` 用 `docker cp` 扔进**运行中的**容器即可恢复，
  后端进程一个字节都没动。与后端线程模型无关。

### 3.2 `calibre_pool` 线程池饥饿

- **提出依据**：读者组要按分类/标签解析可读书目，会走 calibre 相关查询；线程池被长任务
  占满时，请求会排队等待，表现就是「转圈」。
- **推翻证据**（**实测**）：响应在池超时之前就完整返回，且返回的是**完整 JSON**
  （两个组齐全），不是超时后的降级响应；服务端无池等待日志。
- **教训**：池饥饿会表现为「慢/超时/502」，不会表现为「200 + 数据完整 + 前端不画」。

### 3.3 nginx / 外层代理截断

- **提出依据**：此前刚遇到部署包下载被截断（`tar: A lone zero block`），
  很容易顺势认为 HTTP 响应也被中间层截了一半，导致前端 `JSON.parse` 失败。
- **推翻证据**（**实测**）：DevTools 的 Response 面板里 548 B 完整可见，没有
  `Unexpected end of JSON input`；Console 里的错误是 `TypeError`，不是解析错误。
  截断类问题一定伴随长度/解析异常。

### 3.4 旧镜像未重建 / 前端没更新

- **提出依据**：多次热更后，容器里跑的可能还是旧静态资源，「改了没生效」很常见。
- **推翻证据**（**实测**）：
  1. 部署后首页 `index.html` 指纹已经变化；
  2. 浏览器报错栈指向 `a8c2eb4.js`——这是**新构建**的 chunk，旧包里没有这个名字；
  3. 也就是说：新代码确实上线了，新代码带着 bug 上线了。

### 3.5 `prepare()` 里同步 SQLite 读

- **提出依据**：该 handler 的 `prepare()` 阶段会读库；同步 SQLite 读在单线程里同样能卡 loop。
- **推翻证据**（**实测**）：响应 200、正文完整、无慢查询日志；且同 §3.1 的 `docker cp`
  反证——只换前端静态文件即恢复，`prepare()` 根本没被触发过问题。

### 3.6 「8 秒护栏盖不住」——把超时兜底当成了修复

- **提出依据**：既然怀疑是「等太久」，那给 `await` 套一个超时（早期版本 8 秒，
  r20 提到 20 秒），最坏也能停下来报错，不至于无限转圈。
- **推翻证据**（**实测**）：转圈没有上限，也从未出现超时提示；r20/r21 都加了兜底，
  现象一模一样。
- **真正的解释**（**实测 + 代码推导**）：护栏其实**跑到了**——`reload()` 末尾的
  `this.loading = false` 与 `loadError` 赋值都执行了。但组件 `_render` 每次都抛
  `TypeError`，Vue 无法完成渲染，**任何状态变更都无法反映到 DOM**。
  所以「护栏没兜住」的真实含义不是「等得比 8 秒久」，而是「状态更新没有出口」。

> 这一条是整次排查最贵的教训：**spinner 不消失 ≠ 请求没结束**。
> 状态可能早就更新了，只是渲染已经死了。

---

#### 4. 决定性证据

### 4.1 浏览器 Console

```
TypeError: e.modeText is not a function
    at a8c2eb4.js:1:17741
```

三条信息同时成立，才把「前端渲染」这条线钉死：

1. `TypeError` —— 不是网络错误、不是解析错误、不是 5xx；
2. `modeText` —— 正是该模板里新引入的方法名；
3. 明确的文件 + 行列 —— 可以直接回到源码对齐。

### 4.2 `modeText` 的定义位置（实测）

老产物 `a8c2eb4.js`（sha256 `77662f525899e6c807ea63e75fec7077966f95d9c38665f2c4cca169da788de8`，
19,731 B，单行压缩）：

| 记号 | 1-based 列号 |
| --- | --- |
| `computed:{` 起点 | 1891 |
| `modeText:function` 定义 | 2294（**落在 computed 区间内**） |
| `methods:{` 起点 | 3512 |
| 模板里的 `modeText(` 调用 | **17741** |

对照修复后的 `fa190f8.js`：

| 记号 | 1-based 列号 |
| --- | --- |
| `computed:{` 起点 | 1891 |
| `methods:{` 起点 | 3327 |
| `modeText:function` 定义 | 3336（**紧跟 `methods:{`**） |
| 模板里的 `modeText(` 调用 | 17741（调用点没变） |

`modeText:function` 在旧包里位于 `computed` 区间，在新包里位于 `methods` 之后——
这是同一个函数、同一处调用，只换了归宿。

### 4.3 列号与源码对齐（实测）

- Console 报的是 `1:17741`，与上面解析出的调用点列号**完全一致**；
- `app/src/components/ReaderGroupEditor.vue` 第 180 行：
  `{{ modeText(groups[name].mode) }}`，是整份模板里唯一一处 `modeText(` 调用；
- 因此报错栈确实指向这一行，不存在「另一个同名方法」的可能。

### 4.4 为什么 DOM 冻在 spinner

模板结构（当前源码 L159-L163）：

```html
<div v-if="!loaded && loading" class="text-center py-4"><v-progress-circular indeterminate></v-progress-circular></div>
<div v-else-if="loadError" ...>...</div>
```

初次渲染时 `loaded=false`、`loading=true`，先画出 spinner；随后的渲染在
`modeText(...)` 处抛错 → patch 中断 → 屏幕上保留**上一次成功渲染的结果**，即 spinner。
此后 `groups` 被赋值、`loaded` 变 `true`、`loading` 变 `false`，全部写进了组件状态，
但没有任何一次渲染能完成，所以用户永远看不到列表。

这解释了所有「矛盾」现象：

| 现象 | 解释 |
| --- | --- |
| 接口 200、数据完整 | 请求链路完全正常 |
| 页面只有 spinner | 首次渲染成功（还没走到 `modeText`），后续渲染全部中断 |
| 保存能用 | POST 不走这条渲染路径，且成功提示由别的组件渲染 |
| 刷新无效 | 每次挂载都会重新走同一段坏模板 |
| 加超时无效 | 状态更新了，但没有渲染出口（§3.6） |

---

#### 5. 根因

引入提交 **`aa457b8`**（`feat(reader-group): 模板扩到 17 套并分栏；修「成人家属」模板本身不可用`）
做了两件事，单独看都合理，合在一起就炸：

```diff
-            <td>{{ $t(groups[name].mode === "whitelist" ? "settings.reader_group_mode_whitelist" : "settings.reader_group_mode_blacklist") }}</td>
+            <td>{{ modeText(groups[name].mode) }}</td>
```

```diff
+    // 组列表里的模式列：三态映射，别再写成二元三元表达式
+    modeText(mode) {
+      if (mode === "open") return this.$t("settings.reader_group_mode_open");
+      return this.$t(mode === "blacklist" ? ... : ...);
+    }
```

——这个 `modeText(mode)` 被加进了 **`computed` 对象**（旧源码 L279）。

于是运行期发生两件事：

1. Vue 2 把 computed 当**无参属性**求值一次：`modeText` 变成 `modeText(undefined)` 的返回值，
   也就是一个**字符串**（比如「白名单」）；
2. 模板对这个字符串求值 `字符串(...)` → `TypeError: ... is not a function`。

根因不是「三态映射」这个需求，而是**把方法写进了 computed**。Vue 只对
`methods` 里的成员按函数调用，computed 的成员永远是「已求值的值」。

---

#### 6. 修复

提交 **`bc39f47`**（`fix(reader-group): modeText 误放 computed 致渲染中断，按 src 重编 SPA 产物`）：

| 文件 | 改动 |
| --- | --- |
| `app/src/components/ReaderGroupEditor.vue` | `modeText` 从 `computed` 移到 `methods` 首位，逻辑与返回值不变；保留注释说明「模板带参调用 ⇒ 必须在 methods」 |
| `tests/test_reader_group_frontend_contract.py` | 新增 3 条契约测试（见下） |
| `app/dist/**` | 用 `app/src` 重新 `nuxt generate`，`_nuxt` 全部换成新产物 |

契约测试锁住三件事：

1. **模板里不得对 computed 的键带参调用** —— 解析 `<template>` 段（`src.rindex("</template>")`
   截断），把 `computed` 的键名逐个在模板中匹配 `key(`；命中即失败。
   这条测试在旧源码上**确实会红**（已回放验证）。
2. `modeText` 必须出现在 `methods` 段内。
3. `dist` 必须包含只存在于 `src` 的文案片段——防止「改了源码没重编」。

> 这类错误 TypeScript 也拦不住（Vue 2 的 `this` 是 any），静态检查只能靠
> 「模板 vs computed keys」这种结构性断言。见《开发指南》踩坑 #18。

---

#### 7. 验证

### 7.1 现场（用户 NAS，实测）

1. 取 r24 包内的 `app/dist`；
2. `docker cp` 覆盖进**正在运行**的容器；
3. 浏览器强刷 → 读者组列表出现，「分组权限」下拉恢复，不再转圈。

这一步同时完成了两件事：

- **确认修复**：只换前端静态产物即恢复；
- **反向证伪**：后端进程、容器、镜像、网络全部未动 → §3.1/3.2/3.3/3.5 的后端假设
  全部不成立；§3.4「旧镜像」也不成立（否则换文件不会生效）。

### 7.2 边界（实测）

**`docker cp` 只写容器的可写层**，容器一旦重建/重拉即回退。因此这次现场验证
**不是最终部署**，必须用包含 r24 `app/dist` 的镜像重新 `docker compose build` 固化
（已于 §7.3 完成）。

### 7.3 固化（用户 NAS，实测）

- `docker compose build mybooks` **构建通过**，pdfjs 的 COPY 层正常；
- 容器起来后，镜像内 `/app/dist/static/pdfjs/web/viewer.html` 与
  `/app/dist/_nuxt/fa190f8.js`（带 `modeText` 修复的 chunk）**均存在**；
- 页面正常，读者组不再转圈。

镜像内 `app/dist` 实际是 **824** 个文件 = 757 + 67 个历史残留 chunk（`rsync` 同步
构建上下文时未加 `--delete`）。残留 chunk 无引用、不影响功能；清理见 §8.4。

### 7.4 尚未覆盖

- 本次修复未做后端回归（没有任何后端改动）；
- 未在其它浏览器复测，但报错属于渲染期逻辑错误，与浏览器无关（**推断**）。

---

#### 8. 副线教训：重编前端丢了 395 个非构建资源

### 8.1 事实（实测）

`nuxt generate` **先清空 `dist/`** 再生成。而 `app/dist` 里除了构建产物，还有一批
**不是构建出来的**静态资源（历史手工放入）：PDF 阅读器、字体、壁纸、图标等。

| 包 | dist 文件数 |
| --- | --- |
| r20（原始 build.27） | **757** |
| r23（重编后，按「构建产物」口径清点） | **362** |
| r24（取回资源后） | **757** |

缺失的 **395 个文件、15,346,411 B**（gzip 后 4,994,974 B）：

| 目录 / 文件 | 数量 | 未压缩字节 |
| --- | --- | --- |
| `static/pdfjs/**`（PDF 阅读器） | 369 | 14,525,028 |
| `static/js/jquery-1.11.1.min.js` | 1 | 95,786 |
| `icons/*.svg` | 11 | — |
| `static/wallpaper/*` | 4 | — |
| `static/images/*` | 4 | — |
| `static/fonts/*`（Poppins） | 3 | — |
| `static/toolbox-bridge.js` | 1 | — |
| `robots.txt`、`static/README` 等 | 3 | — |

后果（**实测路径依赖**）：

- `webserver/settings.py:232`：`"PDF_VIEWER": "/static/pdfjs/web/viewer.html?file=%(pdf_url)s"`，
  被 `handlers/book.py:4211`、`4264` 使用 → 缺文件直接 **404**；
- `_nuxt/css/7b430fa.css` 里引用了 wallpaper / 字体 / 背景图 → 静默 404、样式退化；
- `toolbox/srt_tool/index.html` 引用 `static/toolbox-bridge.js` → 工具链断。

当时这些**不会让 docker build 失败**（Dockerfile 只强依赖 `dist/logo`、`dist/avatar`），
所以「构建成功」不能当作「产物完整」。**r24 之后已在 builder 末尾加硬门禁**：
`/app-static/dist/static/pdfjs/web/viewer.html` 不存在就直接 `exit 1`，并配
`scripts/check-dist.sh` 与 `pack.sh` 的整目录校验（见 §9.4）。

### 8.2 为什么按产物口径会漏（实测）

重编后逐目录对账：`_nuxt` 下 59 个旧 chunk 名在 321 个 html/js/css/json 中
**引用数为 0**（可安全删除）；但 395 个非 `_nuxt` 文件是**真实依赖**，不是垃圾。
把「构建产物 348 + logo/avatar 14 = 362」当成完整，就正好漏掉这 395 个。

### 8.3 处理（已做）

1. 从 r20 包原样取回 395 个文件写入 `app/dist`（回到 757）；
2. 同一批写入 `public/`（`nuxt.config.js` 的 `dir.static = '../public'`），
   以后 `generate` 自动带出，不再依赖手工补；
3. r24 重打包，清单记 `dist_files=757`、`dist_deleted=0`；
4. 校验脚本对比 r20 与 r24：剩余差异**只有** 59 个旧 `_nuxt` chunk（已被 59 个新 chunk 取代）。

### 8.4 校验口径（以后就这么做）

**整目录校验**，不要按「构建产物」口径：

```sh
### 文件数基线（r24 = 757）
find app/dist -type f | wc -l
### 关键目录必须存在且非空
test -f app/dist/static/pdfjs/web/viewer.html
test -f app/dist/static/toolbox-bridge.js
test -d app/dist/logo && test -d app/dist/avatar
### 与包内清单比对
tar -tzf audiobook-deploy-*.tar.gz | grep -c '^audiobook/app/dist/.*[^/]$'
```

镜像内的数量可能**多于** 757（实测 824 = 757 + 67 个历史残留 chunk）：`rsync` 同步
构建上下文时没加 `--delete`，旧 chunk 只增不减。清理必须用**白名单差集**：

```bash
tar -tzf audiobook-deploy-4.6.0-build.27-r25.tar.gz --wildcards 'audiobook/app/dist/_nuxt/*' | sed 's#^audiobook/app/dist/_nuxt/##' | sort > /tmp/keep.txt; ls /volume1/docker/audiobook/app/dist/_nuxt | sort > /tmp/have.txt; comm -23 /tmp/have.txt /tmp/keep.txt
```

**不要**用「扫引用」判断孤儿：排除 `_nuxt` 后扫描，会把运行时动态加载的
Vue 运行时 `84f214b.js`、语言包 `76d48a7.js` 误判成没人用。

---

#### 9. 部署侧教训

### 9.1 先校验，后破坏

r23 的 `tar: A lone zero block at 76268` 发生在解包阶段，而当时**容器已经停了**，
线上处于不可用状态。事后本地校验证明包本身完好（**实测**）：

| 项 | 结果 |
| --- | --- |
| 大小 | 209,171,397 B |
| SHA256 | `69f02594…` |
| MD5 | `7cc6ee31…` |
| `gzip -t` 全流解压 | 通过（595,456,000 B） |
| 成员数 | 47,112 |
| 尾部 512 B×2 零块 | 完整 |

报错位置 block 76268 × 512 ≈ **39,049,216 B**，约为 gzip 流的 **6.6%** —— 传输被截断的
典型特征，不是包坏了。

**四道门禁必须放在「停容器」之前**：

```sh
set -e
PKG=audiobook-deploy-4.6.0-build.27-r24.tar.gz
EXPECT_SIZE=219162163
EXPECT_SHA=2775c2e1ff1a2a7f01ab3e27babc88d4b2f6aa049e707a7b9fec44e99a717fb9
EXPECT_MEMBERS=47902

[ "$(stat -c %s "$PKG")" = "$EXPECT_SIZE" ] || { echo "大小不符"; exit 1; }
echo "$EXPECT_SHA  $PKG" | sha256sum -c - || exit 1
gzip -t "$PKG" || { echo "gzip 流损坏"; exit 1; }
[ "$(tar -tzf "$PKG" | wc -l)" = "$EXPECT_MEMBERS" ] || { echo "成员数不符"; exit 1; }
### 四道门禁全过，才允许 docker compose down / stop
```

更好的顺序：**先解到新目录再停服务**，解包失败不影响线上。

### 9.2 大包分片 + 逐片校验

200 MB 单文件在群晖/NAS 拷贝链路上断一次就得重传。
r24 已生成 4 片：`part01~03` 70,000,000 B + `part04` 9,162,163 B，
附 `.parts.sha256`（逐片）与整包 `.sha256` / `.md5`。合并后再过一遍整包 SHA。

### 9.3 `docker cp` 只能验证，不能交付

`docker cp` 写的是容器可写层：容器重建/重拉镜像即回退，且不会进入镜像，下次部署又没了。
它是**现场验证手段**，不是发布手段——发布必须 `docker compose build` 重建镜像。

### 9.4 构建期的三个坑（本次实测）

1. `COPY --from=builder /app-static/dist/{logo,avatar}/` 要求源路径**必须存在**，
   否则 BuildKit 直接 `failed to compute cache key`；
2. builder 阶段的预构建分支会 `cp -r /build/dist /app-static/dist` **整体重建**该目录，
   任何之前的 `mkdir` 都会被抹掉——所以兜底 `RUN mkdir -p` 必须放在它**之后**（当前是
   builder 最后一条指令）；
3. 光靠 `mkdir` 只保证构建不报错，**不保证产出的镜像内容完整**。r24 起在 builder 末尾
   增加了 pdfjs viewer 断言（缺则 `exit 1`），并在打包侧加了 `scripts/check-dist.sh`
   与 `pack.sh --check` 的 757 文件数校验。

### 9.5 群晖终端的两条操作约束（实测）

1. busybox 的 `tar` 带通配符（`-t` / `-x` 配 `*.js`）**必须加 `--wildcards`**，
   否则通配符会被当成字面量，结果为空或报错；
2. NAS 终端会把超长命令折行，粘贴多行或带 `\` 续行时容易得到
   `syntax error near unexpected token`——交给用户的命令**一律写成单行**，用 `;` 串联。

---

#### 10. 结论

1. **接口正常 ≠ 页面正常**。排查「一直转圈」时，第一步就该看 Console，而不是 Network 之后
   再猜后端。这次花了大量时间在后端线程模型上，全部无效。
2. **spinner 是渲染结果，不是状态**。状态早更新了、渲染死了，看起来和「请求没回来」
   一模一样。加超时、加兜底都救不了。
3. **Vue 2 的 computed 不接受参数**，模板带参调用 computed 成员必然在 render 期抛错。
   这类错误只能靠结构性测试锁住，靠 review 靠不住（它看起来只是「把三元抽成方法」）。
4. **「构建成功」不等于「产物完整」**。`nuxt generate` 会清空 dist，非构建资源必须放在
   `public/` 并做整目录校验。
5. **部署要先校验后破坏**；大包用分片；`docker cp` 只用于验证。

---

#### 11. 后续动作清单

| # | 动作 | 状态 |
| --- | --- | --- |
| 1 | `modeText` 移入 `methods`，重编 dist | ✅ 已完成（`bc39f47`） |
| 2 | 新增前端契约测试（computed 不得带参调用） | ✅ 已完成 |
| 3 | 395 个非构建资源回填 `app/dist` 与 `public/` | ✅ 已完成（`61f1213`） |
| 4 | r24 重新打包并按整目录口径校验（757） | ✅ 已完成 |
| 5 | 文档更正：CHANGELOG / 开发指南 / 部署包说明 / 本报告 | ✅ 已完成 |
| 6 | 用 r24 重建镜像固化，替代 `docker cp` 临时方案 | ✅ 已完成（§7.3 实测：`docker compose build` 通过，镜像内 `static/pdfjs/web/viewer.html` 与 `fa190f8.js` 均存在，页面正常，dist 按 757 校验） |
| 7 | 部署脚本并入 §9.1 四道门禁（先校验后停容器） | ⏳ 待用户执行（核对 `scripts/deploy.sh`、`scripts/upgrade.sh` 与 `delivery/overlay` 副本，目前只有 `index.html` 的 sha256 比对，尚无大小 / 整包 sha256 / `gzip -t` / 成员数四道） |
| 8 | CI 增加 dist 整目录文件数基线（757）与关键路径存在性检查 | ⏳ 建议 |
| 9 | 把 `tests/test_reader_group_frontend_contract.py` 纳入必跑集 | ⏳ 建议 |

---

#### 附录 A：实测 / 推断 / 当时的误判

### A.1 明确属于「实测」的结论

- 接口 `200`、548 B、数据完整；页面只显示 spinner（用户环境）。
- `a8c2eb4.js` 中 `modeText:function` 位于 `computed` 区间内（列 2294，区间 1891–3511）。
- `fa190f8.js` 中 `modeText:function` 紧跟 `methods:{`（列 3336）。
- 两版 `modeText(` 调用点均在 1-based 列 **17741**，与 Console 报错一致。
- `a8c2eb4.js` sha256 `77662f52…`。
- 契约测试在旧源码上会失败、在新源码上通过。
- `docker cp` r24 的 dist 后页面恢复。
- r20 dist 757 / r23 362 / 缺 395 个（15,346,411 B，gzip 4,994,974 B）。
- 59 个旧 `_nuxt` chunk 在 321 个文本文件中引用数为 0。
- r23 包本地完整性检查全部通过；解包失败位置 block 76268 ≈ 6.6% 流长。
- r24 包：219,162,163 B / 47,902 成员 / 191 个符号链接（包内口径） / dist 757。

### A.2 属于「推断」的结论

- r23 解包失败的直接原因是**传输截断**（本地包完好 + 报错位置特征，但未抓到传输日志）。
- `calibre_pool` 在故障时段的排队情况——没有抓到池指标，结论来自「响应完整且毫秒级」的反证。
- 保存路径不受影响的原因（不走该渲染分支）——基于代码结构推断，未逐行插桩。
- 浏览器无关性——未跨浏览器实测。

### A.3 当时的误判（保留记录，不要再当结论）

| 误判 | 当时的说法 | 后来被什么推翻 |
| --- | --- | --- |
| 误判 1 | 「r20 转圈」是服务启动期 `server_starting` 返回永不 settle 的 Promise（`99b3527` 的归因） | 接口 200、548 B 完整；r21 仍转圈；Console 是渲染期 TypeError |
| 误判 2 | 「5.8 MB 体积差是废弃 chunk」 | 逐目录对账：395 个**真实依赖资源**缺失，废弃 chunk 只占 59 个且引用为 0 |
| 误判 3 | 「r23 只是传输截断，包内容没问题」 | 传输截断属实，但 r23 的 dist 只有 362 / 应有 757，**内容本身也不完整**（两件事叠加） |
| 误判 4 | 「加超时护栏就能兜住转圈」 | 护栏执行了，但渲染已中断，状态变更无法反映到 DOM |
| 误判 5 | 「后端线程/IO/代理」方向 | `docker cp` 只换前端文件即恢复，后端未动 |

> 误判 2 与误判 3 是同一个坑的两面：用「构建产物」口径解释体积，就会把
> 「缺文件」误读成「删了垃圾」。

---

#### 附录 B：复核命令

```sh
### 1) 老产物里 modeText 的归属（需要保留旧包或旧 commit）
git cat-file blob f819cc3:app/dist/_nuxt/a8c2eb4.js > /tmp/old.js
python3 - <<'PY'
s = open('/tmp/old.js', encoding='utf-8').read().split('\n')[0]
print('computed', s.find('computed:{') + 1, 'methods', s.find('methods:{') + 1)
print('def', s.find('modeText:function') + 1, 'call', s.find('modeText(') + 1)
PY

### 2) 新产物
python3 - <<'PY'
s = open('app/dist/_nuxt/fa190f8.js', encoding='utf-8').read().split('\n')[0]
print('methods', s.find('methods:{') + 1, 'def', s.find('modeText:function') + 1)
PY

### 3) 契约测试
python -m pytest tests/test_reader_group_frontend_contract.py -q

### 4) dist 完整性
find app/dist -type f | wc -l            # 期望 757
test -f app/dist/static/pdfjs/web/viewer.html && echo pdfjs-ok

### 5) 包完整性
sha256sum -c audiobook-deploy-4.6.0-build.27-r24.tar.gz.sha256
gzip -t audiobook-deploy-4.6.0-build.27-r24.tar.gz
tar -tzf audiobook-deploy-4.6.0-build.27-r24.tar.gz | wc -l   # 期望 47902
```


---

### 故障复盘：豆瓣 v1 残留导致的「更新元数据」500

> 一句话：删掉了豆瓣 v1 插件和它的 `import`，但漏掉了 `book.py` 里一句
> `if provider_key == douban.KEY:`。这行位于所有 provider 的公共路径上，
> 于是**任何来源**的「更新元数据」都会 `NameError` 500，和用不用豆瓣无关。

- 发生环境：用户 NAS 上的 `4.6.0-build.27-r24` 镜像
- 报错位置：`webserver/handlers/book.py` 第 1310 行，`BookRefer.post`
- 引入提交：`4f7c427`（`chore(meta)!: douban v1 尸体彻底清除`，随 build.27-r12 发布）
- 修复提交：`65ff4cb`（服务端）、`c08e823`（文档）；热更包 `audiobook-hotfix-4.6.0-build.27-r25-douban1.tar.gz`

---

#### 0. 摘要

| 项 | 结论 |
| --- | --- |
| 直接原因 | `BookRefer.post` 里 `if provider_key == douban.KEY:` 引用了已删除的模块，求值即 `NameError` |
| 影响面 | 「更新元数据 / 仅更新封面 / 仅更新作者简介」三个 POST 动作全部 500；页面浏览、阅读、搜索不受影响 |
| 为什么没早发现 | 该分支不是页面加载路径，只在用户手动点「更新元数据」时触发；且 500 被前端当成普通失败提示 |
| 为什么删 v1 时没发现 | 删除提交只改了 `import` 行、`douban.str2date` 与文案，**没有扫描跨模块常量引用** `douban.KEY` |
| 修复 | 抽出 `_resolve_refer_mi`，删除 v1 分支；存量 `provider_key="douban"` 仍按 v2 流程正常保存 |
| 防回归 | 8 条测试，其中一条用 AST 静态检查禁止 `webserver/**` 出现未绑定的 `douban.` 属性访问 |
| 是否已上线 | 代码在 `65ff4cb`（r25）；线上可先用热更包临时顶住，正式仍须重建 r25 镜像 |

---

#### 1. 现象

线上日志：

```
File "/var/www/mybooks/webserver/handlers/book.py", line 1310, in post
    if provider_key == douban.KEY:
NameError: name 'douban' is not defined
```

前端表现：书籍详情页点「更新元数据」（或「仅更新封面」）后请求返回 500，页面提示失败，
有时表现为一直转圈到超时。与选择哪个信息源（`calibre` / `douban_v2` / `xhsd` / `bookbarn`）无关。

**实测**：异常发生在 `post` 的参数解析之后、任何 provider 逻辑之前，
因此「哪个源」不可能影响是否触发。

---

#### 2. 为什么这条分支长期没暴露

三个条件同时成立，缺一不可：

1. **只在写路径上**。`BookRefer.post` 是「更新元数据」的接口（前端 `POST /book/<id>/refer`），
   不是书籍详情页的加载接口。日常浏览、搜索、阅读都不会走到这里。
2. **对所有 provider 都先求值**。`if provider_key == douban.KEY:` 先算右值再比较，
   所以 `provider_key` 是 `calibre` 也照样抛异常——它不是一个"豆瓣专属"分支，而是公共路径上的地雷。
3. **失败被前端弱化**。500 在界面上就是一次普通的「操作失败」，没有堆栈入口；
   只有去翻服务端日志才看得到 `NameError`。

v1 下线（`4f7c427`，build.27-r12）之后，插件目录、插件注册、前端源选择、配置项都清干净了，
所以**没人再从功能路径上想起它**——这也解释了为什么"清得很彻底"的感知与实际残留同时存在。

---

#### 3. 引用链

```
webserver/handlers/book.py
  L54  from webserver.plugins.meta import douban_v2      ← 只有 v2
  L1299 def post(self, id)          (@js @auth，路由 /book/<id>/refer)
  L1310 if provider_key == douban.KEY:                    ← douban 未定义
```

- `webserver/plugins/meta/douban/`：**目录不存在**（实测），v1 插件已被删除。
- 插件注册是**显式 import**（`webserver/services/book_search.py:16-25` 逐个 from-import 并组成
  `_PLUGIN_CLASSES` / `_PROVIDER_PLUGIN_CLASSES`），没有"扫描目录动态加载"，
  所以不会出现"删了目录但注册表里还挂着"的另一种 500。
- `4f7c427` 的实际改动（实测，`git show 4f7c427 -- webserver/handlers/book.py`）：

```diff
-from webserver.plugins.meta import douban, douban_v2
+from webserver.plugins.meta import douban_v2
@@ class BookEdit
-            content = douban.str2date(data["pubdate"])
@@ class BookAddByISBN
-  ... 配置互联网信息源的插件地址（仅部署 douban-rs-api 镜像时才需要；未部署请取消勾选 douban 源）。
```

即：**import 删了、两处显式调用改了，但 `douban.KEY` 这处"常量引用"留了下来**。
Python 不会在 import 时发现它（属性访问在函数体内，运行时才解析名字），
`pyflakes` 之类也只报"未定义名字"，如果 CI 没跑静态检查就一路带到了线上。

---

#### 4. 全仓库同类残留清单与判定

排查口径：`douban` 字面量 + `douban.` 属性访问 + `provider_key == "douban"`，覆盖 `webserver/`、`tools/`、`app/src/`、`delivery/`。

| 位置 | 内容 | 判定 |
| --- | --- | --- |
| `webserver/handlers/book.py:1310`（修复前） | `if provider_key == douban.KEY:` | **真 500，已修**（唯一一处真正会抛异常的） |
| `tools/others/tools.py:23`、`73-88` | `from webserver.plugins.meta import douban`、`douban.get_douban_metadata(...)` | **跑起来即 ImportError**，但这是 calibre 遗留批处理脚本，服务不 import、镜像不执行 → 安全，未改（历史工具，改动无收益） |
| `delivery/overlay/files/webserver/handlers/book.py:53/1292/2250` | 同样的 v1 分支 + `douban.str2date` | **冻结的历史快照**（`opt/p0-p1` 分支交付物），Dockerfile / compose / `pack.sh` 都不引用它，且其 `MANIFEST`/`SHA256SUMS` 依赖原始字节 → 刻意不改 |
| `webserver/handlers/base.py:194-203` | `douban_id = link.split("//")[-1]` 局部变量 | 只是变量名，与模块无关 → 安全 |
| `webserver/settings.py:199/311`、`webserver/base/setting_saver.py:54` | `META_SELECTED_SOURCES` 含 `douban_v2`；`douban_max_count` 被 v2 复用 | 配置键，v2 仍在读 → 安全 |
| `webserver/handlers/admin.py:66/668` | `DEFAULT_META_SOURCES`、`douban_apikey` 校验已移除的注释 | 注释/默认值 → 安全 |
| `app/src/pages/book/_bookid.vue:117` | `['douban','amazon','douban_v2'].includes(book.provider_key)` 决定标题颜色 | 前端常量，命中只是配色 → 安全 |
| locale / 文档文案里的「豆瓣」 | 文案 | 安全 |

结论：**只有一处会抛异常**，其余是"名字或历史遗留"，不是"未定义引用"。
这也是本次没有做大扫除的原因——把安全项一起改，只会扩大回归面。

---

#### 5. 修复

`webserver/handlers/book.py`：

- 新增 `_resolve_refer_mi(provider_key, provider_value, metadata, mi, only_meta, only_author_comments)`（L1272-1295）；
- 删除 `if provider_key == douban.KEY:` 分支；
- 统一流程：**v2 占位注释修正 → 表单 `metadata` 或现有 `mi` → 按需补封面**；
- `post` 里改为一次调用 + 空值兜底（L1334-1338）：

```python
refer_mi = self._resolve_refer_mi(
    provider_key, provider_value, metadata, mi, only_meta, only_author_comments)
if not refer_mi:
    return {"err": "plugin.fail", "msg": _("拉取图书信息异常，请重试")}
```

**为什么保留 `provider_key="douban"` 的兼容**：库里存量书籍的 `provider_key` 字段还可能是 `douban`
（v1 时代写入的）。这类书再点「更新元数据」时，不应该因为源不存在而失败——
按"以表单/现有元数据为准，必要时补封面"处理，行为等同于不再依赖该源。
**没有**恢复 v1 插件：模块、前端入口、配置都已下线，恢复等于把整套 v1 拖回来。

---

#### 6. 测试与静态检查

`tests/test_book_meta_provider_branch.py`（8 条，实测 `8 passed`）：

| 用例 | 覆盖 |
| --- | --- |
| `douban` / `douban_v2` / `xhsd` / `bookbarn` 四参数化 | 各 provider 分支在**没有任何豆瓣模块**时也能正常返回，不抛异常 |
| v2 占位注释 | `comments == "....."` 时清空并走插件 |
| 封面开关 | `only_meta=yes` 不补封面；默认补封面 |
| AST 静态检查 | 遍历 `webserver/**/*.py`，若出现 `douban.` 属性访问而该文件没有绑定 `douban` 名字 → 失败 |
| v1 模块确已删除 | `webserver/plugins/meta/douban/` 下不再有 `.py` 源文件 |

静态检查是这次的关键补充：它防的不是"再写错一次同样的代码"，而是**"再删一次模块时漏掉常量引用"**。

---

#### 7. 验证

**已验证（本地）**

- `python -m pytest tests/test_book_meta_provider_branch.py -q` → 8 passed
- `_resolve_refer_mi` 在 L1272，`post` 调用在 L1334；旧分支已无（行首锚定 `grep -n "^        if provider_key == douban.KEY:"` 无输出）

**须在真机验证（尚未做）**

1. 重建 r25 镜像或打热更包后重启；
2. 书籍详情点「更新元数据」→ 正常返回；
3. `docker logs --since 10m <容器> 2>&1 | grep -c "NameError: name 'douban' is not defined"` → `0`。

---

#### 8. 热更包：能做，但只是临时手段

为了不为 249 KB 的一个文件重传 221 MB 部署包，另出了热更包
`audiobook-hotfix-4.6.0-build.27-r25-douban1.tar.gz`（66,177 B，SHA256 `cd6d1e97…69f8be`）：

```
webserver/handlers/book.py   修复版（ca49dfbd…99b8b）
apply.sh                     备份 → docker cp → sha256 校验 → 提示重启
rollback.sh                  按备份还原 → 校验 → 提示重启
SHA256SUM / README.md
```

```sh
sh apply.sh -c <容器名>
docker restart <容器名>
### 回滚: sh rollback.sh -c <容器名>
```

边界（**必须知道**）：

| 操作 | 结果 |
| --- | --- |
| `docker cp` 后不重启 | **不生效**，Python 不会热加载 |
| `docker restart <容器>` / `docker compose restart mybooks` | 重启进程、保留可写层 → 热更有效 |
| `docker compose up -d --force-recreate`、`docker rm` 重建、重建镜像 | 新容器、可写层丢弃 → **热更失效**，回到镜像内旧代码 |

所以热更是"止血"，正式修复仍应重建 r25 镜像（r25 同时含 Dockerfile 构建门禁，本来就要重建）。

---

#### 9. 教训

1. **删除模块 ≠ 改 import**。删一个模块时，要扫三类引用：
   ① `import` / `from ... import`；② `module.attr` 形式的常量与函数；③ 字符串/配置里的 key。
   本次 ② 漏了，而它恰好落在公共路径上。
2. **公共路径上的 provider 判断要"无害化"**。凡是 `if x == CONST:` 这种写法，
   `CONST` 必须来自仍在维护的模块；否则用 `getattr(mod, "KEY", None)` 或直接查表，
   避免"源已下线"变成"整个功能不可用"。
3. **别名/兼容字段要显式测试**。`provider_key="douban"` 的存量数据没有测试覆盖，
   修复时补了参数化用例，而不是只测当前在用的源。
4. **静态检查要针对"类别"而不是"这一行"**。AST 规则禁止"未绑定的 `douban.` 访问"，
   下次换成别的模块同样能兜住。
5. **用 sha256 判断热更是否到位，别用裸 grep**。修复版的注释里也出现了
   `if provider_key == douban.KEY:` 这句（讲历史），`grep "douban.KEY"` 会误报；
   用行首缩进锚定或直接比对文件 sha256。

---

#### 附录 A：实测 / 推断

**实测**

- 报错原文、行号、`BookRefer.post` 位置（用户线上日志）
- `4f7c427` 的 diff：只改了 import、`douban.str2date`、ISBN 提示文案（`git show`）
- `webserver/plugins/meta/douban/` 不存在；插件注册为显式 import
- 全仓库 `douban` 残留清单（第 4 节表格，逐处 grep + 读代码判定）
- 修复后 8 条测试通过；AST 检查对 `webserver/**` 生效
- 热更包结构、权限、sha256、`sh -n`/`bash -n`、解包复验（本机）

**推断**

- "因为不在页面加载路径，所以长期没被发现"——依据是接口调用时机与前端提示方式，
  没有用户侧的操作记录佐证。
- "线上 r12~r24 都带这个问题"——依据是 r24 包内 `book.py` 与 `HEAD~1` 完全一致；
  更早的 r12~r23 未逐包开箱比对，但该行自 `4f7c427` 起从未被改动（`git log -S` 只命中初始导入）。

**误判（保留记录）**

- 一度以为这是"豆瓣 v2 插件挂了"或"某个源返回异常"，实际与 provider 无关。
- 一度想用 `grep -rn "douban"` 直接判定"还有多少残留"，会把注释、变量名、文案全算进来，
  必须逐个看上下文才能区分"会抛异常"和"只是名字"。

---

#### 附录 B：复现与验证命令

```sh
### 1) 确认修复前的坏行（在旧镜像/旧包里）
docker exec <容器> grep -n "^        if provider_key == douban.KEY:" /var/www/mybooks/webserver/handlers/book.py

### 2) 确认修复后的文件指纹
docker exec <容器> sha256sum /var/www/mybooks/webserver/handlers/book.py
### 期望 ca49dfbd4ac0f1311ab33ed437d26856abeb21c62d092792a31a088f20299b8b

### 3) 日志不再出现该异常
docker logs --since 30m <容器> 2>&1 | grep -c "NameError: name 'douban' is not defined"

### 4) 静态检查 + 单测（仓库内）
python -m pytest tests/test_book_meta_provider_branch.py -q

### 5) 全仓残留扫描（人工复核用）
grep -rn "\bdouban\b" --include="*.py" webserver tools | grep -v "douban_v2"
```