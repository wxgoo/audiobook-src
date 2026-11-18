# -*- coding: utf-8 -*-
"""网页版「音频转写文稿」v1.3 选项的行为级测试。

验证 _worker 的 timeline 排版流程：识别结果 → build_timeline →
layout_timeline(preset/script) → write_srt + 可选 write_ass/write_txt，
以及热词透传。用假 srt_core 替身，不依赖 faster-whisper。
"""

import threading
from pathlib import Path

import pytest

from webserver.services import srt_transcribe as st


class FakeCore:
    """srt_core 替身：记录调用链与参数，返回固定识别结果。"""

    def __init__(self):
        self.calls = []

    def transcribe_audio(self, apath, **kw):
        self.calls.append(("transcribe", str(apath), kw))
        return [{"start": 0.0, "end": 2.0, "text": "你好世界。"}]

    def build_timeline(self, segments, source="", language=""):
        self.calls.append(("build_timeline", source, language))
        return {"segments": segments, "source": source}

    def layout_timeline(self, tl, *, preset="standard", script="original",
                        beautify=False, keep_words=True):
        self.calls.append(("layout", preset, script, beautify))
        return [{"start": 0.0, "end": 2.0, "text": "你好世界。",
                 "preset": preset, "script": script}]

    def write_srt(self, cues, path):
        self.calls.append(("write_srt", list(cues), str(path)))
        Path(path).write_text("srt", encoding="utf-8")

    def write_ass(self, cues, path):
        self.calls.append(("write_ass", list(cues), str(path)))
        Path(path).write_text("ass", encoding="utf-8")

    def write_txt(self, cues, path):
        self.calls.append(("write_txt", list(cues), str(path)))
        Path(path).write_text("txt", encoding="utf-8")


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    core = FakeCore()
    monkeypatch.setattr(st, "srt_core", core)
    adir = tmp_path / "audio"
    adir.mkdir()
    (adir / "01.mp3").write_bytes(b"fake")
    books = [{"book_id": 1, "title": "测试书", "audio_dir": str(adir)}]
    return core, adir, books


def _run_worker(fake_env, **opts):
    core, adir, books = fake_env
    stop = threading.Event()
    old_stop = st._stop
    st._stop = stop
    try:
        st._worker(books, "base", "zh", opts.pop("overwrite", False),
                   opts.pop("keep_txt", True), **opts)
    finally:
        st._stop = old_stop
    return core


def test_worker_default_layout_writes_srt_and_txt(fake_env):
    """默认参数：standard 预设、原样文字、写 .srt + .txt（keep_txt 默认开）。"""
    core = _run_worker(fake_env, preset="standard", script="original",
                       write_ass=False, hotwords="")
    kinds = [c[0] for c in core.calls]
    assert kinds == ["transcribe", "build_timeline", "layout", "write_srt", "write_txt"]
    layout = core.calls[2]
    assert layout[1] == "standard" and layout[2] == "original" and layout[3] is True
    srt_path = core.calls[3][2]
    assert srt_path.endswith("01.srt")
    txt_path = core.calls[4][2]
    assert txt_path.endswith("01.txt")


def test_worker_write_ass_and_preset_script_passthrough(fake_env):
    """勾选 ASS：.ass 也写出；预设/文字转换参数逐层透传到 layout_timeline。"""
    core = _run_worker(fake_env, preset="short", script="simplified",
                       write_ass=True, keep_txt=False, hotwords="")
    kinds = [c[0] for c in core.calls]
    assert kinds == ["transcribe", "build_timeline", "layout", "write_srt", "write_ass"]
    assert core.calls[2][1] == "short"
    assert core.calls[2][2] == "simplified"
    assert core.calls[4][2].endswith("01.ass")


def test_worker_hotwords_passthrough(fake_env):
    """热词透传给 transcribe_audio；空热词传 None（不占用 initial_prompt）。"""
    core = _run_worker(fake_env, preset="standard", script="original",
                       write_ass=False, hotwords="三体,罗辑")
    kw = [c for c in core.calls if c[0] == "transcribe"][-1][2]
    assert kw.get("hotwords") == "三体,罗辑"
    core2 = _run_worker(fake_env, preset="standard", script="original",
                        write_ass=False, hotwords="", overwrite=True)
    kw2 = [c for c in core2.calls if c[0] == "transcribe"][-1][2]
    assert kw2.get("hotwords") is None


def test_worker_cancel_keeps_partial_result(fake_env, tmp_path, monkeypatch):
    """取消粒度：停止后已识别的部分结果仍按排版流程写出（有比没有强）。"""
    core, adir, books = fake_env

    def transcribe_then_stop(apath, **kw):
        st._stop.set()          # 模拟识别中用户点了停止
        return [{"start": 0.0, "end": 1.0, "text": "半截结果"}]

    monkeypatch.setattr(core, "transcribe_audio", transcribe_then_stop)
    _run_worker(fake_env, preset="loose", script="original",
                write_ass=False, keep_txt=False, hotwords="")
    kinds = [c[0] for c in core.calls]
    # 停止命中后不再继续，但本次的部分结果应已写出 .srt（monkeypatch 的
    # transcribe 不记录 calls，所以索引要按 kinds 动态定位）
    assert "write_srt" in kinds
    assert "layout" in kinds
    layout = core.calls[kinds.index("layout")]
    assert layout[1] == "loose"


def test_choices_and_limit():
    """合法值集合与热词长度上限（handler 校验依据）。"""
    assert st.PRESET_CHOICES == ("short", "standard", "loose")
    assert st.SCRIPT_CHOICES == ("original", "simplified", "traditional")
    assert st.HOTWORDS_MAX_LEN > 0
