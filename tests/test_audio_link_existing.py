#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""有声书导入的「同名电子书挂靠」逻辑测试。

背景（真实 bug）：有声书目录是 audios/<book_id>/，电子书在 library/。
原实现判断「同名书已存在」时只看 audios/<book_id>/ 里有没有音频，
所以「电子书先入库、音频后加」的场景会被判定成「这本书没有音频」→
新建一条 calibre 记录，书库里同一本书出现两条。

这里只测纯逻辑（不碰 calibre 数据库）：_pick_linkable_book / _book_has_ebook_file /
开关解析。导入主流程用 mock 太重，核心决策函数单独覆盖足够。
"""

import os
import tempfile
import unittest
from unittest import mock

from webserver.services import audios_import
from webserver.services.audios_import import (
    AudioBookImporter,
    _link_to_existing_enabled,
)


class TestLinkSwitch(unittest.TestCase):
    """AUDIO_LINK_TO_EXISTING_BOOK 开关解析：兼容 bool 和字符串配置"""

    def _conf(self, value):
        return mock.patch.dict(audios_import.CONF, {"AUDIO_LINK_TO_EXISTING_BOOK": value},
                               clear=False)

    def test_default_true_when_missing(self):
        conf = dict(audios_import.CONF)
        conf.pop("AUDIO_LINK_TO_EXISTING_BOOK", None)
        with mock.patch.object(audios_import, "CONF", conf):
            self.assertTrue(_link_to_existing_enabled())

    def test_bool_values(self):
        with self._conf(True):
            self.assertTrue(_link_to_existing_enabled())
        with self._conf(False):
            self.assertFalse(_link_to_existing_enabled())

    def test_string_values(self):
        for v in ("0", "false", "False", "no", "off", ""):
            with self._conf(v):
                self.assertFalse(_link_to_existing_enabled(), "value=%r 应为关闭" % (v,))
        for v in ("1", "true", "yes", "on"):
            with self._conf(v):
                self.assertTrue(_link_to_existing_enabled(), "value=%r 应为开启" % (v,))


class TestPickLinkableBook(unittest.TestCase):
    """从同名书里挑一本挂靠"""

    def _importer(self, has_ebook):
        """has_ebook: 可调用 book_id -> bool，模拟 library 里有没有实体文件"""
        imp = AudioBookImporter.__new__(AudioBookImporter)

        def _fake(book_id):
            return has_ebook(book_id)

        imp._book_has_ebook_file = _fake
        return imp

    def test_empty_ids_returns_none(self):
        imp = self._importer(lambda b: False)
        self.assertIsNone(imp._pick_linkable_book([]))
        self.assertIsNone(imp._pick_linkable_book(None))

    def test_prefers_book_with_ebook_file(self):
        """多本同名时，挑 library 里真有电子书文件的那本"""
        imp = self._importer(lambda b: b == 42)
        self.assertEqual(imp._pick_linkable_book([7, 42, 99]), 42)

    def test_falls_back_to_smallest_id(self):
        """都查不到实体文件时也不能返回 None（否则会新建重复书）"""
        imp = self._importer(lambda b: False)
        self.assertEqual(imp._pick_linkable_book([99, 7, 42]), 7)

    def test_ebook_check_exception_does_not_break(self):
        """检查实体文件时抛异常，仍应回落到最小 id"""
        imp = AudioBookImporter.__new__(AudioBookImporter)

        def boom(book_id):
            raise RuntimeError("db error")

        imp._book_has_ebook_file = boom
        self.assertEqual(imp._pick_linkable_book([5, 3]), 3)


class TestBookHasEbookFile(unittest.TestCase):
    """_book_has_ebook_file：判断 calibre 记录里是否有电子书格式"""

    def _importer_with_data(self, data):
        imp = AudioBookImporter.__new__(AudioBookImporter)
        imp.db = mock.MagicMock()
        imp.db.get_data_as_dict.return_value = data
        return imp

    def test_available_formats_list(self):
        imp = self._importer_with_data([{"available_formats": ["EPUB", "PDF"]}])
        self.assertTrue(imp._book_has_ebook_file(1))

    def test_empty_formats(self):
        imp = self._importer_with_data([{"available_formats": [], "formats": []}])
        self.assertFalse(imp._book_has_ebook_file(1))

    def test_formats_paths_exist(self):
        """没有 available_formats 时，用实际文件路径兜底判断"""
        tmp = tempfile.mkdtemp()
        f = os.path.join(tmp, "book.epub")
        with open(f, "wb") as fh:
            fh.write(b"x")
        try:
            imp = self._importer_with_data([{"formats": [f]}])
            self.assertTrue(imp._book_has_ebook_file(1))
        finally:
            os.unlink(f)
            os.rmdir(tmp)

    def test_formats_paths_missing(self):
        imp = self._importer_with_data([{"formats": ["/nonexistent/a.epub"]}])
        self.assertFalse(imp._book_has_ebook_file(1))

    def test_empty_data(self):
        imp = self._importer_with_data([])
        self.assertFalse(imp._book_has_ebook_file(1))

    def test_exception_returns_false(self):
        imp = AudioBookImporter.__new__(AudioBookImporter)
        imp.db = mock.MagicMock()
        imp.db.get_data_as_dict.side_effect = RuntimeError("boom")
        self.assertFalse(imp._book_has_ebook_file(1))


class TestStatusCounters(unittest.TestCase):
    """状态字典必须含 linked 计数，前端/日志靠它区分「挂靠」和「新建」"""

    def test_linked_in_default_status(self):
        status = AudioBookImporter.get_status()
        self.assertIn("linked", status)

    def test_linked_in_reset_dict(self):
        src = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "webserver", "services", "audios_import.py")
        with open(src, encoding="utf-8") as fh:
            content = fh.read()
        # 两处 status dict 初始化都要有 linked
        self.assertEqual(content.count('"linked": 0,'), 2,
                         "static_status 与 do_import 里的重置都要含 linked")

    def test_progress_data_carries_linked(self):
        """进度上报要带 linked，否则前端 count_processed 少算挂靠的书，
        进度条会卡在 100% 之前不动。"""
        src = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "webserver", "services", "audios_import.py")
        with open(src, encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn('"linked": status["linked"],', content)

    def test_frontend_counts_linked_as_processed(self):
        """前端把 imported+exist+linked 一起算已处理数"""
        vue = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "app", "src", "pages", "admin", "imports.vue")
        with open(vue, encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn("rsp.status.linked", content,
                      "挂靠的书也算处理完，否则进度条走不满")


if __name__ == "__main__":
    unittest.main()
