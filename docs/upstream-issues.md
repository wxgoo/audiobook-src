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
