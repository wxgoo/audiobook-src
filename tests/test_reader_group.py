#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""读者组分级权限测试（移植自 audiobook 按年级分组的功能）。"""

import pathlib
import unittest
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from webserver import models
from webserver.models import Reader
from webserver.services import reader_group
from webserver.services.reader_group import ReaderGroupService

WEBSERVER = pathlib.Path(__file__).resolve().parent.parent / "webserver"


def make_reader(name="kid", extra=None, read_limit=0, cats="", tags=""):
    return Reader(username=name, extra=extra or {},
                  read_limit=read_limit, limit_categories=cats, limit_tags=tags)


class FakeConf(dict):
    def save(self):
        pass


class TestReaderGroupService(unittest.TestCase):

    def setUp(self):
        self.conf = FakeConf()
        patcher = mock.patch.object(reader_group, "CONF", self.conf, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        # 落盘也一起 mock：测试不能往 webserver/auto.py 写东西
        persist = mock.patch.object(reader_group, "_persist", lambda groups: None)
        persist.start()
        self.addCleanup(persist.stop)

    def test_save_and_list_groups(self):
        ok, _ = ReaderGroupService.save_group(
            "低年级", "whitelist", "绘本", ["童话", "绘本"])
        self.assertTrue(ok)
        groups = ReaderGroupService.list_groups()
        self.assertIn("低年级", groups)
        self.assertEqual(groups["低年级"]["mode"], "whitelist")
        self.assertEqual(groups["低年级"]["tags"], "童话,绘本")

    def test_save_group_rejects_bad_mode(self):
        ok, msg = ReaderGroupService.save_group("x", "fancy")
        self.assertFalse(ok)

    def test_delete_group(self):
        ReaderGroupService.save_group("g1", "whitelist", "", "t1")
        ok, _ = ReaderGroupService.delete_group("g1")
        self.assertTrue(ok)
        self.assertNotIn("g1", ReaderGroupService.list_groups())
        ok2, _ = ReaderGroupService.delete_group("g1")
        self.assertFalse(ok2)

    # ---------- 生效规则 ----------

    def test_effective_no_restriction(self):
        r = make_reader()
        eff = ReaderGroupService.effective_limits(r)
        self.assertEqual(eff["read_limit"], 0)

    def test_user_own_settings_win(self):
        """用户自己显式设置了限制 → 组配置被忽略"""
        ReaderGroupService.save_group("全员黑名单", "blacklist", "", "暴力")
        r = make_reader(read_limit=1, tags="漫画")
        eff = ReaderGroupService.effective_limits(r)
        self.assertEqual(eff["read_limit"], 1)
        self.assertEqual(eff["limit_tags"], "漫画")

    def test_group_fallback_whitelist(self):
        """用户没设置 → 回退到组的白名单配置"""
        ReaderGroupService.save_group("低年级", "whitelist", "绘本", "童话")
        r = make_reader(extra={"reader_group": "低年级"})
        eff = ReaderGroupService.effective_limits(r)
        self.assertEqual(eff["read_limit"], 1)
        self.assertEqual(eff["limit_tags"], "童话")
        self.assertEqual(eff["limit_categories"], "绘本")

    def test_group_fallback_blacklist(self):
        ReaderGroupService.save_group("高年级", "blacklist", "", "暴力,恐怖")
        r = make_reader(extra={"reader_group": "高年级"})
        eff = ReaderGroupService.effective_limits(r)
        self.assertEqual(eff["read_limit"], 2)
        self.assertEqual(eff["limit_tags"], "暴力,恐怖")

    def test_assign_rejects_unknown_group(self):
        r = make_reader()
        self.assertFalse(ReaderGroupService.assign(r, "不存在的组"))

    def test_assign_and_unset(self):
        ReaderGroupService.save_group("低年级", "whitelist", "", "童话")
        r = make_reader()
        self.assertTrue(ReaderGroupService.assign(r, "低年级"))
        self.assertEqual(ReaderGroupService.group_of(r), "低年级")
        self.assertTrue(ReaderGroupService.assign(r, ""))
        self.assertEqual(ReaderGroupService.group_of(r), "")

    # ---------- 与 BaseHandler 过滤逻辑的联动 ----------

    def _handler_with(self, user):
        """构造只暴露 is_book_in_reading_range 的最小 handler"""
        from webserver.handlers.base import BaseHandler
        h = BaseHandler.__new__(BaseHandler)
        return BaseHandler.is_book_in_reading_range(h, None) if False else \
            lambda book: BaseHandler.is_book_in_reading_range(
                mock.Mock(wraps=None) if False else h, book, user)

    def test_book_range_uses_group(self):
        from webserver.handlers.base import BaseHandler
        ReaderGroupService.save_group("低年级", "whitelist", "", "童话")
        user = make_reader(extra={"reader_group": "低年级"})
        h = BaseHandler.__new__(BaseHandler)
        # 白名单组：童话书可见，恐怖书不可见
        self.assertTrue(
            BaseHandler.is_book_in_reading_range(h, {"tags": ["童话"]}, user))
        self.assertFalse(
            BaseHandler.is_book_in_reading_range(h, {"tags": ["恐怖"]}, user))
        # 没有组的用户不受限
        other = make_reader()
        self.assertTrue(
            BaseHandler.is_book_in_reading_range(h, {"tags": ["恐怖"]}, other))

    def test_base_is_book_visible_with_group(self):
        from webserver.constants import ALLOW_READ_RANGE_SETTING
        from webserver.handlers.base import BaseHandler
        ReaderGroupService.save_group("低年级", "whitelist", "", "童话")
        user = make_reader(extra={"reader_group": "低年级"})
        h = BaseHandler.__new__(BaseHandler)
        with mock.patch("webserver.handlers.base.CONF",
                        {ALLOW_READ_RANGE_SETTING: True}, create=True), \
                mock.patch.object(BaseHandler, "current_user", user):
            self.assertTrue(
                BaseHandler.is_book_visible(h, {"tags": ["童话"]}))
            self.assertFalse(
                BaseHandler.is_book_visible(h, {"tags": ["成人"]}))


class TestReaderGroupOptionsEndpoint(unittest.TestCase):
    """候选值接口：给前端的 v-combobox 提供真实存在的分类/标签。

    重点验证「库不可用/字段不存在」时不抛异常而是返回空列表——
    这个接口挂了会让整个设置页的分组编辑器打不开，必须容错。
    """

    def _make_handler(self, field_metadata=None, category_values=None,
                      tag_items=None, db_error=None):
        from webserver.handlers.reader_group import ReaderGroupOptions

        h = ReaderGroupOptions.__new__(ReaderGroupOptions)
        h.db_lock = mock.MagicMock()
        h.db_lock.__enter__ = lambda s: s
        h.db_lock.__exit__ = lambda *a: False

        db = mock.MagicMock()
        db.field_metadata = field_metadata if field_metadata is not None else {}
        h.calibre_db = db

        conn = mock.MagicMock()
        if db_error:
            conn.get.side_effect = db_error
        else:
            conn.get.return_value = [(v,) for v in (category_values or [])]
        h.calibre_db_cache = mock.MagicMock()
        h.calibre_db_cache.backend.conn = conn

        async def run_calibre_async(func, *a, **kw):
            return func(*a, **kw)

        async def get_category_with_count_async(field):
            return tag_items or []

        h.run_calibre_async = run_calibre_async
        h.get_category_with_count_async = get_category_with_count_async
        return h

    @staticmethod
    def _call_options(h):
        """绕开 @js / @is_admin 装饰器，直接跑被包住的业务协程。

        @js 会尝试读当前请求的 cookie/headers（需要真实 RequestHandler），
        @is_admin 需要已登录的管理员。两者都没有 functools.wraps，拿不到
        __wrapped__，所以顺着 __closure__ 逐层剥到最内层的业务函数。
        """
        import asyncio

        fn = h.get
        seen = set()
        while id(fn) not in seen:
            seen.add(id(fn))
            closure = getattr(fn, "__closure__", None) or ()
            nxt = None
            for cell in closure:
                try:
                    val = cell.cell_contents
                except ValueError:
                    continue
                if callable(val):
                    nxt = val
                    break
            if nxt is None:
                break
            fn = nxt

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(fn(h))
        finally:
            loop.close()

    def test_returns_categories_and_tags(self):
        h = self._make_handler(
            field_metadata={"#category": {"colnum": 7}},
            category_values=["小说", "历史"],
            tag_items=[{"id": 1, "name": "童话", "count": 3},
                       {"id": 2, "name": "绘本", "count": 1},
                       {"id": 3, "name": "童话", "count": 2}],  # 重复名要去重
        )
        rsp = self._call_options(h)
        self.assertEqual(rsp["err"], "ok")
        self.assertEqual(rsp["categories"], ["小说", "历史"])
        self.assertEqual(rsp["tags"], ["童话", "绘本"])

    def test_no_category_column_returns_empty(self):
        """没装 #category 自定义列时不能报错，只是没有候选值"""
        h = self._make_handler(field_metadata={}, tag_items=[])
        rsp = self._call_options(h)
        self.assertEqual(rsp, {"err": "ok", "categories": [], "tags": []})

    def test_db_error_degrades_gracefully(self):
        """数据库查询炸了也要返回 ok + 空列表，前端仍能自由输入"""
        h = self._make_handler(field_metadata={"#category": {"colnum": 7}},
                               db_error=RuntimeError("db locked"))
        rsp = self._call_options(h)
        self.assertEqual(rsp["err"], "ok")
        self.assertEqual(rsp["categories"], [])


if __name__ == "__main__":
    unittest.main()
