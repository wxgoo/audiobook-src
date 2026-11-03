# -*- coding: utf-8 -*-
"""SRT 字幕生成核心。

基于 faster-whisper（CTranslate2），识别策略借鉴「有声书工具集 v6.22」的经验：
  1. 中文引导语 —— 不加很容易拿到繁体 / 无标点的结果；
  2. VAD 过滤 —— 剔掉静音段，避免「静音幻觉」（请不吝点赞订阅那种）；
  3. 复读剔除 —— Whisper 卡带式重复一行多次时只保留一次；
  4. 幻觉清洗 —— 固定套话表，强特征整句杀，弱特征整句基本是它才杀；
  5. 结果缓存 —— 模型名 + 语言 + 引导语变了不复用旧结果。

纯核心模块，不碰文件遍历 / CLI（见 make_srt.py）。
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

log = logging.getLogger("srt")

# ==================== 引导语 ====================
_ZH_PROMPT = "以下是普通话的句子，请输出简体中文并加上标点。"
_ZH_OTHER_PROMPT = "请输出简体中文并加上标点。"      # 中文书但不是普通话
_EN_PROMPT = "The following is a transcript of an audiobook being read aloud."


def build_initial_prompt(lang: str) -> str | None:
    if lang in ("zh", None, "auto") or str(lang).startswith("zh"):
        if lang and str(lang).startswith("zh-") and lang not in ("zh",):
            return _ZH_OTHER_PROMPT      # 粤语 / 闽南语等变体：不给「普通话」引导
        return _ZH_PROMPT
    if lang and lang.startswith("en"):
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
}


def looks_like_hallucination(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return True
    core = re.sub(r"[\s，。！？、,.!?~～…—-]+", "", t)
    if any(k in t for k in _HALLUC_STRONG):
        return True
    return core in _HALLUC_WEAK


def collapse_repeats(text: str) -> str:
    """卡带式重复：同一小句连续重复 2 次以上时只留一次。"""
    t = re.sub(r"\s+", " ", (text or "").strip())
    if len(t) < 8:
        return t
    # 尝试按整句对半拆，粗略处理「abc abc」式复读
    half = len(t) // 2
    if len(t) % 2 == 0 and t[:half] == t[half:]:
        return t[:half]
    return t


# ==================== SRT 输出 ====================
def _ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
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
                     vad_filter: bool = True) -> list[dict]:
    """转写一个音频文件，返回 [{start, end, text}]（已清洗）。"""
    model = get_model(model_name, device, compute_type)
    prompt = build_initial_prompt(None if lang == "auto" else lang)
    it, info = model.transcribe(
        str(audio_path),
        language=None if lang == "auto" else lang,
        initial_prompt=prompt,
        beam_size=beam_size,
        vad_filter=vad_filter,
        vad_parameters={"min_silence_duration_ms": 500},
    )
    segments = []
    for seg in it:
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
    log.info("识别完成: %s（语言 %s，时长 %.0fs，%d 段）",
             Path(audio_path).name, info.language, info.duration, len(segments))
    return segments


# ==================== 缓存 ====================
def cache_key(audio_path: Path, model_name: str, lang: str) -> str:
    st = Path(audio_path).stat()
    raw = f"{Path(audio_path).name}|{st.st_size}|{st.st_mtime_ns}|{model_name}|{lang}"
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
    (cache_dir / f"{key}.json").write_text(
        json.dumps(segments, ensure_ascii=False), encoding="utf-8")
