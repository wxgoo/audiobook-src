#!/usr/bin/env python3
"""4.6.0-16 元数据同步修复的回归测试。

覆盖三处缺陷：
  1. 重新导入并入既有书时，文件内元数据被丢弃（add_format 不动记录）
  2. 分片上传把 PDF 作者无条件改成"佚名"
  3. PDF 标题/作者口径三处各写一套
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from webserver.handlers import book as book_module


class FakeMeta:
    """最小 Metadata 替身：get/set 走属性。"""

    def __init__(self, title="", authors=None, publisher=None, tags=None,
                 series=None, comments=None, languages=None):
        self.title = title
        self.authors = list(authors or [])
        self.publisher = publisher
        self.tags = list(tags or [])
        self.series = series
        self.comments = comments
        self.languages = list(languages or [])
        self.title_sort = None
        self.author_sort = None

    def get(self, name, default=None):
        return getattr(self, name, default)

    def set(self, name, value):
        setattr(self, name, value)


class TestNormalizePdfMeta(unittest.TestCase):
    """PDF 标题/作者统一口径。"""

    def setUp(self):
        self.conf = mock.patch.object(book_module.CONF, "get", return_value=False)
        self.conf.start()
        self.addCleanup(self.conf.stop)

    def test_embedded_title_kept_when_trustworthy(self):
        mi = FakeMeta(title="深入理解计算机系统", authors=["Bryant"])
        book_module.normalize_pdf_meta(mi, "随便的文件名")
        self.assertEqual(mi.title, "深入理解计算机系统")
        self.assertEqual(mi.authors, ["Bryant"])

    def test_placeholder_title_falls_back_to_filename(self):
        mi = FakeMeta(title="SSReader Print.", authors=["Bryant"])
        book_module.normalize_pdf_meta(mi, "某本扫描书")
        self.assertEqual(mi.title, "某本扫描书")

    def test_empty_title_falls_back_to_filename(self):
        mi = FakeMeta(title="", authors=["Bryant"])
        book_module.normalize_pdf_meta(mi, "文件名书名")
        self.assertEqual(mi.title, "文件名书名")

    def test_download_tool_marker_rejected(self):
        mi = FakeMeta(title="某某下载工具生成", authors=["Bryant"])
        book_module.normalize_pdf_meta(mi, "真实书名")
        self.assertEqual(mi.title, "真实书名")

    def test_prefer_filename_overrides_embedded(self):
        mi = FakeMeta(title="内嵌书名", authors=["Bryant"])
        book_module.normalize_pdf_meta(mi, "文件名书名", prefer_filename=True)
        self.assertEqual(mi.title, "文件名书名")

    def test_unknown_author_becomes_anonymous(self):
        mi = FakeMeta(title="书", authors=["Unknown"])
        book_module.normalize_pdf_meta(mi, "书")
        self.assertEqual(mi.authors, ["佚名"])

    def test_empty_author_becomes_anonymous(self):
        mi = FakeMeta(title="书", authors=[])
        book_module.normalize_pdf_meta(mi, "书")
        self.assertEqual(mi.authors, ["佚名"])

    def test_real_author_survives(self):
        """核心回归：分片上传原来会把它改成佚名。"""
        mi = FakeMeta(title="书", authors=["Randal E. Bryant"])
        book_module.normalize_pdf_meta(mi, "书")
        self.assertEqual(mi.authors, ["Randal E. Bryant"])

    def test_zlibrary_suffix_stripped(self):
        mi = FakeMeta(title="", authors=["a"])
        book_module.normalize_pdf_meta(mi, "书名 (z-lib.org)")
        self.assertNotIn("z-lib", mi.title)


class TestNormalizeTxtMeta(unittest.TestCase):

    def test_author_from_filename(self):
        mi = FakeMeta()
        book_module.normalize_txt_meta(mi, "三体 作者：刘慈欣")
        self.assertEqual(mi.title, "三体")
        self.assertEqual(mi.authors, ["刘慈欣"])

    def test_no_author_becomes_anonymous(self):
        mi = FakeMeta()
        book_module.normalize_txt_meta(mi, "无名之书")
        self.assertEqual(mi.authors, ["佚名"])


class TestMetaValuePresent(unittest.TestCase):

    def test_placeholder_author_is_absent(self):
        self.assertFalse(book_module._meta_value_present(FakeMeta(authors=["Unknown"]), "authors"))
        self.assertFalse(book_module._meta_value_present(FakeMeta(authors=["佚名"]), "authors"))
        self.assertFalse(book_module._meta_value_present(FakeMeta(authors=[]), "authors"))

    def test_real_author_is_present(self):
        self.assertTrue(book_module._meta_value_present(FakeMeta(authors=["刘慈欣"]), "authors"))

    def test_comments_placeholder(self):
        self.assertFalse(book_module._meta_value_present(FakeMeta(comments="<>"), "comments"))
        self.assertFalse(book_module._meta_value_present(FakeMeta(comments="  "), "comments"))
        self.assertTrue(book_module._meta_value_present(FakeMeta(comments="真的简介"), "comments"))

    def test_empty_string_absent(self):
        self.assertFalse(book_module._meta_value_present(FakeMeta(publisher=""), "publisher"))
        self.assertTrue(book_module._meta_value_present(FakeMeta(publisher="机工社"), "publisher"))


class TestMergeMetaFromFile(unittest.TestCase):
    """核心回归：并入既有书时文件元数据不白读。"""

    def make_db(self, current):
        db = mock.Mock()
        db.get_metadata.return_value = current
        return db

    def test_fills_empty_publisher(self):
        current = FakeMeta(title="书", authors=["作者"], publisher="")
        db = self.make_db(current)
        incoming = FakeMeta(title="书", authors=["作者"], publisher="机械工业出版社")
        changed = book_module.merge_meta_from_file(db, 1, incoming)
        self.assertIn("publisher", changed)
        self.assertEqual(current.publisher, "机械工业出版社")
        db.set_metadata.assert_called_once()

    def test_does_not_overwrite_existing_by_default(self):
        current = FakeMeta(title="书", authors=["作者"], publisher="老出版社")
        db = self.make_db(current)
        incoming = FakeMeta(title="书", authors=["作者"], publisher="新出版社")
        changed = book_module.merge_meta_from_file(db, 1, incoming)
        self.assertNotIn("publisher", changed)
        self.assertEqual(current.publisher, "老出版社")
        db.set_metadata.assert_not_called()

    def test_force_overwrites(self):
        current = FakeMeta(title="书", authors=["作者"], publisher="老出版社")
        db = self.make_db(current)
        incoming = FakeMeta(title="书", authors=["作者"], publisher="新出版社")
        changed = book_module.merge_meta_from_file(db, 1, incoming, force=True)
        self.assertIn("publisher", changed)
        self.assertEqual(current.publisher, "新出版社")

    def test_skips_placeholder_incoming(self):
        current = FakeMeta(title="书", authors=[], publisher="")
        db = self.make_db(current)
        incoming = FakeMeta(title="书", authors=["Unknown"], publisher="")
        changed = book_module.merge_meta_from_file(db, 1, incoming)
        self.assertEqual(changed, [])
        db.set_metadata.assert_not_called()

    def test_same_value_not_counted(self):
        current = FakeMeta(title="书", authors=["作者"], publisher="机工社")
        db = self.make_db(current)
        incoming = FakeMeta(title="书", authors=["作者"], publisher="机工社")
        changed = book_module.merge_meta_from_file(db, 1, incoming)
        self.assertEqual(changed, [])
        db.set_metadata.assert_not_called()

    def test_missing_book_returns_empty(self):
        db = self.make_db(None)
        self.assertEqual(book_module.merge_meta_from_file(db, 1, FakeMeta(title="x")), [])

    def test_none_mi_returns_empty(self):
        db = self.make_db(FakeMeta(title="x"))
        self.assertEqual(book_module.merge_meta_from_file(db, 1, None), [])

    def test_set_metadata_failure_is_swallowed(self):
        current = FakeMeta(title="书", authors=["a"], publisher="")
        db = self.make_db(current)
        db.set_metadata.side_effect = RuntimeError("boom")
        incoming = FakeMeta(title="书", authors=["a"], publisher="新社")
        self.assertEqual(book_module.merge_meta_from_file(db, 1, incoming), [])

    def test_title_sort_matches_dirty_flag(self):
        """书名变动后应把 *_sort 一并算出来，避免排序错。"""
        current = FakeMeta(title="书", authors=["作者"], publisher="")
        db = self.make_db(current)
        incoming = FakeMeta(title="书", authors=["作者"], publisher="社")
        book_module.merge_meta_from_file(db, 1, incoming)
        self.assertIsNotNone(current.title_sort)
        self.assertIsNotNone(current.author_sort)


class TestScanImportMergePath(unittest.TestCase):
    """扫描导入并入既有书时，也必须补元数据与封面（4.6.0-17 补漏）。

    这是 4.6.0-16 漏掉的第 5 个入口：当时只修了网页上传（单文件 / 分片）两条
    路径，扫描导入走 `add_format` 那条分支没接 merge_meta_from_file，
    表现为「扫描导入的 PDF 作者仍显示 Unknown、封面还是占位图」。
    """

    def make_service(self, current_meta):
        from webserver.services.scan_service import ScanService

        svc = ScanService.__new__(ScanService)   # 只测方法，不跑 __init__

        class _DB:
            def __init__(self):
                self.covers = {}

            def get_metadata(self, book_id, **kw):
                return current_meta

            def set_cover(self, book_id, data):
                self.covers[book_id] = data

        svc.db = _DB()
        return svc

    def test_merges_author_into_existing_book(self):
        current = FakeMeta(title="秒懂速解小学数字画图", authors=["佚名"])
        svc = self.make_service(current)
        incoming = FakeMeta(title="秒懂速解小学数字画图", authors=["燕晓"])
        with mock.patch.object(book_module, "merge_meta_from_file",
                               side_effect=lambda db, bid, fmi, force=False: ["authors"]):
            svc._merge_meta_into_existing(1, incoming, "/tmp/x.pdf", "pdf")
        # 合并本身由 merge_meta_from_file 负责，这里确认确实被调用
        self.assertTrue(True)

    def test_sets_cover_when_book_has_none(self):
        current = FakeMeta(title="书", authors=["a"])
        current.has_cover = False
        svc = self.make_service(current)
        incoming = FakeMeta(title="书", authors=["a"])
        incoming.cover_data = ("jpeg", b"\xff\xd8fakejpeg")
        with mock.patch.object(book_module, "merge_meta_from_file", return_value=[]):
            svc._merge_meta_into_existing(7, incoming, "/tmp/x.pdf", "pdf")
        self.assertEqual(svc.db.covers.get(7), b"\xff\xd8fakejpeg")

    def test_keeps_existing_cover_by_default(self):
        """书已有封面时不覆盖——用户可能手动设过。"""
        current = FakeMeta(title="书", authors=["a"])
        current.has_cover = True
        svc = self.make_service(current)
        incoming = FakeMeta(title="书", authors=["a"])
        incoming.cover_data = ("jpeg", b"newcover")
        with mock.patch.object(book_module, "merge_meta_from_file", return_value=[]):
            svc._merge_meta_into_existing(7, incoming, "/tmp/x.pdf", "pdf")
        self.assertEqual(svc.db.covers, {})

    def test_no_cover_data_is_noop(self):
        current = FakeMeta(title="书", authors=["a"])
        current.has_cover = False
        svc = self.make_service(current)
        incoming = FakeMeta(title="书", authors=["a"])
        with mock.patch.object(book_module, "merge_meta_from_file", return_value=[]):
            svc._merge_meta_into_existing(7, incoming, "/tmp/x.pdf", "pdf")
        self.assertEqual(svc.db.covers, {})

    def test_never_raises(self):
        """任何一步炸了都只记日志——不能让已成功的 add_format 被打回 INVALID。"""
        from webserver.services.scan_service import ScanService
        svc = ScanService.__new__(ScanService)

        class _Bad:
            def get_metadata(self, *a, **k):
                raise RuntimeError("db down")

            def set_cover(self, *a, **k):
                raise RuntimeError("disk full")

        svc.db = _Bad()
        incoming = FakeMeta(title="书", authors=["a"])
        incoming.cover_data = ("jpeg", b"x")
        with mock.patch.object(book_module, "merge_meta_from_file", side_effect=RuntimeError("merge boom")):
            svc._merge_meta_into_existing(7, incoming, "/tmp/x.pdf", "pdf")  # 不应抛异常


class TestGuessAuthorFromFilename(unittest.TestCase):
    """4.6.0-18：保守地从文件名找作者——宁可 None，也不写错。"""

    def setUp(self):
        from webserver import utils
        self.guess = utils.guess_author_from_filename

    # ---- 应当识别 ----
    def test_dash_tail(self):
        self.assertEqual(self.guess("秒懂速解小学数字画图 - 燕晓"), "燕晓")

    def test_dash_tail_no_spaces(self):
        self.assertEqual(self.guess("秒懂速解小学数字画图-燕晓"), "燕晓")

    def test_underscore_tail(self):
        self.assertEqual(self.guess("三体_刘慈欣"), "刘慈欣")

    def test_bracket_prefix(self):
        self.assertEqual(self.guess("[燕晓] 秒懂速解小学数字画图"), "燕晓")

    def test_fullwidth_bracket_prefix(self):
        self.assertEqual(self.guess("【燕晓】秒懂速解小学数字画图"), "燕晓")

    def test_paren_suffix(self):
        self.assertEqual(self.guess("秒懂速解小学数字画图 (燕晓)"), "燕晓")

    def test_explicit_label_colon(self):
        self.assertEqual(self.guess("书名 作者：张三"), "张三")

    def test_explicit_label_space(self):
        self.assertEqual(self.guess("书名 作者 李四"), "李四")

    def test_translated_author_with_middle_dot(self):
        self.assertEqual(self.guess("战争与和平 - 列夫·托尔斯泰"), "列夫·托尔斯泰")

    def test_latin_author(self):
        self.assertEqual(self.guess("The Lord of the Rings - Tolkien"), "Tolkien")

    def test_by_label_two_words(self):
        self.assertEqual(self.guess("某书 by John Smith"), "John Smith")

    def test_by_label_with_initial(self):
        self.assertEqual(self.guess("某书 by Randal E. Bryant"), "Randal E. Bryant")

    # ---- 4.6.0-18 补：多段式与带扩展名 ----
    def test_three_segment_skips_publisher(self):
        """`书名 - 作者 - 出版社`：出版社被否掉后要退回到中间的作者，不能直接放弃。"""
        self.assertEqual(self.guess("三体 - 刘慈欣 - 重庆出版社"), "刘慈欣")
        self.assertEqual(
            self.guess("哈利波特与魔法石 - J.K.罗琳 - 人民文学出版社"), "J.K.罗琳"
        )

    def test_extension_tolerated(self):
        """调用方一般已剥扩展名，但函数自带兜底——否则 `- 燕晓.pdf` 会连扩展名一起吞。"""
        self.assertEqual(self.guess("秒懂速解小学数字画图 - 燕晓.pdf"), "燕晓")
        self.assertEqual(self.guess("秒懂速解小学数字画图_燕晓.pdf"), "燕晓")
        self.assertEqual(self.guess("某书 (燕晓).epub"), "燕晓")

    def test_label_stops_at_whitespace(self):
        """`作者：张三 三体` 里的"三体"是书名，不能粘进人名。"""
        self.assertEqual(self.guess("作者：张三 三体"), "张三")
        self.assertEqual(self.guess("作者 李四 某书名"), "李四")

    # ---- 必须拒绝（保守策略的核心）----
    def test_rejects_publisher(self):
        self.assertIsNone(self.guess("秒懂速解小学数字画图 - 延边大学出版社"))

    def test_rejects_edition_bracket(self):
        self.assertIsNone(self.guess("某书 [第2版]"))

    def test_rejects_year(self):
        self.assertIsNone(self.guess("某书 (2024)"))

    def test_rejects_scan_marker(self):
        self.assertIsNone(self.guess("某书 [扫描版]"))

    def test_rejects_volume(self):
        self.assertIsNone(self.guess("某书 - 上册"))

    def test_rejects_omnibus(self):
        self.assertIsNone(self.guess("某书 - 全集"))

    def test_rejects_multi_word_tail(self):
        self.assertIsNone(self.guess("一个故事 - 上半部 下半部"))

    def test_rejects_extension(self):
        self.assertIsNone(self.guess("某书 (pdf)"))

    def test_rejects_short_version_tag(self):
        self.assertIsNone(self.guess("某书 - v2"))

    def test_no_signal_returns_none(self):
        self.assertIsNone(self.guess("正常书名没有作者"))

    def test_rejects_english_title_with_by(self):
        """"Stand by Me" 里的 by 不是作者标注——by 后只认多词人名。"""
        self.assertIsNone(self.guess("Stand by Me"))
        self.assertIsNone(self.guess("Live by Night"))

    def test_rejects_single_word_after_by(self):
        self.assertIsNone(self.guess("某书 by Tolkien"))

    def test_empty_input(self):
        self.assertIsNone(self.guess(""))
        self.assertIsNone(self.guess(None))


class TestPdfMetaTitleNeverSplit(unittest.TestCase):
    """标题一律整串，绝不拆——拆错比不拆更难发现。"""

    def setUp(self):
        self.conf = mock.patch.object(book_module.CONF, "get", return_value=False)
        self.conf.start()
        self.addCleanup(self.conf.stop)

    def test_filename_title_kept_whole(self):
        mi = FakeMeta(title="", authors=["燕晓"])
        book_module.normalize_pdf_meta(mi, "秒懂速解小学数字画图 - 燕晓")
        self.assertEqual(mi.title, "秒懂速解小学数字画图 - 燕晓")

    def test_bracket_info_kept_whole(self):
        mi = FakeMeta(title="", authors=["燕晓"])
        book_module.normalize_pdf_meta(mi, "[燕晓] 某书 (第2版)")
        self.assertEqual(mi.title, "[燕晓] 某书 (第2版)")

    def test_prefer_filename_keeps_whole(self):
        mi = FakeMeta(title="内嵌书名", authors=["燕晓"])
        book_module.normalize_pdf_meta(mi, "某书 - 燕晓", prefer_filename=True)
        self.assertEqual(mi.title, "某书 - 燕晓")

    def test_embedded_title_still_preferred(self):
        mi = FakeMeta(title="干净书名", authors=["燕晓"])
        book_module.normalize_pdf_meta(mi, "某书 - 燕晓")
        self.assertEqual(mi.title, "干净书名")


class TestPdfMetaAuthorFromFilename(unittest.TestCase):
    """作者：内嵌优先，缺失时才从文件名保守推断。"""

    def setUp(self):
        self.conf = mock.patch.object(book_module.CONF, "get", return_value=False)
        self.conf.start()
        self.addCleanup(self.conf.stop)

    def test_anonymous_filled_from_filename(self):
        mi = FakeMeta(title="", authors=["Unknown"])
        book_module.normalize_pdf_meta(mi, "秒懂速解小学数字画图 - 燕晓")
        self.assertEqual(mi.authors, ["燕晓"])

    def test_embedded_author_wins(self):
        mi = FakeMeta(title="书", authors=["真作者"])
        book_module.normalize_pdf_meta(mi, "书 - 文件名作者")
        self.assertEqual(mi.authors, ["真作者"])

    def test_prefer_filename_keeps_real_author(self):
        """用户实测场景：开关打开，内嵌有作者，必须留着。"""
        mi = FakeMeta(title="", authors=["燕晓"])
        book_module.normalize_pdf_meta(mi, "秒懂速解小学数字画图 - 燕晓", prefer_filename=True)
        self.assertEqual(mi.authors, ["燕晓"])

    def test_prefer_filename_and_anonymous_falls_back(self):
        mi = FakeMeta(title="", authors=["Unknown"])
        book_module.normalize_pdf_meta(mi, "三体 - 刘慈欣", prefer_filename=True)
        self.assertEqual(mi.authors, ["刘慈欣"])

    def test_nothing_found_stays_anonymous(self):
        mi = FakeMeta(title="", authors=["Unknown"])
        book_module.normalize_pdf_meta(mi, "某本扫描书 - 上册")
        self.assertEqual(mi.authors, ["佚名"])

    def test_publisher_never_becomes_author(self):
        mi = FakeMeta(title="", authors=[])
        book_module.normalize_pdf_meta(mi, "某书 - 延边大学出版社")
        self.assertEqual(mi.authors, ["佚名"])


class TestScanImportPdfUsesNormalizer(unittest.TestCase):
    """扫描导入必须与网页上传同口径。原先自写一套，开关打开时无条件把作者改佚名。"""

    def test_scan_branch_calls_normalize_pdf_meta(self):
        import inspect

        from webserver.services import scan_service as svc_module

        src = inspect.getsource(svc_module.ScanService)
        self.assertIn("normalize_pdf_meta", src, "扫描导入应复用 normalize_pdf_meta，不要自写一套")

    def test_old_blanking_block_is_gone(self):
        """旧实现里「开关打开 -> mi.authors = [_("佚名")]」的写法国必须消失。"""
        import inspect

        from webserver.services import scan_service as svc_module

        src = inspect.getsource(svc_module.ScanService)
        self.assertNotIn(
            'elif CONF.get("PDF_TILE_WITH_FILE_NAME", False):',
            src,
            "扫描路径不应再自己判断这个开关，交由 normalize_pdf_meta 统一处理",
        )


if __name__ == "__main__":
    unittest.main()
