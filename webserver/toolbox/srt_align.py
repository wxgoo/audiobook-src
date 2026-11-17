# -*- coding: utf-8 -*-
"""文稿对齐（★ v1.3，借鉴 OneAsr 的 align 子命令）。

OneAsr 用 CTC ForcedAligner 把「你自己的文稿」逐字打到音频时间轴上，
识别阶段完全跳过。这里没有 CTC 权重，走一条纯 Python 的近似路线：

  1. faster-whisper 开 word_timestamps 转写一遍，只取词/字时间，不用它的文字；
  2. 把文稿与识别文本都归一化（去标点空白、小写）；
  3. difflib.SequenceMatcher 找匹配块，把每一条文稿行映射到词序号 → 时刻。

文稿与音频内容一致（有声书常见）时很准；差异较大时会在 cue 上标 approx=True
并按字数比例兜底，调用方可提示用户时间轴是近似值。
"""
from __future__ import annotations

from difflib import SequenceMatcher

from srt_core import (beautify_text, convert_script, transcribe_audio,
                      words_from_segment)


def _norm(s: str) -> str:
    """归一化：只留字母/数字/汉字，小写。"""
    return "".join(ch.lower() for ch in (s or "") if ch.isalnum())


def align_transcript(audio_path, lines, *, model_name: str = "base",
                     lang: str = "zh", device: str = "auto",
                     compute_type: str = "auto", beam_size: int = 5,
                     hotwords: str | None = None,
                     beautify: bool = False, script: str = "original",
                     preset: str = "standard") -> list[dict]:
    segs = transcribe_audio(
        audio_path, model_name=model_name, lang=lang, device=device,
        compute_type=compute_type, beam_size=beam_size,
        hotwords=hotwords, word_timestamps=True)
    flat: list[dict] = []
    for seg in segs:
        for w in words_from_segment(seg):
            if _norm(w.get("text", "")):
                flat.append(w)
    if not flat:
        return []

    # 识别文本的归一化字符序列 + 字符 → 词下标
    recognized, char2word = [], []
    for wi, w in enumerate(flat):
        for ch in _norm(w["text"]):
            recognized.append(ch)
            char2word.append(wi)
    recognized_s = "".join(recognized)

    norm_lines = [_norm(x) for x in lines]
    transcript_s = "".join(norm_lines)
    blocks = SequenceMatcher(None, transcript_s, recognized_s,
                             autojunk=False).get_matching_blocks()
    ratio = SequenceMatcher(None, transcript_s, recognized_s,
                            autojunk=False).ratio()
    approx_all = ratio < 0.6

    cues: list[dict] = []
    cursor = 0
    total_chars = max(1, len(recognized_s))
    t0 = float(flat[0]["start"])
    t1 = max(float(flat[-1]["end"]), t0 + 0.001)
    last_end = 0.0
    for line, ntext in zip(lines, norm_lines):
        text = (line or "").strip()
        if not text:
            continue
        lo, hi = cursor, cursor + len(ntext)
        cursor = hi
        idxs: list[int] = []
        for a, b, size in blocks:
            if a + size <= lo or a >= hi:
                continue
            s = max(a, lo) - a
            e = min(a + size, hi) - a
            for k in range(s, e):
                if b + k < len(char2word):
                    idxs.append(char2word[b + k])
        if idxs:
            i0, i1 = min(idxs), max(idxs)
            start, end = float(flat[i0]["start"]), float(flat[i1]["end"])
            approx = False
        else:
            # 这一行完全没匹配上：按字数比例摊时间，标注近似
            frac0, frac1 = lo / total_chars, hi / total_chars
            start, end = t0 + frac0 * (t1 - t0), t0 + frac1 * (t1 - t0)
            approx = True
        if start < last_end:
            start = last_end
        end = max(end, start)
        last_end = end
        if beautify:
            text = beautify_text(text)
        if script != "original":
            text = convert_script(text, script)
        cue = {"start": start, "end": end, "text": text}
        if approx or approx_all:
            cue["approx"] = True
        cues.append(cue)
    return cues
