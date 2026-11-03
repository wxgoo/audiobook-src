# srt-tool — 批量音频 SRT 字幕生成

用 faster-whisper（CPU 即可跑）给音频批量生成 `.srt` 字幕。
识别策略借鉴「有声书工具集 v6.22」：中文引导语、VAD 静音过滤、幻觉清洗、复读剔除、结果缓存。

## 安装

```sh
pip3 install faster-whisper
# NAS/纯 CPU 建议固定 int8：
pip3 install ctranslate2==4.8.5
```

> 连不上 huggingface.co 的环境（NAS 常见），先设镜像再跑：
> `export HF_ENDPOINT=https://hf-mirror.com`（可写进 ~/.bashrc）

## 用法

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
| `--ext` | 全部 | 只处理指定扩展名 |
| `--device` / `--compute-type` | auto | CPU 建议 `--compute-type int8` |
| `--no-cache` | 关 | 忽略/不写结果缓存 |

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
