# 变更日志（CHANGELOG）

本项目的版本号规则：**`<上游 mybooks tag>-<自建序号>`**
（上游 tag 无 `v` 前缀，如 `4.6.0`；自己改代码序号 +1，上游发新版序号归 1）

---

## 4.6.0-5（待发布）

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
| 4.6.0-5 | upgrade.sh/deploy.sh 启动验证改轮询，消除 sock 报错误报 | 纯脚本包，不重建镜像 |
| 4.6.0-4 | Mimo-TTS 搜索按钮 + 使用说明；7 个工具页搜索图标可点；读者组 4 处修复 | |
| 4.6.0-3 | 设置页保存优化 | |
| 4.6.0-2 | 读者组 KeyError 修复 | 未单独出成品包 |
| 4.6.0-1 | 全部定制基线（原 v4.8.2/v4.8.3） | |
