# 上游可采纳的修复建议

**给上游的说明**：下表是我们在 `PoxenStudio/mybooks` 4.6.0 基础上的**非新增文件**改动——
全部是对上游已有文件的修改，属于「上游本身的 bug / 缺失」，不涉及我们的定制功能。

每个问题都给了「文件 + 关键词」，可以直接搜。**没有附 diff/patch 文件**——
我们的文件里混着读者组、作者锁定等定制逻辑，反向生成的补丁夹带这些内容，
拿去反而添乱。下面每条的改法都写到了能照着改的程度。

按建议优先级排序，P0 是我们已经在生产环境被咬过的。

| 优先级 | 文件 | 一句话 |
|---|---|---|
| P0 | `handlers/static_files.py` | epub 插图撕裂 + 翻页慢，三个根因叠在一个函数里 |
| P0 | `handlers/admin.py`、`main.py` | f-string 内嵌同种引号，3.11 直接 SyntaxError |
| P0 | `handlers/podcast.py`、`podcast/podcast_provider.py` | 播客订阅源零权限校验，知道 book_id 就能下整本 |
| P1 | `handlers/base.py`、`handlers/meta.py`、`webdav/dav_provider.py` | 管理员被自己的阅读限制拦住，三处漏了三遍 |
| P2 | `services/autofill.py`、`services/ai_fillinfo.py`、`handlers/admin.py` | 长任务无法取消，只能重启容器 |
| P3 | `base/meta_helper.py` | 「插画[美国]某某」「某某 绘」这类作者名漏网 |

---

## P0 — 会在真实环境直接坏掉

### 1. `handlers/static_files.py` — 三成用户级故障都在这一个函数里

| # | 问题 | 症状 | 改法 |
|---|---|---|---|
| 1.1 | **f-string 内嵌同种引号** | 见下方代码，Python 3.11 及更早直接 `SyntaxError` | 见第 2 条 |
| 1.2 | ZIP 条目名 **Unicode 归一化不一致** | macOS 压制的 epub 是 NFD，OPF/浏览器请求 NFC，文件名永远对不上 → **插图全部 404 裂图**，正文正常 | 匹配前对两边都做 NFC/NFD 归一化 |
| 1.3 | ZIP 条目**缺 UTF-8 标志（0x800）** | 中文 Windows 工具压出的 epub，文件名是 GBK 字节，`zipfile` 按规范误读成 CP437 乱码 → 同上，插图全裂 | 把请求名 `encode("cp437")` 还原原始字节，再依次试 `utf-8/gbk/big5` 解码 |
| 1.4 | **每次请求都重开 zip** | 每张插图 1 次 `ZipFile()` 解析中央目录，一本书几十张图 → 弱网下翻页明显慢（用户实测「翻页要等好几秒」） | 按 `(mtime, size)` 缓存 `ZipFile`，LRU 上限 64 |
| 1.5 | **没有 ETag，图片每次都全量重传** | 已看过的页再翻回来还要重新下插图 | 按 `mtime:size:path` 生成弱 ETag，命中 `If-None-Match` 回 304 |

落地方式：在 `StaticFileHandler` 里新增 `_zip_find()` / `_open_zip()` / `_epub_etag()` 三个辅助方法，替换 `get()` 里那段 12 行的 zip 打开逻辑。涉及文件：`webserver/handlers/static_files.py`，关键词 `if path not in zf.namelist():`（L353、L360）。

### 2. `handlers/admin.py` + `webserver/main.py` — Python 3.11 兼容

上游现在的写法用到了 **PEP 701**（f-string 内嵌同种引号），只有 Python 3.12+ 支持：

```python
# admin.py
book_type_query = f"{"not" if book_type == BOOK_TYPE_EBOOK else ""} {CALIBRE_COLUMN_BOOK_TYPE}:={BOOK_TYPE_PHYSICAL}"
# main.py
logging.info(f"The installed version is {CONF.get("installed_version", "NONE")}, {"" if is_upgrade else "no"} need to ...")
```

`webserver/` 其余代码并没有用 3.12 特性，README 也没声明最低版本。
**建议改写成先取变量再插值**，能把支持范围拉回 3.11，本地开发 / CI / 用户自建镜像都受益。

涉及文件：`webserver/handlers/admin.py`（搜 `book_type_query`，L830）、`webserver/main.py`（搜 `The installed version is`，L436）。

### 3. `podcast/podcast_provider.py` + `handlers/podcast.py` — 播客订阅源**完全没有权限校验**

这是我在移植读者组时发现的：`/podcast/book/<id>` 拿 `book_id` 就直接吐整本音频的订阅源，
**不检查这本书当前用户看不看得见**。知道 id 的人可以绕过一切阅读范围限制把整本书的音频下走。

改法（改动不大，纯加校验）：
- `podcast_provider.py` 新增 `filter_book_ids(ids, user)` / `filter_book_ids` 的可见性判定
- `handlers/podcast.py`：`/podcast/all` 传 `self.current_user`；`/podcast/book/<id>` 先校验，不可见按 **404**（不是 403，避免拿来枚举库里有多少本）

涉及文件：`webserver/podcast/podcast_provider.py`（搜 `def get_all_audiobook_ids`）、`webserver/handlers/podcast.py`（搜 `/podcast/` 路由表）。

---

## P1 — 管理员自己被限制住，表现像「权限系统坏了」

我们踩到的现象：管理员打开书详情页，**四个按钮全灰**、书架缺书。查了半天发现是
「阅读范围限制」的几处实现都忘了给管理员豁免——而分类列表那边其实是有豁免的，所以前后表现不一致。

| 文件 | 漏掉的位置 | 改法 |
|---|---|---|
| `handlers/base.py` | `is_book_in_reading_range()` 开头 | 加 `if self.is_admin(): return True` |
| `handlers/meta.py` | `tag_list()` | 加 `if self.current_user.is_admin(): return tag_list` |
| `webdav/dav_provider.py` | `_get_limits()` | 管理员直接返回 `0, set(), set()` |

涉及文件：`webserver/handlers/base.py`（搜 `def is_book_in_reading_range`，L1400）、`webserver/handlers/meta.py`（搜 `def _filter_tags`，L119 附近）、`webserver/webdav/dav_provider.py`（搜 `def _get_user_reading_range`）。

> 顺带一提：这三处是同一个模式漏了三遍，建议上游把「管理员豁免」收成一个
> 共用的 `_limits_of(user)`（我们已经在 `podcast_provider.py` 里这么做了），
> 以后新增入口不容易再漏。

---

## P2 — 长任务没法中断，只能等它跑完

`services/autofill.py`（刮削）和 `services/ai_fillinfo.py`（AI 补全）都是长循环，
**没有任何取消入口**。几千本书的库点错了参数，只能重启容器。

改法很轻：两个 service 各加 `cancel_requested` 标志 + `cancel()` 方法，
在循环的每个主要断点检查一次；`handlers/admin.py` 两个接口接受 `{"cancel": true}`。

涉及文件：`webserver/services/autofill.py`（搜 `def auto_fill_all`）、`webserver/services/ai_fillinfo.py`（搜 `def fill_all`，L137）、`webserver/handlers/admin.py`（搜 `req["idlist"]`）。

---

## P3 — 作者名清洗（可选，看你们要不要）

我们在 `base/meta_helper.py` 里补了一类漏网格式：

| 格式 | 例子 | 原正则为什么没拦住 |
|---|---|---|
| 职责词前缀 | `插画[美国]安德鲁·格拉斯`、`绘画 李四` | `_DYNASTY_REGION_PREFIX` 要求方括号在**首位**，职责词挡在前面就够不着 |
| 单字职责后缀 | `张三 绘`、`李四 校` | 后缀集没含 `绘/校/注`，扩了会误伤 `图图→图`，所以**必须要求前面有空格** |

`译者` 刻意**不进**职责词表——它由 `_TRANSLATOR_SUFFIX` 单独处理，
否则「译者：张三」会把译者当成作者。

涉及文件：`webserver/base/meta_helper.py`（搜 `_TRANSLATOR_SUFFIX`，L27；`_DYNASTY_REGION_PREFIX` 同文件）。

---

## 附：不算 bug 但值得看一眼

| 位置 | 现象 |
|---|---|
| `webserver/resources/book/epubjs.html` | `EPUB_VIEWER` 设成非 MyReader 时的回退阅读器模板（`handlers/book.py` L3872：`self.html_page("book/" + book_reader, ...)`）。走 MyReader 时用不到，我们之前整个目录漏带，v10 已补回。上游不用动，列出来只是提醒：**这个文件在发行包里容易被当成无用资源删掉**。 |
| `webserver/epub_to_audio/` | 是个 **git submodule**（`.git` 里是 `gitdir: ../../.git/modules/...`）。如果你们的发行包只打 `git ls-files`，submodule 内容会整个丢失，`webserver/worker/epub2audio_worker.py` 拉起 `main.py` 时永远 FileNotFoundError。我们就栽在这上面。 |
| `webserver/epub_to_audio/requirements.txt` | 里面 pin 了 `gradio==5.33.1` / `gradio_log` / `docker`，但生产只跑命令行 `main.py`。如果照这份表装，gradio 会把基础镜像里的 numpy/pydantic 顶到不兼容版本，连累 calibre。建议拆成 `requirements-cli.txt` 与 `requirements-webui.txt`。 |

---

# 附二：HorkyChen/epub_to_audiobook 这个 fork 的情况

`webserver/epub_to_audio/` 对应的上游不是 `p0n1/epub_to_audiobook` 主干，而是
**`HorkyChen/epub_to_audiobook`**，指向提交 `8ca3bc4`（提交信息
「修改edge-tts引用到poxenstudio/edge-tts项目」，2026-10-13）。

这个 fork 从 `f387291`（主干 merge PR #149）分出来，**自己加了 15 个提交、703 行**，
主干没有这些。其中好几处是 MyBooks 的转音频功能实际依赖的，所以**不能简单换成主干版本**。

## 它比主干多做了什么（MyBooks 依赖的）

| 提交 | 内容 | 我们是否依赖 |
|---|---|---|
| `3816fc9` 支持生成字幕文件 | `main.py --output_srt`、`edge_tts_provider` 收集 `SentenceBoundary`、写 `.srt` | **是**，见下 |
| `957bd36` 按阅读顺序读章节 | 遍历 `book.spine` 而不是 `get_items_of_type(ITEM_DOCUMENT)` | 是（否则章节顺序随文件打包顺序乱） |
| `41b5e45` 单章过大用 toc 兜底 | 只有一个章节且 >100KB 时，按 TOC 锚点切分 | 是（整本单文件的 epub 全靠它） |
| `3ba1d5b` edge_tts 超时控制 | `AUDIO_GENERATION_TIMEOUT = 120` | 是（网络卡死不会永久挂住） |
| `be5d62b` 覆盖已转音频 | `--overwrite` 参数 | 否，**但注意**：默认改成「跳过已存在」 |
| `1fcd887` 日志截断 | `MAX_DEBUG_LOG_CHARS = 100` | 是（不截断会刷出整章正文） |
| `e2361f1` / `fea4f19` 升级 edge-tts | 升到 7.2.8 | 镜像里由 `third-party/edge-tts` 提供 |

字幕链路是硬依赖：`webserver/handlers/audio.py:588` 读 `ENABLE_AUDIO_SUBTITLE`，
一路传到 `epub2audio_worker` 的 `output_srt` 参数，再进 `main.py --output_srt`。
**主干没有这条链**，换过去 SRT 功能直接消失。

## 它落后主干的 7 个提交（值得跟的只有 2 个）

分叉点之后主干走了 7 个提交，对代码有实际影响的两处：

### 1. 双重 MP3 编码 —— 建议跟（我们已合入）

`f11a014 fix(edge-tts): eliminate double MP3 encode; export once at 48 kbps`

**这个问题在 fork 里是真实存在的，会直接损伤听感。** 原来的流程是：

```
每个 chunk → edge 给 48kbps mp3 → 存临时文件 → 合并时都解成 PCM → 再编一次 mp3
```

最后一次 `combined.export(output_file, format="mp3")` **没给 `bitrate`**，
pydub/ffmpeg 落到默认的 **32 kbps**。实测对比（3 段 1 秒音频、24kHz 单声道）：

| 路径 | 输出码率 | 3 秒文件大小 |
|---|---|---|
| fork 原逻辑 | **32000 bps** | 12,429 字节 |
| 单次编码 48k | **48000 bps** | 18,525 字节 |

码率之外还有代际损失：mp3 解码再编码，每合并一层就多一层量化噪声。
听感上就是主干 issue #156 描述的那种「发闷、发尖」。

**已修**：我们把 `f11a014` 的做法合进 `webserver/epub_to_audio/`，同时保留 fork 的字幕逻辑
（`get_audio_segment()` 返回 PCM 段，字幕事件仍按 `elapsed_ticks` 累加偏移）。
现在每个 chunk 只在内存里攒 PCM，最后统一编一次 48kbps。实测结果：

- MP3 码率 48000 bps、24kHz、单声道
- SRT 时间轴随停顿正确累加（1 秒音频 + 0.5 秒停顿 → 下一条从 1.5 秒开始）
- 不再产生 `/tmp/chapter-*` 临时文件

### 2. 纯标点文本过滤 —— 建议跟（我们已合入）

`fd76745 fix: enhance text filtering for Edge TTS`

`parse_text()` 原来只过滤空白片段，**纯标点片段（`，`、`——`、`...`）会漏进去**，
edge-tts 对这类输入返回 `NoAudioReceived`，那一整段直接静音丢字。
中文书里有大量单独的破折号分段、省略号行，**这个在我们这儿是高频触发**。

**已修**：加 `_is_meaningful_text()`，无字母数字则丢弃；单字母（`A`、`B,`）保留。
边界实测 16 种输入全部符合预期。

### 3. 其余 5 个：不用跟

| 提交 | 为什么不跟 |
|---|---|
| `22f2069` Dockerfile 换 `python:3.11-slim-trixie` | 那是它自己镜像的 base；我们的 Dockerfile 从本地 wheel 装，不受影响 |
| `b36236c` / `ee47a4d` / `a24cac9` | 都是 merge 提交，内容已体现在上面两个 |
| `2a7308a` 修测试 | 只是它测试的路径与 `title_mode`，跟运行时代码无关 |

## 另一件事：`epub_to_audio` 自带的那部分没再更新了

`8ca3bc4` 之后 `HorkyChen/epub_to_audiobook` 的 `develop` 分支没有新提交，而 p0n1 主干还在走。
往后这个 fork 的 `edge-tts` 版本会逐渐跟服务端不兼容。

**注意**：这只说明「`epub_to_audio` 这一块」没动，不代表上游停了 ——
`PoxenStudio/mybooks` 本体一直在更新，见下面的**附三**。

**建议**：不要把 `webserver/epub_to_audio/` 当 submodule 挂着，直接把代码 vendored 进仓库
（我们现在就是这么做的），并把这个 fork 独有的 4 个提交整理成 patch 说明，
将来主干若吸收了字幕能力就能整体切回主干。这件事**不用你们做**，
列在这里只是说明我们为什么现在是 vendored 状态而不是 submodule。

---

## 小结：需要你们改的仍然是前面 P0–P3 那些

这一节里的两条修复**我们已经自己打在 vendored 副本上**，不指望上游动。
写出来是因为：如果你们以后升级 `epub_to_audio`，**别直接覆盖回 `8ca3bc4`**，
那会把 48kbps 和标点过滤两处修复又冲掉。

---

# 附三：怎么盯上游 `PoxenStudio/mybooks` 的改动

## 先更正上一版的一个说法

上一节写「这个 fork 已经停了」。**说错了**，准确情况是：

| 分支 | 最新提交 | 日期 | 说明 |
|---|---|---|---|
| `develop` | `8ca3bc4` | 2026-10-13 | **PoxenStudio 自己的开发分支**，我们的 `epub_to_audio` 就取自这里 |
| `main` | `a24cac9` | 2025-08-29 | p0n1 主干，停在 2025-08 |
| `release/v0.8.3` | `fea4f19` | 2026-01-22 | 旧发布分支 |

`8ca3bc4` 之后 `develop` 上确实没有新提交，但**整个 mybooks 主仓库（`PoxenStudio/mybooks`）一天十几个提交**，
只是没再动 `epub_to_audio` 而已。所以「盯着主干」这件事是**可做且该做**的，盯的对象是：

```
https://github.com/PoxenStudio/mybooks  分支 develop
```

而且这不是第三方仓库——**它就是上游本体**（`webserver/` 那套代码的来源）。
`epub_to_audio` 只是它挂的一个 submodule。

## 上游现在在走什么

`develop` 当前 HEAD `2135ad7`（2026-11-01），最近两周的改动方向：

- **AI 伴读**：`AiChatDialog.vue`（591 行）新增、会话样式调整、调用限额处理
- **阅读统计**：按站点时区切天、月界换算、「即将读完」排除已读完
- **必须登录（`REQUIRE_LOGIN`）**：OPDS 下载直链改回 401 挑战、路由中间件、`$ensureSession`
- **Toolbox**：`epub_merge` 拼图封面重做、`epub_fixer` i18n 修复
- **元数据**：无名图书 API 接入、整库批量补齐（`wuming_*` 六个工具）

## 我们跟它的差距

拿 `develop` 的 `app/src` 和我们仓库的 `app/src` 逐文件比（各 155 / 158 个文件）：

| 情况 | 数量 | 例子 |
|---|---|---|
| 上游有、我们没有 | 1 | `AiChatDialog.vue`（591 行，AI 伴读整个功能） |
| 我们有、上游没有 | 4 | `ReaderGroupEditor.vue`、`TranscribePanel.vue`、`toolbox/author_norm.vue`、`toolbox/book_dedup.vue` |
| 两边都有但内容不同 | 17 | `AppHeader.vue`、`BookCards.vue`、`admin/settings.vue`、`toolbox/*.vue` 等 |

这和 `webserver/` 那边是一致的：我们是「上游 4.6.0 + 定制」，上游已经在往前走，
**差距会随时间变大**，不会自己缩小。

## 一个必须先说的坑：上游的 `package.json` 已经不对了

上游 `app/package.json` 声明 `"nuxt": "^4.6.2"`，但：

- `app/package-lock.json` 里锁的还是 **2.18.1**
- `app/pnpm-lock.yaml` 里已经解析成 **4.6.2**
- 其余依赖全是 Vue 2：`vue ^2.6.14`、`vue-i18n ^8`、`vuetify ^2.6.10`、`webpack ^4`
- `nuxt.config.js` 是 Nuxt 2 写法（`head` / `hooks['build:before']` / `dir.static`）
- `plugins/i18n.js` 里写着 `import Vue from 'vue'`

**Nuxt 4 只支持 Vue 3**。这是 dependabot 提交的 PR（`c120663`，10-25 合入），
合的时候没人验过能不能构建。后果：

- 用 `npm ci` 的人还能装上 2.18.1，**构建正常**
- 用 `pnpm install` 的人会装到 4.6.2，**构建大概率直接失败**

我们本地这份是 `^2.18.1`，并且走的是「Dockerfile 直接用 `app/dist` 已有产物」的快路
（`COPY app/dist*`），根本不跑 `npm`，所以**暂时没被影响**。
但这意味着**不能照抄上游的 `package.json`**。

## 怎么盯：`scripts/watch-upstream.py`

光靠人看 GitHub 提交列表是不现实的——一天十几个提交，绝大多数是 dependabot 升依赖。
写了个脚本按「跟我们有没有关系」分类：

```sh
python3 scripts/watch-upstream.py                  # 看最近 30 个提交
python3 scripts/watch-upstream.py --limit 100      # 看更多
python3 scripts/watch-upstream.py --since-baseline # 只看基线之后的增量
python3 scripts/watch-upstream.py --offline        # 网络不通时看上次拉到的
```

输出分三档：

| 档位 | 含义 | 要不要管 |
|---|---|---|
| ⚠ 改了我们也改过的文件 | `TOUCHED` 列表里的文件被上游动了 | **必看**，下次 merge 必然冲突 |
| ● 碰了 `webserver/` 或 `app/src/` | 可能有我们能直接抄的修复 | 扫一眼 |
| ○ 其余 | 依赖升级、文档、其他目录 | 忽略 |

`TOUCHED` 列表是从 `docs/移植改动清单.md` 抄的（23 个上游文件），
那边加了新改动记得同步 `scripts/watch-upstream.py` 顶部。

基线存在 `docs/upstream-baseline.json`，**提交进仓库**，换机器也能接着盯：

```json
{
  "branch": "develop",
  "commit": "2135ad753a72b52aac80c4746d072e0346890a99",
  "date": "2026-11-01 15:12:06 +0800"
}
```

**建议节奏**：每周跑一次 `--since-baseline`，看看增量；有 ⚠ 就评估要不要跟。
确认看完后 `--baseline` 把位置推进到最新。

注意脚本用 `git` 而不是 GitHub API——未认证的 API 每小时只有 60 次，跑几次就废了。
国内直连 github 时不时断（本次就是），断了加 `--offline` 看缓存。

## 跟不跟：分三类处理

| 上游改动 | 建议 | 理由 |
|---|---|---|
| **安全性 / 数据正确性**（如 `REQUIRE_LOGIN` 相关、时区切天） | 跟 | 这类 bug 我们也会踩 |
| **我们已独立修过的**（如 EPUB 修复页 i18n、`epub_merge` 封面） | 不跟，比一下谁的方案好 | 我们已经改过了，重复劳动 |
| **新功能**（AI 伴读、无名图书 API） | 先不跟 | 需求不是我们的，跟了要一并维护前端 |

整体升级（`upgrade-upstream.sh` 按 tag merge）是另一回事，那个脚本已经在了，
走的是「合上游 release tag → 解冲突」。这个脚本盯的是**两次 release 之间的增量**，
免得攒到发版时一次面对几百个提交。

---

# 附四：v4.6.1 已经发了（2026-11-01），该不该跟

## 先搞清楚版本关系

| tag | commit | 时间 | 说明 |
|---|---|---|---|
| `v4.6.0` | `f45f730` | — | **我们这份就是基于它** |
| `v4.6.1` | `cdbe366` | 2026-11-01 15:52 | 新建 tag，**没有 Release 页面**（只有 tag，没写发布说明） |
| `develop` | `2135ad7` | 2026-11-01 15:12 | v4.6.1 的前 12 个提交 |

`v4.6.1` 就是 `develop` 那一天的快照，比 `develop` HEAD 多 12 个提交（favicon、ipv6、样式微调）。
GitHub 上没有 `releases/tag/v4.6.1` 这个页面，所以看不到「官方变更说明」——
只能自己数：**35 个提交、80 个文件、+8683 −7349 行**。

## 跟我们重叠的 9 个文件（升级必冲突）

| 文件 | 改动 | 我们要不要 |
|---|---|---|
| `webserver/services/autofill.py` | +28 −2，加 `cancel_requested` + `cancel()` | **要**，见下 |
| `webserver/services/ai_fillinfo.py` | +25 −7，同上 | **要** |
| `webserver/handlers/admin.py` | +31 −7，两个接口收 `{"cancel": true}`；favicon 支持 png | **要**（取消部分） |
| `webserver/handlers/base.py` | +11 −3，`is_opds_acquisition()`，下载直链并入 401 分支 | 看情况，见下 |
| `webserver/handlers/book.py` | +21 −13，本月统计改用 `site_month_bounds_server_local` | **要** |
| `app/src/pages/admin/settings.vue` | +80 −23，时区选项改 -12~+12 | 看情况 |
| `app/src/components/AppHeader.vue` | +13 −268 | 顺手，主要是删代码 |
| `app/src/components/BookCards.vue` | +81 −81 | 样式微调 |
| `app/src/components/ReadingTimeBackfillDialog.vue` | +8 −1 | 小修 |

## 其中最重要的一条：**长任务取消，上游做了，跟我建议的一模一样**

我在 P2 里写的建议是「两个 service 各加 `cancel_requested` 标志 + `cancel()` 方法，
在循环的每个主要断点检查一次；`handlers/admin.py` 两个接口接受 `{"cancel": true}`」。

v4.6.1 的实现**逐字对应**：

```python
# autofill.py / ai_fillinfo.py
self.cancel_requested = False

def cancel(self):
    """请求中断当前刮取任务。"""
    if not self.is_running:
        return False
    self.cancel_requested = True
    return True

# 循环里
for batch_start in range(0, len(idlist), batch_size):
    if throttle_aborted or self.cancel_requested:
        break
```

```python
# admin.py
req = tornado.escape.json_decode(self.request.body) if self.request.body else {}
if req.get("cancel"):
    if not AutoFillService().cancel():
        return {"err": "task.not_running", "msg": _("当前没有正在运行的任务")}
    return {"err": "ok", "msg": _("已取消任务")}
```

所以 **P2 这条可以从「给上游的建议」里划掉了**——他们已经修了。

## 顺手确认：P0 的两个 f-string 语法问题**还是没修**

我逐文件搜了 `book_type_query`（`handlers/admin.py`）和 `The installed version is`
（`webserver/main.py`），**v4.6.1 的 diff 里两处都没有**。

这意味着：

- 用 Python 3.11 跑上游 v4.6.1，`admin.py` 和 `main.py` **依然会 SyntaxError**
- 上游自己大概是 3.12+ 在跑，所以感知不到
- **这条 P0 要照旧提给他们**

## 其余值得注意的改动

| 改动 | 影响 |
|---|---|
| `requirements.txt`：`tornado 6.5.9→6.6`、`social-auth-core 5.0.0→6.2.0` | 跟不跟都行。social-auth-core 跨大版本，升级后**登录链路要回归测一遍** |
| `Dockerfile` + `docker/start.sh`：新增 `conf/nginx/ipv6-listen.conf`，启动时探测 IPv6 是否可用再决定监听 | **不能跟**。我们的 nginx 配置是自管的（`conf/nginx/mybooks.conf`），照抄会打架 |
| `app/package.json`：`nuxt 2.18.1 → 4.6.2` | **不能跟**，见附三。这是错的，Vue 2 跑不了 Nuxt 4 |
| `webserver/site_time.py` +77 −17 | 时区工具大改，`book.py` 的统计依赖它。要跟就两个一起 |
| `webserver/assistant/ai_assistant_agent.py` +96 −17 | AI 助手，我们没启用 |
| `skills/mybooks/*`、`tests/test_locale_i18n_keys.py` | 上游自己的 skill 与测试，与我们无关 |
| 18 个 `app/public/logo/favicon_*.png` | 只是图标资源 |
| `conf/nginx/ipv6-listen.conf` | 见上，不跟 |

## 结论：不做整体升级，只挑 4 处

**理由**：v4.6.1 的改动性质和我们的定制不叠加——它主要是「AI 会话、时区统计、favicon、
ipv6」这些新方向，而我们是「读者组、作者锁定、EPUB 修复」。整体 merge 会带来
80 个文件的冲突面，收益却只有下面这几点。

按优先级挑：

| 优先级 | 挑什么 | 为什么 |
|---|---|---|
| P0 | 长任务取消（3 个文件） | 我们已经踩过「点错了只能重启容器」，改动小、风险低 |
| P1 | 本月统计按站点时区切（`book.py` + `site_time.py`） | 我们的容器时区跟站点时区**必然不一致**（东八区容器、用户可能设别的），月初那几小时会算错，是真实 bug |
| P2 | OPDS 下载直链 401（`base.py`） | **仅当我们开了 `REQUIRE_LOGIN`** 才有意义；我们默认没开，可以缓 |
| 不跟 | nuxt 4.6.2、ipv6 nginx、favicon、AI 助手 | 见上表 |

`AppHeader.vue` / `BookCards.vue` / `settings.vue` 这几个前端改动，如果后面要做
「设置页时区选项」才需要一起合，否则纯属增加冲突。

## 关于「部署机上跑不了 watch-upstream.py」

```sh
python3: can't open file '/volume1/docker/audiobook/scripts/watch-upstream.py':
[Errno 2] No such file or directory
```

**原因**：那个脚本是今天才加进包的，NAS 上装的是**上一版包**，里面还没有它。
`upgrade.sh` 每次会把新包解压到 `/volume1/docker/audiobook/`，所以：

- 装上一版包 → 目录里没有 `watch-upstream.py`
- 装这一版包（md5 `fec015c4…` 那个）→ 就有了

**不需要为跑这个脚本专门升级**。想先看效果，两个办法：

1. 直接从包里单独取出来（不动现有部署）：
   ```sh
   cd /volume1/docker
   tar -xzf audiobook-deploy-4.6.0-10.tar.gz audiobook/scripts/watch-upstream.py --strip-components=2
   python3 watch-upstream.py --help
   ```
2. 或者等下次升级时自然会带上。

另外这个脚本**只用 Python 标准库**，NAS 上不用装任何依赖，只要有 `python3` 和 `git`。
