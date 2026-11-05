#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import os
import tempfile
import unittest

from tests.test_main import TestWithUserLogin, setUpModule as init, testdir
from webserver.services import AsyncService
from webserver.services.converter import ConverterService
from webserver.services.extract import ExtractService
from webserver.handlers.static_files import guess_favicon_content_type


def setUpModule():
    init()


class TestConvert(TestWithUserLogin):
    def test_convert(self):
        fin = testdir + "/cases/old.epub"
        fout = "/tmp/output.mobi"
        flog = "/tmp/output.log"
        ok = ConverterService().do_ebook_convert(fin, fout, flog)
        self.assertEqual(ok, True)


class TestExtract(TestWithUserLogin):
    def test_convert(self):
        bid = 666
        fpath = testdir + "/cases/book.txt"
        # 这个用例写的索引落在 extract_path/666/content.json，而它一旦存在，
        # parse_txt_content() 就会认为「已有可用索引」直接 return False。
        # 结果是同一个用例第二次跑必挂——不是产品问题，是用例不自清。
        # 解析前先把这本书的旧索引删干净，保证任何次数重跑结果一致。
        import shutil

        index_dir = os.path.dirname(ExtractService.txt_content_path(bid))
        shutil.rmtree(index_dir, ignore_errors=True)
        self.addCleanup(shutil.rmtree, index_dir, ignore_errors=True)
        ok = ExtractService().parse_txt_content(bid, fpath)
        self.assertEqual(ok, True)


class TestAsyncServiceRegistry(unittest.TestCase):
    def test_same_method_name_uses_distinct_queue(self):
        class FirstService(AsyncService):
            def do_import(self):
                return None

        class SecondService(AsyncService):
            def do_import(self):
                return None

        AsyncService.running = {}
        q1 = FirstService().start_service(FirstService.do_import)
        q2 = SecondService().start_service(SecondService.do_import)

        self.assertIsNot(q1, q2)
        self.assertEqual(len(AsyncService.running), 2)


class TestFaviconContentType(unittest.TestCase):
    def test_svg_payload_uses_svg_content_type(self):
        with tempfile.NamedTemporaryFile("wb", suffix=".ico", delete=False) as tmp:
            tmp.write(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")
            tmp_path = tmp.name

        try:
            self.assertEqual(guess_favicon_content_type(tmp_path), "image/svg+xml")
        finally:
            os.unlink(tmp_path)

    def test_falls_back_to_extension_for_binary_icon(self):
        with tempfile.NamedTemporaryFile("wb", suffix=".ico", delete=False) as tmp:
            tmp.write(b"\x00\x00\x01\x00")
            tmp_path = tmp.name

        try:
            self.assertIn(guess_favicon_content_type(tmp_path), {"image/x-icon", "image/vnd.microsoft.icon"})
        finally:
            os.unlink(tmp_path)
