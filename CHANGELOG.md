# 变更日志（CHANGELOG）

本项目的版本号规则：**`<上游 mybooks tag>-<自建序号>`**
（上游 tag 无 `v` 前缀，如 `4.6.0`；自己改代码序号 +1，上游发新版序号归 1）

---

## 4.6.0-7（待发布）

### 修复 Bug

| Bug | 严重度 | 表现 | 修复 |
|---|---|---|---|
| **成员指向已删除的组 → 静默放行全库** | **致命** | `group_def` 为 `null`、`source` 为 `none`，用户明明"在组里"却能看到所有书 | 组名对不上时不再当作"不限权"，改为按【受限且一本书都读不到】处理（`source: group-missing`）；读组列表时自动清理这些悬空引用，界面顶部弹出黄色告警列出「组名 → 受影响用户」 |

> 触发场景：删组后重建同名组、改名过程中断、从别的机器导入 db 但没带 `READER_GROUPS` 设置。
> 这是权限系统里最危险的兜底方向——数据一脏，权限就静默全开。

| 分类/标签「或」关系不够明确，容易误以为要两边都填 | 中 | 只填标签却被要求也匹配分类，看起来像"选了绘本却看不到书" | 匹配逻辑本就是「或」，但界面上没写清；补齐说明文案，并在 `is_book_in_reading_range` 里显式拦掉"两边都空"（原来借空集合的副作用恰好成立，黑名单则会反向全放行） |

### 新增功能

| 功能 | 文件 | 说明 |
|---|---|---|
| 规则说明补充 | `app/src/components/ReaderGroupEditor.vue` | 表单下方明确写出：分类与标签是「或」，只填一边就够 |
| 悬空引用告警条 | `app/src/components/ReaderGroupEditor.vue` | 黄色 Alert 显示「已删除的组名 → 这些人」，并提示重新分配即可恢复 |
| 自动修复 | `webserver/services/reader_group.py` | `clear_members_of()`：读列表时清掉失效的组引用并写日志，不留下"看不见的病人" |

### 补丁包

`audiobook-patch-4.6.0-7.tar.gz`（222KB，与 4.6.0-6 相同的 12 个文件）
**需要重新构建镜像**。

> 4.6.0-6 未被采用（发现悬空引用问题后合并进 4.6.0-7 一起出），两者内容叠加。

---

## 4.6.0-6（未独立发布）

### 修复 Bug

| Bug | 严重度 | 表现 | 修复 |
|---|---|---|---|
| **白名单组一个条件都没填 = 放行全库（权限完全失效）** | **致命** | 建个「儿童组」白名单、分类和标签都不填，组员照样能看所有书；清空用户名单后也一样 | 新增严格模式 `READER_GROUP_STRICT`（默认开）：白名单空条件 → 返回永不匹配的哨兵条件，成员看不到任何书。想回到原版「空 = 不限权」，在设置里关掉该开关 |

> 这是移植时从上游继承的语义：mybooks 原版认为「白名单空条件 = 不限权」。
> 但读者组是管理员手工建的规则，只写组名不填条件时本意几乎总是「先锁住再配」，
> 放行全库会让整套权限看起来完全失效。故改为默认严格，并可一键切回。

### 新增功能

| 功能 | 文件 | 说明 |
|---|---|---|
| 设置页「严格模式」开关 | `app/src/pages/admin/settings.vue`<br>`webserver/settings.py` | 用户与访问 → 读者组，带说明文字；保存立即生效，不需要重启 |
| 表单空条件实时警示 | `app/src/components/ReaderGroupEditor.vue` | 白名单且分类标签都为空时，保存按钮上方出现橙色提示 |
| 权限排障接口 | `webserver/handlers/reader_group.py` | `GET /api/admin/reader_groups/debug?username=xxx`，一次看清：总开关、所属组、组定义、生效规则及来源（self / group / group-strict / none） |

### 补丁包

`audiobook-patch-4.6.0-6.tar.gz`（221KB，12 个文件：5 个后端 py + 5 个前端 + 2 个脚本）
**含前端改动，需要重新构建镜像**（约 4 分钟）。

---

## 4.6.0-5

### 修复 Bug

| Bug | 严重度 | 表现 | 修复 |
|---|---|---|---|
| **`container is marked for removal and cannot be started`** | **高（服务起不来）** | 上一次 `compose down` 被打断，容器卡在 `State=removing`；下次 `up -d` 无法启动它 | 停容器后等它真正退出；起容器前若检测到 `removing` 残留，先清理再 up |
| 升级结尾误报 `unix:///var/run/supervisor.sock no such file` | 低（仅误报，不影响服务） | `upgrade.sh` 固定 `sleep 20` 后立刻 `supervisorctl status`；容器此时还在跑 `--syncdb` / `--update-config`，supervisord 尚未 exec，socket 自然不存在 | 改为轮询：容器 Running → 等 sock 出现（最多 3 分钟）→ 等 4 个 program 全 RUNNING → 容器内 HTTP 自检，非 200 才提示 |

> 说明：这条报错**不是升级失败**。紧跟其后的"书数: 62"能正常读出来，就说明数据完好、容器活着。
> 只是在 62 本书的库上 syncdb 耗时超过 20 秒，检查跑得太早了。

### 补丁包

`audiobook-patch-4.6.0-5.tar.gz`（6.2KB，2 个文件：`upgrade.sh`、`deploy.sh`）
**纯脚本包，不含镜像内代码，不需要重建镜像、不需要重启容器。**

---

## 4.6.0-4

### 新增功能

| 功能 | 文件 | 说明 |
|---|---|---|
| Mimo-TTS 使用说明 | `app/src/pages/toolbox/mimo_tts.vue` | 折叠面板：API 类型怎么选、api-key 与 Bearer 的区别、密钥来源、保存配置说明 |
| Mimo-TTS 搜索按钮 | `app/src/pages/toolbox/mimo_tts.vue` | 原来只有回车能搜，新增可点击的「搜索」按钮（空输入禁用、搜索中转圈） |

### 修复 Bug

| Bug | 严重度 | 表现 | 修复 |
|---|---|---|---|
| 读者组列表 KeyError: ScopedSession | 致命 | 打开读者组直接 500 报错 | `_groups_with_members` 由 staticmethod 改为实例方法，改用 `self.settings` |
| 编辑组改名后成员名单被清空 | 高 | 改组名后组员"消失"（实际还挂在旧组名下） | 前端记住 `old_name`，后端识别改名并迁移成员归属 |
| 保存组后成员列全部变"-" | 中 | 保存任意组，列表里所有组成员列被置空 | 保存接口响应补上 `members`，与 GET 返回结构一致 |
| 设置页保存卡住、像在重启 | 中 | 点保存长时间无响应、提示弹两次 | 删除重复的全量提交请求；去重弹窗；保存按钮加 loading |
| 7 个工具页搜索图标不可点 | 中 | 只能按回车，点放大镜无反应（chinese_converter / epub_beautify / epub_fixer / epub_merge / epub_split / text_replace / txt_encoding_fixer） | 补 `append-outer-icon` + `@click:append-outer="search"` |
| 批量分配空格分隔失效 | 低 | 手输 `alice bob` 被当作一个用户名，全部 missing | 按 `[,;\s]+` 切分 |
| 组改名可撞已存在组名 | 中 | 两个组的组员混在同一名字下，永久无法区分 | 后端拒绝改名并提示"已存在同名组" |
| 读者组按钮判空崩溃风险 | 低 | combobox 返回非数组时 `.length` 误判 | 加 `!assignUsers` 前置判断 |

### 补丁包

`audiobook-patch-4.6.0-4.tar.gz`（181KB，14 个文件）

---

## 4.6.0-3

### 修复 Bug

| Bug | 表现 | 修复 |
|---|---|---|
| 设置页保存卡住 | 点保存后长时间无响应、像在重启服务 | 删除对 `/admin/settings` 的重复全量提交，成功提示只弹一次，按钮加 loading |

> 说明：服务端重启逻辑本身正确，仅以下 8 个键变化时才重启：
> `cookie_secret`、`xsrf_cookies`、`static_host`、`MAX_UPLOAD_SIZE`、
> `BOOK_NAMES_FORMAT`、`ENABLE_TXT_TO_TXTZ_PLUGIN`、`LOG_LEVEL_DEBUG`、
> `douban_v2_max_per_hour`。其余设置只写配置、不重启。

---

## 4.6.0-2

### 修复 Bug

| Bug | 表现 | 修复 |
|---|---|---|
| 读者组列表 KeyError: ScopedSession | 打开读者组 500 | `_groups_with_members` 改用 `self.settings["ScopedSession"]` |

---

## 4.6.0-1（换算前旧编号 v4.8.2 / v4.8.3）

**本版是移植版的第一个正式基线**，包含相对上游的全部定制。

### 新增功能

| 功能 | 文件 | 说明 |
|---|---|---|
| 读者组分权限管理 | `webserver/handlers/reader_group.py`<br>`webserver/services/reader_group.py`<br>`app/src/components/ReaderGroupEditor.vue` | 按组批量限制可读书目（白名单/黑名单 + 分类/标签）；用户归属存 `Reader.extra`，零数据库迁移 |
| 读者组预置模板 | 同上 | 儿童 / 访客 / 成人家属 / 会员四套开箱配置，一键填充 |
| 批量分配用户到组 | 同上 | 从数据库读取真实用户，下拉多选 chips + 可手输 |
| 音频转写 | `webserver/services/transcribe.py` | faster-whisper / openai-whisper 双后端，输出 `.srt` + `.txt` |
| 数据目录外置 | `webserver/settings.py`、`docker-compose.yml` | 数据统一在 `/volume1/docker/audiobook-data`，源码目录永远干净 |
| 原子升级脚本 | `upgrade.sh` | 预检 → 备份库 → 停容器 → 旧源码改名 → 全新解压 → 污染自检 → 挂载校验 → 构建 → 启动验证 |
| 部署脚本 + 污染自检 | `deploy.sh` | 发现 books/data 混入源码目录立即停止并给清理命令 |
| 跟随上游升级工具 | `upgrade-upstream.sh` | 一条命令：拉代码 → merge 上游 tag → 冲突暂停 → 出包 → 上线 |
| 出包工具 | `merge-*.sh` | 补丁包 + 基准包 → 成品包，自动校验 127 个符号链接 |
| 操作手册 | `START_HERE.md`<br>`UPSTREAM_UPGRADE.md`<br>`PORTING_NOTES.md`<br>`DEPLOY_README.md` | 总纲 + 细则，含"开发侧/NAS 分工"、三种改代码方式 |
| 版本号规则 | `PORTING_NOTES.md` | `<上游tag>-<序号>`，跟上游同步 |

### 修复 Bug

| Bug | 严重度 | 表现 | 修复 |
|---|---|---|---|
| 编辑组改名后成员名单被清空 | 高 | 改个组名，组员全"消失" | 前端记住 `old_name`，后端识别改名并迁移成员 |
| 保存组后成员列全部变"-" | 中 | 保存任意组，列表所有组成员列被置空 | 保存接口响应补上 `members` |
| 数据目录跑进源码目录 | 致命 | 升级后 books/data 出现在 `audiobook/` 下 | 挂载外置 + upgrade.sh/deploy.sh 污染自检 |
| git 推送符号链接丢失 | 中 | myreader-dist 127 个符号链接变普通文件 | 改用 tar 包分发，不依赖 git |

---

## 附：升级历史速查

| 版本 | 主要内容 | 备注 |
|---|---|---|
| 4.6.0-7 | **修悬空组引用静默放行**；悬空引用告警+自动修复 | 含 4.6.0-6 全部内容，需重建镜像 |
| 4.6.0-6 | 修白名单空条件放行全库；严格模式开关；权限排障接口 | 未独立发布，并入 -7 |
| 4.6.0-5 | upgrade.sh/deploy.sh 启动验证改轮询；修容器残留导致起不来 | 纯脚本包，不重建镜像 |
| 4.6.0-4 | Mimo-TTS 搜索按钮 + 使用说明；7 个工具页搜索图标可点；读者组 4 处修复 | 已上线 |
| 4.6.0-3 | 设置页保存优化 | |
| 4.6.0-2 | 读者组 KeyError 修复 | 未单独出成品包 |
| 4.6.0-1 | 全部定制基线（原 v4.8.2/v4.8.3） | |
