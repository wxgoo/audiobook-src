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


if __name__ == "__main__":
    unittest.main()
