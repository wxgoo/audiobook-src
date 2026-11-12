# 变更报告：build.20 / build.21（历史归档）

> 由 `变更报告-4.6.0-build.20.md` 与 `变更报告-4.6.0-build.21.md` 合并，正文未删改。

## 变更报告：`4.6.0-19-r13` → `4.6.0-build.20`

> 对比基线：`4.6.0-19-r13`（旧部署包 `audiobook-deploy-4.6.0-19-r13-patched.tar.gz` 对应的源码状态，
> 即本 fork 的初始提交 `32bc1d4`）。
> 对比终点：`4.6.0-build.20`（提交 `569bc3b` 起的本地构建号 20）。
> 统计口径：`git diff 32bc1d4..HEAD --numstat`，**不含** `delivery/` 下为无 git 环境准备的副本/补丁/压缩包。

---

### 一、版本关系

| 项 | 取值 | 说明 |
|---|---|---|
| 旧版本 | `4.6.0-19-r13` | 第 19 次本地发布，交付标签 `4.6.0-19` |
| 新版本 | `4.6.0-build.20` | 第 20 次本地构建，运行期版本与交付标签**同值** |
| 上游基线 | mybooks tag `4.6.0`（2026-10-25，commit `3c5947c`） | 新旧两版**建在同一个上游 tag 上**，本轮未合入上游新代码 |
| 上游未发布分支 | mybooks `develop` = `4.6.1`（无 tag、无 Release） | 不跟号；等上游正式发 tag 后按主题合入，届时升 `4.6.1-build.20` |
| 已封存号段 | `v4.7.1 ~ v4.8.x` | 与 `4.6.0-build.20` **无版本先后关系**，属号段重置 |

**`4.6.0-build.20` 的版本语义**：它是合法 semver 的**预发布标记（prerelease）**，整串排序**低于** `4.6.0`
（`4.6.0-build.20 < 4.6.0`）。本程序不发布 npm 包、`app/package.json` 无 `engines` 校验，
因此该排序差异没有实际影响。

**关键约束：版本号不参与任何升级门控。** 全仓库仅有三处读取 `VERSION`，都是整串相等比较：
`main.py` 的 `VERSION == "v0.0.1"`（开发版跳过版本检查）、`handlers/admin.py` 的
`last_revsion != VERSION`（只用于提示「构建已变化」）、`services/book_barn.py` 的
`latest_version != VERSION`；表结构检查 `should_check_db_structure()` **恒返回 True**，
刻意不用版本号判断。同一上游基线的两次本地构建之间只有 `build.N` 能区分新旧，
**不要**用 `>` 比较整串（会漏判），也不要为迁就代码去改版本号。

---

### 二、变更总览

| 范围 | 文件数 | 新增行 | 删除行 |
|---|---:|---:|---:|
| **全部（git 口径）** | 123 | 38,353 | 132 |
| 其中 `delivery/` 交付工程（副本/补丁/压缩包） | 73 | 33,841 | 0 |
| **实际源码 / 文档 / 工具改动** | **50** | **4,512** | **132** |

按模块（不含 `delivery/` 副本）：

| 模块 | 文件数 | +行 | −行 | 内容 |
|---|---:|---:|---:|---|
| 备份（P0） | 4 | 1,374 | 0 | `scripts/backup.sh`、`scripts/backup_run.py`、演练与演练清单 |
| 部署工具 | 4 | 378 | 0 | `scripts/check-version-lock.py`、`pack.sh`、`scripts/README.md` |
| 检索 | 3 | 555 | 0 | FTS5 中文书目检索索引（服务 + handler + CLI） |
| 测试 | 6 | 423 | 0 | 缓存、检索、分页、后台任务、AI agent、版本锁 |
| 后端其他 | 10 | 223 | 22 | 站点信息、后台任务、扫描、设置、版本字段 |
| 音频与性能 | 1 | 172 | 74 | `handlers/audio.py`（缓存、Range、标志增量） |
| 上游跟进 | 5 | 147 | 0 | A/B/C/D 主题包与说明 |
| 安全 | 3 | 90 | 15 | MCP token 走 Header、WebSocket 同源校验 |
| 文档 | 7 | 1,082 | 15 | README、CHANGELOG、交付索引、优化记录、评估方案、部署包说明 |
| 分页 | 1 | 43 | 0 | `webserver/base/pagination.py`（游标分页） |
| 构建与部署 | 3 | 15 | 3 | Dockerfile 空值守卫、Makefile `VER` fail-fast、compose `GIT_VERSION` |
| 导入 | 1 | 7 | 0 | Phase2 攒批窗口可配置 |
| 前端 | 2 | 3 | 3 | `package.json` / `package-lock.json` 版本字段 |

**删除文件：0**（本轮只做新增与修改，回退不需要恢复被删文件）。

---

### 三、逐项变更

每项都给出「改了什么 / 为什么 / 影响面 / 如何回退」。回退命令均以本仓库提交号为准。

#### 1. 数据备份与恢复闭环（P0，`182a524`）

- **改了什么**：新增 `scripts/backup.sh`（单入口）与 `scripts/backup_run.py`（仅标准库）：
  SQLite 在线备份 API、文件硬链接快照、日/周/月三层保留、`manifest` + sha256 + `integrity_check`，
  退出码 0/2/3 区分成功/告警/失败；新增 `docs/备份与恢复演练.md`。
- **为什么**：手工 `cp` 数据库在写入中会拿到半截文件；缺少可核验的恢复闭环。
- **影响面**：纯新增脚本，不进入运行时请求链路；不改表结构、不改配置字段。
- **回退**：删除 `scripts/backup*.{sh,py}` 与对应文档即可，无数据影响。

#### 2. MCP token 改走 Authorization 头（P1-1，`f15b515`）

- **改了什么**：`handlers/mcp.py` 等只从 `Authorization: Bearer` 取 token；URL 带 token 默认 403
  （`ALLOW_MCP_TOKEN_IN_URL` 可临时兼容）；日志递归脱敏；`assistant/mcp_client.py` 同步改 Header。
- **为什么**：URL 里的 token 会进访问日志、浏览器历史、反代日志。
- **影响面**：**不兼容变更** —— 旧 MCP 客户端若仍把 token 放 URL 会收到 403。
- **回退**：`git revert f15b515`；或临时设 `ALLOW_MCP_TOKEN_IN_URL=true` 兼容旧客户端（不推荐长期开）。

#### 3. AI WebSocket 同源校验（P1-2，`5353d5e`）

- **改了什么**：`handlers/assistant.py` 的 `check_origin` 改为同源比对（`is_same_host_origin`）。
- **为什么**：原逻辑放任跨站页面建立 WS 会话（CSWSH）。
- **影响面**：反向代理改写 `Host`/`Origin` 的部署需保证两者一致，否则 WS 握手失败。
- **回退**：`git revert 5353d5e`。

#### 4. 音频缓存移出请求线程 / Range 异步 / 标志增量（P1-3、P1-4，`20647d4`、`3c0fded`、`20aad04`）

- **改了什么**：`handlers/audio.py` 三处：
  1. 音频书籍缓存改为单飞后台刷新 + 兜底周期 + 启动预热，不再在请求线程读盘；
  2. Range 读盘改异步分块 + 背压；
  3. 音频标志（是否有声书）由全量扫描改为事件驱动增量更新（`services/scan_service.py` 配合）。
- **为什么**：大库下同步读盘/全量扫描会占满线程池，拖慢整站。
- **影响面**：**行为变化** —— 新建/导入音频后，标志最多滞后一个扫描周期才在列表生效。
- **回退**：按提交逐个 `git revert`（三处互相独立，可单独回退）。

#### 5. 详情页音频目录改用 calibre 解析（`f1f5955`）

- **改了什么**：`handlers/book.py`、`services/audios_import.py` 的音频目录由 calibre 解析，不再全库遍历。
- **为什么**：详情页每次全库扫描，书多时明显卡顿。
- **影响面**：依赖 calibre 元数据一致性；极少数元数据与实际目录不符的老库可能显示为空。
- **回退**：`git revert f1f5955`。

#### 6. 中文书目检索索引（FTS5，`47cdc73`）

- **改了什么**：新增 `webserver/services/search_index.py`（独立 DB 的 FTS5 索引、重建与增量）、
  `webserver/handlers/search_index.py`（HTTP 接口）、`scripts/search_index.py`（命令行）。
- **为什么**：SQLite `LIKE` 检索中文书籍在大库下慢且不排序。
- **影响面**：新增独立索引库文件；**首次使用需重建一次**，否则检索结果为空。
- **回退**：`git revert 47cdc73`；索引库为独立文件，可直接删除，不影响主库。

#### 7. 游标分页（`11126be`）

- **改了什么**：新增 `webserver/base/pagination.py`；书目与有声书列表支持 `after` 游标；
  `handlers/base.py` 输出适配。
- **为什么**：深分页 `LIMIT/OFFSET` 在大库上全表扫描。
- **影响面**：**接口契约变化** —— 前端/第三方分页需按 `after` 游标适配；不传则维持原行为。
- **回退**：`git revert 11126be`。

#### 8. 导入攒批窗口可配置（`bd62261`）

- **改了什么**：`services/audios_import.py` 的 Phase2 攒批窗口改为配置项。
- **为什么**：大批量导入时固定窗口导致耗时过长。
- **影响面**：仅影响导入吞吐；明确单写者一致性约束（不要并发跑两个导入）。
- **回退**：`git revert bd62261`。

#### 9. 失败任务可读错误与重试提示（`f58dba6`）

- **改了什么**：`handlers/mcp.py`、`main.py`、`services/background_service.py` 给失败任务返回可读原因与重试提示。
- **为什么**：失败只显示堆栈，用户无法自助处理。
- **影响面**：仅提示文案与任务状态字段，无 schema 变更。
- **回退**：`git revert f58dba6`。

#### 10. 上游跟进主题包（`2d4050d`）

- **改了什么**：新增 `docs/上游跟进/`（A 安全与元数据、B 扫描与导入、C 音频与播放、D 功能与权限）
  与 `scripts/upstream/patch_tool.py`。
- **为什么**：把「要不要跟上游」变成可拆分的主题决策，避免整包合并。
- **影响面**：纯文档 + 导出工具，不进入运行时。
- **回退**：删除对应目录/脚本。

#### 11. NAS 交付与无 git 覆盖包（`b77fb64`、`bff41d9`）

- **改了什么**：新增 `delivery/`（`nas/00`–`90`、`paths.conf`、`README-NAS.md`）、无 git 覆盖包
  `overlay/`（34 个改动文件 + 基线 sha256 清单）、`patches/`（14 个主题补丁）与自包含发布包。
- **为什么**：群晖上没有 git，必须能在「无 git、无外网」环境校验并覆盖源码。
- **影响面**：不进入镜像；`60-apply-overlay.sh` 会先校验基线再覆盖、失败自动回滚。
- **回退**：删除 `delivery/`；已覆盖的服务器按 `60-apply-overlay.sh` 的备份目录回滚。

#### 12. 版本号统一与版本锁（`129e19c`、`569bc3b`，本轮）

- **改了什么**：
  - `webserver/version.py`、`app/package.json`、`app/package-lock.json`、`docker-compose.yml` 的
    `GIT_VERSION`、`Makefile` 的 `VERSION_LOCK` 统一为 `4.6.0-build.20`；
  - 新增 `scripts/check-version-lock.py`（可独立执行，退出码 0/1）与 `tests/test_version_lock.py`（9 个用例：1 正向 + 8 负向）；
  - `scripts/pack.sh` 打包前强制跑版本锁检查；`pack.sh` 的 CHANGELOG 版本正则支持 `-build.N`；
  - Dockerfile 的 `ARG GIT_VERSION` 默认值为锁值，收到空值直接 `exit 1`（不再写空串）；
  - Makefile 的 `VER` 与 `VERSION_LOCK` 不一致时 `$(error)` 退出（不再用分支名顶掉版本）。
- **为什么**：历史上「界面显示 `v4.8.0`、包名写 `4.6.0-20`」双口径并存，且 `make` 会把分支名写进镜像，
  导致无法判断版本是否真的生效。
- **影响面**：`make` 不带 `VER` 时按锁值构建；带不一致的 `VER` 会**直接失败**（这是保护，不是构建缺陷）。
- **回退**：`git revert 569bc3b`（会同时撤掉版本锁与文档，需谨慎）。

---

### 四、风险与不兼容变更

| 级别 | 项 | 影响 | 应对 |
|---|---|---|---|
| 高 | 需要**重新构建镜像** | 版本号进入镜像内 `version.py`，旧镜像不会显示新版本 | 按第五节重建并重启；用 `delivery/nas/70-check-image.sh` 核对 |
| 中 | MCP 客户端需改 Header | 旧客户端把 token 放 URL → 403 | 改 `Authorization: Bearer <token>`；临时开 `ALLOW_MCP_TOKEN_IN_URL` 过渡 |
| 中 | 检索索引需**首次重建** | 不重建则检索结果为空 | 跑 `scripts/search_index.py` 重建（见第五节） |
| 中 | 前端分页需适配 `after` 游标 | 老前端仍用 `offset`，行为不变但不享受深分页优化 | 升级 `app/dist` 或在接口层继续兼容 `offset` |
| 低 | 音频标志最多滞后一个扫描周期 | 新导入音频在列表里短暂显示为「非音频书」 | 等一个周期或手动触发扫描 |
| 低 | 反向代理改写 `Origin`/`Host` | AI WebSocket 握手被拒 | 保证反代透传两者一致 |
| 低 | 版本串排序低于 `4.6.0` | 只影响「拿版本号比大小」的外部脚本 | 本程序不做版本门控；外部脚本请比 `build.N` |

**无数据库 schema 变更**：本轮没有 migration/schema 文件，`should_check_db_structure()` 恒执行但只做校验，
不会自动改表。

---

### 五、升级步骤与验证方法

#### 升级顺序（NAS / DSM，无外网可用 `delivery/`）

1. **备份**：`scripts/backup.sh`（或 `delivery/nas/20-backup-full.sh`），确认退出码 0；
   再跑 `delivery/nas/30-verify-backup.sh` 校验。
2. **取新源码**：有 git → `git fetch && git merge --ff-only origin/opt/p0-p1`；
   无 git → 解压完整源码包，或 `delivery/nas/60-apply-overlay.sh`（自动基线校验 + 备份 + 回滚）。
3. **核对版本锁**：`python3 scripts/check-version-lock.py` → 必须 `exit 0` 且打印「版本锁检查通过」。
4. **重建镜像**：`make`（`VER` 缺省即 `4.6.0-build.20`）或 `docker compose build && docker compose up -d`。
5. **重建检索索引**（首次升级必须）：`python3 scripts/search_index.py --rebuild`。
6. **重启后自检**：`delivery/nas/70-check-image.sh`（核对镜像/容器内源码与预期一致）。

#### 验证命令与判据

| 检查 | 命令 | 通过判据 |
|---|---|---|
| 版本锁 | `python3 scripts/check-version-lock.py` | 退出码 0；输出含「版本锁检查通过」 |
| 版本单测 | `python3 -m pytest tests/test_version_lock.py -q` | 9 passed |
| 容器内版本 | `docker exec <容器> grep VERSION /var/www/mybooks/webserver/version.py` | 含 `4.6.0-build.20` |
| 界面版本 | 打开首页/关于，或 `GET /api/siteinfo` | `version` 字段为 `4.6.0-build.20` |
| MCP 鉴权 | `curl -H "Authorization: Bearer <token>" <mcp 地址>` | 200；无 Header 时 403 |
| 检索索引 | `GET /api/search_index/status` | 索引存在且条目数与书目数同量级 |
| 分页 | `GET /api/book/list?after=<游标>` | 返回 `after` 与下一页游标 |
| 镜像自检 | `delivery/nas/70-check-image.sh` | 报告「一致」；不一致会指出「构建了但没重启」 |

**失败判据（任一条不满足即回滚）**：版本锁 `exit != 0`；容器内版本与 `4.6.0-build.20` 不符；
`/api/siteinfo` 取不到版本；MCP 正常 Header 仍 403；检索接口报错或空；升级后首页 5xx。

---

### 六、已知限制

1. **Windows 开发机缺 calibre 依赖**：部分集成用例（扫描/导入/元数据）会被 skip，
   必须在容器或 CI 里跑完整 `pytest`。
2. **`pack.sh --check` 的符号链接校验**：Windows 解包不落符号链接，需在 Linux/DSM 上执行。
3. **前端构建需要 node/npm 与外网**：本轮包内已带 `app/dist` 预构建产物，离线部署无需现场构建；
   若改动 `app/src` 则必须在有网环境重建 `dist`。
4. **`4.6.0-build.20` 不能用于排序比较**：只做整串相等比较；需要新旧判断时比较 `build.N` 数值段。
5. **上游 `develop` 的 4.6.1 未合入**：无 tag、无 Release，本轮刻意不跟号。

---

### 七、附录：变更文件清单（不含 `delivery/` 副本）

| 文件 | 模块 | 新增 | 删除 |
|---|---|---:|---:|
| `docs/上游跟进/A-安全与元数据.md` | 上游跟进 | +23 | -0 |
| `docs/上游跟进/B-扫描与导入.md` | 上游跟进 | +22 | -0 |
| `docs/上游跟进/C-音频与播放.md` | 上游跟进 | +27 | -0 |
| `docs/上游跟进/D-功能与权限.md` | 上游跟进 | +24 | -0 |
| `docs/上游跟进/README.md` | 上游跟进 | +51 | -0 |
| `webserver/base/pagination.py` | 分页 | +43 | -0 |
| `app/package-lock.json` | 前端 | +2 | -2 |
| `app/package.json` | 前端 | +1 | -1 |
| `webserver/handlers/admin.py` | 后端其他 | +9 | -0 |
| `webserver/handlers/base.py` | 后端其他 | +61 | -9 |
| `webserver/handlers/book.py` | 后端其他 | +5 | -1 |
| `webserver/main.py` | 后端其他 | +20 | -2 |
| `webserver/mcp/mcp_service.py` | 后端其他 | +3 | -1 |
| `webserver/services/background_service.py` | 后端其他 | +79 | -4 |
| `webserver/services/scan_service.py` | 后端其他 | +24 | -3 |
| `webserver/settings.py` | 后端其他 | +15 | -0 |
| `webserver/toolbox/mimo_tts.py` | 后端其他 | +3 | -1 |
| `webserver/version.py` | 后端其他 | +4 | -1 |
| `docs/交付/NAS备份演练清单.md` | 备份 | +258 | -0 |
| `docs/备份与恢复演练.md` | 备份 | +360 | -0 |
| `scripts/backup.sh` | 备份 | +273 | -0 |
| `scripts/backup_run.py` | 备份 | +483 | -0 |
| `webserver/assistant/mcp_client.py` | 安全 | +16 | -10 |
| `webserver/handlers/assistant.py` | 安全 | +31 | -2 |
| `webserver/handlers/mcp.py` | 安全 | +43 | -3 |
| `webserver/services/audios_import.py` | 导入 | +7 | -0 |
| `CHANGELOG.md` | 文档 | +78 | -4 |
| `README.md` | 文档 | +29 | -8 |
| `docs/交付/交付索引.md` | 文档 | +149 | -0 |
| `docs/交付/应用与回滚.md` | 文档 | +139 | -0 |
| `docs/优化实施与决策记录.md` | 文档 | +200 | -0 |
| `docs/评估与优化方案.md` | 文档 | +465 | -0 |
| `docs/部署包说明.md` | 文档 | +22 | -3 |
| `Dockerfile` | 构建与部署 | +2 | -1 |
| `Makefile` | 构建与部署 | +9 | -2 |
| `docker-compose.yml` | 构建与部署 | +4 | -0 |
| `scripts/search_index.py` | 检索 | +57 | -0 |
| `webserver/handlers/search_index.py` | 检索 | +51 | -0 |
| `webserver/services/search_index.py` | 检索 | +447 | -0 |
| `tests/test_ai_assistant_agent.py` | 测试 | +44 | -0 |
| `tests/test_audio_books_cache.py` | 测试 | +91 | -0 |
| `tests/test_background_tasks.py` | 测试 | +37 | -0 |
| `tests/test_pagination.py` | 测试 | +32 | -0 |
| `tests/test_search_index.py` | 测试 | +91 | -0 |
| `tests/test_version_lock.py` | 测试 | +128 | -0 |
| `scripts/README.md` | 部署工具 | +2 | -0 |
| `scripts/check-version-lock.py` | 部署工具 | +179 | -0 |
| `scripts/pack.sh` | 部署工具 | +12 | -0 |
| `scripts/upstream/patch_tool.py` | 部署工具 | +185 | -0 |
| `webserver/handlers/audio.py` | 音频与性能 | +172 | -74 |

> 合计：50 个文件，+4,512 / -132 行（delivery/ 下另有 73 个交付副本/补丁/压缩包，未计入）。


---

## 变更报告：`4.6.0-build.20` → `4.6.0-build.21`

> 对比基线：build.20（发布提交 `5348bf3`）。
> 对比终点：build.21（本版本提交）。统计口径：`git diff 5348bf3..HEAD`。
> 上游基线不变：mybooks tag `4.6.0`（本轮未合入上游新代码）。

---

### 一、版本关系

| 项 | 取值 |
|---|---|
| 旧版本 | `4.6.0-build.20` |
| 新版本 | `4.6.0-build.21`（第 21 次本地构建，运行期版本与交付标签同值） |
| 版本锁 | 七处载体同步升号：`version.py`、`docker-compose.yml`、`Dockerfile ARG`、`app/package.json`、`package-lock.json`、`Makefile VERSION_LOCK`、`check-version-lock.py`（校验器常量与文案）；`tests/test_version_lock.py` 9 用例通过 |

版本号约束不变：整串相等比较、不参与升级门控、不与 `4.6.0` 比大小（详见 CHANGELOG 号段说明）。

---

### 二、变更总览（6 个提交）

| 主题 | 提交 | 内容 |
|---|---|---|
| 检索 FTS 挪出事件循环 | `6926057` / `503e9fb` | `cached_search_async` 的 `search()`（MATCH + 纯 Python 子串过滤，大库宽查询可达秒级）挪进 blocking_pool；`_connect_read` 每次新建只读连接，线程池执行安全 |
| 有声书缓存测试竞态 | `6926057` / `da52091` | 假扫描改为 Event 闸门，「过期读立即返回旧值」从猜运气变确定性验证（部分机器原版 5/5 必红） |
| 音频缓存标记补齐 | `36d3e71` | `scan_service._sync_sidecar_audio`（扫描导入混放/分季子目录）与 `book_dedup._move_audio`（重复书合并搬音频）补 `mark_has_audio/mark_no_audio`——原来新书最长 6 小时兜底扫描才进有声书列表，合并后被删书还挂在列表里 |
| 备份 fail-closed ×3 | `bec66b6` | ①快照内任一文件复制失败 → 整份快照判失败并清理（原实现只记 warning 退码 2，残缺快照被保留策略当最新一份保护）；②重跑同一 `--timestamp` 不再 rmtree 已存在旧快照；③manifest 原子写（tmp+fsync+replace），失败清理本次产物退码 3；顺带清掉在线备份失败后的半截目标 db |
| 版本锁升号 | 本提交 | 七处载体 + `tests/test_version_lock.py` 字面量同步 |

两人平行修复说明：`6926057` 与 `da52091`/`503e9fb` 是同两处问题的独立修复，
后者 stacked 在前者之上做等价改写（注释更完整，已采纳），无功能叠加。

---

### 三、风险与不兼容变更

| 级别 | 项 | 说明 |
|---|---|---|
| 中 | **需要重建镜像** | `version.py` 进镜像，旧镜像仍显示 build.20 |
| 低 | 备份脚本行为变化 | 退出码 2 语义收窄为「仅轻微软性提示」；快照不完整一律退码 3 并清理。已有 cron 若按 `RC>=3` 告警，语义更严格（更安全） |
| 低 | 有声书列表实时性提升 | 新导入音频即时出现在列表（原来最长等 6 小时兜底），无副作用 |
| 无 | 数据库 schema | 本轮零 schema 变更；`audio_playback.client_ts` 等此前已由启动补列覆盖 |

#### 追记二（设置页归堆 + 提示人性化，`0fb7b52`）

- **用户与访问组重新归堆**：访问权限 / 默认权限与配额 / 读者组三张分散卡
  合并为「访问控制与读者组」一张卡（门槛→访客→读者组一条权限链）；
  注册邀请 + 新用户默认权限 + 下载配额合并为「注册、邀请与新用户」。
  键集不变，保存/脏跟踪/搜索别名机制照旧。
- **作者归一化提示人性化**：两处「改存量书请用作者清理」补位置说明
  （工具箱 → 作者清理）并加直达按钮；全库扫描确认无同类残留。

---

### 四、升级步骤与验证

- **版本改版工具化**（`20d43ce`）：`check-version-lock.py --set 4.6.0-build.<N>`
  一条命令改写全部九处载体（CARRIERS 表登记、预期次数不符拒绝盲改、改完立即
  复检）；`WHY/SEMVER_NOTE` 提示文案函数化（从 VERSION_LOCK 派生）。往返冒烟
  build.21→22→21 全绿。起因：build.21 升号时手工改七处载体，漏了 Dockerfile
  与校验器常量，被校验器连抓两次——「记得改 N 处」变成「跑一条命令」。
- **backup.sh 退出码拆分**（`20d43ce`）：被跳过（锁占用/锁不可用）从 2 拆出为
  独立的 **4**——原来与「有告警」同码，监控只盯 `>=3` 会把连续跳过当成正常；
  cron 告警条件建议改为 `RC != 0`（演练文档表已同步）。配合已交付的三个
  fail-closed 修复，backup.sh 可以放心挂无人值守 cron。

---

### 四、升级步骤与验证

1. 备份：`scripts/backup.sh`（或 `delivery/nas/20-backup-full.sh`），确认退码 0。
2. 取源码：`git fetch && git merge --ff-only origin/master`（或解压本包）。
3. 版本锁：`python3 scripts/check-version-lock.py` → 必须通过。
4. 重建镜像：`make`（`VER` 缺省即 `4.6.0-build.21`）。
5. 重启后核对：`docker exec <容器> grep VERSION /var/www/mybooks/webserver/version.py` 含 `4.6.0-build.21`；`GET /api/siteinfo` 同值。

#### 功能抽查建议

| 检查 | 判据 |
|---|---|
| 大库搜索 | 搜索期间另开页面刷 `/api/user/info` 不再卡顿 |
| 有声书列表 | 扫描导入 epub+mp3 混放目录后，书**立即**出现在 /api/audiobooks |
| 备份演练 | 跑 `backup.sh` 成功退码 0；再跑一次同时间戳退码 3 且旧快照完好 |
| 备份故障注入 | 临时塞满备份盘再跑：退码 3、无残缺快照残留、无 .tmp 清单 |

失败判据：版本锁 exit≠0；容器内版本不符；备份成功路径退码非 0。

---

### 五、已知限制

1. `delivery/patches/01–14`（主题补丁）保留 build.20 状态，**未随 build.21 重新切分**；
   build.21 增量统一收录在 `patches/all-in-one.patch` 与 `delivery/overlay/`
   （overlay 是无 git 部署的权威路径，已重新生成并逐文件校验哈希）。
2. Windows 开发机缺 calibre：部分集成用例 skip，完整 `pytest` 需在容器/CI 跑。
3. `pack.sh --check` 的符号链接校验需在 Linux/DSM 上执行；Windows 侧打包
   （python tarfile 流式重建）已另行验证符号链接原样保留。
