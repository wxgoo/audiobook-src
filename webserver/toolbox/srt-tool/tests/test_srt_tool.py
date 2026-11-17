# -*- coding: utf-8 -*-
"""audiobookSrtMake 的回归测试。

不依赖 faster_whisper（srt_core 里是惰性导入）——只有 transcribe_audio 的
参数透传测试往 _model_cache 里塞假模型。跑法：pytest tests/
"""
import json
import sys
from types import SimpleNamespace

import pytest

import make_srt
import srt_core
from srt_core import (build_initial_prompt, cache_key, collapse_repeats,
                      load_cache, looks_like_hallucination, merge_segments,
                      save_cache, transcribe_audio, write_srt, _ts)


# ============================================================
# 引导语
# ============================================================
class TestPrompt:
    def test_zh_gets_mandarin_prompt(self):
        assert build_initial_prompt("zh") == srt_core._ZH_PROMPT
        assert build_initial_prompt("zh-CN") == srt_core._ZH_PROMPT, \
            "★ zh-CN 是普通话，不该被当方言变体"
        assert build_initial_prompt("zh-Hans") == srt_core._ZH_PROMPT

    def test_yue_gets_non_mandarin_prompt(self):
        assert build_initial_prompt("yue") == srt_core._ZH_OTHER_PROMPT

    def test_auto_and_none_get_mandarin_prompt(self):
        assert build_initial_prompt(None) == srt_core._ZH_PROMPT
        assert build_initial_prompt("auto") == srt_core._ZH_PROMPT

    def test_en_and_other(self):
        assert build_initial_prompt("en") == srt_core._EN_PROMPT
        assert build_initial_prompt("fr") is None


# ============================================================
# 幻觉清洗
# ============================================================
class TestHallucination:
    def test_strong_anywhere(self):
        assert looks_like_hallucination("本章完，请不吝点赞订阅") is True
        assert looks_like_hallucination("subtitle by someone") is True
        assert looks_like_hallucination("字幕由 AI 生成") is True

    def test_weak_whole_sentence_only(self):
        assert looks_like_hallucination("谢谢观看") is True
        assert looks_like_hallucination("谢谢观看！") is True
        # ★ v1.1 新增的音频套话
        assert looks_like_hallucination("欢迎收听") is True
        assert looks_like_hallucination("感谢收看。") is True

    def test_weak_inside_sentence_kept(self):
        assert looks_like_hallucination("他轻声说了句晚安，转身离开") is False
        assert looks_like_hallucination("大家好才是真的好") is False

    def test_normal_kept_and_empty_killed(self):
        assert looks_like_hallucination("三体人舰队抵达太阳系。") is False
        assert looks_like_hallucination("") is True
        assert looks_like_hallucination(None) is True


# ============================================================
# 复读折叠
# ============================================================
class TestCollapse:
    def test_half_split_still_works(self):
        assert collapse_repeats("abcdefabcdef") == "abcdef"
        assert collapse_repeats("深深爱你深深爱你") == "深深爱你"

    def test_unit_loop_three_plus(self):
        assert collapse_repeats("好的，好的，好的，好的") == "好的"
        assert collapse_repeats("从前有座山。从前有座山。从前有座山。") \
            == "从前有座山。"
        assert collapse_repeats("thank you. thank you. thank you.") \
            == "thank you."

    def test_two_repeats_kept(self):
        """重复 2 次可能是对话回声，刻意不折叠。"""
        assert collapse_repeats("从前有座山，从前有座山") \
            == "从前有座山，从前有座山"

    def test_normal_untouched(self):
        t = "罗辑把枪抵在自己胸口，对着空无一人的旷野说出了那个咒语。"
        assert collapse_repeats(t) == t

    def test_short_untouched(self):
        assert collapse_repeats("好的好的") == "好的好的"


# ============================================================
# 段合并
# ============================================================
class TestMerge:
    def test_nearby_merged_with_cjk_comma(self):
        segs = [{"start": 0.0, "end": 2.0, "text": "第一句"},
                {"start": 2.3, "end": 4.0, "text": "第二句"}]
        out = merge_segments(segs)
        assert len(out) == 1
        assert out[0]["text"] == "第一句，第二句"
        assert out[0]["start"] == 0.0 and out[0]["end"] == 4.0

    def test_big_gap_not_merged(self):
        segs = [{"start": 0.0, "end": 2.0, "text": "第一句"},
                {"start": 6.0, "end": 8.0, "text": "第二句"}]
        assert len(merge_segments(segs)) == 2

    def test_max_chars_cap(self):
        segs = [{"start": 0.0, "end": 2.0, "text": "字" * 30},
                {"start": 2.1, "end": 4.0, "text": "字" * 30}]
        out = merge_segments(segs, max_chars=50)
        assert len(out) == 2, "合并后超上限不许并"

    def test_english_joiner_is_space(self):
        segs = [{"start": 0.0, "end": 2.0, "text": "hello world"},
                {"start": 2.1, "end": 4.0, "text": "next part"}]
        out = merge_segments(segs)
        assert out[0]["text"] == "hello world next part"

    def test_existing_punct_no_double(self):
        segs = [{"start": 0.0, "end": 2.0, "text": "第一句。"},
                {"start": 2.1, "end": 4.0, "text": "第二句"}]
        assert merge_segments(segs)[0]["text"] == "第一句。第二句"

    def test_overlap_clamped(self):
        segs = [{"start": 0.0, "end": 10.0, "text": "字" * 60},
                {"start": 8.0, "end": 12.0, "text": "字" * 60}]
        out = merge_segments(segs)
        assert out[0]["start"] == 0.0 and out[0]["end"] == 10.0
        assert out[1]["start"] == 10.0, "★ 重叠时间轴没钳住"
        assert out[1]["end"] >= out[1]["start"]

    def test_input_not_mutated(self):
        segs = [{"start": 0.0, "end": 2.0, "text": "甲"},
                {"start": 2.1, "end": 4.0, "text": "乙"}]
        merge_segments(segs)
        assert segs[0] == {"start": 0.0, "end": 2.0, "text": "甲"}


# ============================================================
# SRT 输出
# ============================================================
class TestWriteSrt:
    def test_format_and_index(self, tmp_path):
        segs = [{"start": 0.0, "end": 1.5, "text": "甲"},
                {"start": 2.0, "end": 3.25, "text": "乙"}]
        p = write_srt(segs, tmp_path / "out.srt")
        text = p.read_text(encoding="utf-8")
        assert text.startswith("1\n00:00:00,000 --> 00:00:01,500\n甲\n")
        assert "2\n00:00:02,000 --> 00:00:03,250\n乙\n" in text

    def test_empty_text_skipped_and_negative_clamped(self, tmp_path):
        segs = [{"start": -0.2, "end": 1.0, "text": "  "},
                {"start": -0.5, "end": 2.0, "text": "正文"}]
        p = write_srt(segs, str(tmp_path / "o.srt"))
        text = p.read_text(encoding="utf-8")
        assert text == "1\n00:00:00,000 --> 00:00:02,000\n正文\n"
        assert _ts(-1.0) == "00:00:00,000", "负时间不许出负号"


# ============================================================
# 缓存
# ============================================================
class TestCache:
    def test_roundtrip(self, tmp_path):
        segs = [{"start": 0.0, "end": 1.0, "text": "甲"}]
        save_cache(tmp_path, "k1", segs)
        assert load_cache(tmp_path, "k1") == segs
        assert not (tmp_path / "k1.json.tmp").exists(), "原子写不许留 tmp"

    def test_corrupt_cache_returns_none(self, tmp_path):
        (tmp_path / "bad.json").write_text("{oops", encoding="utf-8")
        assert load_cache(tmp_path, "bad") is None
        assert load_cache(tmp_path, "missing") is None

    def test_key_sensitivity(self, tmp_path):
        f = tmp_path / "a.mp3"
        f.write_bytes(b"x")
        base = cache_key(f, "base", "zh")
        assert base == cache_key(f, "base", "zh")
        assert base != cache_key(f, "base", "zh", extra="beam=1|cond=False"), \
            "★ extra 不进键，改参数会命中旧缓存"
        assert base != cache_key(f, "small", "zh")
        assert base != cache_key(f, "base", "en")
        st = f.stat()
        import os
        os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
        assert base != cache_key(f, "base", "zh"), "文件更新后必须换键"


# ============================================================
# 文件扫描（--ext 大小写回归）
# ============================================================
class TestFindAudios:
    @pytest.fixture
    def lib(self, tmp_path):
        (tmp_path / "a.mp3").write_bytes(b"x")
        (tmp_path / "b.MP3").write_bytes(b"x")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "c.m4a").write_bytes(b"x")
        (tmp_path / "note.txt").write_text("x")
        return tmp_path

    def test_default_exts(self, lib):
        names = {p.name for p in make_srt.find_audios(lib, None)}
        assert names == {"a.mp3", "b.MP3", "c.m4a"}

    def test_ext_uppercase_regression(self, lib):
        """★ v1.1 修复：「--ext MP3」原来一个文件都扫不出来；
        现在大小写不敏感，.mp3 / .MP3 都算 mp3。"""
        names = {p.name for p in make_srt.find_audios(lib, {"MP3"})}
        assert names == {"a.mp3", "b.MP3"}

    def test_single_file_passthrough(self, lib):
        got = make_srt.find_audios(lib / "a.mp3", None)
        assert got == [lib / "a.mp3"]


# ============================================================
# transcribe_audio：参数透传 / 清洗 / 进度（假模型，不开真识别）
# ============================================================
class FakeSeg:
    def __init__(self, start, end, text):
        self.start, self.end, self.text = start, end, text


class FakeModel:
    """记录 transcribe 的 kwargs，按预置脚本吐段。"""

    def __init__(self, segs):
        self.segs = segs
        self.kw = None

    def transcribe(self, path, **kw):
        self.kw = kw
        return iter(self.segs), SimpleNamespace(language="zh", duration=400.0)


@pytest.fixture
def fake_model(monkeypatch):
    def install(segs):
        m = FakeModel(segs)
        monkeypatch.setitem(srt_core._model_cache, "base|auto|auto", m)
        return m
    return install


class TestTranscribe:
    def test_defaults_and_passthrough(self, fake_model):
        m = fake_model([FakeSeg(0, 2, "正常内容。")])
        out = transcribe_audio("x.mp3", model_name="base", lang="zh")
        assert out == [{"start": 0.0, "end": 2.0, "text": "正常内容。"}]
        assert m.kw["condition_on_previous_text"] is False, \
            "★ 默认必须关上文条件（幻觉复读的根源）"
        assert m.kw["beam_size"] == 5
        assert m.kw["initial_prompt"] == srt_core._ZH_PROMPT
        assert m.kw["vad_filter"] is True

    def test_condition_flag_restores_old(self, fake_model):
        m = fake_model([FakeSeg(0, 2, "内容")])
        transcribe_audio("x.mp3", lang="zh", condition_on_previous=True)
        assert m.kw["condition_on_previous_text"] is True

    def test_cleaning_pipeline(self, fake_model):
        segs = [
            FakeSeg(0, 2, "以下是普通话的句子，请输出简体中文并加上标点。"),
            FakeSeg(2, 4, "请不吝点赞订阅"),
            FakeSeg(4, 6, "谢谢观看，谢谢观看，谢谢观看"),
            FakeSeg(6, 8, "  真正文一段  "),
            FakeSeg(8, 10, "   "),
        ]
        fake_model(segs)
        out = transcribe_audio("x.mp3", lang="zh")
        texts = [s["text"] for s in out]
        # 「谢谢观看」连发先被折叠成单句，再被弱幻觉表整句杀掉；
        # 引导语回吐、强特征、纯空白段各自有防线
        assert texts == ["真正文一段"], texts

    def test_progress_callback_throttled(self, fake_model):
        m = fake_model([FakeSeg(0, 130, "一段"), FakeSeg(130, 260, "二段"),
                        FakeSeg(260, 261, "三段")])
        marks = []
        transcribe_audio("x.mp3", lang="zh",
                         on_progress=lambda d, t: marks.append((d, t)))
        assert len(marks) == 2, "每推进 ~120s 才回调一次"
        assert marks[0] == (130.0, 400.0)
        assert m.kw["condition_on_previous_text"] is False

    def test_progress_exception_swallowed(self, fake_model):
        fake_model([FakeSeg(0, 130, "一段")])
        def boom(d, t):
            raise RuntimeError("UI 炸了也不许影响转写")
        out = transcribe_audio("x.mp3", lang="zh", on_progress=boom)
        assert len(out) == 1

    # ---------- ★ v1.2：should_stop（GUI 停止按钮用） ----------
    def test_should_stop_before_model_load(self):
        """开跑就命中停止：连模型都不加载（不依赖 faster_whisper 也能测）。"""
        assert transcribe_audio("x.mp3", should_stop=lambda: True) == []

    def test_should_stop_midway_returns_partial(self, fake_model):
        """识别中命中停止：停在当前位置，返回已识别的部分段。"""
        fake_model([FakeSeg(0, 2, "第一段"), FakeSeg(2, 4, "第二段"),
                    FakeSeg(4, 6, "第三段")])
        flags = iter([False, False, True])   # 开跑前 False；第1段前 False；第2段前 True
        out = transcribe_audio("x.mp3", lang="zh", should_stop=lambda: next(flags))
        assert [s["text"] for s in out] == ["第一段"]

    def test_should_stop_none_keeps_cli_behavior(self, fake_model):
        """默认 should_stop=None：CLI 行为完全不变，跑完全部段。"""
        fake_model([FakeSeg(0, 2, "一段"), FakeSeg(2, 4, "二段")])
        out = transcribe_audio("x.mp3", lang="zh")
        assert [s["text"] for s in out] == ["一段", "二段"]


# ============================================================
# CLI 冒烟（假转写，验证扫描 → 缓存 → 合并 → 落盘）
# ============================================================
class TestCLI:
    def _argv(self, *extra):
        return ["make_srt.py", *extra]

    @pytest.fixture
    def audio(self, tmp_path):
        a = tmp_path / "book.mp3"
        a.write_bytes(b"fake")
        return tmp_path, a

    def test_full_run_and_cache_hit(self, audio, tmp_path, monkeypatch, caplog):
        root, a = audio
        cache = tmp_path / "cache"
        calls = []
        segs = [{"start": 0.0, "end": 2.0, "text": "第一句"},
                {"start": 2.1, "end": 4.0, "text": "第二句"}]

        def fake_transcribe(path, **kw):
            calls.append(path)
            return [dict(s) for s in segs]

        monkeypatch.setattr(make_srt, "transcribe_audio", fake_transcribe)
        monkeypatch.setattr(sys, "argv", self._argv(
            str(root), "--cache-dir", str(cache), "--lang", "zh"))
        assert make_srt.main() == 0
        srt = (root / "book.srt").read_text(encoding="utf-8")
        # 默认开合并：两条碎段并成一条
        assert srt.count("\n00:00:0") == 1, "碎段应被合并"
        assert "第一句，第二句" in srt
        assert len(calls) == 1
        assert list(cache.glob("*.json")), "结果要写缓存"

        # 第二遍：缓存命中，不再识别，结果一致
        (root / "book.srt").unlink()
        monkeypatch.setattr(sys, "argv", self._argv(
            str(root), "--cache-dir", str(cache), "--lang", "zh"))
        assert make_srt.main() == 0
        assert (root / "book.srt").read_text(encoding="utf-8") == srt
        assert len(calls) == 1, "★ 缓存命中时不应再转写"

    def test_no_merge_keeps_segments(self, audio, tmp_path, monkeypatch):
        root, a = audio
        monkeypatch.setattr(make_srt, "transcribe_audio",
                            lambda p, **kw: [
                                {"start": 0.0, "end": 2.0, "text": "甲"},
                                {"start": 2.1, "end": 4.0, "text": "乙"}])
        monkeypatch.setattr(sys, "argv", self._argv(
            str(root), "--cache-dir", str(tmp_path / "c"), "--no-cache",
            "--no-merge"))
        assert make_srt.main() == 0
        srt = (root / "book.srt").read_text(encoding="utf-8")
        assert "00:00:00,000 --> 00:00:02,000" in srt
        assert "00:00:02,100 --> 00:00:04,000" in srt

    def test_skip_existing_and_overwrite(self, audio, tmp_path, monkeypatch):
        root, a = audio
        (root / "book.srt").write_text("旧字幕", encoding="utf-8")
        calls = []
        monkeypatch.setattr(make_srt, "transcribe_audio",
                            lambda p, **kw: calls.append(p) or [])
        monkeypatch.setattr(sys, "argv", self._argv(
            str(root), "--cache-dir", str(tmp_path / "c"), "--no-cache"))
        assert make_srt.main() == 0
        assert calls == [], "已有字幕默认跳过"
        assert (root / "book.srt").read_text(encoding="utf-8") == "旧字幕"

        monkeypatch.setattr(sys, "argv", self._argv(
            str(root), "--cache-dir", str(tmp_path / "c"), "--no-cache",
            "--overwrite"))
        assert make_srt.main() == 0
        assert len(calls) == 1, "--overwrite 必须重做"

    def test_failure_returns_1_and_no_srt(self, audio, tmp_path, monkeypatch):
        root, a = audio
        def boom(p, **kw):
            raise RuntimeError("解码失败")
        monkeypatch.setattr(make_srt, "transcribe_audio", boom)
        monkeypatch.setattr(sys, "argv", self._argv(
            str(root), "--cache-dir", str(tmp_path / "c"), "--no-cache"))
        assert make_srt.main() == 1, "失败要反映在退出码上"
        assert not (root / "book.srt").exists()

    def test_dry_run_touches_nothing(self, audio, tmp_path, monkeypatch):
        root, a = audio
        monkeypatch.setattr(make_srt, "transcribe_audio",
                            lambda p, **kw: (_ for _ in ()).throw(
                                AssertionError("dry-run 不许转写")))
        monkeypatch.setattr(sys, "argv", self._argv(str(root), "--dry-run"))
        assert make_srt.main() == 0
        assert not (root / "book.srt").exists()


def test_version_declared():
    assert srt_core.__version__ == "1.3.0"
    assert make_srt.__version__ == "1.3.0"


def test_gui_smoke():
    """★ v1.2：GUI 能构建、轮询跑 400ms 后自动关窗，全程不报错。

    无显示环境（CI/SSH）跳过；比纯 import 测试强一点：连 Tk 构建、
    控件布局、设置加载一起验了。
    """
    try:
        import tkinter as tk
        probe = tk.Tk()
        probe.destroy()
    except Exception:
        pytest.skip("无显示环境，跳过 GUI 冒烟")
    import queue

    import make_srt_gui
    app = make_srt_gui.SrtGuiApp(queue.Queue())
    app.root.after(400, app.root.destroy)
    app.run()
    assert not (app.worker and app.worker.is_alive()), "未点开始不应有 worker"
