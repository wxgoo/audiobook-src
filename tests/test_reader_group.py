#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""读者组分级权限测试（移植自 audiobook 按年级分组的功能）。"""

import pathlib
import unittest
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.pool import StaticPool

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

    def test_open_group_is_unrestricted(self):
        """「不限」组（成人家属模板）：全库可读，且不保留匹配条件。"""
        ok, _ = ReaderGroupService.save_group("成人家属", "open", "绘本", "童话")
        self.assertTrue(ok)
        g = ReaderGroupService.list_groups()["成人家属"]
        self.assertEqual(g["mode"], "open")
        # 不限组留着条件只会让人误判（写了却不生效），一律清空
        self.assertEqual(g["categories"], "")
        self.assertEqual(g["tags"], "")
        r = make_reader(extra={"reader_group": "成人家属"})
        eff = ReaderGroupService.effective_limits(r)
        self.assertEqual(eff["read_limit"], 0)
        self.assertEqual(eff["source"], "group-open")
        self.assertTrue(reader_group.book_matches_limits({"tags": ["恐怖"]}, eff))

    def test_blacklist_without_conditions_allows_everything(self):
        """黑名单空条件 = 什么都不屏蔽，不能和白名单空条件一起判成「读不到书」。"""
        ReaderGroupService.save_group("全放行", "blacklist", "", "")
        r = make_reader(extra={"reader_group": "全放行"})
        eff = ReaderGroupService.effective_limits(r)
        self.assertEqual(eff["read_limit"], 2)
        self.assertTrue(reader_group.book_matches_limits({"tags": ["恐怖"]}, eff))
        self.assertTrue(reader_group.book_matches_limits({}, eff))

    def test_whitelist_without_conditions_still_blocks(self):
        """反向保护：白名单空条件在严格模式下必须仍然看不到书。"""
        ReaderGroupService.save_group("待配置", "whitelist", "", "")
        r = make_reader(extra={"reader_group": "待配置"})
        eff = ReaderGroupService.effective_limits(r)
        self.assertEqual(eff["read_limit"], 1)
        self.assertFalse(reader_group.book_matches_limits({"tags": ["童话"]}, eff))

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
        # is_book_visible 里会 `if self.is_admin(): return True`，而 is_admin()
        # 读的是 self.admin_user（由 prepare/auth 装饰器在真实请求里设置）。
        # 这里用 __new__ 绕过了初始化，没有这个属性 → AttributeError。
        # 显式置 False（普通读者），被测的是读者组判定本身。
        h.admin_user = False
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
        # usernames 是后来加的第三个候选（把用户划进组时用），
        # 所以这里从「只要 categories/tags」放宽成「这三项都要在、且为空」。
        self.assertEqual(rsp["err"], "ok")
        self.assertEqual(rsp["categories"], [])
        self.assertEqual(rsp["tags"], [])
        self.assertEqual(rsp["usernames"], [])

    def test_db_error_degrades_gracefully(self):
        """数据库查询炸了也要返回 ok + 空列表，前端仍能自由输入"""
        h = self._make_handler(field_metadata={"#category": {"colnum": 7}},
                               db_error=RuntimeError("db locked"))
        rsp = self._call_options(h)
        self.assertEqual(rsp["err"], "ok")
        self.assertEqual(rsp["categories"], [])


class TestReviveOrphanGroups(unittest.TestCase):
    """悬空组名一键重建空分组。

    事故背景：设置页保存把 READER_GROUPS 整份抹掉，组定义没了，但成员的
    Reader.extra["reader_group"] 还写着组名。旧实现在 GET 列表时顺手把这些
    引用 clear 掉 —— 管理员还没看到提示，唯一能恢复归属的线索就没了，
    重建同名组也找不回人。这里把「只报告不清除」和「重建后成员归位」都锁住。
    """

    GROUP = "儿童"

    def setUp(self):
        self.conf = FakeConf()
        patcher = mock.patch.object(reader_group, "CONF", self.conf, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        persist = mock.patch.object(reader_group, "_persist", lambda groups: None)
        persist.start()
        self.addCleanup(persist.stop)
        # StaticPool：内存库必须复用同一条连接，否则 collect_groups 里
        # session.close() 之后就查不到刚才插的数据了
        engine = create_engine("sqlite://", poolclass=StaticPool,
                               connect_args={"check_same_thread": False})
        self.session = scoped_session(
            sessionmaker(bind=engine, autoflush=True, autocommit=False))
        self.addCleanup(self.session.remove)
        models.Base.metadata.create_all(engine)
        for name in ("kid", "kid2"):
            self.session.add(make_reader(name=name,
                                         extra={reader_group.MEMBER_KEY: self.GROUP}))
        self.session.commit()

    def _names_in_group(self, name):
        rows = self.session.query(Reader).all()
        return sorted(r.username for r in rows
                      if (r.extra or {}).get(reader_group.MEMBER_KEY) == name)

    def test_orphan_groups_lists_members_of_missing_group(self):
        orphan = ReaderGroupService.orphan_groups(self.session)
        self.assertEqual(sorted(orphan[self.GROUP]), ["kid", "kid2"])
        # 只读不写：查询本身不能改动成员归属
        self.assertEqual(self._names_in_group(self.GROUP), ["kid", "kid2"])

    def test_collect_groups_does_not_clear_orphans(self):
        """GET/POST 共用入口只能报告悬空引用，绝不能顺手清掉（旧 bug）。"""
        from webserver.handlers.reader_group import collect_groups

        h = mock.Mock()
        h.settings = {"ScopedSession": self.session}
        groups, orphan = collect_groups(h)
        self.assertEqual(sorted(orphan[self.GROUP]), ["kid", "kid2"])
        self.assertNotIn(self.GROUP, groups)
        # 查完之后数据还在 —— 这是「重建能找回人」的前提
        self.assertEqual(self._names_in_group(self.GROUP), ["kid", "kid2"])

    def test_revive_all_creates_empty_group_and_keeps_members(self):
        n, revived = ReaderGroupService.revive_groups(None, self.session)
        self.assertEqual((n, revived), (1, [self.GROUP]))
        groups = ReaderGroupService.list_groups()
        self.assertIn(self.GROUP, groups)
        self.assertEqual(groups[self.GROUP]["mode"], "whitelist")
        self.assertEqual(groups[self.GROUP]["categories"], "")
        self.assertEqual(groups[self.GROUP]["tags"], "")
        # 成员归属从来就没丢过，组一回来人自动归位
        self.assertEqual(self._names_in_group(self.GROUP), ["kid", "kid2"])
        # 重建后不再有悬空引用
        self.assertEqual(ReaderGroupService.orphan_groups(self.session), {})

    def test_revive_specific_name_only(self):
        self.session.add(make_reader(name="guest1",
                                     extra={reader_group.MEMBER_KEY: "访客"}))
        self.session.commit()
        n, revived = ReaderGroupService.revive_groups([self.GROUP], self.session)
        self.assertEqual((n, revived), (1, [self.GROUP]))
        self.assertNotIn("访客", ReaderGroupService.list_groups())
        # 没点重建的那个组保持原样，人继续挂着等管理员处理
        self.assertEqual(ReaderGroupService.orphan_groups(self.session), {"访客": ["guest1"]})

    def test_revive_ignores_known_or_unknown_names(self):
        """名字不在悬空集合里（已重建 / 打错字）时什么都不做，不能凭空建组。"""
        n, revived = ReaderGroupService.revive_groups(["不存在的组"], self.session)
        self.assertEqual((n, revived), (0, []))
        self.assertEqual(ReaderGroupService.list_groups(), {})

    def test_revive_without_session_is_noop(self):
        self.assertEqual(ReaderGroupService.revive_groups(None, None), (0, []))
        self.assertEqual(self._names_in_group(self.GROUP), ["kid", "kid2"])

    def test_revived_empty_whitelist_still_blocks_books(self):
        """重建出来的是空白名单：严格模式下组员仍读不到书，不能静默放行全库。"""
        ReaderGroupService.revive_groups(None, self.session)
        r = make_reader(extra={reader_group.MEMBER_KEY: self.GROUP})
        eff = ReaderGroupService.effective_limits(r)
        self.assertEqual(eff["read_limit"], 1)
        self.assertEqual(eff["source"], "group-strict")
        self.assertFalse(reader_group.book_matches_limits({"tags": ["童话"]}, eff))


class TestPresets(unittest.TestCase):
    """预置模板：只是表单初值，但 mode 写错会让整组静默失效。"""

    def test_preset_modes_are_valid(self):
        valid = {"whitelist", "blacklist", "open"}
        for p in reader_group.get_presets():
            self.assertIn(p["mode"], valid, p["name"])

    def test_preset_names_and_desc_present(self):
        presets = reader_group.get_presets()
        names = [p["name"] for p in presets]
        self.assertEqual(len(names), len(set(names)))
        for p in presets:
            self.assertTrue(p["desc"].strip(), p["name"])

    def test_family_preset_is_open_mode(self):
        """成人家属必须是 open：白名单留空在严格模式下等于一本书都看不到。"""
        presets = {p["name"]: p for p in reader_group.get_presets()}
        self.assertEqual(presets["成人家属"]["mode"], "open")

    def test_open_preset_has_no_conditions(self):
        for p in reader_group.get_presets():
            if p["mode"] == "open":
                self.assertEqual(p["categories"], "", p["name"])
                self.assertEqual(p["tags"], "", p["name"])

    def test_preset_tags_normalized(self):
        """模板里的标签串必须是「去空白、去重、逗号分隔」，否则保存后既难比对也难排查。"""
        for p in reader_group.get_presets():
            tags = [t for t in p["tags"].split(",") if t]
            self.assertEqual(len(tags), len(set(tags)), p["name"])
            self.assertEqual(p["tags"], ",".join(tags), p["name"])

    def test_presets_cover_common_scenes(self):
        names = {p["name"] for p in reader_group.get_presets()}
        for expected in ("儿童", "青少年", "访客", "长辈听书",
                         "公版经典", "成人家属", "会员"):
            self.assertIn(expected, names)

    def test_preset_count_is_enough(self):
        """模板太少等于没有：管理员还是得从头手填。"""
        self.assertGreaterEqual(len(reader_group.get_presets()), 14)

    def test_presets_have_known_group(self):
        """分栏标题必须是后端定义的常量，写错字会让那一条单独成一栏。"""
        allowed = {reader_group.PRESET_GROUP_FAMILY, reader_group.PRESET_GROUP_TOPIC}
        for p in reader_group.get_presets():
            self.assertIn(p["group"], allowed, p["name"])

    def test_preset_groups_are_contiguous(self):
        """同栏模板必须连在一起：前端按首次出现的顺序分栏，
        中间插一条别栏的，界面上就会被拆成两个同名小标题。"""
        seen, current = set(), None
        for p in reader_group.get_presets():
            if p["group"] != current:
                self.assertNotIn(p["group"], seen, p["name"])
                seen.add(p["group"])
                current = p["group"]

    def test_non_open_presets_have_tags(self):
        """除了「不限」，模板必须有条件 —— 空白名单在严格模式下读不到书。"""
        for p in reader_group.get_presets():
            if p["mode"] == "open":
                continue
            self.assertTrue(p["tags"].strip(), p["name"])

    def test_presets_never_use_categories(self):
        """#category 列在多数书库是空的，拿它做模板会静默失效（见 PRESET_GROUPS 注释）。"""
        for p in reader_group.get_presets():
            self.assertEqual(p["categories"], "", p["name"])


if __name__ == "__main__":
    unittest.main()
