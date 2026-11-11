#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""读者组列表 / 候选值接口的回归测试（build.27-r20 之后的修复）。

背景：页面上「分组权限」下拉为空、已分组列表一直转圈。根因不在渲染或权限，
而是这两个接口把同步 IO 放在唯一的 ioloop 线程上：列表接口是同步 def get
（Reader 全表扫描），候选值接口还要碰 calibre 的 field_metadata。任何一步
卡住（数据库写锁 60s、calibre 预热持锁）整个进程都跟着冻，后发的请求全部
排队。这里用「闸门 + 心跳协程」把「慢查询期间事件循环仍能推进」变成确定
事实，而不是靠读代码判断。
"""

import asyncio
import json
import threading
import types
import unittest
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import StaticPool

from webserver import models, utils
from webserver.handlers import reader_group as rg_handlers
from webserver.handlers.reader_group import (
    ReaderGroupOptions, _collect_groups,
)
from webserver.models import Reader
from webserver.services import reader_group as rg_service
from webserver.services.reader_group import ReaderGroupService

GATE_TIMEOUT = 5.0


class Gate:
    """扫描闸门：进入即挂起，由测试显式放行。"""

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.thread_ids = []


class FakeCalibre:
    def __init__(self, meta=None, rows=None, gate=None):
        self.meta = meta or {}
        self.rows = rows or []
        self.gate = gate

    @property
    def field_metadata(self):
        return self.meta

    @property
    def backend(self):
        calibre = self

        class _Backend:
            conn = calibre

        return _Backend()

    def get(self, sql, params=None):
        if self.gate is not None:
            self.gate.thread_ids.append(threading.get_ident())
            self.gate.entered.set()
            if not self.gate.release.wait(GATE_TIMEOUT):
                raise RuntimeError("calibre 闸门超时")
        return self.rows


class FakeHandler:
    """只实现两个接口依赖的最小面：线程池封装、session、calibre 句柄。"""

    def __init__(self, scoped=None, calibre=None, tag_items=None, tag_error=None):
        self._scoped = scoped or (lambda: None)
        self.calibre_db = calibre or FakeCalibre()
        self.calibre_db_cache = self.calibre_db
        self.tag_items = tag_items if tag_items is not None else []
        self.tag_error = tag_error

    async def run_sqlite_async(self, func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        session = self._scoped()
        try:
            return await loop.run_in_executor(
                utils.blocking_pool, lambda: func(session, *args, **kwargs))
        finally:
            if hasattr(session, "close"):
                session.close()

    async def run_calibre_async(self, func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            utils.blocking_pool, lambda: func(*args, **kwargs))

    async def get_category_with_count_async(self, field):
        loop = asyncio.get_running_loop()

        def _call():
            if self.tag_error:
                raise self.tag_error
            return self.tag_items

        return await loop.run_in_executor(utils.blocking_pool, _call)


def _bind(handler, method):
    return types.MethodType(method, handler)


def make_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    models.Base.metadata.create_all(engine)
    return scoped_session(sessionmaker(bind=engine))


class TestGroupsConfig(unittest.TestCase):

    def test_json_string_groups_are_parsed(self):
        """历史数据：auto.py 里被写成 JSON 字符串时不能静默丢掉所有组。"""
        conf = {"READER_GROUPS": json.dumps({"低年级": {"mode": "whitelist",
                                                       "tags": "童话"}})}
        with mock.patch.object(rg_service, "CONF", conf, create=True):
            groups = ReaderGroupService.list_groups()
        self.assertIn("低年级", groups)
        self.assertEqual(groups["低年级"]["tags"], "童话")

    def test_garbage_groups_value_falls_back_to_empty(self):
        with mock.patch.object(rg_service, "CONF", {"READER_GROUPS": "not json"},
                               create=True):
            self.assertEqual(ReaderGroupService.list_groups(), {})

    def test_members_of_db_error_returns_dict(self):
        """DB 读失败必须返回 {}：返回 [] 会让调用方 .get() 抛 AttributeError。"""
        class BrokenSession:
            def query(self, *a, **kw):
                raise RuntimeError("database is locked")

        self.assertEqual(ReaderGroupService.members_of(BrokenSession()), {})

    def test_collect_groups_survives_db_error(self):
        """DB 挂了也要把组定义（纯内存）吐出来，而不是 500。"""
        class BrokenSession:
            def query(self, *a, **kw):
                raise RuntimeError("database is locked")

        conf = {"READER_GROUPS": {"低年级": {"mode": "whitelist", "tags": "童话"}}}
        with mock.patch.object(rg_service, "CONF", conf, create=True):
            groups, orphan = _collect_groups(BrokenSession())
        self.assertEqual(groups["低年级"]["members"], [])
        self.assertEqual(orphan, {})


class TestGroupListEndpoint(unittest.TestCase):

    def setUp(self):
        self.session = make_session()
        self.addCleanup(self.session.remove)
        self.conf = mock.MagicMock()
        self.conf.get = mock.MagicMock(side_effect=lambda k, d=None: (
            self.groups if k == rg_service.GROUPS_KEY else d))
        patcher = mock.patch.object(rg_service, "CONF", self.conf, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _make_readers(self, mapping):
        for name, group in mapping.items():
            self.session.add(Reader(username=name, extra={"reader_group": group}))
        self.session.commit()

    def test_returns_groups_and_members(self):
        self.groups = {"低年级": {"mode": "whitelist", "categories": "", "tags": "童话"}}
        self._make_readers({"kid": "低年级", "kid2": "低年级"})
        handler = FakeHandler(scoped=self.session)
        handler._load_groups = _bind(handler, rg_handlers.ReaderGroupList._load_groups)

        rsp = asyncio.run(handler._load_groups())

        self.assertEqual(rsp["err"], "ok")
        self.assertEqual(sorted(rsp["groups"]["低年级"]["members"]), ["kid", "kid2"])
        self.assertEqual(rsp["orphans"], {})

    def test_empty_config_returns_empty_groups(self):
        self.groups = {}
        handler = FakeHandler(scoped=self.session)
        handler._load_groups = _bind(handler, rg_handlers.ReaderGroupList._load_groups)

        rsp = asyncio.run(handler._load_groups())

        self.assertEqual(rsp, {"err": "ok", "groups": {}, "orphans": {}})

    def test_orphans_are_reported(self):
        self.groups = {"低年级": {"mode": "whitelist"}}
        self._make_readers({"kid": "已删除的组"})
        handler = FakeHandler(scoped=self.session)
        handler._load_groups = _bind(handler, rg_handlers.ReaderGroupList._load_groups)

        rsp = asyncio.run(handler._load_groups())

        self.assertEqual(rsp["orphans"], {"已删除的组": ["kid"]})

    def test_timeout_returns_error_instead_of_hanging(self):
        """数据库一直忙时接口必须按上限返回错误，不能让前端无限转圈。"""
        async def blocked(func, *a, **kw):
            await asyncio.sleep(30)

        handler = FakeHandler(scoped=self.session)
        handler.run_sqlite_async = blocked
        handler._load_groups = _bind(handler, rg_handlers.ReaderGroupList._load_groups)

        with mock.patch.object(rg_handlers, "_LIST_TIMEOUT", 0.05):
            rsp = asyncio.run(handler._load_groups())

        self.assertEqual(rsp["err"], "timeout")


class TestOptionsEndpoint(unittest.TestCase):

    def _handler(self, calibre=None, tag_items=None, tag_error=None):
        session = make_session()
        self.addCleanup(session.remove)
        session.add(Reader(username="kid", extra={}))
        session.add(Reader(username="mom", extra={}))
        session.commit()
        handler = FakeHandler(scoped=session, calibre=calibre,
                              tag_items=tag_items, tag_error=tag_error)
        handler._load_options = _bind(handler, ReaderGroupOptions._load_options)
        handler._category_options = _bind(handler, ReaderGroupOptions._category_options)
        return handler

    def test_slow_calibre_does_not_block_event_loop(self):
        gate = Gate()
        calibre = FakeCalibre(meta={"#category": {"colnum": 3}},
                              rows=[("绘本",), ("科普",)], gate=gate)
        handler = self._handler(calibre=calibre, tag_items=[{"name": "童话"}])

        async def scenario():
            ticks = 0
            heartbeat_done = asyncio.Event()

            async def heartbeat():
                nonlocal ticks
                while not heartbeat_done.is_set():
                    ticks += 1
                    await asyncio.sleep(0.001)

            hb = asyncio.create_task(heartbeat())
            task = asyncio.create_task(handler._load_options())
            try:
                while not gate.entered.is_set():
                    await asyncio.sleep(0.001)
                # 分类查询卡在工作线程里：请求协程没完成，但事件循环必须还在跑
                self.assertFalse(task.done())
                before = ticks
                await asyncio.sleep(0.05)
                self.assertGreater(ticks, before, "慢查询期间事件循环被阻塞")
                self.assertFalse(task.done())

                gate.release.set()
                return await asyncio.wait_for(task, GATE_TIMEOUT)
            finally:
                gate.release.set()
                heartbeat_done.set()
                await hb

        rsp = asyncio.run(scenario())

        self.assertEqual(rsp["err"], "ok")
        self.assertEqual(rsp["categories"], ["绘本", "科普"])
        self.assertEqual(rsp["tags"], ["童话"])
        self.assertEqual(rsp["usernames"], ["kid", "mom"])
        self.assertEqual(rsp["degraded"], [])
        # calibre 访问发生在工作线程，不是 ioloop 线程
        self.assertNotEqual(gate.thread_ids[0], threading.get_ident())

    def test_tag_failure_degrades_only_that_part(self):
        handler = self._handler(tag_error=RuntimeError("tag query failed"))

        rsp = asyncio.run(handler._load_options())

        self.assertEqual(rsp["err"], "ok")
        self.assertEqual(rsp["degraded"], ["tags"])
        self.assertEqual(rsp["tags"], [])
        self.assertEqual(rsp["usernames"], ["kid", "mom"])

    def test_no_category_column_returns_empty_categories(self):
        handler = self._handler(calibre=FakeCalibre(meta={}))

        rsp = asyncio.run(handler._load_options())

        self.assertEqual(rsp["categories"], [])
        self.assertEqual(rsp["degraded"], [])


if __name__ == "__main__":
    unittest.main()
