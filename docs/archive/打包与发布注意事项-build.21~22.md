# 打包机与发布注意事项（build.21 ~ build.22，历史归档）

> 由 `上传说明-4.6.0-build.21.md` 与 `打包机注意事项-2026-11-07.md` 合并，正文未删改。

## 4.6.0-build.21 发布（2026-11-07）

### 零、本次包（先看这里）

| 文件 | sha256 | md5 | 大小 |
|---|---|---|---|
| `audiobook-deploy-4.6.0-build.21.tar.gz`（**部署包，要部署的是这个**） | `6b865ad22865ec735d59b3df19ae1c112bed44e4521c7006d1b05bbbb67865ce` | `d44891bf0dfbe0c5a6e71efc4817746c` | 203M |
| `audiobook-src-4.6.0-build.21-full.tar.gz`（源码快照，含 delivery/ 与包校验清单） | `d5f831ea9c3c602d1fccd5d9c79862076157265973bfdcc3c0acc6859011148f` | `34d4094728c8301a4438a44f28641f2f` | 207M |

> ⚠️ 2026-11-07 晚**重切过四次**：补「追记」（--set 版本改版工具、backup.sh 退码 4）→
> backup.sh 退码 4）；第二次改从 git HEAD 全量构建（不再依赖旧部署基准，
> 内容 = d88b51e 树 + 预构建产物），并含变更报告追记与 r11 说明存档。
> 上面是最终哈希，此前任何拷贝作废，以本表为准。
> 说明：包内 app/node_modules 的 .bin 链接已物化为真实文件（功能等价、
> 更抗 Windows 解压）；myreader-dist 的 119 条关键符号链接原样保留。
> 第三次重切另含：设置页「用户与访问」归堆 + 作者归一化直达入口（见追记）。

> 两个包均为 unix tar 格式流式重建，**193 个符号链接逐条验证原样保留**；
> 部署包 `app/dist` 为本机 Node26 `nuxt build --spa` 重建（744 文件），
> 部署后无需现场 npm。gitee `master` 与 `opt/p0-p1` 已同源（`16d21c6` + 发布提交）。

```bash
cd /volume1/docker
sh /volume1/docker/audiobook/scripts/upgrade.sh \
   /volume1/docker/audiobook-deploy-4.6.0-build.21.tar.gz
```

---

### 一、build.20 → build.21 改了什么（6 个提交 + 版本升号）

详细见包内 `docs/变更报告-4.6.0-build.21.md` 与 CHANGELOG。摘要：

1. **检索 FTS 查询挪出事件循环**：`cached_search_async` 的 `search()`（MATCH +
   纯 Python 子串过滤）原来跑在 ioloop 上，大库宽查询冻全站数百毫秒~秒级。
   （`6926057`/`503e9fb`，两人平行修复取合并结果）
2. **有声书缓存测试竞态**：假扫描 Event 闸门化，「过期读立即返回旧值」从猜运气
   变确定性验证（部分机器原版 5/5 必红）。
3. **音频缓存标记补齐**：扫描导入 sidecar（含分季子目录）与重复书合并搬音频
   补 `mark_has_audio/mark_no_audio`——新书即时进有声书列表、被删书即时消失。
4. **备份脚本三个 fail-closed 缺口**（重点，详见 CHANGELOG）：
   - 快照内任一文件复制失败 → 整份判失败并清理，**残缺快照不再顶替好快照**；
   - 重跑同一 `--timestamp` **不再 rmtree 已存在的旧快照**；
   - manifest 原子写（tmp+fsync+replace），失败清理本次产物退码 3；
   - 顺带：在线备份失败不再留半截目标 db 文件；新增 `tests/test_backup_run.py`
     6 例回归（含「失败运行绝不触发保留策略」）。
5. **版本锁七处载体升号** build.20 → build.21（含 `check-version-lock.py`
   校验器常量——它是第七处载体，漏改会整体校验失败）。
6. **版本改版工具化**：`check-version-lock.py --set 4.6.0-build.<N>` 一条命令
   改写全部九处载体（CARRIERS 表登记、次数不符拒绝盲改、改完立即复检）；
   `WHY/SEMVER_NOTE` 文案函数化。往返冒烟 build.21→22→21 全绿。
7. **backup.sh 跳过退码拆分**：被跳过（锁占用/锁不可用）从 2 拆出为独立的 **4**——
   原来与「有告警」同码，监控只盯 `>=3` 会把连续跳过当成正常；cron 告警
   建议改为 `RC != 0`（演练文档表已同步）。

### 二、升级步骤

1. 备份：`sh delivery/nas/20-backup-full.sh`（或 scripts/backup.sh），确认退码 0。
2. 版本锁：`python3 scripts/check-version-lock.py` → 必须通过。
3. 重建镜像：`make`（`VER` 缺省即 build.21）→ `docker compose up -d`。
4. 核对：容器内 `grep VERSION webserver/version.py` = `4.6.0-build.21`；
   `GET /api/siteinfo` 同值。

**无数据库 schema 变更**；检索索引无需重建（索引版本未变）。

### 三、部署后抽查

| 检查 | 判据 |
|---|---|
| 大库搜索不卡站 | 搜索期间另开页面刷 `/api/user/info` 正常响应 |
| 有声书列表实时性 | 扫描导入 epub+mp3 混放目录后书立即出现在列表 |
| 备份幂等 | 同时间戳重跑退码 3 且旧快照完好；正常备份退码 0 |
| 备份故障注入 | 临时塞满备份盘再跑：退码 3、无残缺快照残留、无 .tmp 清单 |
| 版本锁 | `check-version-lock.py` 通过；镜像内版本 = build.21 |

### 四、已知限制

1. `delivery/patches/01–14` 主题补丁保留 build.20 状态未重新切分；build.21
   增量统一在 `patches/all-in-one.patch` 与 `delivery/overlay/`（后者为
   无 git 部署的权威路径，已重新生成并逐文件校验）。
2. overlay 本轮**新增了 20 个文件**（版本载体七处 + CHANGELOG + README +
   docs/交付 + 变更报告）——build.20 的 overlay 漏了版本载体，无 git 升级
   会把版本写回 build.20；build.21 起已补全，`60-apply-overlay.sh` 照常使用。
3. 完整 `pytest` 仍需容器环境；Windows 侧已跑：版本锁 9 例、备份回归 6 例、
   缓存/检索/分页/后台任务 26 例，全部通过。

---

## 打包机注意事项（2026-11-07，fix2/fix3 事故与移植总结）

> 收件人：另一台 Windows 打包机。本轮所有修复包见同目录（哈希在各 .sha256）。
> **当前最新部署包：`audiobook-deploy-4.6.0-build.22.tar.gz`（212,560,377 字节，
> sha256 `ad3c2b3986a4e10dbc87e37ac10630307fb4298ebca09507370d90ee55fdf51c`）**
> = build.21 + LF 修复 + 归一化文案 + 本轮上游移植 + **版本锁九处载体已升号 build.22**
> （`check-version-lock.py --set` 完成，CHANGELOG 已补 build.22 条目）；源码快照
> `audiobook-src-4.6.0-build.22-full.tar.gz`（sha256 `ba774def8555…cb616`，顶层目录已同步
> 改名，且内层 27 行 overlay 缺陷已修复——见第二节）。NAS 升级用 build.22 部署包。

### 一、必须落实的防复发三项

1. **`.gitattributes` 强制 LF**（本包 `audiobook/.gitattributes` 已写好，直接 `git add` 提交）。
   同时打包机执行 `git config core.autocrlf false`（或 `input`）后重新 checkout。
   事故回放：CRLF 工作树直接打包 → `docker/start.sh` shebang 变 `#!/bin/sh\r` → 容器 `exec ...: no such file or directory` 循环重启。
2. **`pack.sh --check` 已加两项检查**（本包 scripts/pack.sh 已含，提交即可）：
   - docker/ conf/ scripts/ Dockerfile* docker-compose.yml run_webserver.sh 出现 `\r` 即失败；
   - `app/dist` 语言包抽查 `openClean` 键——缺了说明 dist 落后于 src，先 `npm run build-spa` 再打包。
3. **打包前确认 dist 与 src 同步**：本轮「作者归一化没实现」的根因就是 dist 早于 src
   （缺 4 个 locale 键）。build-spa 一次即可，别再手工补 dist。

### 二、build.21-full 源码包的原有缺陷 —— **已在 build.22 修复**

内层 `audiobook-nas-release.tar.gz` 的 `audiobook-ops/overlay/MANIFEST.tsv` 曾有 **27 行
引用了内层没有携带的文件**（CHANGELOG.md、Dockerfile、Makefile、README.md、app/locales/*、
app/package*、settings.vue、author_norm.vue、docker-compose.yml、docs/上传说明/交付/变更报告/部署包说明、
scripts/check-version-lock.py、pack.sh、tests/test_backup_run/test_search_index_async/test_version_lock、
book_dedup.py、version.py）——无 git 覆盖部署会漏掉这 27 个文件。

**build.22 已修复**：这 27 个文件已从外层 `delivery/overlay/files/`（权威源）补进内层
overlay/files/，内层三份清单（SHA256SUMS / overlay/SHA256SUMS / overlay/MANIFEST.tsv）
全量重生成，overlay 与清单逐行对账 0 差异。git 侧收录时无需额外动作，此问题随源码包更新自然消失。

另：包内 6 个 SVG 图标与 3 处 pdfjs `.bcmap` 含**孤立的 CR 字节**——经复核不是缺陷：
`.bcmap` 是 pdfjs 的二进制格式（NUL 启发式误判为文本）；SVG 的 CR-only 换行是合法 XML，
历版包原样下发从未出过问题。按「第三方资产保持字节原样」原则未做改动，
各校验器已把「无 CRLF 的孤立 CR」归类为原生内容而非污染。

### 三、本轮上游移植清单（已并入本包源码树，git 侧请照单收录）

对上游 mybooks develop（至 `fdf982a6`，2026-11-05）26 个候选提交的分诊结论：

**已移植（本轮，改动文件如下）**
| 上游提交 | 内容 | 改动文件 |
|---|---|---|
| `d7dd8af1` | EPUB 修复页 i18n 全失效（扁平点键→嵌套）+ 进度条常驻 | app/locales/{zh,zh-TW,en}.json、app/src/pages/toolbox/epub_fixer.vue、webserver/handlers/toolbox.py、webserver/i18n/{en,zh-TW}.json、dist 三语言 chunk（fix3 包已同步重构） |
| `8ccab741` | 必须登录时 OPDS 下载直链回 401 挑战（防阅读器存假书） | webserver/handlers/base.py（`is_opds_acquisition` + 判定行） |
| `c0245c78`（适配） | OPDS 服务关闭后 `from=opds` 直链 404 | webserver/handlers/book.py（BookDownload.prepare 三行；base.py 匿名 /get/ 旁路本 fork 本就没有，无需移植；module-gate 相关跳过） |
| `606a5031`+`26509dd7`+`2b231705` | 「即将读完」排除已标记读完（相关 NOT EXISTS）+ 并发窗口复查 | webserver/services/reading_dashboard_service.py |
| `cc474f9f`/`2df57310` | tornado 6.6、social-auth-core 6.2.0 | requirements.txt（需重建镜像生效） |
| —— | 换行纪律 + dist 同步检查 | scripts/pack.sh、.gitattributes（新增） |
| —— | 设置页「作者重名/别名归一」指路条目 | app/src/pages/admin/settings.vue + 三语键（重建 dist 后生效） |

**fork 已自行吸收（无需再动）**：`ab733828` 批量任务取消、`8e4d668a` epub_merge 200、
`699a681d` 分享落地页、`6d8b59cb` REQUIRE_LOGIN 阅读器、`7f22d343` txt 分享、
`17e74e9f` 登录失败、`e8ab79b6`/`85e95437` 推荐异常与 sqlite 日志、`ed1b7ddd`/`e939a7cb`/
`8f91217c`/`380b1b9c` MyNexus 四件、`076c31e1` epub_merge 封面简介、`928841e4` 时区切天
（fork 的 `site_month_bounds_server_local()` 为等价自研实现）。

**明确不跟**：nuxt 2→4（大迁移）、功能模块门控架构（与 fork 自有权限体系冲突）、
封面背景/首页动效（装饰性，后续想要再单独评估）、koreader 插件（已独立成库）。

### 四、版本号

fix3 包内容 = build.21 + LF + 归一化文案 + 本轮上游移植，`version.py` 仍为
`4.6.0-build.21`（未动版本锁）。你们下一次在 git 侧收录上述改动后，用
`check-version-lock.py --set 4.6.0-build.22` 升号再出正式包。
