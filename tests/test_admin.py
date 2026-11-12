#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

from types import SimpleNamespace
from unittest import mock
from tests.test_main import TestWithUserLogin, setUpModule as init

def setUpModule():
    init()

class TestAdmin(TestWithUserLogin):
    def test_book_list(self):
        d = self.json("/api/admin/book/list?sort=id&num=10")
        self.assertEqual(d["err"], "ok")
        self.assertEqual(len(d["items"]), 10)


class TestAdminTrashBooks(TestWithUserLogin):
    def setUp(self):
        super().setUp()
        # 恢复流程末尾会调 `AutoFillService().auto_fill(book_id)`
        # （webserver/handlers/admin.py:1582，AUTO_FILL_META 打开时）。测试库里
        # 没有真实可刮削的来源，这次回写会真的写进 calibre 库：book 1 的作者被
        # 清成 Unknown，原「加西亚·马尔克斯」变成孤儿行被 calibre 回收，于是
        # 同一次全量里 test_main::TestMeta::test_author 变成 14 != 15。
        # 这里把刮削服务整体钉成 no-op：本组用例测的是回收站接口的入参/出参，
        # 不对刮削行为负责。
        autofill = mock.patch("webserver.handlers.admin.AutoFillService")
        autofill.start()
        self.addCleanup(autofill.stop)

    def new_api(self):
        from tests.test_main import _app
        return _app.settings["legacy"].new_api

    def tearDown(self):
        """把 calibre 进程内视图的 id 集合复位回磁盘真实状态。

        回收站恢复/清理接口是这么写的（webserver/handlers/admin.py）：

            ok, failed = TrashManager.restore_trash_books(cache, book_ids)
            if ok:
                self.calibre_db.data.books_added(tuple(ok))

        而 calibre 的 `View.books_added()` 是**无条件前置拼接**：

            self._map = ids + self._map      # calibre/db/view.py:486

        它不去重、也不校验 id 在库里是否真的存在。本夹具库里压根没有回收站
        记录，测试又把 TrashManager 钉成「原样返回」，于是每跑一次恢复用例，
        `_map` 就多叠一份 [1] / [1, 2]。而 `db.count()` 读的正是
        `View.count() == len(View._map)`（内存，不是磁盘），所以后面
        test_main 的 `sys.books == 13` 就被撑成 16。

        这里按磁盘真实 id 复位，等价于真实环境下「恢复其实就是把磁盘上已有的
        行重新挂回视图」的语义。
        """
        super().tearDown()
        from tests.test_main import _app
        legacy = _app.settings["legacy"]
        view = legacy.count.__self__
        view._map = tuple(sorted(legacy.new_api.all_book_ids()))
        view._map_filtered = tuple(sorted(legacy.new_api.all_book_ids()))

    def test_list_trash_books(self):
        entries = [
            SimpleNamespace(book_id=1, title="Book One", author="Author A", mtime=100.0),
            SimpleNamespace(book_id=2, title="Book Two", author="Author B", mtime=200.0),
        ]
        with mock.patch.object(self.new_api(), "list_trash_entries", return_value=(entries, [])):
            d = self.json("/api/admin/trash/books")
        self.assertEqual(d["err"], "ok")
        self.assertEqual(len(d["books"]), 2)
        # sorted by mtime desc: book_id=2 first
        self.assertEqual(d["books"][0]["book_id"], 2)
        self.assertEqual(d["books"][0]["title"], "Book Two")
        self.assertEqual(d["books"][0]["author"], "Author B")

    def test_restore_trash_books_requires_ids(self):
        d = self.json("/api/admin/trash/books/restore", method="POST", body="{}")
        self.assertEqual(d["err"], "params.error")

    def test_restore_trash_books_success(self):
        # 恢复接口内部走 `TrashManager.restore_trash_books(cache, ids)`，
        # 它才真正调 `cache.move_book_from_trash()`。只把 new_api 的方法换成
        # mock 是够不到那层的（TrashManager 拿的是同一个 cache 对象，但它自己
        # 也会被测试入口整体钉成空实现）。这里改成直接断言到 TrashManager 层，
        # 顺带验证「ids 原样传进去、结果原样透出」。
        from webserver.base import trash_manager as tm_mod

        calls = []

        def fake_restore(cache, book_ids):
            calls.append(list(book_ids))
            return list(book_ids), {}

        with mock.patch.object(tm_mod.TrashManager, "restore_trash_books", side_effect=fake_restore):
            d = self.json(
                "/api/admin/trash/books/restore",
                method="POST",
                body='{"book_ids": [1, 2]}',
            )
        self.assertEqual(d["err"], "ok")
        self.assertEqual(sorted(d["restored"]), [1, 2])
        self.assertEqual(calls, [[1, 2]])

    def test_restore_trash_books_partial_failure(self):
        from webserver.base import trash_manager as tm_mod

        def fake_restore(cache, book_ids):
            ok, failed = [], {}
            for book_id in book_ids:
                if book_id == 2:
                    failed[book_id] = "A book with the id 2 already exists"
                else:
                    ok.append(book_id)
            return ok, failed

        with mock.patch.object(tm_mod.TrashManager, "restore_trash_books", side_effect=fake_restore):
            d = self.json(
                "/api/admin/trash/books/restore",
                method="POST",
                body='{"book_ids": [1, 2]}',
            )
        self.assertEqual(d["err"], "partial")
        self.assertEqual(d["restored"], [1])
        self.assertIn(2, [int(k) for k in d["failed"].keys()])

    def test_purge_trash_books_requires_ids(self):
        d = self.json("/api/admin/trash/books/purge", method="POST", body="{}")
        self.assertEqual(d["err"], "params.error")

    def test_purge_trash_books_success(self):
        from webserver.base import trash_manager as tm_mod

        calls = []

        def fake_purge(cache, book_ids):
            calls.append(list(book_ids))
            return list(book_ids), {}

        with mock.patch.object(tm_mod.TrashManager, "purge_trash_books", side_effect=fake_purge):
            d = self.json(
                "/api/admin/trash/books/purge",
                method="POST",
                body='{"book_ids": [1]}',
            )
        self.assertEqual(d["err"], "ok")
        self.assertEqual(d["purged"], [1])
        self.assertEqual(calls, [[1]])
