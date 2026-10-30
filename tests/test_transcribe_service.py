#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""音频转写文稿测试：不依赖真实 whisper，全部 mock。

覆盖两个后端（faster-whisper / openai-whisper）以及 SRT + TXT 双产物输出。
"""

import sys
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

from webserver.services import transcribe


# ---------------- 假后端 ----------------

class FakeSeg:
    """faster-whisper 的 Segment 是 dataclass，这里用简单对象模拟属性访问。"""

    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text


class FakeInfo:
    def __init__(self, duration):
        self.duration = duration


class FakeFasterModel:
    """faster-whisper 的 transcribe 返回 (生成器, info)"""

    def __init__(self, segments):
        self._segments = segments

    def transcribe(self, audio, language=None, beam_size=5, vad_filter=True,
                   word_timestamps=False, **_kw):
        return iter(self._segments), FakeInfo(self._segments[-1].end if self._segments else 0)


class FakeOpenAIModel:
    """openai-whisper 的 transcribe 返回 dict，verbose=True 时带 segments"""

    def __init__(self, segments):
        self._segments = segments

    def transcribe(self, audio, language=None, verbose=False, word_timestamps=False, **_kw):
        segs = [{"start": s.start, "end": s.end, "text": s.text} for s in self._segments]
        return {
            "text": " ".join(s.text.strip() for s in self._segments),
            "segments": segs if verbose else [],
        }


DEFAULT_SEGS = [
    FakeSeg(0.0, 2.44, " 第一章开始了。 "),
    FakeSeg(2.44, 5.10, "这是一段转写出来的文字。"),
]


def install_backend(kind="faster", segments=None):
    """把指定后端装进 sys.modules，并重置探测缓存。返回 contextmanager。"""
    segs = segments if segments is not None else DEFAULT_SEGS
    transcribe._model_cache.clear()
    transcribe._backend = None

    if kind == "faster":
        mod = types.ModuleType("faster_whisper")
        mod.WhisperModel = lambda *a, **kw: FakeFasterModel(segs)
        mod.__version__ = "1.2.1"
        # av 也必须存在，否则 _check_av_compat 的 ImportError 分支被跳过不影响；
        # 这里给个低版本让检查通过
        fake_av = types.ModuleType("av")
        fake_av.__version__ = "15.1.0"
        return mock.patch.dict(sys.modules,
                               {"faster_whisper": mod, "av": fake_av, "whisper": None})
    else:
        mod = types.ModuleType("whisper")
        mod.load_model = lambda name=None: FakeOpenAIModel(segs)
        return mock.patch.dict(sys.modules,
                               {"whisper": mod, "faster_whisper": None})


def reset_probe():
    transcribe._backend = None
    transcribe._model_cache.clear()


# ---------------- 测试 ----------------

class TestBackendDetection(unittest.TestCase):

    def setUp(self):
        reset_probe()

    def tearDown(self):
        reset_probe()

    def test_no_backend(self):
        with mock.patch.dict(sys.modules, {"whisper": None, "faster_whisper": None}):
            reset_probe()
            self.assertFalse(transcribe.whisper_available())
            self.assertEqual(transcribe.detect_backend(), "")

    def test_prefers_faster(self):
        with install_backend("faster"):
            self.assertEqual(transcribe.detect_backend(), "faster")
            self.assertTrue(transcribe.whisper_available())

    def test_falls_back_to_openai(self):
        with install_backend("openai"):
            self.assertEqual(transcribe.detect_backend(), "openai")

    def test_rejects_too_new_av(self):
        """av>=16 删掉了 metadata_errors 参数，必须在探测阶段拦下并报清晰错误。"""
        transcribe._backend = None
        fake_av = types.ModuleType("av")
        fake_av.__version__ = "19.0.2"
        with mock.patch.dict(sys.modules, {"av": fake_av}):
            with self.assertRaises(RuntimeError) as ctx:
                transcribe._check_av_compat()
            self.assertIn("av", str(ctx.exception))
            self.assertIn("<16", str(ctx.exception))

    def test_accepts_av_15(self):
        fake_av = types.ModuleType("av")
        fake_av.__version__ = "15.1.0"
        with mock.patch.dict(sys.modules, {"av": fake_av}):
            transcribe._check_av_compat()  # 不抛异常即通过

    def test_av_missing_is_ok(self):
        with mock.patch.dict(sys.modules, {"av": None}):
            # ImportError 被吞掉，视为可以通过（openai-whisper 后端不需要 av）
            transcribe._check_av_compat()


class TestSrtFormatting(unittest.TestCase):
    """SRT 时间码与文本清洗，前端 parseSRT 依赖这个格式"""

    def test_srt_time_format(self):
        self.assertEqual(transcribe._srt_time(0), "00:00:00,000")
        self.assertEqual(transcribe._srt_time(83.456), "00:01:23,456")
        self.assertEqual(transcribe._srt_time(3725.5), "01:02:05,500")
        self.assertEqual(transcribe._srt_time(-1), "00:00:00,000")

    def test_build_srt_basic(self):
        srt = transcribe.build_srt([
            {"start": 0.0, "end": 2.44, "text": " Chapter one. "},
            {"start": 2.44, "end": 5.1, "text": "Hello world."},
        ])
        self.assertIn("1\n00:00:00,000 --> 00:00:02,440\nChapter one.", srt)
        self.assertIn("2\n00:00:02,440 --> 00:00:05,100\nHello world.", srt)

    def test_srt_merges_newlines(self):
        """SRT 一条 cue 内不能有裸换行，否则前端会把它当成两条"""
        srt = transcribe.build_srt([
            {"start": 0.0, "end": 1.0, "text": "line1\nline2"},
        ])
        self.assertIn("line1 line2", srt)
        # 单条 cue = 序号 + 时间行 + 文本行 + 末尾空行，只应有一个空行分隔
        self.assertEqual(srt.strip().count("\n\n"), 0)

    def test_zero_length_segment_gets_min_duration(self):
        """end == start 时补 0.5s，否则前端 parseSRT 的 end>start 过滤会丢掉它"""
        srt = transcribe.build_srt([
            {"start": 5.1, "end": 5.1, "text": "zero"},
        ])
        self.assertIn("00:00:05,100 --> 00:00:05,600", srt)

    def test_empty_text_skipped(self):
        srt = transcribe.build_srt([
            {"start": 0.0, "end": 1.0, "text": "   "},
            {"start": 1.0, "end": 2.0, "text": "kept"},
        ])
        self.assertNotIn("\n\n\n", srt)
        self.assertIn("kept", srt)
        self.assertEqual(srt.count("-->"), 1)

    def test_cue_index_is_sequential(self):
        """跳过了空文本后，序号必须连续（前端不依赖，但播放器/编辑器会）"""
        srt = transcribe.build_srt([
            {"start": 0.0, "end": 1.0, "text": ""},
            {"start": 1.0, "end": 2.0, "text": "a"},
            {"start": 2.0, "end": 3.0, "text": "b"},
        ])
        self.assertTrue(srt.startswith("1\n"))
        self.assertIn("\n2\n", srt)
        self.assertNotIn("\n3\n", srt)


class TestTranscribeFile(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.tmp = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        reset_probe()
        # 先清掉上一轮留下的产物（.txt/.srt），再写测试用音频，
        # 否则会误删本用例自己的 chapter1.mp3
        for leftover in Path(self.tmp).glob("chapter*"):
            try:
                leftover.unlink()
            except OSError:
                pass
        self.audio = Path(self.tmp) / "chapter1.mp3"
        self.audio.write_bytes(b"fake audio")

    def tearDown(self):
        reset_probe()

    def test_writes_both_srt_and_txt(self):
        with install_backend("faster"):
            fracs = []
            ok, msg, txt = transcribe.transcribe_file(
                self.audio, model_size="small", lang="auto",
                progress_cb=lambda f, n="": fracs.append(f))
            self.assertTrue(ok, msg)
            out_txt = Path(txt)
            out_srt = out_txt.with_suffix(".srt")
            self.assertEqual(out_txt.name, "chapter1.txt")
            self.assertTrue(out_srt.exists(), "必须产出 .srt，播放器靠它做高亮跟随")
            self.assertIn("第一章开始了", out_txt.read_text("utf-8"))
            srt = out_srt.read_text("utf-8")
            self.assertIn("00:00:00,000 --> 00:00:02,440", srt)
            self.assertGreaterEqual(fracs[-1], 1.0)

    def test_keep_txt_false_only_writes_srt(self):
        with install_backend("faster"):
            ok, msg, txt = transcribe.transcribe_file(self.audio, keep_txt=False)
            self.assertTrue(ok, msg)
            self.assertTrue(Path(txt).with_suffix(".srt").exists())
            self.assertFalse(Path(txt).exists(), "keep_txt=False 时不应写 .txt")

    def test_openai_backend_also_writes_srt(self):
        with install_backend("openai"):
            ok, msg, txt = transcribe.transcribe_file(self.audio)
            self.assertTrue(ok, msg)
            srt = Path(txt).with_suffix(".srt").read_text("utf-8")
            self.assertIn("-->", srt)
            self.assertIn("第一章开始了", srt)

    def test_no_segments_reports_error(self):
        """纯音乐/静音时 VAD 会过滤掉全部片段，要给出明确提示而不是写空文件"""
        with install_backend("faster", segments=[]):
            ok, msg, txt = transcribe.transcribe_file(self.audio)
            self.assertFalse(ok)
            self.assertIn("没有识别到", msg)
            self.assertFalse(Path(self.tmp, "chapter1.srt").exists())

    def test_rejects_unsupported_ext(self):
        p = Path(self.tmp) / "note.exe"
        p.write_bytes(b"x")
        with install_backend("faster"):
            ok, msg, txt = transcribe.transcribe_file(p)
            self.assertFalse(ok)
            self.assertIn("不支持", msg)

    def test_rejects_missing_file(self):
        with install_backend("faster"):
            ok, msg, txt = transcribe.transcribe_file(Path(self.tmp) / "nope.mp3")
            self.assertFalse(ok)
            self.assertIn("不存在", msg)

    def test_unavailable_reports_error(self):
        with mock.patch.dict(sys.modules, {"whisper": None, "faster_whisper": None}):
            reset_probe()
            ok, msg, txt = transcribe.transcribe_file(self.audio)
            self.assertFalse(ok)
            self.assertIn("whisper", msg)

    def test_transcribe_many_counts(self):
        b = Path(self.tmp) / "chapter2.mp3"
        b.write_bytes(b"x")
        with install_backend("faster"):
            fracs = []
            done, failed, results = transcribe.transcribe_many(
                [self.audio, b], progress_cb=lambda f, n="": fracs.append(f))
            self.assertEqual((done, failed), (2, 0))
            self.assertEqual(len(results), 2)
            self.assertTrue(all(r["ok"] for r in results))
            # 每条结果都要带上 srt 路径，方便前端提示「字幕已生成」
            self.assertTrue(all(r["srt"].endswith(".srt") for r in results))
            self.assertGreaterEqual(fracs[-1], 1.0)

    def test_stop_event_cancels_batch(self):
        with install_backend("faster"):
            stop = threading.Event()
            stop.set()
            done, failed, results = transcribe.transcribe_many(
                [self.audio], stop_event=stop)
            self.assertEqual(done, 0)
            self.assertEqual(results, [])


class TestCollectAudioFiles(unittest.TestCase):
    """目录自动展开成音频文件列表"""

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.tmp = tempfile.mkdtemp()
        base = Path(cls.tmp) / "有声书"
        (base / "第一季").mkdir(parents=True)
        (base / "第一季" / "ep01.mp3").write_bytes(b"x")
        (base / "第一季" / "ep02.M4B").write_bytes(b"x")   # 大写扩展名
        (base / "ep03.flac").write_bytes(b"x")
        (base / "cover.jpg").write_bytes(b"x")              # 非音频
        (base / ".hidden.mp3").write_bytes(b"x")            # 隐藏文件跳过
        (base / "readme.txt").write_bytes(b"x")

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_directory_expands_recursively(self):
        files, skipped = transcribe.collect_audio_files([Path(self.tmp) / "有声书"])
        names = sorted(Path(f).name for f in files)
        self.assertEqual(names, ["ep01.mp3", "ep02.M4B", "ep03.flac"])
        self.assertEqual(skipped, [])

    def test_mixed_files_and_dirs(self):
        base = Path(self.tmp) / "有声书"
        files, skipped = transcribe.collect_audio_files(
            [base / "ep03.flac", base / "第一季", base / "readme.txt"])
        self.assertEqual(len(files), 3)
        self.assertEqual(skipped, [str(base / "readme.txt")])

    def test_dedup_and_missing(self):
        base = Path(self.tmp) / "有声书"
        files, skipped = transcribe.collect_audio_files(
            [base, base / "ep03.flac", Path(self.tmp) / "不存在"])
        self.assertEqual(len(files), 3)
        self.assertEqual(skipped, [str(Path(self.tmp) / "不存在")])


if __name__ == "__main__":
    unittest.main()
