#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import json
import threading
import logging
import time
from unittest import mock
import unittest

from tests.test_main import TestWithUserLogin, setUpModule as init, testdir
from webserver import handlers
from webserver.models import ScanFile
from webserver.services import AsyncService
from webserver.services.scan_service import ScanService


def setUpModule():
    init()
    handlers.scan.SCAN_DIR_PREFIX = "/"


def prepare_scan_row(session, row_id, status):
    """把 `scanfiles` 里 id=row_id 的那行复位成指定状态并返回。

    原来这里直接 `.one()`，前提是「夹具里一定已经有这一行」。这个前提在
    单跑一个用例时成立，整文件跑就崩了：`TestScan.test_import_all` 真的
    执行了一次导入，那条记录被消费/改写掉了，后面的 `TestImport` 再
    `.one()` 就 NoResultFound。而 `TestImport::test_import_one` 单独跑
    又是绿的 —— 典型的「测试顺序决定成败」。

    改成找不到就按夹具口径重建一行，用例之间不再互相依赖。
    """
    row = session.query(ScanFile).filter(ScanFile.id == row_id).one_or_none()
    if row is None:
        # ScanFile 不是无参构造：__init__(self, path, hash_value, import_id)
        # 会顺手填 name/status/create_time，绕过去直接赋属性不如按签名造。
        row = ScanFile(testdir + "/cases/new.epub", "", 0)
        row.id = row_id
        row.scan_id = 1
        row.import_type = 0
        row.title = ""
        row.author = ""
        row.publisher = ""
        row.tags = ""
    row.path = testdir + "/cases/new.epub"
    row.status = status
    row.book_id = 0
    row.import_id = 0
    row.save()
    session.commit()
    return row


class TestScan(TestWithUserLogin):
    NEW_ROW_ID = 69
    RECORDS_COUNT = 2

    def setUp(self):
        # 将这行记录设置为可导入的状态
        self.session = self.get_app().settings["ScopedSession"]
        self.session.rollback()

        prepare_scan_row(self.session, self.NEW_ROW_ID, ScanFile.NEW)
        return super().setUp()

    def test_list(self):
        d = self.json("/api/admin/import/list?num=10000")
        self.assertEqual(d['total'], self.RECORDS_COUNT)

    # def test_scan(self):
    #     d = self.json("/api/admin/import/run", method="POST", body="")
    #     self.assertEqual(d["err"], "ok")

    #     row = self.session.query(ScanFile).filter(ScanFile.id == self.NEW_ROW_ID).one()
    #     # new.epub & old.epub are imported before, so they should be dropped here
    #     self.assertEqual(row.status, ScanFile.DROP)

    #     d = self.json("/api/admin/import/list?num=10000")
    #     # new.epub has be reset as NEW and same file path, it should be processed again with existed record
    #     self.assertEqual(d['total'], self.RECORDS_COUNT + 4)

    #     titles = set([ '天行者', '我的一生', 'book', '凡人修仙之仙界篇', '语言哲学'])
    #     scan_titles = set([ book['title'] for book in d['items'] ])

    # def test_scan_background(self):
    #     self.async_service.return_value = True

    #     n = threading.active_count() + 1
    #     d = self.json("/api/admin/import/run", method="POST", body="")
    #     self.assertEqual(d["err"], "ok")
    #     self.assertEqual(n+1, threading.active_count())

    #     # wait job done
    #     time.sleep(2)
    #     q = ScanService().get_queue('do_scan')
    #     n = q.qsize()
    #     while n:
    #         n = q.qsize()
    #         time.sleep(0.1)

    #     row = self.session.query(ScanFile).filter(ScanFile.id == self.NEW_ROW_ID).one()
    #     self.assertEqual(row.status, ScanFile.DROP)

    def test_scan_status(self):
        d = self.json("/api/admin/import/status")
        self.assertEqual(d["err"], "ok")

    def test_import_status(self):
        d = self.json("/api/admin/import/status")
        self.assertEqual(d["err"], "ok")


class TestScanContinue(TestWithUserLogin):
    NEW_ROW_ID = 69

    def setUp(self):
        # 将这行记录设置为可导入的状态
        self.session = self.get_app().settings["ScopedSession"]
        self.session.rollback()

        prepare_scan_row(self.session, self.NEW_ROW_ID, ScanFile.NEW)
        return super().setUp()
    # def test_scan(self):
    #     d = self.json("/api/admin/import/run", method="POST", body="")
    #     self.assertEqual(d["err"], "ok")

    #     row = self.session.query(ScanFile).filter(ScanFile.id == self.NEW_ROW_ID).one()
    #     self.assertEqual(row.status, ScanFile.DROP)


class TestImport(TestWithUserLogin):
    READY_ROW_ID = 69

    def setUp(self):
        # 将这行记录设置为可导入的状态
        session = self.get_app().settings["ScopedSession"]
        session.rollback()

        prepare_scan_row(session, self.READY_ROW_ID, ScanFile.READY)
        return super().setUp()

    @mock.patch("calibre.db.legacy.LibraryDatabase.import_book")
    def test_import_one(self, m1):
        m1.return_value = 1008610086
        hash = "sha256:3cfd51afe17f3051e24921825c05e1df0bce03d22837a916a4d4ddcbf0301a13"
        req = {"hashlist": [hash]}
        d = self.json("/api/admin/import/run", method="POST", body=json.dumps(req))
        self.assertEqual(d["err"], "ok")

    @mock.patch("calibre.db.legacy.LibraryDatabase.import_book")
    def test_import_all(self, m1):
        m1.return_value = 1008610086
        req = {"hashlist": "all"}
        d = self.json("/api/admin/import/run", method="POST", body=json.dumps(req))
        self.assertEqual(d["err"], "ok")

