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

v1.3 优化（借鉴 OneAsr 的 Qwen3-ASR + ForcedAligner 流水线设计）：
  - 词/字级时间轴（word_timestamps）：把「测时间」和「排版」拆开。识别结果
    以 timeline 形式缓存，排版参数（预设 / 美化 / 字形）改动无需重新识别；
  - layout_timeline：按 short / standard / loose 三档预设做字幕断行，
    cue 的起止时刻取自所含词/字，比 Whisper 段级边界更准；
  - render 思路：timeline.json 边车 + 纯排版重出（见 srt_tools.py render）；
  - beautify_text / convert_script：中英文数字间空格、标点归位、简繁转换；
  - ASS（卡拉 OK 逐词高亮）/ TXT 输出；热词提示；日语/韩语引导语。

纯核心模块，不碰文件遍历 / CLI（见 make_srt.py / srt_tools.py）。
"""
from __future__ import annotations

import hashlib
import inspect
import json
import logging
import os
import re
from pathlib import Path

log = logging.getLogger("srt")

__version__ = "1.3.1"

# ==================== 引导语 ====================
_ZH_PROMPT = "以下是普通话的句子，请输出简体中文并加上标点。"
_ZH_OTHER_PROMPT = "请输出简体中文并加上标点。"      # 中文书但不是普通话
_EN_PROMPT = "The following is a transcript of an audiobook being read aloud."
# ★ v1.3：OneAsr 支持 zh|en|yue|ja|ko...，补上日/韩引导语（同样是为了稳住
# 字形与标点；裸 auto 不给引导语，交给模型自己判断）
_JA_PROMPT = "以下は朗読された音声の文字起こしです。句読点をつけてください。"
_KO_PROMPT = "다음은 낭독된 오디오의 전사입니다. 문장 부호를 붙여 주세요."


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
    if lang.startswith("ja"):
        return _JA_PROMPT
    if lang.startswith("ko"):
        return _KO_PROMPT
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


# ==================== 美化 / 字形（★ v1.3，借鉴 OneAsr 的 transcript polish / --script） ====================
_CJK_CLASS = r"\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af"
_RX_SPACE_BEFORE_PUNCT = re.compile(rf"\s+([，。！？、；：…—～)）】」》”])")
_RX_SPACE_AFTER_PUNCT = re.compile(rf"([，。！？、；：…—～(（【「《“])\s+")
_RX_CJK_LATIN = re.compile(rf"([{_CJK_CLASS}])([A-Za-z0-9])")
_RX_LATIN_CJK = re.compile(rf"([A-Za-z0-9])([{_CJK_CLASS}])")
_RX_HSPACES = re.compile(r"[ \t\u3000]+")


def beautify_text(text: str, *, spaced: bool = True) -> str:
    """成稿字幕美化（只改文字，不碰时间轴）：
       - 去掉重复空白；
       - 标点旁边的空格删掉（OneAsr 的「标点旁边不加空格」）；
       - 汉字/假名/韩文与英文字母、数字之间补一个空格（可选）。
     不做简繁转换，也不改标点本身 —— 那由 convert_script 负责。
    """
    t = _RX_HSPACES.sub(" ", (text or "").replace("\n", " ")).strip()
    t = _RX_SPACE_BEFORE_PUNCT.sub(r"\1", t)
    t = _RX_SPACE_AFTER_PUNCT.sub(r"\1", t)
    if spaced:
        t = _RX_CJK_LATIN.sub(r"\1 \2", t)
        t = _RX_LATIN_CJK.sub(r"\1 \2", t)
    return t.strip()


_opencc_cache: dict[str, object] = {}
_opencc_warned = False


def has_script_converter() -> bool:
    """opencc-python-reimplemented 是否可用（status 命令/日志用）。"""
    try:
        import opencc  # noqa: F401
        return True
    except ImportError:
        return False


def convert_script(text: str, target: str) -> str:
    """简繁字形转换：target ∈ {original, simplified, traditional}。
    依赖可选的 opencc-python-reimplemented；没装就原样返回并只提示一次，
    不阻塞识别/排版（OneAsr 的 --script 默认是 original，同样不动文字）。
    """
    global _opencc_warned
    if not text or target in (None, "", "original"):
        return text
    cfg = "t2s" if target == "simplified" else "s2t" if target == "traditional" else None
    if cfg is None:
        return text
    if cfg not in _opencc_cache:
        try:
            import opencc
            _opencc_cache[cfg] = opencc.OpenCC(cfg)
        except ImportError:
            if not _opencc_warned:
                log.warning("--script %s 需要 opencc-python-reimplemented，"
                            "未安装则保持原字形（pip install opencc-python-reimplemented）",
                            target)
                _opencc_warned = True
            return text
    return _opencc_cache[cfg].convert(text)


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


def _ass_ts(seconds: float) -> str:
    """ASS 时间戳 H:MM:SS.cc（百分之一秒）。"""
    cs = int(round(max(0.0, seconds) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


_ASS_HEADER = """[Script Info]
; generated by srt-tool v{ver} (OneAsr-inspired word timeline)
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,36,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,20,20,24,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def write_ass(cues, path: Path | str, *, karaoke: bool = True) -> Path:
    r"""ASS 输出。cue 带 words（词/字级时间轴）时输出 {\kX} 卡拉 OK 扫光标记，
    与 OneAsr 的 --ass 同思路；没有 words 就退化成整条高亮。"""
    path = Path(path)
    lines = [_ASS_HEADER.format(ver=__version__)]
    idx = 0
    for cue in cues:
        text = (cue.get("text") or "").strip()
        if not text:
            continue
        idx += 1
        def esc(s: str) -> str:
            return (s.replace("{", "(").replace("}", ")")
                     .replace("\n", "\\N").replace(",", "，"))

        words = cue.get("words") or []
        if karaoke and words:
            pieces = []
            for w in words:
                wt = esc((w.get("text") or "").replace("\n", ""))
                if not wt:
                    continue
                dur_cs = max(0, int(round((float(w.get("end", 0)) -
                                         float(w.get("start", 0))) * 100)))
                pieces.append("{\\k%d}%s" % (dur_cs, wt))
            body = "".join(pieces)
        else:
            body = esc(text)
        lines.append(f"Dialogue: 0,{_ass_ts(cue['start'])},{_ass_ts(cue['end'])},"
                     f"Default,,0,0,0,,{body}\n")
    path.write_text("".join(lines), encoding="utf-8")
    return path


def write_txt(cues, path: Path | str) -> Path:
    """TXT 输出：一行一条（按字幕 cue 断行，不看时间轴），对应 OneAsr --txt。"""
    path = Path(path)
    lines = [(c.get("text") or "").strip() for c in cues]
    lines = [x for x in lines if x]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
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


# ==================== 词/字级时间轴 + 排版（★ v1.3，借鉴 OneAsr） ====================
# OneAsr 把「ASR 测时间」和「字幕排版」拆成两个阶段：先得到 ForcedAligner 的
# 词/字级 timeline，再用 DP + preset 排版，改预设 / 字形只重跑 render。
# faster-whisper 没有 ForcedAligner，但 word_timestamps=True 能给出近似的词级
# 时间；没有词级时间时按字符均分，排版逻辑完全一致。
SUBTITLE_PRESETS: dict[str, dict] = {
    "short":    {"max_chars": 16, "max_duration": 2.5, "min_break": 6,
                 "max_gap": 0.6},
    "standard": {"max_chars": 28, "max_duration": 4.5, "min_break": 10,
                 "max_gap": 0.8},
    "loose":    {"max_chars": 48, "max_duration": 8.0, "min_break": 16,
                 "max_gap": 1.2},
}
_END_PUNCT = "。！？!?…；;”』」》"
_SOFT_PUNCT = "，,、：:"
_ATTACH_PUNCT = "，。！？、；：,.!?;:…—～)）】」》”’\"'"


def _tokenize_for_timing(text: str) -> list[str]:
    """无词级时间时把文本切成可分配时间的小单元：
       汉字/假名/韩文逐字；连续英文数字成词；标点/空格贴在前一个单元上。"""
    out: list[str] = []
    for ch in text:
        if re.match(r"[A-Za-z0-9]", ch) and out and \
                re.match(r"[A-Za-z0-9]", out[-1][-1]):
            out[-1] += ch
        elif ch in _ATTACH_PUNCT or ch.isspace():
            if out:
                out[-1] += ch
            else:
                out.append(ch)
        else:
            out.append(ch)
    return [u for u in out if u]


def words_from_segment(seg: dict) -> list[dict]:
    """取段的词/字级单元 [{text,start,end}]。优先用真实 word_timestamps，
    否则按字符均分段时间（仍能在 timeline 上做一致的排版）。"""
    text = (seg.get("text") or "").strip()
    if not text:
        return []
    ws = seg.get("words") or []
    items: list[dict] = []
    for w in ws:
        wt = w.get("text") or w.get("word") or ""
        if not str(wt).strip():
            continue
        items.append({
            "text": str(wt),
            "start": float(w.get("start", seg.get("start", 0.0)) or 0.0),
            "end": float(w.get("end", seg.get("end", 0.0)) or 0.0),
        })
    if items:
        return items
    units = _tokenize_for_timing(text)
    start = max(float(seg.get("start") or 0.0), 0.0)
    end = max(float(seg.get("end") or 0.0), start + 0.001)
    n = len(units)
    step = (end - start) / n
    return [{"text": u, "start": start + i * step,
             "end": start + (i + 1) * step} for i, u in enumerate(units)]


def build_timeline(segments, *, source: str = "", language: str = "",
                   duration: float | None = None) -> dict:
    """把识别段包成 timeline（一边车文件 / 缓存内容）。segments 可以是
    [{start,end,text,words}]，也可以直接是旧版 [{start,end,text}]。"""
    out = []
    for s in segments or []:
        text = (s.get("text") or "").strip()
        if not text:
            continue
        out.append({"start": float(s.get("start") or 0.0),
                    "end": float(s.get("end") or 0.0),
                    "text": text,
                    "words": words_from_segment(s)})
    return {"version": 2, "source": source, "language": language,
            "duration": duration, "segments": out}


def load_timeline(cache_dir: Path, key: str) -> dict | None:
    """读 timeline；旧版缓存是纯段列表，自动包成 timeline，向后兼容。"""
    data = load_cache(Path(cache_dir), key)
    if data is None:
        return None
    if isinstance(data, list):
        return build_timeline(data)
    if isinstance(data, dict) and isinstance(data.get("segments"), list):
        data.setdefault("version", 2)
        return data
    return None


def save_timeline(cache_dir: Path, key: str, timeline: dict) -> None:
    save_cache(Path(cache_dir), key, timeline)


def _clean_cue(text: str, *, beautify: bool, script: str) -> str:
    t = _RX_HSPACES.sub(" ", text.replace("\n", " ")).strip()
    if beautify:
        t = beautify_text(t)
    if script and script != "original":
        t = convert_script(t, script)
    return t.strip()


def layout_timeline(timeline: dict, *, preset: str = "standard",
                    max_chars: int | None = None, max_gap: float | None = None,
                    beautify: bool = False, script: str = "original",
                    keep_words: bool = True) -> list[dict]:
    """按预设把 timeline 排成字幕 cue（OneAsr 的 render/DP 排版思路）。

    断行规则（按优先级）：
      1. 硬断：累计字数 > max_chars，或相邻词间隔 > max_gap（静音）；
      2. 软断：句末标点且已够 min_break 字，或持续时间 > max_duration；
      3. 否则继续累积。
    cue 的 start/end 取自所含词的边界，计时比段级更精细。跨段拼接时若两侧
    都是中文且左段无结尾标点，补一个逗号（延续 v1.1 merge_segments 行为）。
    """
    cfg = dict(SUBTITLE_PRESETS.get(preset) or SUBTITLE_PRESETS["standard"])
    if max_chars is not None:
        cfg["max_chars"] = max_chars
    if max_gap is not None:
        cfg["max_gap"] = max_gap
    cues: list[dict] = []
    cur: dict | None = None

    def flush() -> None:
        nonlocal cur
        if cur is None:
            return
        txt = _clean_cue(cur["raw"], beautify=beautify, script=script)
        if txt:
            start = max(0.0, cur["start"])
            end = max(cur["end"], start)
            if cues and start < cues[-1]["end"]:
                start = cues[-1]["end"]      # VAD/词边界偶尔重叠，钳住
                end = max(end, start)
            cue = {"start": start, "end": end, "text": txt}
            if keep_words and cur["words"]:
                cue["words"] = cur["words"]
            cues.append(cue)
        cur = None

    for si, seg in enumerate(timeline.get("segments") or []):
        for u in words_from_segment(seg):
            utxt = str(u.get("text") or "")
            if not utxt.strip():
                continue
            if cur is None:
                cur = {"raw": utxt, "seg": si,
                       "start": float(u.get("start") or 0.0),
                       "end": float(u.get("end") or 0.0),
                       "words": [u]}
                continue
            raw = cur["raw"]
            # 跨段中文拼接补逗号（前段没标点、下一个词以中文开头）
            joiner = ""
            if si != cur["seg"] and raw.rstrip()[-1:] not in _END_PUNCT + _SOFT_PUNCT \
                    and re.match(r"^[\u4e00-\u9fff]", utxt):
                joiner = "，"
            cand = raw + joiner + utxt
            gap = float(u.get("start") or 0.0) - cur["end"]
            end = max(cur["end"], float(u.get("end") or 0.0))
            too_long = len(cand.strip()) > cfg["max_chars"]
            too_gap = gap > cfg["max_gap"]
            soft_end = (raw.rstrip()[-1:] in _END_PUNCT and
                        (len(raw.strip()) >= cfg["min_break"] or
                         si != cur["seg"]))
            too_dur = (end - cur["start"]) > cfg["max_duration"]
            if too_long or too_gap or soft_end or too_dur:
                flush()
                cur = {"raw": utxt, "seg": si,
                       "start": float(u.get("start") or 0.0),
                       "end": float(u.get("end") or 0.0), "words": [u]}
            else:
                cur["raw"] = cand
                cur["end"] = end
                cur["seg"] = si
                cur["words"].append(u)
    flush()
    return cues


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
                     word_timestamps: bool = True,
                     hotwords: str | None = None,
                     vad_min_silence_ms: int = 500,
                     on_progress=None,
                     should_stop=None) -> list[dict]:
    """转写一个音频文件，返回 [{start, end, text, words?}]（已清洗）。

    ★ v1.1：
      - condition_on_previous 默认 **False**。Whisper 默认会把前面已识别的
        文本喂回模型当上下文，有声书里这是幻觉复读（同一句连发、把套话
        越滚越长）的最大来源；关掉又快又稳。要旧行为传 True。
      - on_progress(done_sec, total_sec)：每识别约 2 分钟音频回调一次
        （过夜批量跑时不再长时间静默）；total 拿不到时为 None。
    ★ v1.2：should_stop —— 可选的无参回调，返回 True 时尽快中止：开始前
      命中直接返回空列表；识别中命中则停在当前位置，返回已识别的部分段
      （调用方自行决定丢弃还是采用，GUI 停止按钮用）。
    ★ v1.3：
      - word_timestamps 默认 True：让 faster-whisper 输出词/字级时间，供
        layout_timeline 做更精细的字幕断行（OneAsr 的 ForcedAligner 思路）。
        没有词级时间的假模型/老版本，返回段里就没有 words 键，旧行为不变。
      - hotwords：专有名词/人名提示。新版 faster-whisper 用原生 hotwords 参数，
        老版本降级为拼进 initial_prompt。
      - vad_min_silence_ms：VAD 静音阈值（OneAsr --chunk-seconds 的近亲）。
    """
    if should_stop is not None and should_stop():
        return []
    model = get_model(model_name, device, compute_type)
    prompt = build_initial_prompt(None if lang == "auto" else lang)
    kw = dict(
        language=None if lang == "auto" else lang,
        initial_prompt=prompt,
        beam_size=beam_size,
        vad_filter=vad_filter,
        vad_parameters={"min_silence_duration_ms": vad_min_silence_ms},
        condition_on_previous_text=condition_on_previous,
        word_timestamps=word_timestamps,
    )
    if hotwords:
        if "hotwords" in inspect.signature(model.transcribe).parameters:
            kw["hotwords"] = hotwords
        else:
            hint = f"可能出现的专有名词：{hotwords}"
            kw["initial_prompt"] = (prompt + " " + hint) if prompt else hint
    it, info = model.transcribe(str(audio_path), **kw)
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
            item = {"start": seg.start, "end": seg.end, "text": text}
            words = []
            for w in (getattr(seg, "words", None) or []):
                if isinstance(w, dict):
                    wt, ws, we = w.get("word"), w.get("start"), w.get("end")
                else:
                    wt, ws, we = getattr(w, "word", None), \
                        getattr(w, "start", None), getattr(w, "end", None)
                if wt is None or ws is None or we is None:
                    continue
                words.append({"text": str(wt), "start": float(ws),
                              "end": float(we)})
            if words:
                item["words"] = words
            segments.append(item)
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
