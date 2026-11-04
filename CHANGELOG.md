# 变更日志（CHANGELOG）

本项目的版本号规则：**`<上游 mybooks tag>-<自建序号>`**
（上游 tag 无 `v` 前缀，如 `4.6.0`；自己改代码序号 +1，上游发新版序号归 1）

旧编号 `v4.8.x` 已废弃，对应关系见文末「旧编号时期发布说明」。

> 想查某个改动为什么这么做：搜版本号，或看 [`docs/`](docs/) 下的专题记录。

---

## 4.6.0-19（当前）

> **性能与稳健性专项**：修掉一批「同步 handler 阻塞事件循环冻住全站」的重 IO
> 调用、两个前端时序死锁、一个并发序列化崩溃，并给音频批量转码补上取消能力。

### 一、音频批量转码：扫描不再冻住全站 + 新增取消

**事件循环阻塞**（最重的一类问题）：`/api/toolbox/audio_transcode/scan` 与
`scan_all` 原来在 Tornado ioloop 线程上同步跑 ffprobe——单本书最多 200 个文件
逐个起子进程（单个超时上限 20s），扫描期间**全站请求**（包括不碰数据库的
`/api/user/info`）一起被冻住；「扫描全库」还要全库目录遍历 + 每本书一个 ffprobe。

修法（与 `utils.run_in_threadpool` 注释里自己警告过的反模式对齐）：

1. `audio_transcode.py` 拆出纯文件系统/子进程函数：`book_audio_dir`（calibre 读）、
   `list_mp3_in_dir`（FS）、`probe_files_in_dir`（FS + ffprobe）；
2. handler 改 `async def`：calibre 读走 `run_calibre_read_async`，探测走
   `run_in_threadpool`，书名一次批量取；
3. `start()` 不再接收 db——音频目录由 handler 先在 calibre 池里解析好，后台
   转码线程只做 FS/子进程操作，不再持有任何 calibre 对象。

**新增「取消任务」**：几小时的批量转码点错了只能干等。新增
`POST /api/toolbox/audio_transcode/cancel` + 页面「取消任务」按钮。粒度是
「当前文件」：正在跑的 ffmpeg 等它转完（或超时）即停，后续文件不处理；
已转成功的 m4a 保留，失败/未处理的 mp3 原样保留。取消收尾窗口内拒绝启动
新任务（否则会覆盖取消中的状态），`finally` 兜底保证状态不卡死在 cancelling。

**其它**：ffmpeg 预检（环境缺 ffmpeg 直接拒绝而不是逐文件报错）；
`task_snapshot()` 改深拷贝（浅拷贝把 errors/queue/skipped 与后台线程共享，
轮询序列化可能撞 `dict changed size during iteration`）；
修复报错文案里 `%` 优先级错误（`% x or y` 的 y 兜底永远不可达）；
`kept` 计数入初始状态字典。

### 二、转码页两个前端死锁 + 杂修

- **进页死锁**：`mounted` 只调一次 `refreshProgress()`，若进页时已有任务在跑
  （别的标签页启动的），`pollTimer` 不会启动——进度永久冻结、`canStart` 一直
  false，只能 F5。现在 `refreshProgress` 发现在跑且无定时器时自动补起轮询。
- 网络失败从 unhandled rejection 改为 toast 提示；单本模式 `canStart` 校验
  输入框里的 ID（clearable 清空后原来会发 `book_id:null`）；
  文件列表最多渲染 200 行 + 「共 N 个」提示。
- 「重复书清理」合并成功后的自动重扫不再把「已合并 N 组/备份路径」提示
  冲掉（`doScan(keepResult)`）。
- 顶栏：`/user/info` 迟到导致消息角标/后台任务图标最多延迟 30 秒——登录态
  就位后立即重 kick 轮询；后台任务类型映射补齐 `catalog_extract`/`transcribe`/
  `other`（工具箱任务默认就是 other，缺了渲染成空白），三语言 locale 补齐
  `taskTypeSaveMeta` 等缺失键。

### 三、有声书转换与音频接口

- `epub2audio` 进度：读取线程往 `chapters` 插键与轮询 handler 的 JSON 序列化
  并发跑，无锁时进度接口随机 500。加 `_plock` 互斥 + 快照深拷贝；
  `end_time` 初值 0 改 None（`is None` 判断在 0 上恒假，异常路径 execution_time
  算负数）。
- `AudioConversion.post` 改异步：`save_book_meta` 会整本 EPUB 读入再写回
  （含封面），大书秒级~分钟级，挪进 calibre 池；删除末尾复制粘贴出来的
  永不可达的第二组 `except` 死代码；`AudioConversionCancel` 去掉同步
  `time.sleep(1)`（纯冻住事件循环 1 秒）。
- **CIP 文件过滤条件写反**：`file.find(PREFIX) > 0` 恰好放过以
  「图书在版编目CIP数据」**开头**的文件（find 返回 0），反而过滤了前缀在
  中间的。两处改 `startswith`。
- **合集下载 key 未绑定书**：一张有效下载 key 可以拉任意书的合集 zip，
  开 VIP 配额时等于买过 A 书就能绕过付费校验拉 B 书。下载时按 key 属主
  补一次购买校验。
- `DailyDownloadMap` 只增不清 → 写入路径上超限时清两天前的旧记录。

### 四、零散修复

| 位置 | 问题 |
|---|---|
| `services/batch_add.py` | 已有任务在跑时提前 return 跳过 finally，临时 CSV 泄漏 |
| `services/converter.py` | 转换超时只 kill 不 wait：僵尸进程 + stderr 管道不收尾 |
| `handlers/admin.py` | nginx `-t`/reload 的 subprocess 无超时（nginx 卡住会挂死请求），加 60s 兜底并处理 TimeoutExpired |
| `handlers/toolbox.py` | PDF 瘦身的 filename 未清洗直接拼路径，`../` 可指到 sources 之外（管理员接口也收紧） |
| `handlers/static_files.py` | `_open_zip` 缓存 miss 竞态：两线程同时 miss 各开一个 ZipFile，被顶掉的句柄永不 close；打开动作移入锁内 |
| `models.py` | `raise "bug"`（Python 3 必然 TypeError）改 `raise TypeError`；裸 `except` 收窄 |
| `handlers/user.py` | 头像保存失败裸 `except` 不记日志，补 `logging.exception` |

### 五、测试

- 新增 `tests/test_audio_transcode.py`（24 例）：快照隔离、start 校验
  （ffmpeg 预检/运行中拒绝/取消窗口拒绝/无效码率回退）、转码成功/失败/取消
  三条路径的文件系统行为、run_queue 终态（done/cancelled）、探测聚合与抽样。
  首跑就抓到重构引入的真 bug（外层 except 引用旧参数名 `files` → NameError）。
- 新增 `tests/test_epub2audio_worker_progress.py`（5 例）：快照隔离、并发解析
  下序列化不崩、end_time 初值、计数正确性。
- 存量回归：`test_meta_merge.py` + `test_audio_narrator.py`（89 例）与
  `test_models.py` + `test_utils.py` 全部通过。

### 六、第二轮（同版本补充）：上传/导入链路修复 + 三个功能

> 聚焦 PDF/EPUB 上传、扫描导入、监听导入的审查结果 + 三个用户功能。

**上传/导入链路修复**

| 位置 | 问题 |
|---|---|
| `handlers/base.py` `@js` | CORS 任意回显 + `Allow-Credentials:true`：任何恶意网页可带着用户 Cookie 读本站 API。改为只回显同站点 Origin；异常 traceback 只回管理员，其他用户只看类型+消息（原实现任何访客可构造参数触发并拿到服务器路径） |
| `handlers/book.py` 分片上传 | 同步 handler：GB 级合并+元数据解析+calibre 入库全在 ioloop（分片上传正是为大文件设计的）；不进 `_upload_slot` 与单文件上传互踩；`int()` 参数不设防（`total_chunks=10^9` → 上亿次 exists）；`temp_chunks/` 孤儿目录无人清扫。改 async：合并/解析进线程池、calibre 走 `run_calibre_async`、参数钳制、24h 孤儿清扫、全程持信号量；错误响应不再回传原始异常文本 |
| `handlers/book.py` | 同名书判定顺序 bug：迭代中遇到作者不匹配的候选会把先前已找到的同作者候选清成 None（books 是集合、顺序漂移），本该并入既有书的会建重复书。单文件/分片两处同修 |
| `handlers/book.py` | `update_meta=1` 显式传参被 `== 1`（字符串比整数）静默判 False |
| `services/scan_service.py` | `do_import` 置锁后有 ~40 行裸露代码（选择器解析、`_collect_files`），任一异常把导入锁泄漏到重启——之后所有导入被拒、监控线程永远等不到空闲。整段包进 try/except 兜底复位 |
| `services/scan_service.py` + `audios_import.py` + `handlers/scan.py` | 扫描导入与有声书导入互斥只有单侧设防（批量删除侧是三方检查）：补齐双向检查与 handler 预检；拒绝时顺手清理批量上传的暂存目录 |
| `handlers/scan.py` | `ImportRun` 的 paths 形态原样透传任意路径（`SCAN_DIR_PREFIX` 定义了从未使用）：收口在扫描目录内 |
| `handlers/scan.py` | `BatchAddRun`：补 `is_running` 预检（原来连发两份 CSV 会顺序执行两遍重复建书）；CSV 解析异常路径补 unlink |
| `services/batch_add.py` | `_download_cover` 对 CSV 里的 URL 无限制直接 GET：限 http(s) + 8MB 封顶（SSRF/内存耗尽） |

**监听导入可靠性（monitor_service.py）**

- **线程自愈**：`inotify.read` 异常原实现直接退出线程且 `_running` 仍 True（`start()` 幂等短路），自动导入静默失效到重启。现在 read 异常自动重建 watcher（退避重试），调度线程加看门狗兜底拉起
- **大文件防截断**：文件 CREATE 事件不再入队（拷贝超 3s 防抖窗口就会把截断文件当正常哈希入库、之后永久跳过）；完成信号改为 CLOSE_WRITE / MOVED_TO（cp/scp/WebDAV/rsync 都会触发其一）
- **队列溢出**：处理 `IN_Q_OVERFLOW`——溢出期间事件全丢且原实现静默吞掉；现在告警 + 重扫监听根补齐
- **配置变更生效**：`scan_upload_path` 改了原来要重启；调度线程每秒检查、变更即重建监听并补扫
- **生命周期**：`stop()` 补 join（快速关→开旧线程会复活成双消费）；滞留的合并队列由调度线程营救

**新功能**

1. **电子书下一级子目录的音频同目录处理**：`collect_sidecar_audio_dirs`（纯 FS，可单测）——`书名/书名.epub + 书名/第一季/*.mp3` 这类分季布局，扫描导入时音频随书进 `.audio/`，跨子目录同名加「子目录名-」前缀；书目录与贡献音频的子目录都写 `audiodir:` 防重标记（否则「导入有声书」会把子目录按 ID3 再建一本重复书）。`_copy_or_convert_file` 增加可选 `dest_name`（向后兼容）
2. **播放进度服务端存储（跨设备续播）**：新表 `audio_playback`（自动建表）；`GET/POST /api/audio/<id>/progress`；前端 5s 心跳节流 15s 上报，暂停/切集/离开页面立即推；进页时本地与服务端「谁新用谁」，两台设备轮流听也能接上。服务端存取语义与播放器一致（track_index + 集内秒数）
3. **读者组总开关** `READER_GROUPS_ENABLED`（默认开）：关闭时组规则全链路失效——收口在 `effective_limits()` 单点（所有判定点都经它取组配置），用户自身 `read_limit/limit_*` 不受影响；成员归属保留，重开即恢复。设置页「用户与访问 → 读者组」置顶新增开关，三语言文案
4. **播放页字幕开关接线**：`showSubtitle` 原来只改按钮颜色不控制任何渲染（无效开关）；现在关=回封面视图、开=恢复字幕视图偏好

**另增测试**：`tests/test_sidecar_audio_dirs.py`（7 例，纯文件系统）。

---

## 4.6.0-18

> **只改元数据，不动业务流程**。6 个文件，可热更，不必重建镜像。
> ①根治「扫描导入 PDF 作者变佚名」；②「有声书演播者不再冒充作者」。

### 一、现象与根因：扫描导入的 PDF 作者被无条件覆盖成"佚名"

「秒懂速解小学数字画图 - 燕晓.pdf」扫描导入后显示「作者：佚名」、无封面；
同一文件直接调 `read_book_metadata` 却能读出 `authors=['燕晓']`、403KB 封面——
元数据是读到了，被导入代码覆盖的。

根因：`scan_service.py` 的扫描导入自己写了一套 PDF 归一化，其中
`PDF_TILE_WITH_FILE_NAME=True` 分支**无条件** `mi.authors = [_("佚名")]`。
`book.py` 的 `normalize_pdf_meta` 在 4.6.0-16 已修过同一坑（作者不再被无条件改佚名），
但只覆盖网页上传三条路径，扫描导入是漏掉的第四处。

### 修法

1. **扫描导入改用 `normalize_pdf_meta`**，删掉自写的取值分支——两边口径统一，
   开关只决定「标题取文件名还是内嵌」，作者永远是「内嵌非占位值就保留」。
2. 归一化抛异常时**不阻断导入**，退回最小兜底（标题用文件名、作者保留）。
3. **标题一律整串，不做任何拆分**。文件名前后可能带 `[作者]`/`[出版]`/`（版本）`
   等各种信息，靠规则剥干净不现实，剥错比不剥更难发现。内嵌标题可信用内嵌，
   不可信才回退文件名整串。calibre 入库的目录/文件名按它自己的规则生成，与源文件名无关。

### 二、新增 `utils.guess_author_from_filename`

内嵌作者缺失时，从文件名**保守**地捞作者，捞不到才是"佚名"。

只认五类明确信号：`作者：X`、`[X] 书名`、`书名 (X)`、`书名 - X`、`by 多词西文名`，
候选还需通过人名形态校验（挡住出版社、版本、卷册、扩展名、英文标题虚词）。
**宁可返回 None 也绝不猜错**——错作者比没作者更难让用户发现。

几个刻意做对的细节：

- **分隔符形态逐个取段、不锚定结尾**。`三体 - 刘慈欣 - 重庆出版社` 这种三段式里，
  只认最后一段会取到出版社再被噪声词否掉，白丢中间的真作者。
- **函数自己再剥一次扩展名**。调用方（上传/扫描）本来已剥，万一漏了，
  `书名 - 燕晓.pdf` 会把 `.pdf` 一起吞进候选，再被 `pdf` 噪声词否掉。
- **`作者：张三 三体` 在空白处截断**，不贪婪吃到 20 字，避免把书名粘进人名。
- **含空格的候选按形态分流**：`上半部 下半部` 这类中文描述片段整段拒掉，
  `John Smith`/`Randal E. Bryant` 这类全西文多词人名放行。
- **按「最靠右」择优**：书源命名习惯是书名在前、作者在后；同位置按
  标签 > 括号 > 分隔符 > by 排序，结果可复现。

### 三、有声书的 artist 是演播者，不是作者

> 「李慧敏那个音频是中央台播音员，演播的长篇书，不是作者，是演播者，
> 估计音频这块是普遍现象，因为不可能都是作者自己读吧」

用户库里「哈利波特与魔法石」每首音轨的标签都是：

```
TALB（专辑）  = 哈利波特与魔法石
TPE1（艺术家）= 李慧敏
TIT2（标题）  = 01
```

`TPE1` 填的是播音员，真作者 `J·K·罗琳` 在标签里一个字都没有。旧实现直接
`author = artist`，书库于是长出一个「李慧敏」作者——作者页、去重、自动刮削全部跟着错。

#### 修法

1. `_extract_audio_metadata` 第二个返回值语义改为**演播者**（原来是 author），
   函数名、注释、调用点同步改，防止以后又被误用。
2. 建书处：作者优先取目录内的**同名电子书**（4.6.0-15 已有），没有电子书就
   **老实标佚名**——宁可没作者，也不让演播者占位。
3. 演播者信息不丢，写三处（都是 best-effort，失败只记日志）：
   - `#narrator` 自定义列（新增，`main.py` 启动时自动建，幂等）
   - `tags`：`演播:李慧敏`
   - `comments`：追加「演播：李慧敏」，不覆盖已有简介
4. 演播者不再走 `guess_authors` / `resolve_author_list`：别名表里没有播音员，
   硬套会误伤。
5. **扫描导入也要补演播者**：epub+mp3 混在一个目录时（用户库 15 本哈利波特
   都是这样），扫书走的是 `_sync_sidecar_audio`，音频被带进 `.audio/` 却从不
   调 `attach_narrator`，`#narrator` 全空。现在复制完音频顺带读首曲标签补上，
   作者仍是电子书作者，不动。
6. `attach_narrator` 抽成**模块级函数**（原为 `AudioBookImporter` 实例方法），
   因为现在有两个调用方：`do_import`（导入有声书）和 `_sync_sidecar_audio`（扫书带音频）。

### 四、`audiodir:` 防重标记填上目录名

这些标记会出现在「已导入」列表里，原来 `title` 留空，表现为几行**书名空白**的
有声书图标，看着像导入失败。它们其实是「本目录音频已随书带走」的标记（没有它，
点「导入有声书」会按 ID3 再建重复书）。现在 `title` 填目录名、
`data.sidecar_of_book` 记归属书 id，列表里一眼能看出是哪本书的音频。

### 注意

- 「PDF 标题使用文件名」开关打开时，标题=文件名整串（含「- 作者」尾巴）是**预期行为**；
  想要干净标题请关闭开关，内嵌标题可信时自动采用。
- 存量已错标的书**不会自动修复**，删掉重扫/重导即可。
- 有电子书时以电子书作者为准，演播者照样写入（电子书本身没有演播者信息）。

### 热更

```sh
sh tools/hotfix.sh patch /path/to/4.6.0-18
# 或手工 docker cp 这 6 个文件后重启容器：
#   webserver/utils.py
#   webserver/constants.py
#   webserver/main.py
#   webserver/handlers/book.py
#   webserver/services/scan_service.py
#   webserver/services/audios_import.py
```

---

## 4.6.0-17

> **两件事**：①根治「books/audios/ 删了又回来」（改 `Dockerfile` + `docker/start.sh`）；
> ②补漏「扫描目录导入并入既有书时，作者与封面不更新」（改 `scan_service.py`）。
> **必须重建镜像**——`start.sh` 在镜像里，光重启容器不会生效。
> 只想先验证 ② 的话，`docker cp webserver/services/scan_service.py audiobook-mybooks-1:/var/www/mybooks/webserver/services/`
> 再 `supervisorctl restart mybooks:tornado` 即可（热更不持久，验证完仍要重建）。

### 背景：删掉的 audios 目录重新部署后又出现

> 「audios 上一次删除了，这次重新部署，又来了，哪里的问题？」

`books/audios/` 是 4.6.0-13 之前的旧音频布局（`audios/<book_id>/`），4.6.0-15 起
读取端已全部删除、目录也清理过。但只要**容器重启**，它就会自己回来。

### 根因：镜像里的「种子目录」+ 启动时自动拷贝

两条代码合力，一次重启就回流一次：

1. **`Dockerfile`（上游原样）**：构建时 `mkdir -p /data/books/audios`，构建末尾
   `mv /data/* /prebuilt/` —— 于是镜像里永远躺着一个 `/prebuilt/books/audios` 空目录；
   另有 `ln -s /data/books/audios app/dist/audios`（旧布局的静态软链，早已无人使用）。
2. **`docker/start.sh`（上游原样）**：每次容器启动执行
   `for f in /prebuilt/books/*; do [ ! -d /data/books/$f ] && cp -rvf ...; done`
   —— 「镜像里有、宿主上没有」的目录**一律拷回**。

`/data/books` 挂载宿主 `audiobook-data/books`，于是：删掉 → 容器一重启 → 拷回。
跟「重新部署」没有必然关系，光重启就够。

### 修法

- `docker/start.sh`：拷贝循环跳过 `audios`（带注释说明为什么）
- `Dockerfile`：删掉 `mkdir -p /data/books/audios` 和 `ln -s ... app/dist/audios` 两行

dist/audios 软链安全删除：前端只有 `/audios/<id>/collection` 这种 **API 路由**，
nginx 也没有静态 audios 转发，没有任何消费者。

### 已部署环境怎么清（不重建镜像也能立刻根治）

```sh
# 1. 删掉镜像层里的「种子目录」，挡住下次启动拷回（容器不重建就一直在）
docker exec audiobook-mybooks-1 rm -rf /prebuilt/books/audios

# 2. 清掉宿主上的现状
rm -rf /volume1/docker/audiobook-data/books/audios
```

之后无论重启多少次都不会再出现。下次用本版重建镜像后连第 1 步都不需要。

### 上游 v4.6.1 解决了没有

**没有**。逐字核对过上游 `v4.6.1` 分支：`Dockerfile` 仍有 `mkdir -p /data/books/audios`
和 `ln -s /data/books/audios app/dist/audios`；`start.sh` 的拷贝循环也没有排除逻辑。
这是上游自己的布局（上游还在用 `audios/<id>/`），只有我们 fork 迁到 `.audio/`
之后才成为问题。

### 验证

- `sh -n docker/start.sh` 通过
- `grep -n audios Dockerfile` 0 命中
- `scripts/upgrade.sh` 的旧布局残留检查（步骤 1.5）保留，装包时仍会提醒

### 补漏：扫描目录导入并入既有书时，作者与封面仍不更新

部署 -16 后用户反馈「那个 PDF 重新导入还是封面和作者没提取出来」。
追问得知走的是**扫描目录导入**，不是网页上传——这正是 -16 漏掉的入口。

`add_format` 在全项目有 **6 个**调用点，-16 只把 `merge_meta_from_file` 挂在了
其中 2 个（单文件上传、分片上传）。扫描导入并入既有书那条分支
（`scan_service.py:1436`）原样不动：

```python
self.db.add_format(row.book_id, fmt.upper(), fpath, True)   # 只换格式文件
row.status = ScanFile.IMPORTED                              # 标题/作者/封面一概不动
```

**修法**：新增 `ScanService._merge_meta_into_existing()`

- 文本字段复用 `merge_meta_from_file`（默认只补空字段）
- **封面单独补**：`merge_meta_from_file` 不管 `cover_data`（二进制，走 calibre 的
  `set_cover`），这一步只有并入路径需要
- 默认不覆盖已有封面（用户可能手动设过），`merge_meta_force` 时才整体覆盖
- 全程 try/except：任何一步失败只记日志，不能让已成功的 `add_format` 被打回 INVALID

**容器内实测**（用户那份 31MB PDF）：

| 阶段 | 结果 |
|---|---|
| 造一本同名旧书 | authors=['佚名']，has_cover 空 |
| 扫描导入并入 | merge 改动字段 `['authors', 'publisher']` |
| 读回 | authors=['燕晓']、has_cover=**Yes** |

标题那步没进 changed 是因为旧书标题已对（非空即不覆盖）；文件名里的
「- 燕晓」后缀由 -16 的 `normalize_pdf_meta` 已经从标题去掉。

### 另：用户实测报告（-16 的元数据修复有效，需部署后重新导入）

用户上传《秒懂速解小学数字画图 - 燕晓.pdf》（31MB，走分片上传）显示
「标题=完整文件名、作者 Unknown、无封面」，怀疑元数据没取到。

容器内用 **-16 代码**复现整个分片上传元数据链路：

| 项 | 结果 |
|---|---|
| `read_book_metadata` 合并结果 | title=秒懂速解小学数字画图，authors=[燕晓] ✅ |
| `normalize_pdf_meta` 之后 | 不变（内嵌作者非占位符，不回退佚名）✅ |
| 封面 | `cover_data = jpeg` ✅（PDF 内嵌封面被读取）|

该文件本身元数据完整（pypdf 实测：`/Title=秒懂速解小学数字画图`、`/Author=燕晓`、
XMP 一致、第 1 页 1145×1566 封面图）。截图中的现象（标题=完整文件名 + 作者 Unknown）
正是 **-15 及以前**分片上传「无条件取文件名做标题 + 无条件佚名」的行为——
**NAS 上跑的还是旧包**。部署本版后删掉这本书重新导入即恢复。

判定 NAS 版本：

```sh
docker exec audiobook-mybooks-1 grep -c merge_meta_from_file /var/www/mybooks/webserver/handlers/book.py
# 0    = 旧包（-15 及以前），需要升级
# 非 0 = 已是 -16 及以后
```

---

## 4.6.0-16

> **修「同步到文件」看起来没生效**。改后端 3 个文件 + 前端 2 个组件 + 3 份语言包，
> **需要重建前端**。

### 背景：用户反馈「元数据根本没改」

> 「文件处理的同步文件信息，能不能真的更改 pdf、epub 的元数据，我感觉根本没改，
> 重新导入这本改过的书，元数据提取还是不正确」

先做底层闭环验证（容器内真实写入 + 读回 + 重新导入）：

| 格式 | 文件字节变化 | 读回 title | 读回 authors | 重新导入一致 |
|---|---|---|---|---|
| EPUB | 1910 → 2400 ✅ | ✅ | ✅ | ✅ |
| PDF | 1821 → 2060 ✅ | ✅ | ✅ | ✅ |

**写入链路本身是通的**。问题全在「重新导入」这一步，共三处缺陷，另有顺带三修（脚本整理）。

### 缺陷 1：重新导入并回原书，而 `add_format` 不动元数据（主因）

改完书名点同步，文件里确实写进了新书名。再把这本书重新导入时：

```
文件内现在: '新书名-WEB修改' ['新作者-WEB修改']
books_with_same_title(miB): {1}     ← 命中了自己
```

命中同名 → 走 `add_format` 并入原书。但实测 `add_format` **只替换格式文件，
完全不碰 title/authors**。文件换了、记录没换，用户看到的就是「改了等于没改」。

**修法**：新增 `merge_meta_from_file()`。并入既有书时把文件里的元数据补进记录。

- **默认只补空字段**（书名/作者/出版社/标签/丛书/简介/语言），不破坏「书库记录是权威」的既有设计
- `merge_meta_force=1` 时整体覆盖（给需要「以文件为准」的场景）
- 返回实际改动的字段名，前端提示「已从文件更新了：作者、出版社」

> 为什么默认不覆盖：`_add_format_to_existing_book` 这条路径本来就是「把库内元数据
> **写回**新格式文件」，设计意图明确是库内记录权威。无条件覆盖会反过来把它们冲掉。

### 缺陷 2：分片上传把 PDF 作者无条件改成「佚名」

```python
# Handle special formats like txt and pdf
if fmt in ["txt", "pdf"]:
    mi.title = utils.remove_zlibrary_suffix(filename.replace("." + fmt, ""))
    mi.authors = [_("佚名")]          # ← 无条件
```

大文件走分片上传，PDF 标题**无条件取文件名**、作者**无条件回退佚名**，
刚同步进 PDF 的元数据在这里被直接丢掉。

### 缺陷 3：PDF/TXT 标题作者口径三处各写一套

同一个 PDF 走不同入口，得到三个不同结果：

| 入口 | 标题 | 作者 |
|---|---|---|
| `_receive_new_book`（单文件） | 三态判断（空/下载工具/SSReader Print. 才用文件名） | 仅 `unknown` 才换佚名 |
| `BookUploadChunk`（分片） | 无条件文件名 | 无条件佚名 |
| `BookSperate`（分离格式） | 无条件文件名 | 无条件佚名 |

**修法**：抽 `normalize_pdf_meta()` / `normalize_txt_meta()`，四处调用点全部收口。

- `PDF_PLACEHOLDER_TITLES` 收纳 `SSReader Print.` / `Microsoft Word - ` / `Untitled`
- `_AUTHOR_PLACEHOLDERS` 收纳 `unknown` / `未知` / `佚名` / `anonymous` / `none`
- `PDF_TILE_WITH_FILE_NAME` 现在**真正对所有入口生效**（之前只有单文件上传读它）
- `reset_book_meta` 的 PDF 分支也不再无条件把作者打成佚名

### 顺带修一：限流暂停时间被截断

`autofill.py` 里 `wait = int(wait)` 把浮点秒数直接截短：1.8s → 1s，
实际只睡 1 秒就重试，比服务端窗口早走 0.8 秒，大概率再撞一次限流。
`resume_at` 又被 `int()` 截断，进度条显示的恢复时刻比真实时刻早最多 1 秒。

改为 `math.ceil(wait)`，`resume_at` 保留毫秒精度。这是既有回归用例
`test_pause_then_retry_completes_all` 一直在报的错，之前没修。

### 顺带修二：弹窗组件构建失败

`AudioListDialog.vue` 把 `_lastAudiosSig` / `_diagTaps` 放在 `data` 里，
`_` 开头是 Vue 2 保留键，触发 `vue/no-reserved-keys`，**前端构建直接失败**。
改为在 `created` 里挂到实例上（与 `_el` 一致）。

### 补充：远程缺失的 epub 阅读器模板

`webserver/resources/book/epubjs.html` 在远程分支里不存在，但
`book.py` 的 `html_page("book/epubjs.html")` 要读它——缺了则在线读 EPUB 失败。
本版补回。

### 顺带修三：`tools/` 与 `scripts/` 脚本同名，看不出来该用哪个

两处各有一套同名脚本，名字一样、用途完全不同：

| 原名 | 两侧的差别 |
|---|---|
| `hotfix.sh` | `scripts/` 从**部署包**里挑 `.py`；`tools/` 从**源码目录**挑 `.py` |
| `upgrade_from_upstream.sh` | `scripts/upgrade-upstream.sh` 全自动跟上游；`tools/` 那个是手工 git 补丁合并 |

**只改 `tools/` 侧**（`scripts/` 是部署包的正式入口，改名会让已发手册失效）：

```
tools/hotfix.sh                →  tools/hotfix-from-src.sh
tools/upgrade_from_upstream.sh →  tools/upgrade-from-upstream-manual.sh
```

两个脚本头部加「与 `scripts/` 下哪个的区别」对照，`INSTALL_GUIDE.md` 两处章节各加
区分说明 + 12 处命令示例同步改名，`scripts/README.md` 新增对照表。

同时把 16 个脚本（`tools/` 6 + `scripts/` 10）统一 `chmod +x`——此前
`tools/hotfix.sh`、`tools/upgrade_from_upstream.sh`、`tools/category_backfill.py`、
`tools/migrate_from_upstream.sh`、`tools/recommend_benchmark.py`、`scripts/watch-upstream.py`
是 `644` 却带 shebang，`./xxx` 直接跑会 `Permission denied`。

### 影响面

| 文件 | 改动 |
|---|---|
| `webserver/handlers/book.py` | 新增 4 个 helper + 5 处调用点收口 |
| `webserver/services/autofill.py` | 限流等待取整方式 |
| `app/src/components/Upload.vue` | 上传结果提示带上「更新了哪些字段」 |
| `app/src/components/AudioListDialog.vue` | 保留键改为实例字段 |
| `app/locales/{zh,zh-TW,en}.json` | 新增 `uploadSuccessMerged` + `metaField.*` |
| `webserver/resources/book/epubjs.html` | 补回缺失模板 |
| `myreader-dist` | 删除 8 个悬空符号链接，`pack.sh` 收紧为断链必须为 0 |
| `tests/test_meta_merge.py` | 新增 24 项用例 |
| `tools/hotfix.sh` → `tools/hotfix-from-src.sh` | 改名去重 + `chmod +x` |
| `tools/upgrade_from_upstream.sh` → `tools/upgrade-from-upstream-manual.sh` | 改名去重 + `chmod +x` |
| 其余 14 个脚本 | 统一 `chmod +x` |
| `INSTALL_GUIDE.md`、`scripts/README.md` | 同步改名 + 新增两套脚本的分工对照表 |

### 验证

```
Ran 1287 tests — 以远程分支为基线逐条对比
差异（仅出现在改动后 = 新引入）: 无
```

### 怎么用

1. 改完元数据，先点「同步到文件」（这一步一直是好的）
2. 重新导入同一个文件时，如果并进了同名书，提示会告诉你补了哪些字段
3. 想强制以文件为准：上传请求带 `merge_meta_force=1`

---

## 4.6.0-15

### 彻底移除旧布局 `audios/<book_id>/`

4.6.0-13 起音频写入书目录内的 `.audio/`（`library/<作者>/<书名> (id)/.audio/`），
-14 修了读取端。本版把旧布局的支持代码**全部删除**——读、写、扫描、删除、播客、
TTS 输出、重复书合并，一律只认 `.audio/`。

- **升级前检查**：`scripts/upgrade.sh` 新增步骤 1.5，发现 `audiobook-data/books/audios/`
  下仍有音频文件时会列出并要求确认；`audio_dir.describe_leftover_legacy_audio()`
  供启动自检复用。
- `webserver/base/audio_dir.py`：删 `legacy_audio_dir()`/`legacy_audio_dirs()`/
  `LEGACY_AUDIO_ROOT`；`audio_dir_for_read` 不再回退旧目录（书不在 library 时返回
  `(None, False)`，调用方按无音频处理）；`audio_dir_for_write` 去掉「旧布局有内容就
  继续写旧位置」的抢跑分支；原函数更名 `obsolete_audio_dirs()`（仅供检查用）；
  核心函数新增可选 `library_root` 参数（测试/工具注入）。
- `webserver/handlers/audio.py`：7 处硬编码 `AUDIO_OUTPUT_FOLDER/<id>/` 与
  `AudioFile` 的旧目录兜底全部清除；`AudioBooks` 列表页、`AudioBooksCache._scan`
  改走 `find_audios_by_scanning_library()`；转换输出目录改 `audio_dir_for_write`；
  `AudioUtils.clear_audio` 支持 `extra_dirs`（线程池外先算好路径，避免子线程碰
  calibre Cache），并新增 `audio_dirs_of()`；`AudioDelete`/合集下载/购买改走
  `resolve_audio_dir`。常量 `AUDIO_OUTPUT_FOLDER` 删除。
- `webserver/handlers/base.py`：`get_audio_books_count()` 改扫 library（旧实现只数
  `audios/` 下数字目录，旧目录空了之后侧边栏的有声书计数恒为 0）。
- `webserver/handlers/podcast.py` / `podcast_provider.py`：音频文件服务与剧集列表
  改走 `audio_dir_for_read`。
- `webserver/toolbox/mimo_tts.py`：TTS 输出目录改 `audio_dir_for_write(self.db, ...)`，
  不再看 `audio_output_folder` 配置；`core_api.py` 配置白名单同步调整。
- **修复 book_dedup 已然断掉的导入**：`handlers/book_dedup.py` 还在
  `from webserver.services.audios_import import AUDIO_OUTPUT_DIR`（该常量
  -13 就没了，页面一开就 ImportError）。`DuplicateBookMerger` 去 `audio_root` 参数，
  音频目录改由 `audio_dir_for_read/for_write` 从 calibre 库解析，搬移目标变为
  保留书目录的 `.audio/`；测试夹具同步重写为 library 布局（43 项全过）。
- **修复 -14 引入的统计接口 NameError 回归**：P1 时区改造重写「本月起止」时删掉了
  `current_year`/`current_month` 的计算，返回值仍引用旧变量 → `/api/reading/stats`
  每次调用都 500（前端 `.catch` 吞掉，历史页统计卡片静默消失）。现从月起点取
  站点时区的年/月，与统计口径一致。前端未消费这两个字段，纯后端修复。

> **升级注意**：如果你的 `audiobook-data/books/audios/` 里还有书（-12 及更早导入的），
> 必须先手工把音频搬进对应书目录的 `.audio/`，否则升级后那些音频不可见。
> upgrade.sh 会在动手前提醒。

### 音频播放链路三处根治（弹窗卡死 / 进度不动）

现象：详情页有声书弹窗、`/audio/<id>` 播放页都出现过「点播放一动不动，
进度停在某个值，Ctrl+F5 才能恢复」。定位下来是三处独立缺陷叠加：

1. **nginx 覆盖缓存头**：`location ~ ^/(api|get|read|opds|auth)/` 里的
   `expires $get_expires` 使 `/api/` 命中 `default -1s`，强行下发
   `Cache-Control: no-cache` + 过去的 `Expires`，把后端下发的 ETag/
   Last-Modified 全部盖掉 → 播放器每次 seek 都要整段重下。
   新增 `location ~ ^/api/audio/[0-9]+/`（置于通用规则之前），不设 expires，
   透传 Range 并关闭 `proxy_buffering`。
2. **后端 HTTP 不合规**：`BaseHandler.head()` 直接转调 `get()`，HEAD 请求
   把整个音频文件当响应体写出；且 `AudioFile` 无 ETag/Last-Modified，
   Range 的 `end` 未夹紧（`bytes=0-999999999` 会写出超出实际内容的
   Content-Length，浏览器读不满一直等）；416 缺 `Content-Range`。
   现 HEAD 提前返回、补 `ETag`/`Last-Modified`/`private, max-age=3600`、
   夹紧 `end` 并按 RFC 7233 补 416 头。
3. **前端 seek 时序**：`/audio/<id>` 的 `mounted` 里 `initializePlayer()`
   先 `loadTrack(0)`、`restorePlaybackPosition()` 又 `loadTrack(同一集, 上次时间)`，
   第二次走 `isSameFile` 分支直接写 `currentTime`，打断加载 →
   `loadedmetadata` 再触发 → 再写，形成死循环。此外「未缓冲任何数据就 seek」
   会立刻发中段 Range 请求，在网络盘环境下迟迟不回，元素永远停在
   `readyState=1`。
   现改为：加载只走一次；`seek` 等 `canplay`（rs>=3）后再落地并对齐整秒；
   `play()` 全部接住 Promise；恢复位置同步到进度条；`preload` 改 `auto`；
   新增 `@error`/`@stalled` 日志。

> 顺带：详情页「有声书」按钮不再打开内嵌弹窗，直接跳转 `/audio/<id>`
> （与顶部按钮一致）。弹窗组件保留但入口不再触发。

### 新增工具箱：音频批量转码

`/toolbox/audio_transcode`（侧栏「管理 → 音频转码」）。把书 `.audio/`
里的 mp3 批量转 m4a：`-map_metadata -1` 洗掉杂乱的 ID3 标签（此前正是
播音员名被当成作者、导致建错书），`-movflags +faststart` 让浏览器秒开可拖，
AAC 码率可选 64k/96k/128k。

- 支持**批量**：可扫描全库后多选，按队列逐本处理；无 mp3 的书自动跳过
- 安全：m4a 成功生成后才删除对应 mp3；单文件失败不中断，失败的 mp3 保留并列出原因
- 后台线程执行，页面轮询进度（当前书/总进度/失败明细）；同一时刻只允许一个任务

### 修复

- 扫描导入时同目录音频不随书挂载（`scan_service._sync_sidecar_audio`）
- `audiobooks/` 导入目录内含 epub 时电子书优先合并（不再按 ID3 建错书）
- 弹窗续播同会话即时生效；清除音频/取消转换加二次确认

---

## 4.6.0-14

> **紧急修复：4.6.0-13 的有声书导入完全不可用**，请直接升级到本版，跳过 -13。
> 只改后端 3 个文件，**不需要重建前端**。

### 追记（2026-11-03 晚）：字幕工作流落地

- **歌词视图改为固定 20 行窗口跟随**：当前句始终位于窗口正中（上下各 10/9 行），
  窗口随播放整体步进；窗口外句子不渲染，整章上千行字幕不再拖慢布局。
  安全区居中用 flex-grow 伪元素实现（`justify-content: center` 在内容溢出时
  会把顶部裁进不可滚动区，属 flexbox 已知坑）。改动在
  `app/src/pages/audio/_id.vue`，**需重建前端**后生效。
- **确认上游已内置「播放时显示字幕」**：`pages/audio/_id.vue`（正式播放器）与
  `AudioListDialog`（试听弹窗）都会取音频同目录同名 `.srt/.vtt`，随播放滚动高亮、
  点击字幕跳进度、可开关。后端 `AudioDetail` 接口同样会附 `subtitle` URL。
  **无需改代码，只差 `.srt` 文件本身**。
- 交付独立工具 [`srt-tool/`](../srt-tool/)（faster-whisper，PC 上跑，生成同目录同名
  `.srt`），识别策略借鉴 v6.22：中文引导语、VAD 过滤、幻觉清洗、结果缓存。
  用法见 `srt-tool/README.md`；完整工作流见 `docs/字幕生成与播放.md`。
- 修复 `.gitignore` 通配 `audio/`、`book/` 误伤前端页面，导致 gitee 仓库丢失
  `app/src/pages/audio/`、`app/src/pages/book/`（改根目录锚定 `/audio/`、`/book/`），
  并补齐这两个目录与 `imports.vue` 的空导入提示（与 NAS 部署包对齐）。

### 严重 bug：`'LibraryDatabase' object has no attribute 'cache'`

`4.6.0-13` 把音频路径改造收口到 `webserver/base/audio_dir.py` 后，导入链路里写成了：

```python
audio_dir_for_read(self.db.cache, book_id)     # ← 错的
```

但 `AsyncService` 注入的 `self.db` 就是 calibre 的 `LibraryDatabase` 本身，
它**没有 `cache` 属性**，cache 是 `db.new_api`。结果每一本书都在 `_check_audio_exists`
第一步就抛 `AttributeError`，被外层 `except` 吞成一行「文件无效」：

```
[E] error processing .../1.哈利·波特与魔法石: 'LibraryDatabase' object has no attribute 'cache'
```

**所有 15 本书全军覆没**，界面上每一行都显示「文件无效」，看起来像文件坏了，
实际是代码 bug。

**修法**：新增 `audio_dir.cache_of(db)`，传 `LibraryDatabase` 还是 cache 都能正确工作；
`audios_import.py` 三处 `.cache` 全部改为直接传 `self.db`。

同时补了回归用例：`FakeLibraryDb` 刻意**不实现 `.cache`**，专门守住这条路。

### 顺带修掉同一批暴露出来的三个问题

#### 1. 「有声书目录里没有找到可导入的书」是误报

`/admin/audio_import/status` 在任务结束后返回空 `status={}`，前端拿 `total=0`
就判成「目录里没东西」。跑得快的任务（比如上面那种秒级全失败）第一次轮询时任务
已经结束，于是弹出与事实完全相反的提示——用户明明看到列表里有 15 行。

现在任务结束后也返回最后一次真实状态。

#### 2. 书名乱码：GBK 标签被按 latin-1 读

界面上出现 `¹þÀû²¨ÌØÓëËÀÍöÊ¥Æ÷` 这种书名，是很多老 mp3 的 ID3v1 标签
没写编码声明，mutagen 按 latin-1 解码的经典结果。

新增 `_fix_mojibake()`：检测到「字符全在 latin-1 高半区」的特征就按 GBK 重新解码，
还原失败（出现替换字符）则保持原样，不会把正常的法语/德语标签改坏。

验证：`¹þÀû²¨ÌØÓëËÀÍöÊ¥Æ÷ → 哈利波特与死亡圣器`，`café déjà vu` 原样不动。

#### 3. 单个目录消失会把整个导入任务 abort

`subdirs` 是开跑前一次性取的，中途你把某个目录移走/改名，`os.listdir` 就抛
`FileNotFoundError`，整个任务终止，本轮剩下的书一本都处理不到，日志里只有
一句 `failed: [Errno 2]`。

现在单条目录消失只跳过这一条并记日志，其它书照常导入。

### 新增 `scripts/hotfix.sh`：只改 Python 时不必重建镜像

`upgrade.sh` 是「全量解压 + `docker compose build` + `up -d`」，NAS 上一次十几分钟。
但绝大多数修复只动了 `webserver/` 下的 .py——这部分在 Dockerfile 里就是
`COPY webserver/`，纯 Python，不参与编译。为它重建整个镜像纯属浪费。

```sh
sh scripts/hotfix.sh /volume1/docker/audiobook-deploy-4.6.0-14.tar.gz --restart
```

只从包里解出 `webserver/` + `tools/` + `server.py`（不解 197M 全包），
`docker cp` 覆盖 → 容器内 `compileall` 预检 → 编译不过**自动回滚** →
通过则重启并检查 4 个进程 + HTTP 200。全程约 10 秒，旧代码备份在
`audiobook-hotfix-backup/<时间戳>/`，回滚命令脚本会打印出来。

前端（`app/`）、阅读器产物（`myreader-dist/`）、Dockerfile、依赖这类改动
仍然要走 `upgrade.sh`，脚本里有一张对照表。

### 日志可诊断性

导入失败时的日志以前只有一句异常，看不出是哪一步挂的（`db.cache` 那个 bug 就是
这样被埋成「文件无效」的）。现在带上阶段名和 book_id：

```
[AUDIO_IMPORT] error processing <路径> [阶段=解析书目录 book_id=571]: xxx (AttributeError)
```

四个阶段：`查重` → `创建书籍记录` → `解析书目录` → `复制音频`。

### 4.6.0-14 后续热修（NAS 上以小补丁包安装）

**① BIG5 繁体标签修复**（线上首例：台湾版哈利波特有声书的 ID3 标签是 BIG5，
GBK 解出来含替换符，`_fix_mojibake` 按设计放弃修改 → 书名作者乱码）：

- `webserver/services/audios_import.py` `_fix_mojibake()` 加编码回退：
  `for enc in ("gbk", "big5")`，谁解出来没有 `\ufffd` 用谁，都失败保持原样
- 自测 5 类：GBK 样例（仍还原）、BIG5 繁体（新增命中）、真 latin-1（café 不动）、
  ASCII、正常中文——全过
- **同时把修复日志从 `logging.debug` 升到 `logging.info`**：默认级别下可见，
  格式 `[AUDIO_IMPORT] fixed mojibake (gbk|big5): '...' -> '...'`，
  出问题一眼能看出走的哪条编码路径

**② P1 时区统计（上游 v4.6.1 方案移植）**：本月阅读统计按站点时区切月

- `webserver/site_time.py` 新增 `site_month_bounds_server_local()`：
  取站点时区的本月 1 号 00:00 / 下月 1 号 00:00，转成 **naive 服务器本地时刻**
  ——因为 `read_date` 存的是 `datetime.now()`（容器本地 naive，见
  `models.py` `ReadingState`），不是 UTC，比较口径必须一致
- `webserver/handlers/book.py` `BookReadingStats.get` 三处
  `extract('year'/'month', read_date)` 改为 `read_date >= start AND < end`
  （半开区间）。原写法按容器时区切月：站点时区设成别的（如 UTC-5）时，
  月初那几小时会被算进上个月
- 单测验证了跨时区换算与 **DST 切换**：站点 NY 的 11-01 00:00（夏令时，
  UTC-4）→ 上海 naive 12:00；12-01 00:00（冬令时，UTC-5）→ 上海 naive 13:00，
  边界各自正确
- 站点时区就是 Asia/Shanghai 时行为与之前完全一致（同口径），无感知

**③ P0 长任务取消**：核对确认 4.6.0-14 已包含（`autofill.py` / `ai_fillinfo.py`
的 `cancel_requested` + `cancel()`，`admin.py` 两个接口收 `{"cancel": true}`），
无需改动。至此上游 v4.6.1 值得跟的 4 处已全部落地（详见上文「上游发了 v4.6.1」节）。

安装方式：NAS 上用小补丁包 `audiobook-hotfix-big5-tz.tar.gz`（64KB，3 个文件）
`docker cp` 覆盖 + 重启；源码目录同步覆盖。主部署包已包含全部改动。

---

## 4.6.0-13

> 相对 `-12` 只改了后端 + 脚本 + Dockerfile，**前端无改动，不需要重建**。

### 变更：有声书音频改为「跟着书目录走」

用户的原始设想（也是这次改动的动机）：

> 「imports/audiobooks/ 下的子目录，如果有书和音频，就全部归到一个目录，如 library/id，
> 而不是书进了 library、音频去了 audios。」
>
> 「书和音频分家，多了都不知道是不是一家的。」

以前音频统一堆在 `/data/books/audios/<book_id>/`，只用数字 id 跟书关联。书一多就有两个
问题：删掉 library 里的书，`audios/<id>/` 变成没人认领的孤儿；从目录名完全看不出音频属于
哪本书。

**新位置**：

| | 旧 | 新 |
|---|---|---|
| 电子书 | `library/<作者>/<书名> (id)/` | 同左（不动） |
| 音频 | `audios/<id>/` | `library/<作者>/<书名> (id)/.audio/` |

一本书的东西现在全在一个目录里。

#### 为什么多一层 `.audio/` 而不是直接放书目录根

用户的本意是「和书同目录」，这一点由「在书目录内部」满足。但书目录根是 calibre 的地盘，
它按 `metadata.db` 里登记的 formats 维护格式文件，同层多出 mp3 有被当成「未登记文件」
处理的风险（calibre 各版本行为不一致）。`.audio` 以点开头，calibre 遍历时按惯例忽略
隐藏目录，风险最小。

#### 路径必须动态解析——这是换布局丢掉的唯一好处

旧布局 `audios/<id>/` 虽然难看，但路径**永不变**。新布局的目录名是 `书名 (id)`，
**书改名 / 作者改名时目录名会跟着变**。所以路径绝对不能缓存成常量，每次都要走
`cache.field_for("path", book_id)` 重新算。

新增 `webserver/base/audio_dir.py` 统一收口这件事，原来散落在 9 个文件里的
18 处路径拼接全部改走它：

- `audio_dir_for_read(cache, id)` —— 读：优先新位置，没有音频再回退旧位置
- `audio_dir_for_write(cache, id)` —— 写：一律新位置；书目录不存在返回 `None`
- `find_audios_by_scanning_library()` —— 扫 library 找所有带音频的书
- `legacy_audio_dirs()` —— 旧布局的 `<数字>/` 目录

#### 三个容易踩的地方（都写了处理）

1. **迁移期间双布局共存**。`_check_audio_exists` 必须两边都认，只认新布局会把还没迁的
   旧数据判成「这本书没有音频」，导入时重复入库。
2. **旧布局已有音频的书，写入继续走旧位置**。否则新导入的音频进 `.audio/`、老的还在
   `audios/<id>/`，一本书的音频被劈成两半，播放器只认其中一处。等迁移脚本统一搬。
3. **书目录不存在时不硬造**。否则 library 里会留下一堆空壳目录。导入时遇到这种情况
   把该行标成 `INVALID` 并记日志，不静默跳过。

#### 迁移脚本：`scripts/migrate-audio-dirs.py`

```
python3 scripts/migrate-audio-dirs.py           # 预演，只出清单
python3 scripts/migrate-audio-dirs.py --apply   # 真搬
```

- 默认 dry-run，必须显式 `--apply` 才动文件
- 目标已存在同名文件时**跳过而不覆盖**
- 最前面的 `--book-id` 可只处理指定书
- 库里找不到对应书的书目录（孤儿）**只报告不删**，等人工确认
- 字幕 `.srt/.vtt` 和封面图跟着音频一起搬，否则播放器找不到
- 搬空后才删源目录，源目录里还有别的东西就留着
- 启动时先用 `field_for` 探一下 cache。cache 失效时 `book_dir_of` 会静默返回 `None`，
  所有书都会被当成孤儿——清单看起来「没东西可迁」，其实一条都算不出来

`upgrade.sh` 已接入：容器起来、进程全绿之后自动跑一次预演，**把清单打出来问你一句
要不要搬**。迁移失败不阻断升级（代码本身兼容双布局，没迁成只是维持旧样子）。容器里
没有这个脚本时跳过，不报错。

#### 验证

沙箱没有完整 calibre，`field_for` 无法真实调用，所以写了 `scripts/test-audio-dirs.py`：
假 cache + 临时目录树，把 `audio_dir_for_read/write`、扫描、迁移计划、文件搬迁的分支
全跑一遍，**47 项全通过**。

这一步抓出了一个真 bug：最初的 `audio_dir_for_write` 无条件写新位置，导致「旧布局已有
音频、又新导入了音频」的书被劈成两处。现在有专门用例守住它。

```bash
python3 scripts/test-audio-dirs.py   # 通过 47，失败 0
```

#### 已知未验证的部分

calibre 对书目录里多出 `.audio/` 的实际反应**没有实测过**（沙箱缺 calibre）。
缓解措施：点开头隐藏、`audio_output_folder` 配置仍指向旧路径可随时回退、迁移脚本
不删源目录直到搬空。如果真出问题，把 `.audio/` 改名回 `audios/<id>/` 即可恢复。

---

## 4.6.0-12

> 相对 `-11` 只改了播放页 + 3 个语言文件，**需要重建前端**（已重建）。

### 新增：整篇字幕滚动视图（当前句高亮 + 自动跟随）

原先播放页只有一个单句字幕条（`subtitle-section`），只显示正在播的那一句。
看书时想上下文对照就很别扭，只能来回拖进度条。

现在左侧封面区多了一个**视图切换按钮**（`mdi-format-list-bulleted` / `mdi-image`）：

- **整篇模式**：把当前章的全部字幕竖排出来，当前句紫色高亮 + 左侧竖线 + 加粗，
  已播过的句子略暗、未播的更暗，层级一眼能分清
- **自动跟随**：当前句变化时自动滚动。但**不是每句都居中滚**——只有当前句掉出
  「中线上 35% ~ 下 65%」这个舒适区才滚，否则播放时会一直晃、看着累
- **点击任意句**跳到该句起点（复用原有的 `seekToCue`）
- 上下边缘做了渐隐遮罩（`mask-image`），像歌词一样"滚进视野"而不是硬切
- 开关状态记在 `localStorage`（`audio_lyrics_view`），下次进来保持

**移动端**：原本 `.cover-section` 在 768px 以下被 `display: none` 隐藏（没封面可看）。
现在改成——有字幕时显示字幕整篇，没字幕时才隐藏，避免留一块空白挤压播放列表。
移动端首次进入默认就是整篇模式（没有封面视图，切换按钮也一并隐藏）。

**几个实现上的坑**（都已验证）：

1. 用 `scrollTop` 手算，不用 `scrollIntoView`。后者会连带滚动最近的**可滚动祖先**，
   把整个播放页顶上去。
2. `.lyrics-container` 必须 `position: relative`，否则子元素的 `offsetTop`
   会相对 `.cover-section` 计算，滚动位置整体偏掉。
3. 首次展开（`v-show` 从 false 变 true）时 `clientHeight` 还是 0，必须
   `$nextTick` 后再定位，否则跳到顶部。
4. 切到没有字幕的轨道时自动退回封面，避免留下一块空面板。

**验证**（headless Chromium 实测）：

- 滚动定位精度：当前句中心与容器中心偏差 **0px**（真实 flex 布局下）
- 连续播放 60 句：滚动 30 次、跳过 30 次 —— 舒适区判定生效
- 47 次跨句跳转：**0 次**落在视口外
- 边界：首句 `scrollTop=0`（无负数），末句正好等于 `maxScroll`（无过度滚动）

---

## 4.6.0-11

> 相对 `-10` 改了后端 2 个文件 + 前端 1 个页面 + 3 个语言文件，**需要重建前端**（已重建）。

### 修复：有声书导入完全不能用（三个 bug 叠在一起）

用户报的原话：「明明 imports 目录里有电子书和音频文件，点击导入有声书，只是扫描，
实际一个都没导入，自动监听也没把有声书导入进去，界面有声书数量没有」。

三个现象背后是**三个独立缺陷**，缺一个都表现为「什么都没发生」：

#### 1. 自动监听根本没看 `audiobooks/` 目录

`monitor_service.py` 里两处把有声书目录**主动跳过**：

```python
if base_name == constants.AUDIO_BOOK_IMPORTS:      # _add_watch_recursive
    logging.info("[Monitor] Skipping imports folder: %s", entry.path)
    continue
```

```python
if name == constants.AUDIO_BOOK_IMPORTS:           # _monitor_loop
    continue
```

结果：`imports/audiobooks/` 下不论放什么都不会产生任何事件。

**修法**：去掉这两处跳过；事件按路径分流成两个队列——
`_pending_audio`（走 `AudioBookImporter`）和原来的 `_pending_files`（走 `ScanService`）。
新增 `is_audio_path()` / `is_audio_file()` 做判定，`_scheduler_loop` 对两个队列
各自独立防抖、独立派发。

即使以前把 `audiobooks/` 纳入监听，音频也进不了电子书链路——`_on_file_event` 用
`SCAN_EXT`（epub/pdf/mobi…）过滤，mp3 会被当成「非书籍文件」丢掉。所以**光去掉跳过不够**。

#### 2. 音频直接放 `audiobooks/` 根目录时一个都不导入

`_do_import_internal()` 只遍历一级子目录：

```python
subdirs = sorted([d for d in os.listdir(import_dir) if os.path.isdir(...)])
```

说明文案写的是「有声书放到 `audiobooks/`」，用户把 mp3 直接扔进去完全合理，
但这样 `subdirs` 是空列表 → `total = 0` → 循环一次都不跑 → 静默结束。
`_update_progress` 在 `total=0` 时把 `progress` 设成 100，前端看到「已完成」，
**既没报错也没提示**，所以看起来像「点了没反应」。

**修法**：根目录存在音频文件时，把根目录本身当成「一本书」插到列表首位（`dir_name = "."`），
书名依次退回 ID3 标签 → 第一个音频文件名，不会建出书名叫 `"."` 的书。
同时忽略 `.` / `~` 开头的隐藏临时目录（以前会当成书处理）。

#### 3. `total=0` 时界面毫无反馈

前端 `importAudiobooks()` 拿到 `count_total === 0` 就正常收尾，什么都不提示。
现在补一条 info 弹窗，明确指出该把音频放到哪、支持哪些格式。

### 顺带修正

- 导入说明文案只写了「音频文件为 **mp3** 格式」，实际支持 **mp3/m4a/m4b/wav/wma/opus** 六种；
  文案改为「独立子目录（一本书一个目录，目录名即书名）」并列出全部格式，消除歧义。
- `monitor_service` 的 `AUDIO_IMPORT_DIR` 原来在模块导入时按配置算死。设置页改过
  `scan_upload_path` 后音频分流会指向旧目录，现在 `start()` 里重新解析。
- 启动日志多打一行，明确「有声书目录一并监控」及其路径，方便排查。

### 关于「界面有声书数量」

`BaseHandler.get_audio_books_count()` 数的是 `audio_output_folder`（默认
`/data/books/audios/`）下**以数字命名的子目录数**，跟 `imports/audiobooks/` 没有关系。
导入一本都没成功，这个数当然是 0——它是 1 和 2 的结果，不是独立故障。

### 验证

- 目录枚举：子目录 2 个 + 根目录散装音频 → 识别出 `['.', '三体', '平凡的世界']` 3 个单元
  （旧逻辑只有 2 个，散装音频全丢）
- 路径分流 6 个用例全过：根目录音频 / 子目录音频 / 子目录本身 → 判为有声书；
  普通电子书 / 电子书目录 / `audiobooks_bak` 同名前缀旁系目录 → 判为普通文件
  （前缀匹配带 `os.sep`，不会误伤 `audiobooks_backup` 这类目录）
- 调度线程实测：只放音频事件 → 触发 1 次 `AudioBookImporter.do_import`；
  只放电子书事件 → 触发 `ScanService.do_import`；两类同时 → 各触发一次，互不阻塞
- 书名兜底 5 种组合全对（无 ID3 / 有 ID3 / 根目录 / 子目录）
- 配置变更后 `AUDIO_IMPORT_DIR` 重绑定生效，旧目录不再被认作音频目录

---

## 4.6.0-10

> 相对 `-9` 只动了内嵌阅读器的 4 个 chunk，**不需要重建前端**，但仍需 `upgrade.sh` 重打镜像。

### 修复：阅读器本地阅读统计写不进去

**症状**：云端书每次翻页后控制台报

```
[stats] failed to persist reading events: TypeError: Cannot read properties of undefined (reading 'id')
    at a.upsertBook (0w9daefn615~0.js:484:167)
```

**根因**：`StatisticsDb.upsertBook` 的 INSERT 分支，新建书籍行后立刻按 `md5` 反查 id：
`(await this.db.select("SELECT id FROM book WHERE md5 = ? LIMIT 1", ...))[0].id`。
书首次入库时写后立即读查不到行，`[0]` 是 `undefined`，读 `.id` 直接抛错。
已入库的书走 UPDATE 分支（复用开头查到的 id，不涉及写后读），所以不报——
**这就是"只有某几本书一直刷这个错"的原因**。

**重要**：这个 bug **上游 4.6.0 原生就有**，不是我们的改动引入的。
已比对确认：我们改前的 reader chunk 与上游官方包逐字节一致。

**修法**（`myreader-dist` 是构建产物，压缩 JS 直改；同一个类被复制进 3 个
chunk、调用方副本 2 处，共 5 处全部修补，`node --check` 全过）：

- 尾部改为重试读（间隔 40ms × 3 次）→ 仍查不到返回 `null`
- 调用方拿到 `null` 直接跳过后续 `insertPageEvent` / `recomputeBookTotals`

效果：若根因是写后读可见性竞态 → 统计恢复正常；若写永不生效 → 安静跳过
（与修复前等价，但不再刷错误日志）。**不影响阅读与进度同步**。

### 与上游 4.6.0 的完整性核对

拿上游官方容器镜像包（`mybooks4.6.0.tar`，约 2GB）逐文件比对：

| 部分 | 结果 |
|---|---|
| reader `static/chunks` 198 个文件 | **191 个逐字节相同**；差异 4 个正是本版补丁，另 3 个是同代码的另一次构建（BUILD_ID 不同） |
| 后端 `webserver/` | 差异全部是**我们新增**（坏字体处理、字符集嗅探、作者归一化、读者组），上游没有任何被我们删掉的内容 |
| 坏字体处理 | 上游**一处都没有**（`FONT` / `sfnt` / `epub-lite` 全无） |

结论：这份定制是上游的**严格超集**。那本慢书在上游上同样慢，而且更糟（无剥离）。

### 整理：运维脚本全部收进 `scripts/`

原来 14 个 `.sh` 散在仓库根目录，哪些能用在现役版本、哪些是 v9 那趟的一次性工具，看不出来。
现在按「能否再用」分两处：

| 位置 | 内容 |
|---|---|
| `scripts/` | 6 个长期脚本：`upgrade.sh`（升级入口）、`deploy.sh`（首装）、`check-reader.sh`（只读诊断）、`protect-custom.sh`、`upgrade-upstream.sh`、`pack.sh`（出包），附 `README.md` 索引 |
| `scripts/archive/` | 9 个一次性脚本，头部统一标注【已归档】+ 归档原因（**仅在源码仓库，不随部署包下发**） |

同时修掉三处会实际咬人的问题：

- **`deploy.sh` 移到 `scripts/` 后找错工作目录**：它原来 `cd $(dirname $0)` 然后校验 `Dockerfile`，
  移层后会在 `scripts/` 里找。改为「自身目录有 `Dockerfile` 就用自身，否则用上一级，都没有则报错退出」，
  两种摆放位置都认。
- **`upgrade-upstream.sh` 找不到 `protect-custom.sh`**：查找路径从 3 个补到 5 个
  （自身目录 → 上一层 `scripts/` → `/volume1/docker/scripts/` → `/volume1/docker/` → 现役源码目录）。
  `check` 阶段改为复用同一个 `$PROTECT` 变量，不再硬编码 `$(dirname $0)`。
- **补丁包流程的残留文档**：`docs/操作总纲.md` 第三章还在教人打 `audiobook-patch-*.tar.gz`
  再跑 `merge-patch3.sh`，而那个脚本和补丁包早已不存在。整段改为「开发侧直接出成品包 → NAS 装」，
  并明确写出该流程已废弃。

`protect-custom.sh`、`upgrade-upstream.sh` 此前从未进过 git（换台机器就丢），这次一并纳入。

### 修复：仓库里的 myreader-dist 是残骸，直出的包必然 502

**症状**：从仓库直接 `tar` 出的包，`deploy.sh` 第 2 步报

```
!! 缺 myreader-dist/node_modules
!! 有效符号链接: 0
!! MyReader 产物不完整 —— 部署后 /readerx 会 502，书页打不开。
```

**根因有两层**：

1. **仓库里那份产物本身就是残的** —— 1246 条、58M、**0 个符号链接**，
   缺 `node_modules`、`.pnpm`、`app/src`、`media`。而部署包需要的是
   2732 条、92M、127 个链接的完整版。
   两份**文件数不同**，但 `git status` 一直是干净的，所以这个缺口长期没暴露。
   原因是 `.gitignore` 的 `node_modules/`、`media/`、`*.mp3`、`src` 这些通配规则
   本意是挡运行时数据和音频库，把产物里的必需内容一起挡掉了。

2. **即使产物补全，打包方式也会毁掉链接** —— `tar --transform 's,^\.,audiobook,'`
   的替换规则会连带作用于**符号链接的目标内容**，
   `../../../../node_modules/...` 被改写成 `audiobook./../../../node_modules/...`。
   包能解开、文件数也对，但 127 个链接全断。

**修法**：

- 用部署包里那份完整产物覆盖仓库中的 `myreader-dist`，补 1486 个文件（含全部 127 个链接）
- `.gitignore` **末尾**追加 18 条例外（`!myreader-dist/**` 等）。
  必须放末尾——git 后出现的规则优先；带注释说明为什么需要、改完怎么验证
- 新增 `scripts/pack.sh`：用 `cp -al` 硬链接镜像出 `audiobook/` 目录树，
  再 `cd` 到父目录 `tar -czf ... audiobook`，**完全不用 `--transform`**；
  打完自动解压实数链接（`--check` 可单独验已有包）
- `docs/操作总纲.md` 步骤 3 换掉之前那段会踩坑的手工 `tar` 写法

**验证**：`git clone` 一份出来，2732 条 / 92M / 127 链接全在，119 个有效
（8 个断链是产物固有残留，源产物、clone 产物、打包产物三份一致）。
`sh scripts/pack.sh` 从仓库直出 → 199M → 有效链接 119 / 断链 8 → 校验通过，
与手工组装的包行为完全一致。

### 追加修复：nginx 补 /runtime-config.js 转发

阅读页 console 报 `runtime-config.js:1 Uncaught SyntaxError: Unexpected token '<'`。
根因：该文件是 Next.js 服务端路由（9100 的 Node 动态返回），但 nginx 的
myreader location 只覆盖 readerx/_next/assets 等前缀，请求落进 SPA 兜底返回 index.html。
自内嵌阅读器上线起就存在，非本次升级引入。

修法：`conf/nginx/mybooks.conf` 加 `location = /runtime-config.js` 精确转发。
本地 nginx + 假后端端到端实测三条路径全过；NAS 上已先热修验证（200 application/javascript）。
conf 打进镜像，需重建生效（upgrade.sh / deploy.sh 均会做）；仓库已永久修复。

### 补齐：webserver/epub_to_audio 整个目录丢了

EPUB 转有声书（「听书」里的自动转音频）从 4.6.0-9 起就是坏的，报错在
`webserver/worker/epub2audio_worker.py` 里拉 `subprocess python3 main.py` 时失败——
因为 `main.py` 压根不在。

上游 4.6.0 镜像里这个目录是**内嵌的第三方项目**（p0n1/epub_to_audiobook，
自带 `.git` 指向 `../../.git/modules/webserver/epub_to_audio`，是个 git submodule）。
移植时只带了仓库里 `git ls-files` 能看到的路径，submodule 内容没跟过来。

补回 61 个文件（0.5M）。**没有带**的内容及原因：

| 跳过 | 原因 |
|---|---|
| `examples/` (2.1M) | Robinson Crusoe 示例 epub + 两张 README 截图，运行时不用 |
| `.github/`、`.dockerignore`、`.gitattributes` | 上游 CI 与镜像构建用 |
| `.git` | 一行 `gitdir:` 指针，指向本仓库不存在的路径，留着 `git status` 会报错 |
| `__pycache__/` | 开发残留，见「顺手清掉 __pycache__」 |

同时改了两处依赖：

- `webserver/epub_to_audio/requirements.txt`：去掉 gradio / gradio_log / docker
  的 pin，改为注释说明为什么生产不装（gradio 那条链会顶掉基础镜像里
  numpy/pydantic 的版本，连 calibre 一起弄坏；我们只跑命令行 `main.py`，
  不跑它的 WebUI `main_ui.py`）
- `Dockerfile`：在装完主依赖后单独补 `EbookLib / mutagen / pydub / sentencex`，
  并 `import` 一遍做自检（缺了就让构建失败，而不是等用户点转换才报错）。
  `edge-tts` 不在这一批里——它已经从 `third-party/edge-tts` 装了 PoxenStudio
  定制版，再装一次会覆盖成 PyPI 官方版、丢掉 `proxy` 参数。

### 修复：转音频的音质（48kbps）+ 纯标点段落丢字

补回 `epub_to_audio` 之后顺着它的上游查下去，发现这个目录对应的不是
`p0n1/epub_to_audiobook` 主干，而是 **`HorkyChen/epub_to_audiobook`** 这个 fork
（提交 `8ca3bc4`）。fork 落后主干 7 个提交，其中两个是**真实影响听感与内容**的：

**① 双重 MP3 编码，输出被压到 32kbps**

原流程：每个 chunk 编成 mp3 存临时文件 → 合并时全部解成 PCM → 最后再编一次 mp3。
最后一次 `combined.export(..., format="mp3")` **没给 `bitrate`**，落到 ffmpeg 默认的
32kbps。实测（3 段 1 秒、24kHz 单声道）：

| 路径 | 码率 | 3 秒大小 |
|---|---|---|
| 原来 | 32000 bps | 12,429 字节 |
| 现在 | 48000 bps | 18,525 字节 |

**② 纯标点片段会整段丢**

`parse_text()` 只过滤空白，`——`、`...`、`，` 这类单独成段的会送进 edge-tts，
返回 `NoAudioReceived`，那一段静音丢字。中文书里破折号分段、省略号行很常见。

**改法**（`webserver/epub_to_audio/audiobook_generator/tts_providers/edge_tts_provider.py`）：

- 把主干 `f11a014` 的做法合进来：`get_audio_segment()` 返回内存 PCM 段，
  `text_to_speech` 攒齐后**只编一次**、指定 `bitrate="48k"`
- 把主干 `fd76745` 的 `_is_meaningful_text()` 合进来：无字母数字的片段丢弃，
  单字母（`A`、`B,`）保留
- **fork 的字幕逻辑原样保留**：`collect_subtitles`、`cue_events`、`elapsed_ticks`
  一个字没动，`--output_srt` 照常出 `.srt`

实测（mock edge_tts，三段 1 秒音频 + 0.5 秒停顿）：
MP3 48000bps/24kHz/单声道；SRT 时间轴 `0.0 / 1.5 / 3.0` 秒正确累加；
不再产生 `/tmp/chapter-*` 临时文件。文本过滤边界 16 种输入全部符合预期。

> **以后升级 `epub_to_audio` 别直接覆盖回 `8ca3bc4`**，会把这两处修复冲掉。
> 详细对照见 `webserver/epub_to_audio/` 内的改动注释（单次 48kbps、过滤纯标点片段）。

### 新增：盯上游改动的工具

上一版里写「epub_to_audiobook 这个 fork 已经停了」——**说错了，已更正**。
准确情况：`HorkyChen/epub_to_audiobook` 的 `develop` 分支停在 `8ca3bc4`（2026-10-13），
但**上游本体 `PoxenStudio/mybooks` 一天十几个提交**，只是没再动 `epub_to_audio` 而已。

新增 `scripts/watch-upstream.py`，按「跟我们有没有关系」给上游提交分档：

```
⚠ 改了我们也改过的文件（升级必冲突）     ← 必看
● 碰了 webserver/ 或 app/src/           ← 扫一眼
○ 其余（dependabot、文档）               ← 忽略
```

```sh
python3 scripts/watch-upstream.py                  # 最近 30 个
python3 scripts/watch-upstream.py --since-baseline # 只看增量
python3 scripts/watch-upstream.py --offline        # github 断了看缓存
```

基线 `docs/upstream-baseline.json` 已记到 `2135ad7`（2026-11-01）。

**顺带查出一个上游的坑**：上游 `app/package.json` 被 dependabot 把 `nuxt` 从 `2.18.1`
顶成 `^4.6.2`（PR `c120663`，10-25 合入），但两个锁文件互相矛盾——
`package-lock.json` 锁的仍是 2.18.1，`pnpm-lock.yaml` 已解析成 4.6.2。
其余依赖全是 Vue 2（`vue ^2.6.14`、`vuetify ^2.6.10`）、`nuxt.config.js` 是 Nuxt 2 写法，
而 **Nuxt 4 只支持 Vue 3**。用 `npm ci` 还能构建，用 `pnpm install` 大概率直接失败。

我们本地是 `^2.18.1`，且 Dockerfile 走 `COPY app/dist*` 已有产物、不跑 npm，暂未受影响。
但**别照抄上游的 `package.json`**。

### 上游发了 v4.6.1：只挑 4 处，不做整体升级

`v4.6.1`（`cdbe366`，2026-11-01）共 **35 个提交、80 个文件、+8683 −7349 行**，
GitHub 上**没有 Release 页面**，只有 tag，所以没有官方变更说明，得自己数。

跟我们重叠的 9 个文件里，有两条值得跟：

**① 长任务取消（上游已经做了，和我之前建议的逐字一致）**

`autofill.py` / `ai_fillinfo.py` 加 `cancel_requested` + `cancel()`，
循环每个批次和每本书前检查；`handlers/admin.py` 两个接口收 `{"cancel": true}`。
—— 这是当年给上游提的 P2 建议（长任务无法取消，只能重启容器），现已落地，可从未解决清单里划掉。

**② 本月阅读统计按站点时区切**

`handlers/book.py` 原来用 `extract('year'/'month', read_date)`，等于按**容器时区**切月；
容器是东八区、用户设了别的时区时，月初那几小时会被算进上个月。
改用 `site_time.site_month_bounds_server_local()` 换算（`site_time.py` 同步 +77 −17）。

**P0 的两个 f-string 语法问题，v4.6.1 仍然没修**——`book_type_query`（`admin.py`）
和 `The installed version is`（`main.py`）两处都没动，Python 3.11 下照旧 SyntaxError。

**明确不跟**：`nuxt 2.18.1 → 4.6.2`（错的，Vue 2 跑不了 Nuxt 4）、
`conf/nginx/ipv6-listen.conf`（我们的 nginx 配置自管，照抄会打架）、
favicon 资源、AI 助手。

详细对照见当版发布说明中的播放链路修复记录。

### 盯上游：watch-upstream.py 补 --tags 与 --between

```sh
python3 scripts/watch-upstream.py --tags                     # 上游发新版了吗
python3 scripts/watch-upstream.py --between v4.6.0..v4.6.1   # 两个版本之间改了什么
```

`--between` 输出和基本模式同一套分档（⚠ 冲突 / ● 相关 / ○ 其余），
不用再手动数 80 个文件。

### 部署包瘦身：归档内容不再下发

部署包里混着不该给 NAS 用的东西，逻辑上混乱（"哪个脚本该跑"要多想一步），体积也白占：

| 排除项 | 是什么 | 原来占 |
|---|---|---|
| `scripts/archive/` | 9 个一次性脚本（v9 合并、回退 v8、导产物…） | 10 条 |
| `docs/archive/` | 旧版 NAS 操作手册、坏字体排查记录 | 2 条 |
| `docs/settings-redesign/` | 界面设计稿截图 | 10 条 |
| `audiobook-src/` | 误提交的嵌套仓库条目（空目录，无内容） | 1 条 |

`audiobook-src` 还是 git 层面的脏数据：它以 submodule 模式（`160000`）被提交，
但 `.gitmodules` 里没有它 —— 早期在仓库里 clone 自己留下的残迹。已 `git rm --cached` 清掉。

做法：
- `pack.sh` 打包时硬排除这四类；`--check` 增加断言，包里出现就给红
- `docs/坏字体修复-4.6.0-9-归档.md` 归入 `docs/archive/`（它是排查记录，不是现行手册；
  功能本身 `epub_font_fix.py` / `tools/fix_broken_fonts.py` 仍在用）
- README / 操作总纲 / 部署包说明 / scripts README 里凡指向 archive 的地方，
  统一注明"仅在源码仓库，不随包下发"

包体积 199M → 198M（归档本身很小，主要是逻辑清晰了）。归档内容在仓库里完好保留。

### 顺手清掉 `__pycache__`

仓库里散着 17 个 `__pycache__`（`webserver/`、`tools/`、`tests/` 下都有），
合计约 5MB。`.dockerignore` 里早就排掉了，所以镜像里没有；
但 `pack.sh` 没排，于是每份部署包都带着它们，解压到 NAS 上纯占地方。

`pack.sh` 打包时现在会清掉 `__pycache__` 与 `*.pyc/*.pyo`，`--check` 里加了断言：
超过 5 个就报错。这些文件本来就在 `.gitignore` 里、不在版本库中，删了不影响任何东西。

包体积随之下到 197M。

### 交付

包与校验值不在正文里写死（每次回填都会改变包本身，自相矛盾）。
定稿的 md5 见仓库外的交付说明 `上传说明.md`；脚本自检：

```sh
sh scripts/pack.sh --check /workspace/audiobook-deploy-4.6.0-10.tar.gz
```

包已做成**可复现**：`--sort=name --mtime=<最后一个提交时间>` 加 `gzip -n`，
同一份源码重出多少次字节都一样。所以核 md5 是有意义的——
对不上就是包坏了，或者源码在出包之后又改过。

---

## 4.6.0-9

> **这一版前后端都动了，必须重建镜像**（`upgrade.sh` 会自动做，约 4 分钟）。

>
> 核心一句话：**作者名不再被刮削搞乱，人工改过的作者也不会再被覆盖；
> 同名不同作者的书不会被误合并。**

### 背景：作者名为什么会乱

calibre 的目录结构是 `library/<作者>/<书名> (<id>)/`。
**作者名差一个字符，就是两个不同的目录，同一作者的书被物理拆到两处。**
而且拆开之后再合并，要搬文件夹、改数据库、重建索引，很麻烦。

脏作者名有三个来源，之前一条都没拦住：

| # | 来源 | 典型脏数据 |
|---|---|---|
| 1 | **有声书 ID3** 的 `artist` / `albumartist` | `某某听书`、`酷我音乐`、多歌手逗号连写 |
| 2 | **8 个元数据刮削源** | `(法)法布尔`、`王学富(译)`、`插画[美国]安德鲁·格拉斯` |
| 3 | **电子书内嵌元数据** | 出版社录入的 `温德著`、`韦东山 主编` |

更麻烦的是**刮削会把已经改好的作者又覆盖掉**：

> `autofill.py` 的 `should_update()` 用的是 `or` 判断——**缺封面 *或* 缺简介就触发刮削**，
> 压根不看作者写得好不好。触发后 `mi.smart_update(refer_mi, replace_metadata=True)`
> 直接把作者覆盖成刮削源的值。所以「先手工改好 → 过几天自动刮削又乱了」是必然的。

### 新增功能

| 功能 | 说明 |
|---|---|
| **S0 作者锁定** | 在界面上手动改过作者的书，打上 `#author_locked = 1` 标记。之后自动刮削**只更新封面/简介/标签，不碰作者**。日志会记一行「作者已锁定，保留 X（刮削值 Y）」，出问题能查 |
| **S2 作者别名表** | 同一作者的不同写法归一到标准名。落盘 `/data/toolbox/author_norm/config.json`，可手工编辑；支持繁简自动归一（`J·k·羅琳` 与 `J·K·罗琳` 同一个键） |

> **别名表默认是空的**——不预置任何数据，因为猜错的别名比不归一更糟。
> 什么都不配的情况下，这一版仍然生效的是 S0 锁定 + S1 清洗 + S3 刮削源清洗 + S4 入库归一。

### 修复 Bug

| Bug | 严重度 | 表现 | 修复 |
|---|---|---|---|
| **人工改好的作者被自动刮削覆盖** | **高** | 手工把作者改对，过几天自动刮削又变回脏名 | `autofill.py` 单本与批量两条路径都在 `smart_update` **之前**存下 `old_authors`，刮削后若已锁定则还原。批量路径的 `updates` 元组从 2 元扩到 3 元 |
| **`(法)法布尔` 这类国籍前缀清不掉** | **高** | 作者名带 `(法)` `[美]` `【英】`，看着一样的两本书分到两个目录 | `meta_helper.py` 复用已有 `_DYNASTY_REGION_PREFIX`；单字 `绘/校/注/译` 必须前面有空格才剥离（否则 `图图` → `图`） |
| **`插画[美国]安德鲁·格拉斯` 国籍剥不掉** | 中 | 「插画」挡在 `[` 前面，`^\[` 匹配不到 | 新增 `_DUTY_PREFIX`，执行顺序改为：`原作：` → **职责词** → 国籍/朝代。顺序不能换 |
| **`温德著` / `韦东山 主编` 后缀残留** | 中 | 作者名带「著」「主编」，目录名跟着脏 | `_AUTHOR_SUFFIX` 扩到 `绘\|校\|注\|原著\|改编\|主编\|插图` |
| **`王惟恒，李艳` 不拆，`李绍山、陈存军` 拆** | 中 | 同样是合著，顿号能拆、中文逗号不能拆，行为无法解释 | `_MULTI_AUTHOR_SEP` 补中文逗号 `，` |
| **`Rowling,J.K.` 被拆成两个作者** | 中 | 上一条修完后引入的新问题：西文「姓, 名」被逗号切开 | 新增 `_AUTHOR_INITIAL`，任一段是首字母缩写（`J.K.` / `JK`）时整体不拆 |
| **豆瓣 V2 把译者拼进作者** | **高** | `王学富(译)` 直接进作者字段，成为 `#translators` 之外的脏数据 | 六个刮削源（douban_v2 / baike / youshu / xhsd / neodb / ujxsw）统一在返回 `Metadata` 前过一遍 `guess_authors` |
| **刮削源清洗后 `mi.authors[0]` 崩** | **中** | 源返回 `著` / `[美]` / `佚名` 时清洗结果为空列表，紧接着 `mi.authors[0]` 抛 `IndexError`，整批刮削任务中断 | baike / xhsd / youshu 三处都改为 `mi.authors = _authors or [_raw or "佚名"]`，兜底用**原文**而不是「佚名」（保留信息量） |
| **有声书 ID3 的作者名完全不过滤** | **高** | `audios_import.py` 直接把 `artist` 写进作者，是全流程最大的一个口子 | 导入时先 `guess_authors` 清洗、再 `resolve_alias` 查别名表；清洗为空回退原文，不把有作者的书标成「佚名」 |

### 改动范围

**21 个文件：新增 4 个，修改 17 个。后端 15 个 + 前端 6 个。**

| 文件 | 增/删 | 改了什么 |
|---|---|---|
| `webserver/base/author_norm.py` | **新增 462 行** | 归一化核心：`clean_authors` / `author_norm_key` / `loose_author_key` / `author_key_set` / `authors_conflict` / `AliasStore` / `resolve_alias` / `resolve_author_list` / `lock_author` / `is_author_locked` |
| `webserver/handlers/author_norm.py` | **新增 270 行** | 管理接口 4 个 handler + `routes()` |
| `tests/test_author_norm.py` | **新增 248 行** | 32 个单元测试 |
| `app/src/pages/toolbox/author_norm.vue` | **新增 400 行** | 体检 + 别名表两个 Tab |
| `webserver/services/book_dedup.py` | +20 | **作者冲突守卫**（防同名不同作者误合并） |
| `webserver/base/meta_helper.py` | +34 / −7 | `_DUTY_PREFIX`、`_AUTHOR_SUFFIX` 扩展、中文逗号、`_AUTHOR_INITIAL`、执行顺序调整 |
| `webserver/handlers/book.py` | +28 / −3 | `edit_book` 归一化 + 打锁（兼容字符串入参）；**另 5 处入库/刮削路径只归一化、不打锁** |
| `webserver/services/autofill.py` | +29 / −4 | S0 锁定核心：单本 + 批量两条路径 |
| `webserver/services/audios_import.py` | +12 | 有声书导入归一化 |
| `webserver/plugins/meta/douban_v2/api.py` | +7 | 清洗（**保留**译者拼接行为，书页展示需要） |
| `webserver/plugins/meta/baike/api.py` | +7 / −1 | 清洗 + 空结果兜底 |
| `webserver/plugins/meta/youshu/api.py` | +7 / −1 | 清洗 + 空结果兜底 |
| `webserver/plugins/meta/xhsd/api.py` | +6 / −1 | 清洗 + 空结果兜底 |
| `webserver/plugins/meta/neodb/api.py` | +4 | 清洗 |
| `webserver/plugins/meta/ujxsw/api.py` | +4 | 清洗 |
| `webserver/constants.py` | +5 | `COLUMN_AUTHOR_LOCKED` / `CALIBRE_COLUMN_AUTHOR_LOCKED` |
| `webserver/main.py` | +4 / −1 | 注册 `#author_locked`（int 型）+ `author_norm` 路由 |
| `webserver/base/formatter.py` | +4 | 管理列表透传 `author_locked` 字段 |
| `app/src/pages/admin/books.vue` | +40 | 作者列锁图标 + 编辑框勾选 + 保存联动 |
| `app/src/components/AppHeader.vue` | +1 | 工具箱入口 |
| `app/locales/{zh,zh-TW,en}.json` | +44 / 各 | 44 个 `authorNorm.*` key + 3 个 `admin.books.*` key |

### 三个容易踩的设计坑（写在这里免得下次又踩）

1. **`norm_key` 不能当清洗用。** `(法)法布尔` 过一遍键函数得到 `法法布尔`——它把括号删了但留下了里面的「法」。所以必须**先 L1 清洗，再算键**，两步不能合并。
2. **`loose_key` 抓不到中英双写。** 去掉字母后 `J.K. Rowling` 变成空串，本意是让 `罗琳 (J.K.Rowling)` 能对上 `罗琳`，但对纯英文名直接失效。
3. **`_` 是 i18n 函数，不能拿来接译者列表。** 写 `_authors, _ = guess_authors(...)` 会把整个文件的 `_("...")` 全部弄崩。统一改用 `_trans` / `_cleaned_trans`。合并脚本里有一道专门的自检挡这个。

### 补丁包

| 文件 | 大小 | 说明 |
|---|---|---|
| `audiobook-patch-4.6.0-9.tar.gz` | 约 110 KB | 21 个文件，覆盖即用（含前端） |
| `audiobook-deploy-4.6.0-9.tar.gz` | 94 MB | 完整可部署包（基于 `-8` 合并） |
| `merge-4.6.0-9.sh` | 11 KB | 合并脚本，含 21 项校验 |

### 部署

```sh
# 三个文件都放 /volume1/docker/
sh merge-4.6.0-9.sh
sh /volume1/docker/audiobook/upgrade.sh /volume1/docker/audiobook-deploy-4.6.0-9.tar.gz
```

**必须重建镜像**，两条理由，任一条都够：

1. 新增了 calibre 自定义列 `#author_locked`，`main.py` 启动时会自动建列；
2. **本版含前端改动**（管理页锁图标、作者归一化页面、三语文案），必须重新 `npm run build-spa`。

`upgrade.sh` 会自动完成这两件事，不需要手工操作。构建约 4 分钟。

### 验证

| 项目 | 结果 |
|---|---|
| 32 个单元测试（有 / 无 OpenCC 两种环境） | 全过 |
| 28 例清洗回归（21 正例 + 7 反例） | 全过 |
| 33 例极端输入（`著` / `[美]` / `空串` × 3 个源） | 零崩溃 |
| 9 个端到端场景（锁定保留 / 未锁归一 / 繁简归一 / 空值不崩 / 目录合并 / 打锁 / 字符串入参 / 未登记保留） | 全过 |
| 合并脚本真实演练（基于 `-8` 部署包） | 通过，BOOK_NAV 13 组 + 文案键 2457 个未受损 |
| **9 例作者冲突判定**（法布尔/繁简/路遥vs天蚕土豆/佚名/曹雪芹/Unknown） | 全过 |
| **体检报告实测**（DUP 3 组 / SUS 1 组 / DIRTY 3 条，canonical 选对） | 全过 |
| **三语文案键完整性**（前端用到的 136 个 key × 3 语言） | **缺失 0** |
| **i18n 插值参数一致性**（16 处 `$t(k, {…})` 与文案占位符比对） | **全对** |
| **Vue 模板非法标签名扫描**（`<div:key=` 这类） | **0 处** |
| **前后端路由对齐**（5 个接口路径逐条比对） | 全对 |
| 21 个文件语法检查 | 全过 |

反例（**不该动**的，确认没被误伤）：`图图` / `绘心` / `张文` / `绘图：王五` / `Rowling,J.K.` / `J·K·罗琳` / `张三`。

### 升级后要做什么

1. **重启后看日志**：搜 `[AUTHOR_NORM]`，能看到打锁与命中的记录。
2. **手工改一次作者试试**：改完等一轮自动刮削（或手动点刮削），确认作者没被改回去。
3. **别名表按需配**：默认空的，不用就不配。配了才生效，位置 `/data/toolbox/author_norm/config.json`。
   **也可以直接在界面上配**：侧边栏「工具箱 → 作者归一化」（`/toolbox/author_norm`），见下节。
4. **存量脏数据这一版不清理**——只保证不再产生新的。跑一次体检知道有多脏，再决定怎么清。

### 追加：管理界面与同名重复书守卫（4.6.0-9 第二批）

第一批只做了后端，这一批把管理界面补齐，并修了一个**会丢书**的隐患。

#### 修 Bug：同名重复书清理会误合并不同作者的书

`book_dedup.py` 原来只按**书名**分组，判断方向时只看「电子书 / 音频」的分布：

```python
len(with_ebook) == 1 and with_audio    # 就算 merge
```

**全程没比过作者。** 所以《人生》（路遥，epub）+《人生》（某个网络作者，音频）
会被判成重复书直接合并——音频挂到路遥那本下面，或者反过来，**书就串了**。

修法是在方向判断之前加一道作者冲突守卫：

```python
if authors_conflict(ebook_authors, b["authors"]):
    return {... "action": "skipped",
            "reason": "作者不同（路遥 vs 天蚕土豆），不是重复书，请人工确认"}
```

`authors_conflict()` 的判定刻意做得**宽松**：

| A | B | 判定 | 为什么 |
|---|---|---|---|
| `法布尔` | `(法)法布尔` | 不冲突 | 先 L1 清洗再算键，两者同键 |
| `J.K.罗琳` | `J·k·羅琳` | 不冲突 | 繁简 + 分隔符归一后同键 |
| `路遥` | `天蚕土豆` | **冲突** | 两个非空键完全不相交 |
| `佚名` | `路遥` | 不冲突 | **任一边为空一律不判冲突** |
| `Unknown` | `路遥` | 不冲突 | 同上，占位名不算有效作者 |

> **宁可放过，不可误杀。** 判成冲突只是跳过合并（书还在，人再看一眼），
> 判成不冲突则会真合并（很难回退）。所以空白/占位作者（`佚名`/`未知`/`Unknown`）
> 一律从键集合里剔除，不作为「这是另一个人」的证据。

例：9 个用例全部按预期通过，其中 `曹雪芹,高鹗` vs `(清)曹雪芹` 判为不冲突（有交集）。

#### 新增：作者归一化管理页 `/toolbox/author_norm`

侧边栏「工具箱」下新增入口，两个 Tab：

**Tab 1 · 体检**（只读，不改数据）

按归一化键给全库作者聚类，报三类：

| 类别 | 含义 | 建议 |
|---|---|---|
| **确定重复** | 归一化键相同、显示名不同（`法布尔` / `(法)法布尔`） | 高置信，一键加入别名表 |
| **疑似重复** | 键不同但一个名字包含另一个（`罗琳` / `J.K.罗琳`） | 需要人确认，可能是两个人 |
| **脏名候选** | L1 清洗后名字变了（`温德著` → `温德`） | 不一定要动，存量走「作者清理」 |

标准名（canonical）的选取规则：**优先选 L1 清洗后没变的写法**（`(法)法布尔` 和 `法布尔` 之间选后者），
再按书数降序。

> 体检**故意不改数据**。归一化键相同只能证明「写法可能指同一人」，不能证明「一定是同一人」
> （张三/张叁可能是两个人）。合并决策必须人来看，落地机制是别名表。

**Tab 2 · 别名表**

可视化编辑 `config.json`：标准名 + 别名列表 + 备注。支持增删规则、增删别名、
`never_merge` 名单（永不归一的词）。右侧有「归一化预览」输入框——输入一个作者名，
实时显示「清洗后 → 算键 → 查表命中 → 最终结果」，调规则时不用真导一本书来试。

#### 新增：作者锁图标

管理端「书籍列表」的作者列，已锁定的书后面显示一个小锁图标：

* **点锁 = 解锁**（调 `PUT /api/admin/book/<id>/author_lock`）
* 打开作者编辑框时，底部有「保存后锁定作者」勾选框，默认跟随当前锁定状态
* 改完作者点保存，按勾选状态自动落锁/解锁
* **批量编辑不动锁**（避免一次改一批书时把大量书误锁）

#### 新增接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/admin/author_norm/scan` | 体检报告（只读） |
| GET | `/api/admin/author_norm/alias` | 读别名表 |
| POST | `/api/admin/author_norm/alias` | 存别名表 |
| POST | `/api/admin/author_norm/test` | 归一化预览 |
| PUT | `/api/admin/book/<id>/author_lock` | 单本开锁/落锁 |

全部 `@is_admin` 保护。

### 打包 bug：部署包带进了运行时数据目录（`cache/` `sync/`）

**这是 4.6.0-9 首次打包时的失误，已在重出的包里修好。** 记在这里，避免下次再犯。

| 项 | 内容 |
|---|---|
| **现象** | `deploy.sh` 第 6 步「源码目录污染自检」报 `!! 源码目录出现数据类目录: sync cache`，中止部署 |
| **根因** | 基准包 `audiobook-deploy-4.6.0-7/8.tar.gz` 里就带着 `cache/`（52 张缩略图）和 `sync/1/reading.json`。`merge` 脚本解压基准包再重打包，原样继承了下来。**从 `-7` 起每个包都有** |
| **为什么没早发现** | 合并脚本只清了 `.git` / `__pycache__` / `*.pyc`，**从没检查过数据类目录** |
| **危害** | ① 污染新源码目录，部署中止；② `sync/1/reading.json` 是**旧快照**（`cached_through: 2026-10-29`），解压会盖掉现役文件，**阅读进度回退** |
| **修法** | `merge-4.6.0-9.sh` 增加「剔除运行时数据目录」步骤，移除 `cache/` `sync/` `books/` `audio/`，并在重打包后**复检**，残留则中止 |

> **⚠️ `calibre/` 不能一起删。** 它看着像书库数据，其实是 35 条**源码**路径
> （`calibre/7.6/calibre/*.py` 补丁 + `calibre/plugins/cbz_meta/` 等自定义插件），
> 删了镜像构建直接失败。真正的地点数据在 `/volume1/docker/audiobook-data/books`。
>
> 第一版修复时我错把它写进了剔除列表，实测后撤掉了。脚本里留了注释挡住这个坑。

**上游也没做对**：`.gitignore` 没忽略 `sync/` `cache/`，`.dockerignore` 只排除了
`__pycache__` 和各类 `.xxx_cache`，**没排除根目录的 `cache/`**。所以这是上游的疏漏，
不只是我们的打包问题。

#### 根治：从忽略文件层面堵住

只清部署包是治标——每次 `git add .` 或 `docker build` 还会把数据带进去。这次改了根因：

| 文件 | 补充 | 作用 |
|---|---|---|
| `.gitignore` | `cache/` `sync/` | 运行时生成的缩略图与阅读进度快照不再入库 |
| `.dockerignore` | `cache` `sync` `books` `audio` | 不进构建上下文，layer 不再被几百张图拖慢 |

同时执行了 `git rm -r --cached cache sync`，把**已经跟踪**的 51 个运行时文件移出索引
（磁盘文件保留，不影响运行）。

#### 顺手修掉一个会让构建失败的历史损坏

整理时发现仓库里有 8 个 `.vue` 被早期的一次性脚本 `fix-template-key.py` **改坏了**——

```html
<!-- 坏的：:key 粘进了标签名，这是非法标签 -->
<div:key="'w-' + f.key" :id="'f-' + f.key">

<!-- 对的 -->
<div :key="'w-' + f.key" :id="'f-' + f.key">
```

受影响文件：`settings.vue` / `BookCards.vue` / `BookListAddBooksDialog.vue` /
`FolderEditor.vue` / `ServerFileBrowser.vue` / `folder.vue` / `login.vue` / `tag.vue`。

这种写法 **ESLint 报错、`nuxt build` 直接失败**，但因为一直是从源码树打包、
没走过仓库这条路，所以没暴露。现在已全部改回正确写法，并加了扫描复检（0 处残留）。
那个 `fix-template-key.py` 也一并删了——它会制造问题，不是解决问题。

### 文档与仓库整理（归一）

工作区积累了大量历史产物，`ls` 一眼看不完。这次清掉 20 个文件，**从 30 个减到 10 个**：

| 删除 | 理由 |
|---|---|
| `merge-4.6.0-4.sh` ~ `-8.sh`（5 个） | 被 `-9` 完全取代，校验清单只增不减 |
| `merge-patch2.sh`、`merge-patch3.sh` | 更早期的打包脚本 |
| `fix-eslint-final.py`、`fix-template-key.py` | 一次性脚本，后者还会改坏文件 |
| `UPSTREAM_DIFF_4.6.0.md` | 一次性对照报告 |
| `UPSTREAM_UPGRADE.md` | 与 `START_HERE.md` 第三章重复 |
| `如何执行.md` | 与 `NAS操作手册.md` **重复 90%**（同样 0→6 步） |
| `audiobook-scripts.tar.gz` | 旧脚本包 |
| `audiobook-patch-4.6.0-1` ~ `-8.tar.gz`（8 个） | 历史补丁包 |
| `audiobook-4.6.0-8-full.tar.gz` | 旧 full 包 |
| `changed-files/`、`dist/`、`v9/changed-files-README.md`、`__pycache__/` | 打包残留 |

**留下的 10 个**，每个都有不可替代的用途：

| 文件 | 用途 |
|---|---|
| `audiobook-deploy-4.6.0-9.tar.gz` | 部署包 |
| `audiobook-patch-4.6.0-9.tar.gz` | 补丁包 |
| `audiobook-4.6.0-9-full.tar.gz` | 完整源码包 |
| `merge-4.6.0-9.sh` | 本轮合并脚本 |
| `protect-custom.sh` | 保护 BOOK_NAV 与三语文案 |
| `upgrade-upstream.sh` | 跟随上游升级 |
| `START_HERE.md` | 操作总纲（升级/改代码/Gitee/回退） |
| `CHANGELOG.md` | 本文件 |
| `NAS操作手册.md` | 本次升级逐步操作 |
| `设计稿-4.6.0-9-作者归一化.md` | 归一化设计依据 |

> 归并原则：**同一个问题只留一份文档**。`START_HERE.md` 是总纲，遇到具体问题往下翻；
> 逐步操作看 `NAS操作手册.md`；`如何执行.md` 与之重复，删。

### 追加：繁体 epub 打开慢 — 坏字体剥离（4.6.0-9 第三批，v9 包）

> 完整排查与测试记录见 `docs/archive/坏字体修复-4.6.0-9.md`（归档，不随包下发）。

**问题**：一本 3.11MB 的繁体 epub 打开要 50-60 秒，console 报
`OTS parsing error: invalid sfntVersion: 1179602516`（= ASCII `FONT`）。
calibre 从 PDF 转 epub 时把带子集加密的字体原样搬进包里，这种以 `FONT`
魔数开头的伪字体不是合法 sfnt，浏览器一律拒绝加载；数据本体是加密的，
**无法还原，只能删**。实测该书 4 个坏字体占全书体积 **52.4%**。

**修复（三件套，共用 `webserver/services/epub_font_fix.py`）**：

| 链路 | 文件 | 时机 |
|---|---|---|
| B 新书转换 | `services/converter.py` + `batch_convert.py` | 转换出包后就地清理 |
| A 旧书下载 | `handlers/book.py`（`epub_lite_path` + 负缓存） | 首次下载生成精简副本，缓存在 `CACHE_DIR/epub-lite/` |
| C 存量清扫 | `tools/fix_broken_fonts.py`（命令行） | dry-run / --apply / -r / --json |

另有阅读器侧兜底（`static_files.py`：坏字体 404 + no-store，CSS 动态剥离坏 `@font-face`）。

**效果**：样本 3.11MB → 1.65MB（省 46.9%），正文逐字一致；
用户实测打开从 50-60 秒降到 **1.15 秒**（`[open-perf] total=1155ms`）。

**踩坑记录**：`mkstemp` 产生的 0600 权限会经 `shutil.move` 带进书库导致
calibre/nginx 读不到——替换前必须恢复原文件的 mode/uid/gid/mtime。

**部署**：用 **v10 包** `audiobook-deploy-4.6.0-9-v10.tar.gz`
（md5 `111f9a72b72cb6ad617e94f2e75da385`）。v9 及更早缺这批改动。
白名单 `build/patch-files-v3.txt` 已补 4 条。

### 追加：阅读器统计库 upsertBook 报错修复（4.6.0-9 第四批，v10 包）

**症状**：云端书每次进度推送报
`[stats] failed to persist reading events: Cannot read properties of undefined (reading 'id')`。

**根因**：`StatisticsDb.upsertBook` 的 INSERT 分支末尾
`(await this.db.select("SELECT id FROM book WHERE md5 = ? LIMIT 1",...))[0].id`
—— 书首次入库时写后立即读查不到行，`[0]` 为 undefined 直接抛错。
已入库的书走 UPDATE 分支（复用先查到的 id）不出错，所以只有新书一直报。
UPDATE 分支不涉及写后读，症状与之吻合。

**修复**（myreader-dist 为构建产物，压缩 JS 直改；同一类被复制进 3 个
chunk、caller 副本 2 处，全部修补，`node --check` 全过）：

- 尾部改为重试读（间隔 40ms × 3 次）→ `r?.id ?? null`
- caller 拿到 null 直接跳过后续 `insertPageEvent` / `recomputeBookTotals`

若根因是写后读可见性竞态 → 重试后统计恢复正常；若写永不生效 →
安静跳过（效果与修复前等价但不再刷错误日志）。不影响阅读与进度同步。

**部署**：用 **v10 包**（相对 v9 只改 myreader-dist 4 个 chunk）：
`audiobook-deploy-4.6.0-9-v10.tar.gz`，md5 `111f9a72b72cb6ad617e94f2e75da385`。

---

## 4.6.0-8（待发布）

### 修复 Bug

| Bug | 严重度 | 表现 | 修复 |
|---|---|---|---|
| **管理员被自己的读者组拦住** | **高** | 用 admin 登录后打开任意书籍详情页，四个按钮全灰（置灰不可点）；书架、分类、标签也少一截 | `is_book_visible()` 漏了 `is_admin()` 豁免——分类列表那边（`book.py::_filter_categories_by_reading_range`）一直有，判定入口这里没有，于是管理员和普通组员走同一套限制。补上后管理员永远全可见 |
| 标签列表同样漏豁免 | 中 | 管理员侧边栏标签数量比实际少 | `base.py::_filter_tags` 与 `meta.py::_filter_tags` 两处独立实现，都只读 `read_limit`，一并补管理员豁免 |
| WebDAV 挂载对管理员限流 | 低 | 管理员用 WebDAV 挂载时只能看到组内那几本 | `dav_provider.py::_get_user_reading_range` 新增 `admin` 判定，返回"不受限" |
| **Podcast 分类页 / 标签页恒 404** | **高** | `/podcast/category/绘本`、`/podcast/tag/少儿` 一律 404，首页菜单点进去全挂 | 两处调用漏传 `user`，provider 把「没传 user」当成「未登录」直接返回空 dict。补上 `self.current_user` |
| **Podcast 分类过滤直接把 dict 变 list** | **高** | 只要用户受限且点分类页，`'list' object has no attribute 'keys'`，500 | `categories = [c for c in categories …]` 丢掉了值和类型，改为按 key 重建 dict：`{c: v for c, v in …}`。`get_tags` 同病 |
| **Podcast 单书订阅源无权限校验** | **高** | 知道 book_id 就能拼 `/podcast/book/<id>` 拿到整本音频订阅，读者组形同虚设 | 两个入口（匿名 + token）都补 `filter_book_ids` 校验，不在范围内一律 404（不用 403，避免被拿来枚举书目） |
| `/podcast/all` 不按用户过滤 | 中 | 全库有声书订阅源对任何登录用户都是全量 | 改为 `filter_book_ids(get_all_audiobook_ids(), current_user)`，未登录返回空 |
| Podcast 分类/标签/作者只读用户自身设置，不认读者组 | 中 | 用户自己的 `read_limit` 为 0 但在「儿童组」里，Podcast 首页照样列出全部目录 | 统一走 `ReaderGroupService.effective_limits()`，与网页端同一套口径；管理员豁免一并生效 |

> 根因是同一件事在 5 处各写了一遍判定（网页 / 标签两处 / WebDAV / Podcast），补一处就会漏四处。
> 这次全部统一为：**未登录 → 空条件书；管理员 → 全放行；其余 → 走生效限制。**
>
> Podcast 那套更彻底——它自带一份"读 user.read_limit"的实现，既不看读者组、
> 也没有管理员豁免，分类页还因为漏传 user 而永久 404。等于读者组管不到播客，
> 而管理员反而被播客拦住。这次让 Podcast 直接复用 `ReaderGroupService`，
> 以后调权限规则只需改一处。

### 新增功能

| 功能 | 文件 | 说明 |
|---|---|---|
| 详情页有声书弹窗加进度记忆 | `app/src/components/AudioListDialog.vue` | 试听中途关掉弹窗，重新打开自动回到上次位置，章节行右侧显示「上次听到 12:34」 |
| 弹窗内进度条 | 同上 | `v-slider` 可拖动定位，下方显示 `当前 / 总长`；原来只能听不能拖 |

实现要点：

- 键名 `audiobook_preview_<用户ID>_<书ID>_<章节url哈希>`，**按章节隔离**——不同章节时长差异大，按书存一个进度会出现「听第 3 章，点第 1 章却从第 3 章位置开始」。
- 恢复时机放在 `canplay` 且 `duration` 已有值之后，避开 HTMLAudio 元数据刷新把 `currentTime` 打回 0 的坑。
- 听完（距结尾 3 秒内）自动清 key，下次从头；`pagehide` 与 `beforeDestroy` 双保险各存一次（iOS Safari 不触发 `beforeunload`）。
- 与正式播放器（`/audio/:id`）的 `audiobook_progress_*` **互不干扰**：那套记的是「音轨索引 + 轨内偏移」（一本多轨），弹窗这套记的是「单文件秒数」。

### 界面调整

| 调整 | 说明 |
|---|---|
| **有声书导入挪进「导入与存储 · 上传」** | 原来单独挂在「阅读与浏览」下，跟它实际干的事（决定音频遇上同名电子书时是挂靠还是新建）对不上。现在紧跟「忽略根据书名和作者的同书检查」——两个开关管的是同一件事，挨着放才看得懂 |
| **「读者组分级权限」移到「默认权限与配额」下方** | 原来藏在「访客与公开访问」后面，滚半天找不到。现在紧跟默认配额，进去第一眼就是「启用阅读范围控制」这个总开关 |
| 总开关改名并加说明 | `ALLOW_READ_RANGE_SETTING` 的标签从「允许设置阅读范围」改为「启用阅读范围控制（总开关）」，并补一句 tips：关闭时所有读者组规则一律不生效，所有人按公开访问权限看全库 |

> 关于「这个开关能不能和用户组合并」——**不能合并，它俩是两层**：
> `READER_GROUPS` 定义「哪些书给谁看」，`ALLOW_READ_RANGE_SETTING` 是「这套机制要不要启用」。
> 合并掉开关会有一个说不清的状态：想让所有组都失效，就得把组一个个删掉，
> 但用户身上还留着 `reader_group` 引用，下次再打开就变成「组不存在 → 一本书都读不到」。
> 保留开关，关掉时是干净的「全员放开」，随时能开回来。界面上按上面那样挪位置，就不容易被忽略。

### 修复 Bug（续）

| Bug | 严重度 | 表现 | 修复 |
|---|---|---|---|
| **`settings.vue` 有 5 处 `<template v-for>` 的 `:key` 写错位置** | 中 | Vue2 里 `<template v-for="x in y" :key="...">` 是无效写法——编译器会**直接丢弃这个 key** 并报 `cannot be keyed`，列表渲染退化为「按索引复用」，出现勾选串行、输入框内容跟着跑 | 5 处全部改为把 key 放在真实子元素上 |

> **更正一处此前的判断**：早先我说「全仓 16 处错误、涉及 12 个 vue」，那是批量 grep 的误判。
> 逐文件核对上游原文后确认：**只有 `admin/settings.vue` 一个文件真有问题（5 处）**，
> 其余 10 个 vue（`AppHeader`/`BookCards`/`FolderEditor`/`ServerFileBrowser`/`folder`/`login`/`tag` 等）
> 上游写的本来就是对的——只是把 `:key` 换行写在下一行，或者属性顺序和我们不同，语法完全正确。
> 那 10 个文件已**全部还原为上游原版**，不进补丁（放进去只会增加合并冲突面）。
>
> 批量替换过程中还误伤出两类问题，都已修复并加了自动检查：
> - **11 处标签名粘连**：`<v-chip:key=` 少了空格，会被解析成名为 `v-chip:key` 的标签。
>   Vue 编译器**不报错**（HTML 解析器容忍），但浏览器里这个标签渲染不出来。
> - **1 处注释被污染**：`:key="'w-' + grp.key"` 被塞进了 `<!-- 注释 -->` 里，同时那个 `div` 丢了 `:key`。
>
> 教训：`<template v-for :key>` 这类批量替换没法靠「看起来规范」判断对错，
> 只能拿上游原文逐文件比对，或者用编译器实测。这次两样都补上了。

### 补丁包

`audiobook-patch-4.6.0-8.tar.gz`（16 个文件：5 个后端 py + 6 个 vue + 3 个 locale + 2 个脚本）
**含前端改动，需要重新构建镜像**（约 4 分钟）。

其中 `folder.vue` / `FolderEditor.vue` / `ServerFileBrowser.vue` 三个是**上游原版逐字节一致**的，
进包的原因见下一节——`-7` 基准包里这三个文件是旧写法，不覆盖就构建不过。

改动文件的实际内容见 `changed-files/` 目录（与项目同结构），逐条说明见 `changed-files/README.md`。

### 修复：Docker 构建卡在 `vue/valid-v-for`

| 项 | 内容 |
|---|---|
| 表现 | `docker compose build` 到 `[mybooks builder 8/8] RUN npm run build-spa` 失败 |
| 报错 | `FolderEditor.vue 6:17` / `ServerFileBrowser.vue 23:17` / `folder.vue 10:11`，均为 `Custom elements in iteration require 'v-bind:key' directives  vue/valid-v-for` |
| 直接原因 | `build-spa` = `eslint --ext .js,.vue src && nuxt build --spa`，`vue/valid-v-for` 是 error，`eslint` 返回非 0，`nuxt build` 根本没执行 |
| 根本原因 | `-7` 基准包里这三个文件是「`<template v-for :key>` + 子元素无 key」的历史遗留。Vue2 编译会把 template 上的 key 丢掉，移到子元素后子元素仍缺 key，于是规则报错 |

上游 4.6.0 这三个文件本身是对的（每个子元素各带 `:key`）。所以修法是**用上游原版覆盖**，
把 key 逐个放回 `<v-icon>` / `<v-chip>` / `<v-text-field>` / `<span>` 上。

> 澄清一个容易搞错的点：`vue/valid-v-for` 只要求"该元素有没有 key 属性"，
> **不要求 key 写在属性第一位、也不要求同行**。实测把 `:key` 放在 `:color` 之后跨行写，
> 规则照样通过。所以不需要为了这条规则去调属性顺序。

新增兜底脚本 **`fix-eslint-final.py`**，`merge-4.6.0-8.sh` 现在**无条件**跑一遍（以前只在发现
`template:key` 时才跑）：

| 能力 | 说明 |
|---|---|
| `<template v-for :key>` | key 下移到第一个真实子元素 |
| 子元素缺 key | 自动补 `:key`，索引变量从最近的外层 `template v-for` 取（`(item, idx)` → `idx`） |
| `<v-chip:key=` 粘连 | 补空格 |
| 补不了的 | 打印文件+行号，退出码 1，**不让有问题的包进入构建** |

打包前后各查一次：注入前查基准包、打包后再查成品。任一处残留就中止，不出包。

实测：
- 模拟 `-7` 基准包注入 16 处错误 → 全部修正 → **118 个 .vue 的 ESLint 0 错误、模板编译 0 错误**
- 用真实 `-7` 基准包端到端跑 `merge-4.6.0-8.sh` → 出包 95MB，成品 ESLint 0 错误
- 幂等：对已修好的源码再跑一次，文件零改动

### 脚本：保护 BOOK_NAV 与三语文案

新增 `protect-custom.sh`，三动作 `save` / `apply` / `check`，已接入两条升级链路。

**为什么需要**：上游升级时 `webserver/settings.py` 和 `app/locales/*.json` 会被整段替换，
而这两处恰好是我们改动最集中的地方——`BOOK_NAV` 上游 9 组、我们 13 组，被覆盖后分类导航直接变回上游版；
文案被覆盖后，界面会显示 `settings.reader_group_strict` 这样的原始键名。**不报错，只是功能静默消失**，
最难发现。

| 动作 | 时机 | 行为 |
|---|---|---|
| `save` | 合并前 | `BOOK_NAV` 整段 + 3 份 locale → `/tmp/custom-snap` |
| `apply` | 合并后 | `BOOK_NAV` 整段替换回去；locale 按 key 递归合并（我们的键补回，上游新增键保留） |
| `check` | 打包前 | `BOOK_NAV` 少于 13 组报错；文案键逐一比对快照，缺哪个报哪个 |

设计取舍：
- `BOOK_NAV` **整段替换**而不是逐行 merge——上游改这段时是「重排分类」，逐行 merge 只会产出一堆无意义冲突。
- locale **按 key 合并**——上游可能新增键，我们只负责把自己的补回去。
- `check` 有快照就按快照逐键比对（不漏任何自定义键），没快照退回 6 个关键键兜底。

接入点：
- `upgrade-upstream.sh`：步骤 3 合并前 `save`；冲突解决后 `3.2 apply + check + 提示 commit`；步骤 4 打包前再 `check` 一次。
- `merge-4.6.0-N.sh`：注入补丁后 `check`，不通过直接中止（不出包）。

实测（用真实源码走完整链路）：
- 正常：13 组 / 2457 个文案键，通过
- 模拟上游覆盖：准确报出「BOOK_NAV 只有 9 组」+ 缺失的 4 个键，退出码 1，未出包
- `apply` 后：4 个文件与原始源码**逐字节一致**
- 上游新增键场景：新键保留、我们的键回归，双向都对

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

## 附：旧编号时期发布说明（v4.7.1 ~ v4.8.0）

> 这段内容原本堆在 `README.md` 里。由于 `README` 应承担"项目说明"职责，
> 发布说明统一迁到这里留存。旧编号 `v4.8.2` 对应新编号 `4.6.0-1`。
> 下面几条按当时写法保留，未做改写。

## v4.8.0 音频转写可用 + 读者组易用性 + 有声书挂靠 + 内嵌阅读器

**内嵌阅读器 MyReader（修 `/readerx` 502）**

* 之前 `/readerx/open?bookId=…&format=…` 一直 **502 Bad Gateway**：`myreader-dist/` 里
  只有 `.keep` 占位，容器里 `/var/www/myreader/app/server.js` 不存在 → supervisor 起不来 →
  9100 不监听 → nginx upstream 拒绝连接。**现在源码包内直接附带构建好的产物**
  （92MB / 2605 文件），开箱即用。
* MyReader 的 GitHub Release 里只有 `.deb` / `.dmg` / `.apk` / `.exe` 这些桌面和移动安装包，
  **没有**容器可用的 web 产物，所以是从 `PoxenStudio/MyReader` tag `0.9.1` 源码构建的
  （`pnpm build-docker-dist`），构建步骤见 `INSTALL_GUIDE.md` 第八节。
* 修掉一个很隐蔽的坑：`.dockerignore` 里的 `**/node_modules`（给前端源码用的）会把
  `myreader-dist` 下**三层**产物依赖一起排掉。其中 `app/.next/node_modules/` 那层被排掉时，
  服务能正常启动、9100 也能监听，但**第一个请求才报** `Cannot find module 'js-md5-<hash>'`。
  已加显式放行，并用真实 `docker build` + 起容器实测过（`/readerx/...` 返 200）。
* 实测数据：`pnpm install --frozen-lockfile` 21.8s，`next build` 35s，产物 92MB。

**音频转写（Whisper）**

* **镜像内置 `faster-whisper`**（构建参数 `WITH_WHISPER=1`，默认开）。不装 torch，约 +250MB，
  比 openai-whisper 快 4 倍以上。不需要就把参数设成 `0`。
* **转写同时产出 `.srt` + `.txt`**：`.srt` 带时间轴，播放页会自动配对同名字幕文件，
  **播放时逐句高亮跟随**；`.txt` 是纯文本全稿，用于搜索/复制/离线阅读。
* **模型下载走 `hf-mirror.com`**（`HF_ENDPOINT`），并关闭 xet 通道（`HF_HUB_DISABLE_XET=1`）——
  国内直连 huggingface.co 基本不通，原实现会卡死。
* **模型缓存在 `/data/models/whisper`**，容器重建不用重下。`TRANSCRIBE_MODEL` /
  `TRANSCRIBE_LANG` / `TRANSCRIBE_KEEP_TXT` 可在设置里调。
* 锁定 `av<16`：faster-whisper 1.2.x 仍调 `av.open(metadata_errors=...)`，av 16+ 删了该参数会
  `TypeError`。运行期也加了版本守卫，报错信息直接给出修复命令。

**读者组**

* **分类/标签从「手打文本框」改成下拉多选**（`v-combobox multiple`）：候选值来自系统里
  真实存在的分类与标签（新增接口 `/api/admin/reader_groups/options`），点选即可，
  仍允许自由输入。以前打错一个字符就静默失效（白名单看不到任何书、黑名单什么都没屏蔽）。
* 组列表里的分类/标签以 chips 呈现，重复值自动去重。

**有声书挂靠（修上游 bug）**

* **后加音频不再变成另一本书**。电子书在 `library/`、有声书在 `audios/<book_id>/`，两套目录。
  上游导入音频时只看「这本书有没有 `audios/<id>/`」，没有就新建一本书——于是先导 epub、
  后加音频，书库里就多出一条同名记录。
* 现在发现**同名书籍已存在**就复用它的 `book_id`（挑选优先级：`library/` 里真有格式文件的那本 →
  都没有则取最早的 id），音频仍放 `audios/<book_id>/`。一条记录、一个封面、一套元数据。
* 新增设置项 **`AUDIO_LINK_TO_EXISTING_BOOK`**（默认开），后台「系统设置 → 阅读与浏览 →
  有声书导入」可关；关掉恢复旧行为。扫描结果多一项「已挂靠」计数，日志打
  `[AUDIO_IMPORT] 同名书籍已存在(book_id=N)，音频将挂到该书而非新建`。
* 注意：本改动只影响之后的导入，**历史重复记录用内置的「重复书清理」一次合并**（见下）。

**同名重复书清理（迁移工具）**

* 后台「管理 → 重复书清理」（`/toolbox/book_dedup`）：先**扫描预览**（只读），
  看清每组的"保留/删除"关系后再一键合并。不用连 SSH、不用一条条手点。
* 合并时自动完成：音频目录 `audios/<重复id>/` → `audios/<保留id>/`（封面、`.srt` 字幕
  一起搬，不覆盖目标已有文件）→ 阅读进度/收藏/书单/评论/分享**改指**到保留书 →
  删掉重复记录 → 修正 `ScanFile` 指向。
* **三条安全线**：① 方向不明确的组（两本都有电子书、都没有电子书、同名超 8 本）
  只报告不改动；② 执行前用 `sqlite3.backup()` 在线备份用户库到 `data/backup/`；
  ③ 删 calibre 记录前再校验一次"确实没有电子书格式"，有就拒删。
* 书单关联的冗余行被删时会同步扣减 `book_count`，避免书单显示数量虚高；
  共读同步记录（`book_records`，身份是 `book_hash`）删而不改指，否则 hash 与 id 会串书。

**工程**

* 新增 `PORTING_NOTES.md`：全部改动清单、上游更新合并指引、冲突解决速查、隐性耦合点。
* 测试：`test_transcribe_service.py` 24 项（双后端 + SRT 格式 + 边界）、
  `test_reader_group.py` 14 项（含 options 接口容错）、`test_audio_link_existing.py` 17 项
  （开关解析 / 挂靠挑选 / 状态计数）、`test_book_dedup.py` 43 项（含真实 SQLite 库的
  关联数据迁移验证），合计 98 项全通过。

### v4.7.4 修复

* **`COPY myreader-dist*` 报 "no source files were specified"**：Docker 的 COPY 通配符零匹配会直接报错（不是静默跳过）。
  改为内置 `myreader-dist/.keep` 占位文件 + `COPY myreader-dist/`，始终有源可拷。
  自 v4.8.0 起源码包已附带真实产物，这个问题不会再出现。


### v4.7.3 修复与加速

**修复（都是会让构建直接失败/异常的硬问题）**

* **`third-party/*` 是空的 git submodule**：`COPY` 空目录会失败。改为「有就拷、空则警告并继续」。
  * `foliate-js` 缺失 → 仅微信读书批注导入(CFI 生成)不可用，其他功能不受影响。
  * `edge-tts` 缺失 → 自动回退 PyPI 官方版。注意官方版 `list_voices` 不支持 `proxy` 参数，
    代理环境下听书可能异常；需要完整功能请 `git submodule update --init third-party/edge-tts`。

**加速**

* `.dockerignore` 重写：排除 `node_modules`/`.nuxt`/`dist`/`__pycache__`/`.DS_Store` 等，
  以及前端专用的大体积库（`third-party/epubreader-js` 35M 等），构建上下文更小、传输更快。
* `docker-compose.yml` 加 `target: production`，跳过 test 阶段（省一次完整 pip install）。
* 新增 **`make fast-build` / `make fast-up`**：BuildKit + 本地层缓存（`.buildcache`），
  改代码后重建通常 1 分钟内完成；`make clean-cache` 清缓存。
* `cfi_gen` 的 `npm ci` 补上国内源（原来没走镜像，国内很慢）。

**关于 `mybooks_base`（慢的主因）**

基础镜像约 **1.5 GB**（Ubuntu 24.04 + Calibre 7.6 + FFmpeg + Node），首次构建必须拉取。
之后会命中本地缓存。国内建议给 Docker 配 `registry-mirrors`（`docker.1ms.run`、
`docker.m.daocloud.io`、`hub.rat.dev` 实测均可用）。

### v4.7.2 修复（Node 版本过低）

* **builder 阶段基础镜像 `node:16-alpine` → `node:20-alpine`**。Nuxt 2 的 CLI 链里 `@clack/core` 用了
  `node:util` 的 `styleText`（Node ≥ 20.12 才有），Node 16 下 `import` 阶段直接失败：
  ```
  import { styleText } from 'node:util';
  SyntaxError: The requested module 'node:util' does not provide an export named 'styleText'
    at file:///build/node_modules/@nuxt/cli/bin/nuxi.mjs:78:21
  ```
  注意 ESLint 那步是通过的（`0 errors`），报错发生在真正开始构建时，很容易误判。
* Dockerfile 里加了 Node 主版本断言，低于 20 时构建直接给出明确提示，而不是含糊的模块错误。
* 实测：Node 16.20.2 的 `util.styleText === undefined`；Node 20.19.0 下 `npm ci`（5 秒）+
  `npm run build-spa`（36 秒 `Compiled successfully`）全部通过。

### v4.7.1 修复（构建问题）

* **`app/package.json` 的 `nuxt` 版本写错**：原为 `^4.6.2`（会解析到 Nuxt 4 / Vue 3），本项目是 Nuxt 2 + Vue 2，导致
  `npm install` 拉一整套 Nuxt 4 依赖后编译报 `<template v-for> key should be placed on the <template> tag`。
  已改为 `^2.18.1`，与 `package-lock.json` 里锁定的 2.18.1 一致。
* **Dockerfile 改用 `npm ci`**：严格按 lockfile 安装，杜绝 `^` 范围重新解析出不兼容大版本。
* **20 处 `<template v-for>` 的 `:key` 统一移到 `<template>` 标签上**：Vue 3 编译器强制此规则，
  这样即便将来依赖解析异常也不会因此直接构建失败。
* **新增 `app/.npmrc`**（npmmirror 源），`docker-compose.yml` 默认传 `BUILD_COUNTRY: CN`，构建更快。
* 实测结果：`npm ci` 5 秒装完 1448 个包 → `npm run build-spa` 36 秒 `Compiled successfully`，ESLint 0 error。

### v4.7 新增（移植自 audiobook 项目）

* **读者组分级权限**：管理员定义读者组（白名单/黑名单 + 分类/标签），用户划入组即可批量限制可读书目，不用逐个设置。
  API：`GET/POST /api/admin/reader_groups`、`POST /api/admin/reader_groups/delete`、`POST /api/admin/reader_groups/assign`（管理员）。
  生效规则：用户自己显式设置过阅读范围就用自己；否则回退组配置。组定义持久化在站点设置（`READER_GROUPS`），用户归属存在用户 `extra.reader_group`，零数据库迁移。
* **音频转写文稿（可选）**：Whisper 把有声书音频转成可阅读的 .txt 文稿。
  服务器需 `pip install -r requirements-optional.txt`（含 openai-whisper/torch，体积大故不进主依赖）；
  未安装时 `GET /api/admin/transcribe/available` 返回 `{"available": false}`，前端可隐藏入口。
  API：`POST /api/admin/transcribe/run|cancel`、`GET /api/admin/transcribe/status`。转写进度接入既有后台任务体系。
  路径支持文件或目录（目录自动递归收集音频），前端带服务器目录浏览器（复用服务端目录浏览，范围限 /data）。

> Windows 安装器（exe）自 v4.6 起已彻底移除，Docker 是唯一官方部署方式，见下节。



---

## 附：升级历史速查


| 版本 | 主要内容 | 备注 |
|---|---|---|
| 4.6.0-8 | **修管理员被读者组拦住（详情页按钮全灰）**；标签/分类/WebDAV/Podcast 五处口径统一；**修 Podcast 分类标签页 404 与单书订阅越权**；有声书弹窗加进度记忆 | 含 -7 全部内容，需重建镜像 |
| 4.6.0-7 | **修悬空组引用静默放行**；悬空引用告警+自动修复 | 含 4.6.0-6 全部内容，需重建镜像 |
| 4.6.0-6 | 修白名单空条件放行全库；严格模式开关；权限排障接口 | 未独立发布，并入 -7 |
| 4.6.0-5 | upgrade.sh/deploy.sh 启动验证改轮询；修容器残留导致起不来 | 纯脚本包，不重建镜像 |
| 4.6.0-4 | Mimo-TTS 搜索按钮 + 使用说明；7 个工具页搜索图标可点；读者组 4 处修复 | 已上线 |
| 4.6.0-3 | 设置页保存优化 | |
| 4.6.0-2 | 读者组 KeyError 修复 | 未单独出成品包 |
| 4.6.0-1 | 全部定制基线（原 v4.8.2/v4.8.3） | |

### 追记（4.6.0-15 发布后热修，914e11d）

**播放请求 500（`'AudioFile' object has no attribute 'db'`）**：-14 字幕热修把
`scan.py` 里的 `self.db` 习惯带进了 `audio.py`/`podcast.py`——BaseHandler 上没有
这个属性（只有 `self.calibre_db`）。症状极具迷惑性：播放列表能显示（走扫描）、
详情页计数正常，**一点播放就 500**。全部改用 `self.calibre_db`。
