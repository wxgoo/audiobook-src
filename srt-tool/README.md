# srt-tool — 批量音频 SRT 字幕生成（v1.3.1）

用 faster-whisper（CPU 即可跑）给音频批量生成 `.srt` 字幕。
识别策略借鉴「有声书工具集 v6.22」；**v1.3 起借鉴 OneAsr 的
Qwen3-ASR + ForcedAligner 流水线设计**，把「测时间」和「排版」拆开，
支持词/字级时间轴、断行预设、可重排的 timeline、ASS/TXT 输出等。

## 更新日志

### v1.3.1（跟进 OneAsr v1.4.0 ~ v1.5.0）

- **文稿编码自动识别**（OneAsr v1.4.2 同款修复）：`align` / `transcript`
  读 `.txt/.srt` 时按文件自身编码解析——BOM 精确识别（UTF-8/UTF-16/UTF-32）
  → 严格 UTF-8 → GB18030（Windows 记事本 ANSI 默认）。以前 GBK 文稿会被
  静默替换成乱码；现在读不出会明确报错，不再出「对齐结果全是 �」。
- **媒体格式补齐**（OneAsr v1.4.0）：批量扫描支持 `.flv .ts .mpeg .mpg
  .wmv .3gp`；网页版工具箱同步补 `.m4b .opus .mp4 .mkv .mov .webm` 等。
- **评估后不引入**的项（附原因）：
  - OneAsr v1.4.1 对齐时间轴修复（标点粘 token 导致逐行滞后）——本项目
    按匹配「词」取时间戳，行首标点不参与匹配，天然没有这个问题；
  - v1.5.0 polish 分号——`beautify_text` 的标点正则一开始就含 `；`；
  - v1.4.0 失控 chunk 减半重试——已有复读折叠 + 幻觉清洗覆盖同类场景；
  - v1.5.0 盲 VAD 最低能量点切分——需要读音频算能量包络，收益/成本比低，
    现有词间静音 gap 硬断已覆盖大多数停顿切分。

### v1.3.0（借鉴 OneAsr）

| OneAsr 的做法 | 本项目的落地 | 用法 |
|---|---|---|
| ASR → ForcedAligner 词/字级时间轴 | faster-whisper `word_timestamps=True`，识别结果以 `timeline` 缓存（无词级时间时按字符均分） | 默认开启，`--no-word-timestamps` 关闭 |
| `render` 子命令：不加载模型，按 timeline 重新出字幕 | `srt_tools.py render --timeline ... --preset short` | 改预设/美化/字形**不用重新识别** |
| `short / standard / loose` 字幕长度预设 | `layout_timeline` 按字数、句末标点、静音间隔、最大时长断行 | `--preset` |
| `--script original\|simplified\|traditional` | `convert_script`（可选 opencc，没装就原样返回不报错） | `--script` |
| `transcript inspect / split / polish` | `srt_tools.py transcript inspect / split / beautify` | 不跑模型，纯文稿处理 |
| `align`：音视频 + 自己的文稿 → 字幕，跳过识别文字 | `srt_align.py`：whisper 词级时间 + `SequenceMatcher` 近似对齐 | `srt_tools.py align --audio ... --text ...` |
| `--txt` / `--ass`（卡拉 OK 逐词扫光） | `write_txt` / `write_ass`，cue 带 words 时写 `{\kX}` 标记 | `--txt` / `--ass` |
| `--hotwords` / 热词组 | 拼进 `initial_prompt`，新版 faster-whisper 用原生 `hotwords` 参数 | `--hotwords "三体,罗辑"` |
| `--events=json` 机器可读进度 | `--events-json`，stdout 每行一个 JSON 事件 | `--events-json` |
| `status` 机器可读安装快照 | `srt_tools.py status --json` | 看版本/缓存目录/依赖状态 |
| `zh\|en\|yue\|ja\|ko` 多语言 | 补日语/韩语引导语，GUI 语言下拉扩展 | `--lang ja` 等 |

> 说明：OneAsr 用的是 Rust + Qwen3-ASR + wgpu/Vulkan 的 CTC/ForcedAligner，
> 本项目保持 Python + faster-whisper 轻量栈，借鉴的是**架构与功能形态**
> （时间/排版分离、预设、可重出、文稿模式），不捆绑其模型权重。
> 词级时间来自 whisper 而非 CTC 强制对齐， Audiobook 这类朗读场景足够用。

### v1.2.0

- **图形界面版**：新增 `make_srt_gui.py`，打包出 `make_srt_gui.exe`，双击即用。
  选目录/选文件、选模型、选语言、勾选项都在窗口里点，进度条 + 实时日志，
  可随时点「停止」；上次选的路径和参数会记住。
- **打包**：`build.py` 一次产出三个 exe：`make_srt.exe`（命令行）、
  `make_srt_gui.exe`（图形界面）、`srt_tools.exe`（后期工具），共用 `dist/make_srt/`。

### v1.1.0

- **识别质量**：`condition_on_previous_text` 默认关闭（幻觉复读的根源）；
  复读剔除升级为「子单元带标点连发 ≥3 次折叠」；弱幻觉表补音频套话；粤语细分。
- **字幕可读性**：VAD 切碎的相邻小段自动合并成可读字幕（间隔/长度可调）；
  重叠时间轴钳制。
- **修复**：`--ext MP3` 大小写不敏感；Windows GBK 控制台生僻字文件名不崩；
  缓存写盘原子化；缓存键纳入 beam/条件上下文参数。
- **体验**：转写进度回调；`--beam-size`、`--cache-dir` 可调；新增 pytest 套件。

## 安装

```sh
pip3 install faster-whisper
# NAS/纯 CPU 建议固定 int8：
pip3 install ctranslate2==4.8.5
# 可选：中文字形转换（--script simplified/traditional 才需要）
pip3 install opencc-python-reimplemented
```

> 连不上 huggingface.co 的环境（NAS 常见），先设镜像：
> `export HF_ENDPOINT=https://hf-mirror.com`

## 图形界面（推荐日常用）

双击 `dist\make_srt\make_srt_gui.exe`（或 `python make_srt_gui.py`）：

1. 「选目录…」选整个有声书目录（含子目录），或「选音频文件…」只处理单个文件；
   也可以把文件夹拖到 exe 图标上；
2. 参数一般不用动：模型默认 `base`；中文书把语言改成 `zh`，引导语才生效；
3. v1.3 新增：**断行预设**（short/standard/loose）、**中文字形**、**热词**、
   **成稿美化**、**另存 ASS / TXT**、**存 timeline 边车**；
4. 点「开始生成」——进度条 + 实时日志；识别慢可随时点「停止」；
5. 已有字幕的文件默认跳过；「只列出文件」相当于 `--dry-run`。

## 命令行

```sh
# 整个目录（含子目录），中文书
python3 make_srt.py /path/to/audiobooks --lang zh

# 短句预设 + 美化 + 简繁 + 同时出 ASS/TXT
python3 make_srt.py ./audio --preset short --beautify --script simplified --ass --txt

# 热词（人名/书名），CPU 求快
python3 make_srt.py ./audio --hotwords "三体,罗辑,智子" --beam-size 1 --compute-type int8

# 先看会处理哪些文件
python3 make_srt.py ./audio --dry-run
```

### make_srt.py 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--model` | `base` | tiny/base/small/medium/large-v3（GUI 另有 large-v3-turbo） |
| `--lang` | `auto` | zh / en / yue / ja / ko / auto |
| `--overwrite` | 关 | 已有同名 .srt 也重新生成 |
| `--ext` | 全部 | 扩展名过滤，大小写不敏感 |
| `--device` / `--compute-type` | auto | CPU 建议 `--compute-type int8` |
| `--beam-size` | 5 | CPU 求快可传 1 |
| `--hotwords` | 无 | 热词/专有名词，逗号分隔 |
| `--vad-min-silence` | 500 | VAD 静音阈值毫秒 |
| `--no-word-timestamps` | 关 | 关闭词级时间（默认开） |
| `--preset` | `standard` | short / standard / loose（断行预设） |
| `--beautify` | 关 | 中英文数字间加空格、标点旁去空格 |
| `--script` | `original` | original / simplified / traditional（需 opencc） |
| `--merge-gap` / `--max-chars` | 预设值 | 覆盖预设的合并间隔 / 单条最大字数 |
| `--no-merge` | 关 | 退回 v1.1 段级输出，不走预设排版 |
| `--output-dir` | 音频同目录 | 统一输出目录 |
| `--save-timeline` | 关 | 写 `{stem}.timeline.json` 边车 |
| `--ass` / `--txt` | 关 | 额外输出 ASS（逐词卡拉 OK）/ TXT |
| `--events-json` | 关 | stdout 输出机器可读事件 |
| `--cache-dir` / `--no-cache` | `~/.cache/srt-tool` / 关 | 结果缓存 |

> **缓存键 = 文件名+大小+mtime+模型+语言 + beam/条件上下文/词级/热词/VAD**。
> 排版参数（预设、美化、字形）**不进缓存键**：改这些参数直接复用缓存里的
> timeline，不重新识别。

## 后期工具（不跑模型）

```sh
# 用 timeline 重排版面（改预设不用音频、不用模型）
python srt_tools.py render --timeline book.timeline.json --preset short --beautify

# 文稿：摘要 / 只拆过长行 / 美化（都不写回原文件）
python srt_tools.py transcript inspect --input book.txt --audio-seconds 3600 --json
python srt_tools.py transcript split --input book.txt --preset standard --output out.txt
python srt_tools.py transcript beautify --input book.txt --script simplified --output out.txt

# 你已有正确文稿：音视频 + 文稿 → 字幕（跳过识别文字，只打时间轴）
python srt_tools.py align --audio book.mp3 --text book.txt --output book.srt

# 安装/依赖状态
python srt_tools.py status --json
```

`render` 的排版预设：

| 预设 | 单条最大字数 | 最大时长 | 行为 |
|---|---|---|---|
| `short` | 16 | 2.5s | 短句，适合快节奏/竖屏 |
| `standard` | 28 | 4.5s | 默认，句末标点断行 |
| `loose` | 48 | 8s | 长句，少断行 |

`align` 说明：用 whisper 的词级时间 + 序列匹配把文稿行打到时间轴上。
文稿与音频内容一致时效果最好；差异大时会在内部标记 `approx`，命令行会提示
时间轴是近似值。若需要严格逐字强制对齐，建议用 OneAsr 本体的 CTC/ForcedAligner。

## 缓存与 timeline

- 识别结果（timeline：段 + 词/字时间）存 `~/.cache/srt-tool/<hash>.json`，
  键含所有影响识别的参数；原子写，写一半被杀不会留半个 JSON。
- 旧版缓存（纯段列表）自动兼容，读时包成 timeline。
- `--save-timeline` 写出边车后，可用 `srt_tools.py render` 无限次重排版面：
  断行预设、中英空格、简繁字形随便改，都不再碰音频。

## 测试

```sh
python -m pytest tests/ -q     # 59 条，不需要 faster-whisper
```

## 性能参考（CPU）

| 机器 | 模型 | 1 小时音频约需 |
|---|---|---|
| RS2416+（C2538 4核） | base | 1-3 小时（过夜跑） |
| 普通笔记本 4 核 | base | 10-20 分钟 |
| 有 GPU | large-v3 | 几分钟 |

字幕输出为「同目录同名.srt」，UTF-8，可直接给 mybooks 网页播放器用。
