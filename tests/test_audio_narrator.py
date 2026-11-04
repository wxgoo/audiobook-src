#!/usr/bin/env python3
"""4.6.0-18 有声书演播者修复的回归测试。

覆盖的缺陷：
  中文有声资源的 ID3 里 TPE1(artist) 填的是播音员，不是作者。旧实现直接拿
  artist 当作者，导致书库凭空出现「李慧敏」这类伪作者（用户库里那本
  「哈利波特与魔法石」，每首音轨都是 TPE1=李慧敏，真作者 J·K·罗琳 完全缺失）。

修法：artist 一律视为演播者。作者优先取同名电子书，否则佚名；
      演播者写进 #narrator 列 + tags + comments，信息不丢但不占作者位。
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from webserver.services import audios_import as ai


class FakeTag(list):
    """模拟 mutagen 的标签值（list 子类，取 [0] 得到字符串）。"""

    def __init__(self, value):
        super().__init__([value])


class FakeAudio:
    def __init__(self, tags):
        self.tags = tags


class TestExtractReturnsNarrator(unittest.TestCase):
    """_extract_audio_metadata 第二个返回值必须是演播者，语义不能含糊。"""

    def _run(self, tags):
        with mock.patch("mutagen.File", return_value=FakeAudio(tags)):
            return ai._extract_audio_metadata("/tmp/x.mp3", "兜底书名")

    def test_artist_is_returned_as_narrator(self):
        """用户实测场景：TALB=书名，TPE1=李慧敏。"""
        title, narrator = self._run({
            "album": FakeTag("哈利波特与魔法石"),
            "artist": FakeTag("李慧敏"),
        })
        self.assertEqual(title, "哈利波特与魔法石")
        self.assertEqual(narrator, "李慧敏")

    def test_albumartist_fallback(self):
        title, narrator = self._run({
            "album": FakeTag("三体"),
            "albumartist": FakeTag("某人"),
        })
        self.assertEqual(title, "三体")
        self.assertEqual(narrator, "某人")

    def test_title_falls_back_when_no_album(self):
        title, narrator = self._run({
            "title": FakeTag("第一卷"),
            "artist": FakeTag("某播音员"),
        })
        self.assertEqual(title, "第一卷")
        self.assertEqual(narrator, "某播音员")

    def test_missing_artist_gives_none_narrator(self):
        title, narrator = self._run({"album": FakeTag("某书")})
        self.assertEqual(title, "某书")
        self.assertIsNone(narrator)

    def test_unreadable_file_returns_fallback(self):
        with mock.patch("mutagen.File", return_value=None):
            title, narrator = ai._extract_audio_metadata("/tmp/x.mp3", "兜底")
        self.assertEqual(title, "兜底")
        self.assertIsNone(narrator)

    def test_exception_swallowed(self):
        with mock.patch("mutagen.File", side_effect=RuntimeError("boom")):
            title, narrator = ai._extract_audio_metadata("/tmp/x.mp3", "兜底")
        self.assertEqual(title, "兜底")
        self.assertIsNone(narrator)

    def test_docstring_states_narrator_semantics(self):
        """函数名/文档必须写明第二个返回值是演播者，避免以后又被当作者用。"""
        doc = ai._extract_audio_metadata.__doc__ or ""
        self.assertIn("演播", doc)
        self.assertIn("不是作者", doc)


class TestAttachNarrator(unittest.TestCase):
    """attach_narrator 要把演播者写进三处，且任何失败都不能抛。"""

    def make_db(self, tags=None, comments=""):
        db = mock.Mock()
        meta = mock.Mock()
        meta.tags = list(tags or [])
        meta.comments = comments
        db.get_metadata.return_value = meta
        db.new_api.set_field = mock.Mock()
        return db

    def test_writes_narrator_column(self):
        db = self.make_db()
        ai.attach_narrator(db, 7, "李慧敏")
        # 第一次 set_field 必须是 #narrator 列
        first_call = db.new_api.set_field.call_args_list[0]
        self.assertEqual(first_call.args[0], "#narrator")
        self.assertEqual(first_call.args[1], {7: "李慧敏"})

    def test_writes_tag(self):
        db = self.make_db()
        ai.attach_narrator(db, 7, "李慧敏")
        fields = [c.args[0] for c in db.new_api.set_field.call_args_list]
        self.assertIn("tags", fields)
        tag_call = next(c for c in db.new_api.set_field.call_args_list if c.args[0] == "tags")
        self.assertTrue(any("李慧敏" in t for t in tag_call.args[1][7]))

    def test_appends_to_existing_comments(self):
        db = self.make_db(comments="原有简介")
        ai.attach_narrator(db, 7, "李慧敏")
        cmt_call = next(c for c in db.new_api.set_field.call_args_list if c.args[0] == "comments")
        value = cmt_call.args[1][7]
        self.assertIn("原有简介", value)
        self.assertIn("李慧敏", value)

    def test_skips_existing_tag(self):
        """重复导入时不能把同一个标签写两遍。"""
        db = self.make_db(tags=["演播:李慧敏"])
        ai.attach_narrator(db, 7, "李慧敏")
        fields = [c.args[0] for c in db.new_api.set_field.call_args_list]
        self.assertNotIn("tags", fields)

    def test_skips_existing_comment(self):
        db = self.make_db(comments="演播：李慧敏")
        ai.attach_narrator(db, 7, "李慧敏")
        fields = [c.args[0] for c in db.new_api.set_field.call_args_list]
        self.assertNotIn("comments", fields)

    def test_empty_narrator_is_noop(self):
        db = self.make_db()
        ai.attach_narrator(db, 7, None)
        ai.attach_narrator(db, 7, "")
        db.new_api.set_field.assert_not_called()

    def test_never_raises_on_db_failure(self):
        db = self.make_db()
        db.new_api.set_field.side_effect = RuntimeError("db down")
        ai.attach_narrator(db, 7, "李慧敏")  # 不应抛异常

    def test_never_raises_when_metadata_missing(self):
        db = self.make_db()
        db.get_metadata.side_effect = RuntimeError("gone")
        ai.attach_narrator(db, 7, "李慧敏")  # 不应抛异常


class TestImportDoesNotUseArtistAsAuthor(unittest.TestCase):
    """源码层面的硬约束：建书处不能再把 artist 当 author。"""

    def test_no_artist_as_author(self):
        import inspect

        src = inspect.getsource(ai.AudioBookImporter._do_import_internal)
        self.assertNotIn(
            "title, author = _extract_audio_metadata",
            src,
            "建书处不应再把 _extract_audio_metadata 的第二个返回值当作者",
        )

    def test_author_set_to_anonymous_for_audio_only(self):
        import inspect

        src = inspect.getsource(ai.AudioBookImporter._do_import_internal)
        # 纯音频分支里必须有显式的佚名兜底
        self.assertIn('author = _("佚名")', src)

    def test_narrator_attached(self):
        import inspect

        src = inspect.getsource(ai.AudioBookImporter._do_import_internal)
        self.assertIn("attach_narrator", src)


class TestScanSidecarAudioWritesNarrator(unittest.TestCase):
    """扫描导入电子书时，同目录音频的演播者也要写进去。

    用户库里 15 本哈利波特都是 epub+mp3 混在一个目录，扫书时音频被
    _sync_sidecar_audio 带进书的 .audio/，但那条路径从不调 attach_narrator，
    导致 #narrator 全空——演播者信息白白丢了。
    """

    def test_scan_service_calls_attach_narrator(self):
        import inspect

        from webserver.services import scan_service as ss

        src = inspect.getsource(ss.ScanService._sync_sidecar_audio)
        self.assertIn("attach_narrator", src)
        self.assertIn("_extract_audio_metadata", src)

    def test_narrator_reading_is_best_effort(self):
        """读标签失败不能让整个书目导入失败。

        判定方式：定位 `_extract_audio_metadata(` 这行**调用**（不是注释里的
        提及），从包含它的上一个 `try:` 起算，到方法末尾之间必须出现
        `except`。这样不依赖源码里的注释措辞。
        """
        import inspect
        import re

        from webserver.services import scan_service as ss

        src = inspect.getsource(ss.ScanService._sync_sidecar_audio)
        # 只认真正的调用形式，带左括号，避开注释/字符串里的裸词
        idx = src.find("_extract_audio_metadata(")
        self.assertGreater(idx, -1, "方法里没有 _extract_audio_metadata( 调用")

        head = src[:idx]
        try_pos = head.rfind("try:")
        self.assertGreater(try_pos, -1, "补演播者的调用没被 try 包住")

        # try 块必须闭合，且 except 要在方法体内（不能在 try 之前）
        tail = src[try_pos:]
        self.assertIn("except", tail, "有 try 但没 except")


if __name__ == "__main__":
    unittest.main()
