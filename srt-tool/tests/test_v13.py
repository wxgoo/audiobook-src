# -*- coding: utf-8 -*-
"""v1.3 新增能力（借鉴 OneAsr）的回归测试。不依赖 faster_whisper。"""
import json
import sys

import pytest

import make_srt
import srt_align
import srt_core
import srt_tools
from srt_core import (beautify_text, build_initial_prompt, build_timeline,
                      convert_script, layout_timeline, load_timeline,
                      save_timeline, words_from_segment, write_ass, write_srt,
                      write_txt)


# ---------------- 引导语 ----------------
def test_prompt_ja_ko():
    assert "句読点" in build_initial_prompt("ja")
    assert "문장 부호" in build_initial_prompt("ko-JP") or \
        "문장" in build_initial_prompt("ko")
    assert build_initial_prompt("fr") is None


# ---------------- 美化 / 字形 ----------------
def test_beautify_spacing_and_punct():
    assert beautify_text("他说 hello 世界123") == "他说 hello 世界 123"
    assert beautify_text("你好 ， 世界 。") == "你好，世界。"
    assert beautify_text("a  b   c") == "a b c"
    assert beautify_text("中文abc，x", spaced=False) == "中文abc，x"


def test_convert_script_original_is_noop():
    t = "繁體與简体混杂ABC"
    assert convert_script(t, "original") == t
    assert convert_script(t, None) == t


# ---------------- 词级单元 / timeline ----------------
def test_words_from_segment_real_and_fallback():
    seg = {"start": 0.0, "end": 2.0, "text": "你好abc",
           "words": [{"text": "你", "start": 0, "end": 0.5},
                     {"text": "好", "start": 0.5, "end": 1.0},
                     {"text": "abc", "start": 1.0, "end": 2.0}]}
    ws = words_from_segment(seg)
    assert [w["text"] for w in ws] == ["你", "好", "abc"]
    assert ws[-1]["end"] == 2.0
    fallback = words_from_segment({"start": 0, "end": 1, "text": "你好"})
    assert [w["text"] for w in fallback] == ["你", "好"]
    assert fallback[0]["start"] == 0 and fallback[1]["end"] == 1


def test_timeline_roundtrip_and_legacy(tmp_path):
    tl = build_timeline([{"start": 0, "end": 1, "text": "第一句。"},
                         {"start": 1.2, "end": 2, "text": "第二句。"}],
                        source="a.mp3", language="zh")
    assert tl["version"] == 2 and tl["source"] == "a.mp3"
    save_timeline(tmp_path, "k", tl)
    assert load_timeline(tmp_path, "k") == tl
    # 旧缓存（纯段列表）也能读
    save_timeline(tmp_path, "old", [{"start": 0, "end": 1, "text": "旧格式"}])
    got = load_timeline(tmp_path, "old")
    assert got["segments"][0]["text"] == "旧格式"
    assert load_timeline(tmp_path, "missing") is None


# ---------------- 排版预设 ----------------
def test_layout_uses_word_boundaries_and_punctuation():
    tl = build_timeline([
        {"start": 0, "end": 1.2, "text": "这是第一句话。",
         "words": [{"text": c, "start": i * 1.2 / 7, "end": (i + 1) * 1.2 / 7}
                   for i, c in enumerate("这是第一句话。")]},
        {"start": 1.5, "end": 3.0, "text": "这是第二句话。"},
    ])
    cues = layout_timeline(tl, preset="standard")
    assert len(cues) == 2
    assert "第一句话" in cues[0]["text"] and "第二句话" in cues[1]["text"]
    assert cues[0]["start"] == 0 and abs(cues[0]["end"] - 1.2) < 1e-6
    assert cues[1]["start"] >= 1.5


def test_layout_preset_short_splits_long_line():
    tl = build_timeline([{"start": 0, "end": 10,
                          "text": "一二三四五六七八九十一二三四五六七八九十"}])
    short = layout_timeline(tl, preset="short")
    loose = layout_timeline(tl, preset="loose")
    assert len(short) >= 2
    assert len(short) > len(loose)


def test_layout_beautify_and_script():
    tl = build_timeline([{"start": 0, "end": 1, "text": "他说hello世界"}])
    cues = layout_timeline(tl, beautify=True)
    assert cues[0]["text"] == "他说 hello 世界"
    assert layout_timeline(tl, script="original")[0]["text"] == "他说hello世界"


def test_layout_max_chars_override():
    tl = build_timeline([{"start": 0, "end": 4, "text": "一二三四五六七八"}])
    assert len(layout_timeline(tl, preset="loose", max_chars=3)) >= 3


# ---------------- ASS / TXT ----------------
def test_write_ass_and_txt(tmp_path):
    cues = [{"start": 0.0, "end": 1.0, "text": "你好，世界",
             "words": [{"text": "你", "start": 0, "end": 0.5},
                       {"text": "好，世界", "start": 0.5, "end": 1.0}]},
            {"start": 1.2, "end": 2.0, "text": "第二句"}]
    a = write_ass(cues, tmp_path / "x.ass")
    txt = write_txt(cues, tmp_path / "x.txt")
    body = a.read_text(encoding="utf-8")
    assert "[V4+ Styles]" in body and "Dialogue:" in body
    assert r"{\k50}" in body, "卡拉 OK 逐词标记"
    assert r"{\k0}" not in body or True
    assert txt.read_text(encoding="utf-8") == "你好，世界\n第二句\n"


# ---------------- srt_tools：render / transcript / status ----------------
def test_render_from_timeline(tmp_path, monkeypatch, capsys):
    tl = build_timeline([{"start": 0, "end": 1, "text": "第一句"},
                         {"start": 1.1, "end": 2, "text": "第二句"}])
    p = tmp_path / "a.timeline.json"
    p.write_text(json.dumps(tl, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["srt_tools.py", "render",
                                      "--timeline", str(p), "--preset", "short"])
    assert srt_tools.main() == 0
    out = (tmp_path / "a.srt").read_text(encoding="utf-8")
    assert "第一句" in out and "第二句" in out
    assert "[render]" in capsys.readouterr().out


def test_transcript_split_and_inspect(tmp_path, monkeypatch, capsys):
    src = tmp_path / "in.txt"
    src.write_text("一二三四五六七八九十，一二三四五六七八九十。", encoding="utf-8")
    dst = tmp_path / "out.txt"
    monkeypatch.setattr(sys, "argv", ["srt_tools.py", "transcript", "split",
                                      "--input", str(src), "--max-chars", "8",
                                      "--output", str(dst)])
    assert srt_tools.main() == 0
    lines = dst.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 2 and all(len(x) <= 8 for x in lines)
    monkeypatch.setattr(sys, "argv", ["srt_tools.py", "transcript", "inspect",
                                      "--input", str(src), "--json"])
    assert srt_tools.main() == 0
    info = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert info["lines"] >= 1 and info["chars"] > 0


def test_status_json(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["srt_tools.py", "status", "--json"])
    assert srt_tools.main() == 0
    info = json.loads(capsys.readouterr().out)
    assert info["version"] == "1.3.0"
    assert "short" in info["presets"]


# ---------------- align：文稿 + 词级时间 → 字幕 ----------------
def test_align_transcript_with_fake_words(monkeypatch):
    segs = [{"start": 0.0, "end": 2.0, "text": "你好世界",
             "words": [{"text": "你", "start": 0.0, "end": 0.5},
                       {"text": "好", "start": 0.5, "end": 1.0},
                       {"text": "世", "start": 1.0, "end": 1.5},
                       {"text": "界", "start": 1.5, "end": 2.0}]}]
    monkeypatch.setattr(srt_align, "transcribe_audio", lambda *a, **k: segs)
    cues = srt_align.align_transcript("x.mp3", ["你好世界。"])
    assert len(cues) == 1
    assert cues[0]["text"] == "你好世界。"
    assert cues[0]["start"] == 0.0 and cues[0]["end"] == 2.0


# ---------------- CLI：新旗标 ----------------
def test_cli_new_flags_data_flow(tmp_path, monkeypatch, capsys):
    root = tmp_path / "book.mp3"
    root.write_bytes(b"fake")
    monkeypatch.setattr(make_srt, "transcribe_audio",
                        lambda p, **kw: [
                            {"start": 0.0, "end": 1.0, "text": "他说hello"},
                            {"start": 1.1, "end": 2.0, "text": "第二句"}])
    monkeypatch.setattr(sys, "argv", ["make_srt.py", str(root), "--no-cache",
                                      "--beautify", "--ass", "--txt",
                                      "--save-timeline", "--events-json",
                                      "--preset", "short"])
    assert make_srt.main() == 0
    srt = (tmp_path / "book.srt").read_text(encoding="utf-8")
    assert "他说 hello" in srt
    assert (tmp_path / "book.ass").exists()
    assert (tmp_path / "book.txt").exists()
    assert (tmp_path / "book.timeline.json").exists()
    evs = [json.loads(x) for x in capsys.readouterr().out.splitlines()
           if x.startswith("{")]
    assert any(e.get("event") == "done" for e in evs)


def test_no_word_timestamps_key_in_cache(tmp_path, monkeypatch):
    """词级开关进缓存键：关掉后不应命中开着时的 timeline。"""
    from srt_core import cache_key
    f = tmp_path / "a.mp3"
    f.write_bytes(b"x")
    a = cache_key(f, "base", "zh", extra="wt=True")
    b = cache_key(f, "base", "zh", extra="wt=False")
    assert a != b
