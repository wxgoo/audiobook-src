# srt-tool — 批量音频 SRT 字幕生成

用 faster-whisper（CPU 即可跑）给音频批量生成 `.srt` 字幕。
识别策略借鉴「有声书工具集 v6.22」：中文引导语、VAD 静音过滤、幻觉清洗、复读剔除、结果缓存。

## 更新日志

### v1.2.0

- **图形界面版**：新增 `make_srt_gui.py`，打包出 `make_srt_gui.exe`，双击即用，
  不再「一闪而过」。选目录/选文件、选模型、选语言、勾选项都在窗口里点，
  进度条 + 实时日志，可随时点「停止」；上次选的路径和参数会记住。
  把音频文件夹直接拖到 exe 图标上可自动填入路径。识别逻辑与命令行版
  完全共用（srt_core），结果、缓存、参数含义一致。
- **打包**：`build.py` 现在一次产出两个 exe —— `make_srt.exe`（命令行，
  给脚本/NAS 用）+ `make_srt_gui.exe`（图形界面，日常双击用），
  共用同一个 `dist/make_srt/` 目录。
- `srt_core.transcribe_audio` 新增 `should_stop` 回调：返回 True 时当前小段
  识别完即中断（GUI 停止按钮用），默认 None 不影响命令行行为。

### v1.1.0

- **识别质量**：`condition_on_previous_text` 默认关闭（幻觉复读的根源）；
  复读剔除升级为「子单元带标点连发 ≥3 次折叠」；弱幻觉表补充音频套话
  （欢迎/感谢收听收看）；粤语引导语细分。
- **字幕可读性**：VAD 切碎的相邻小段自动合并成可读字幕（间隔/长度可调，
  `--no-merge` 关闭）；重叠时间轴钳制。
- **修复**：`--ext MP3` 大小写不敏感（原来一个文件都扫不到）；Windows
  GBK 控制台遇生僻字文件名不再崩（stdout 兜 UTF-8）；缓存写盘原子化；
  缓存键纳入 beam/条件上下文参数（改参数不再命中旧结果）。
- **体验**：转写进度回调（每约 2 分钟音频报一次百分比）；`--beam-size`、
  `--cache-dir` 可调。
- 新增 pytest 套件（39 条，无需 faster-whisper 即可跑）。

## 安装

```sh
pip3 install faster-whisper
# NAS/纯 CPU 建议固定 int8：
pip3 install ctranslate2==4.8.5
```

> 连不上 huggingface.co 的环境（NAS 常见），先设镜像再跑：
> `export HF_ENDPOINT=https://hf-mirror.com`（可写进 ~/.bashrc）

## 图形界面（推荐日常用）

打包后双击 `dist\make_srt\make_srt_gui.exe`（或 `python make_srt_gui.py`）：

1. 「选目录…」选整个有声书目录（含子目录），或「选音频文件…」只处理单个文件；
   也可以直接把文件夹拖到 exe 图标上；
2. 参数一般不用动：模型默认 `base`，中文书把语言改成 `zh` 引导语才生效；
   机器快可上 `small` / `medium`；
3. 点「开始生成」——进度条显示整体和当前文件进度，日志区实时滚动；
   识别慢可随时点「停止」，当前小段识别完就中断，已完成文件的字幕不受影响；
4. 字幕写在音频同目录（同名 `.srt`），已有字幕的文件自动跳过
   （勾「已有 .srt 也重做」强制重做）；「只列出文件」相当于命令行的 `--dry-run`。

界面参数与命令行参数对照：

| 界面 | 等价命令行 | 默认 |
|---|---|---|
| 模型 | `--model` | base |
| 语言 | `--lang` | auto |
| 设备 / 计算类型 | `--device` / `--compute-type` | auto |
| 扩展名过滤 | `--ext` | 空=全部 |
| 束宽 beam | `--beam-size` | 5 |
| 合并最大间隔(秒) / 单条最大字数 | `--merge-gap` / `--max-chars` | 0.8 / 50 |
| 已有 .srt 也重做 | `--overwrite` | 关 |
| 合并碎段成可读字幕 | （默认开）`--no-merge` 关闭 | 开 |
| 使用结果缓存 | （默认开）`--no-cache` 关闭 | 开 |
| 喂回上文上下文 | `--condition-previous` | 关（不建议开） |
| 只列出文件 | `--dry-run` | 关 |

## 用法（命令行版）

```sh
# 整个目录（含子目录），跳过已有字幕
python3 make_srt.py /path/to/audiobooks --lang zh

# 先看看会处理哪些文件
python3 make_srt.py /path/to/audiobooks --dry-run

# 强制重做、指定模型与扩展名
python3 make_srt.py ./audio --overwrite --model small --ext mp3,m4a
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--model` | `base` | tiny/base/small/medium/large-v3，越大越准越慢 |
| `--lang` | `auto` | 中文有声书明确传 `zh`，引导语才生效 |
| `--overwrite` | 关 | 已有同名 .srt 也重新生成 |
| `--ext` | 全部 | 只处理指定扩展名（大小写不敏感，`mp3` 与 `MP3` 等价） |
| `--device` / `--compute-type` | auto | CPU 建议 `--compute-type int8` |
| `--beam-size` | 5 | 束宽；CPU 上求快可传 `1`（质量略降，速度约 2-4×） |
| `--condition-previous` | **关** | 把已识别文本喂回模型当上下文（旧行为）。幻觉复读多的时候别开 |
| `--no-merge` | 关 | 默认把 VAD 切碎的相邻小段合并成可读字幕 |
| `--merge-gap` / `--max-chars` | 0.8 / 50 | 合并参数：最大间隔秒数 / 单条字幕最大字符数 |
| `--cache-dir` | `~/.cache/srt-tool` | 缓存目录 |
| `--no-cache` | 关 | 忽略/不写结果缓存 |

> v1.1 起 `condition_on_previous_text` 默认关闭 —— Whisper 把前面已识别的
> 文本喂回模型当上下文，是有声书幻觉复读（同一句连发、套话越滚越长）的
> 最大来源；关掉又快又稳。复读剔除同时升级：同一 2~24 字单元带标点间隔
> 连发 ≥3 次只留一次（只重复 2 次的可能是对话回声，不动）。
>
> 识别结果会进缓存（键含 beam/条件上下文参数），改参数后自动重新识别，
> 不会命中旧结果。

## 测试

```sh
python -m pytest tests/ -q     # 39 条，不需要装 faster-whisper
```

## 性能参考（CPU）

| 机器 | 模型 | 1 小时音频约需 |
|---|---|---|
| RS2416+（C2538 4核） | base | 1-3 小时（过夜跑） |
| 普通笔记本 4 核 | base | 10-20 分钟 |
| 有 GPU | large-v3 | 几分钟 |

字幕输出为「同目录同名.srt」，UTF-8，可直接给 mybooks 网页播放器用（v6.22 同目录字幕优先的逻辑同样适用于我方的 audiobook：有 .srt 就不再识别）。

## 缓存

识别结果存 `~/.cache/srt-tool/`，键 = 文件名+大小+mtime+模型+语言。
参数没变重复跑直接命中，改了模型或文件更新过会重新识别。
