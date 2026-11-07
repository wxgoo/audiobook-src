# -*- coding: utf-8 -*-
"""SRT 字幕生成核心。

基于 faster-whisper（CTranslate2），识别策略借鉴「有声书工具集 v6.22」的经验：
  1. 中文引导语 —— 不加很容易拿到繁体 / 无标点的结果；
  2. VAD 过滤 —— 剔掉静音段，避免「静音幻觉」（请不吝点赞订阅那种）；
  3. 复读剔除 —— Whisper 卡带式重复时只保留一次（整句对半 + 子单元连发）；
  4. 幻觉清洗 —— 固定套话表，强特征整句杀，弱特征整句基本是它才杀；
  5. 结果缓存 —— 模型名 + 语言 + 引导语变了不复用旧结果。

v1.1 优化：
  - condition_on_previous_text 默认关（有声书幻觉复读的根源，关掉又快又稳，
    要旧行为显式传 condition_on_previous=True）；
  - merge_segments：VAD 切碎的小段合并成可读字幕（缓存里存原始段，
    合并在写出前做，改合并参数不用重新识别）；
  - on_progress：转写进度回调（过夜跑不再长时间静默）；
  - 缓存写盘原子化；缓存键可带影响结果的参数（beam / 条件上下文）。

纯核心模块，不碰文件遍历 / CLI（见 make_srt.py）。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path

log = logging.getLogger("srt")

__version__ = "1.2.0"

# ==================== 引导语 ====================
_ZH_PROMPT = "以下是普通话的句子，请输出简体中文并加上标点。"
_ZH_OTHER_PROMPT = "请输出简体中文并加上标点。"      # 中文书但不是普通话
_EN_PROMPT = "The following is a transcript of an audiobook being read aloud."


def build_initial_prompt(lang: str | None) -> str | None:
    """按语言给引导语。

    ★ v1.1：粤语（yue*）不给「普通话」引导；其余 zh 系（含 zh-CN / zh-Hans
      这类带地区码的普通话写法）都给普通话引导 —— 原来的分支只认裸 "zh"，
      zh-CN 会被误当成方言变体。
    """
    if not lang or lang == "auto" or str(lang).startswith("zh") \
            or str(lang).startswith("yue"):
        if str(lang).startswith("yue"):
            return _ZH_OTHER_PROMPT      # 粤语 / 闽南语等：不给「普通话」引导
        return _ZH_PROMPT
    if lang.startswith("en"):
        return _EN_PROMPT
    return None


# ==================== 幻觉清洗 ====================
# 强特征：正常书里几乎不会出现，句子里一带上就算
_HALLUC_STRONG = (
    "请不吝点赞", "点赞订阅", "订阅频道", "关注频道", "一键三连",
    "字幕由", "字幕组", "翻译：", "时长：", "请看下集", "下集再见",
    "字幕制作", "by 字幕", "subtitle", "subtitle by",
    "amara.org", "subtitles by", "please subscribe",
)
# 弱特征：日常内容里可能出现，只有整句（去标点空白后）基本就是它才算
_HALLUC_WEAK = {
    "谢谢观看", "谢谢大家", "再见", "谢谢", "拜拜", "晚安", "晚安晚安",
    "谢谢收看", "我们下期再见", "下次再见", "明儿见", "你们说对不对",
    "music", "音樂", "大家好", "哈喽大家好",
    # ★ v1.1：音频类自媒体常见的整句套话（只在「整句就是它」时才杀）
    "欢迎收听", "感谢收听", "欢迎收看", "感谢收看",
}


def looks_like_hallucination(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True
    core = re.sub(r"[\s，。！？、,.!?~～…—-]+", "", t)
    if any(k in t for k in _HALLUC_STRONG):
        return True
    return core in _HALLUC_WEAK


# 卡带式重复的子单元形态：「好的，好的，好的」「thank you. thank you. thank you.」
# —— 单元（2~24 字）+ 可选标点空白间隔，同一单元连发 ≥3 次（含首次）。
# {2,} 表示除首次外还要再出现 2 次；只有 2 次的可能是正常对话回声，不动。
_RX_UNIT_REPEAT = re.compile(
    r"(.{2,24}?)(?:[\s，。！？、,.!?~～…；;：:\-—]*\1){2,}")


def collapse_repeats(text: str) -> str:
    """卡带式重复折叠：
      ① 整句对半 ——「abc abc」这种恰好重复两遍的整句；
      ② 子单元连发 —— 同一 2~24 字单元带标点间隔连发 ≥3 次只留一次
        （★ v1.1 新增：原来只认整句对半，「好的，好的，好的」接不住）。
    只重复 2 次的子单元可能是对话回声，刻意不折叠。
    """
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) < 8:
        return t
    # ① 整句对半，粗略处理「abc abc」式复读
    half = len(t) // 2
    if len(t) % 2 == 0 and t[:half] == t[half:]:
        t = t[:half]
    # ② 子单元连发 ≥3 次 → 只留一次
    t = _RX_UNIT_REPEAT.sub(r"\1", t)
    return t.strip()


# ==================== SRT 输出 ====================
def _ts(seconds: float) -> str:
    ms = int(round((seconds or 0) * 1000))
    if ms < 0:
        ms = 0                      # 浮点误差 / VAD 边界偶尔给出负值
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(segments, path: Path | str) -> Path:
    """segments: 可迭代的 {start, end, text}。返回写入的文件路径。"""
    path = Path(path)
    blocks = []
    idx = 0
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        idx += 1
        blocks.append(f"{idx}\n{_ts(seg['start'])} --> {_ts(seg['end'])}\n{text}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path


# ==================== 段合并（★ v1.1） ====================
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff]")


def _joiner(left: str, right: str) -> str:
    """两段拼接的连接符：中文之间不加标点直接接会 jam 词，补个逗号；
    左段已有结束标点就不再补。西文之间补空格。"""
    if left and left[-1] in "，。！？…—-,.!?;；:：\"”』」】）)]":
        return ""
    if _CJK_RE.search(right) and _CJK_RE.search(left):
        return "，"
    return " "


def merge_segments(segments, max_gap: float = 0.8, max_chars: int = 50):
    """把 VAD 切碎的相邻小段合并成可读字幕。

    合并条件：间隔 ≤ max_gap 秒，且合并后不超过 max_chars 字。
    顺带把重叠时间戳钳住（后段 start 早于缓冲 end 时，从缓冲 end 起）——
    VAD 边界偶尔给出相互重叠的时间轴，部分播放器会闪字。
    返回新列表，不改动入参。
    """
    out: list[dict] = []
    buf: dict | None = None

    def flush():
        nonlocal buf
        if buf is not None:
            out.append(buf)
            buf = None

    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        start = max(float(seg.get("start") or 0.0), 0.0)
        end = max(float(seg.get("end") or 0.0), start)
        if buf is not None:
            gap_ok = (start - buf["end"]) <= max_gap
            size_ok = len(buf["text"]) + len(text) + 1 <= max_chars
            order_ok = start >= buf["start"]
            if gap_ok and size_ok and order_ok:
                buf["text"] = buf["text"] + _joiner(buf["text"], text) + text
                buf["end"] = max(buf["end"], end)
                continue
        flush()
        # 与上一条输出重叠时钳到它的结束点（VAD 边界偶尔给重叠时间轴）
        if out and start < out[-1]["end"]:
            start = out[-1]["end"]
            end = max(end, start)
        buf = {"start": start, "end": end, "text": text}
    flush()
    return out


# ==================== 转写 ====================
_model_cache: dict[str, object] = {}


def get_model(model_name: str, device: str = "auto", compute_type: str = "auto"):
    key = f"{model_name}|{device}|{compute_type}"
    if key not in _model_cache:
        from faster_whisper import WhisperModel
        log.info("加载模型 %s（首次会下载到 ~/.cache/huggingface）...", model_name)
        _model_cache[key] = WhisperModel(model_name, device=device,
                                         compute_type=compute_type)
    return _model_cache[key]


def transcribe_audio(audio_path: Path | str, *, model_name: str = "base",
                     lang: str = "auto", device: str = "auto",
                     compute_type: str = "auto", beam_size: int = 5,
                     vad_filter: bool = True,
                     condition_on_previous: bool = False,
                     on_progress=None,
                     should_stop=None) -> list[dict]:
    """转写一个音频文件，返回 [{start, end, text}]（已清洗）。

    ★ v1.1：
      - condition_on_previous 默认 **False**。Whisper 默认会把前面已识别的
        文本喂回模型当上下文，有声书里这是幻觉复读（同一句连发、把套话
        越滚越长）的最大来源；关掉又快又稳。要旧行为传 True。
      - on_progress(done_sec, total_sec)：每识别约 2 分钟音频回调一次
        （过夜批量跑时不再长时间静默）；total 拿不到时为 None。
    ★ v1.2：should_stop —— 可选的无参回调，返回 True 时尽快中止：开始前
      命中直接返回空列表；识别中命中则停在当前位置，返回已识别的部分段
      （调用方自行决定丢弃还是采用，GUI 停止按钮用）。
    """
    if should_stop is not None and should_stop():
        return []
    model = get_model(model_name, device, compute_type)
    prompt = build_initial_prompt(None if lang == "auto" else lang)
    it, info = model.transcribe(
        str(audio_path),
        language=None if lang == "auto" else lang,
        initial_prompt=prompt,
        beam_size=beam_size,
        vad_filter=vad_filter,
        vad_parameters={"min_silence_duration_ms": 500},
        condition_on_previous_text=condition_on_previous,
    )
    total = getattr(info, "duration", None)
    segments = []
    last_mark = -1.0
    for seg in it:
        if should_stop is not None and should_stop():
            log.info("收到停止请求，提前结束: %s", Path(audio_path).name)
            break
        text = collapse_repeats(seg.text.strip())
        # 防引导语回吐：音频接近无声/机器音时，模型可能把 prompt 原样吐出来
        if prompt and (text in prompt or (len(prompt) > 10 and prompt in text)):
            log.debug("剔除引导语回吐: %r", text)
            continue
        if looks_like_hallucination(text):
            log.debug("剔除幻觉: %r", text)
            continue
        if text:
            segments.append({"start": seg.start, "end": seg.end, "text": text})
        # 进度：每推进 ~120s 音频打一次（回调异常不影响转写）
        if on_progress is not None and total and \
                seg.end - last_mark >= 120.0:
            last_mark = seg.end
            try:
                on_progress(seg.end, total)
            except Exception:
                pass
    log.info("识别完成: %s（语言 %s，时长 %.0fs，%d 段）",
             Path(audio_path).name, info.language, info.duration, len(segments))
    return segments


# ==================== 缓存 ====================
def cache_key(audio_path: Path, model_name: str, lang: str,
              extra: str = "") -> str:
    """缓存键 = 文件名+大小+mtime+模型+语言（+ 额外影响结果的参数）。

    ★ v1.1：extra 用于把 beam_size / condition_on_previous 这类会改变
      识别结果的参数算进键里 —— 不然改了参数还命中旧缓存，结果对不上。
    """
    st = Path(audio_path).stat()
    raw = f"{Path(audio_path).name}|{st.st_size}|{st.st_mtime_ns}|" \
          f"{model_name}|{lang}"
    if extra:
        raw += f"|{extra}"
    return hashlib.sha1(raw.encode()).hexdigest()


def load_cache(cache_dir: Path, key: str) -> list[dict] | None:
    p = cache_dir / f"{key}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def save_cache(cache_dir: Path, key: str, segments: list[dict]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    # ★ v1.1：原子写（tmp + replace）—— 写到一半被杀/断电不会留半个 JSON
    p = cache_dir / f"{key}.json"
    tmp = cache_dir / f"{key}.json.tmp"
    tmp.write_text(json.dumps(segments, ensure_ascii=False),
                   encoding="utf-8")
    os.replace(tmp, p)
