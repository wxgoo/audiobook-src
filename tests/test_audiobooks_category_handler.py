"""AudioBooks / AudioBookCategories 的 category 过滤与口径一致性。

核心断言（也写进了接口 docstring 的承诺）：

1. `?category=X` 只返回该分类的有声书；未知分类返回 err:ok 空页（不是报错）；
2. 过滤先于分页：after 游标在过滤后的集合上推进，翻到底 next_cursor=None；
3. **口径一致性**：tab 的 count 必须等于用同一用户请求
   `/api/audiobooks?category=X` 时看到的 total——历史上统计侧与列表侧
   各写各的口径，出现过「树里 328 本点进去 12 本」的事故；
4. 受限用户（读者组范围）下 tab 与列表同步削减；
5. 空分类不出现在 tab 里。
"""

import asyncio
import unittest
from unittest import mock

from webserver.base import audio_category_agg as agg
from webserver.handlers import audio as audio_module
from webserver.handlers.audio import AudioBookCategories, AudioBooks, AudioBooksCache
from webserver.constants import CALIBRE_COLUMN_CATEGORY

# 测试书集：三本书，两本「科幻」、一本无分类；书 3 只有音频元数据但没有
# tags/category（访客视角唯一可见的那本）
BOOKS = {
    1: {"id": 1, "title": "三体", "tags": ["太空"], CALIBRE_COLUMN_CATEGORY: "科幻"},
    2: {"id": 2, "title": "流浪地球", "tags": ["太空"], CALIBRE_COLUMN_CATEGORY: "科幻"},
    3: {"id": 3, "title": "随笔集", "tags": [], CALIBRE_COLUMN_CATEGORY: ""},
}


class FakeMI:
    def __init__(self, category, tags):
        self._category = category
        self.tags = tags
        self.authors = []

    def get(self, key):
        return self._category if key == CALIBRE_COLUMN_CATEGORY else None


class FakeCache:
    def __init__(self, mapping):
        self.mapping = mapping  # {book_id: FakeMI}

    def get_metadata(self, book_id, get_cover=False, get_user_categories=False):
        return self.mapping.get(book_id)


class FakeHandler:
    """只实现两个接口依赖的最小面。可见性按测试需要开启。"""

    def __init__(self, args=None, current_user=None, is_admin=False,
                 read_range=True, effective=None):
        self.args = args or {}
        self.current_user = current_user
        self.admin_flag = is_admin
        self.calibre_db_cache = FakeCache({
            1: FakeMI("科幻", ["太空"]), 2: FakeMI("科幻", ["太空"]), 3: FakeMI("", [])})
        self.effective = effective
        self.request = mock.Mock()
        self.request.headers = {}
        self.written = None

    # ---- AudioBooks.get 的输入 ----
    def get_argument_start(self):
        return int(self.args.get("start", 0))

    def get_argument(self, key, default=""):
        return self.args.get(key, default)

    def get_books(self, ids=None):
        return [BOOKS[b] for b in (ids or []) if b in BOOKS]

    def is_admin(self):
        return self.admin_flag

    async def catalog_categories(self):
        """分类浏览页的骨架（全库 count 降序）。

        顺序是「全库 count 降序」，故意让全库最多的「历史」在有声书里为 0、
        全库最少的「文学」也为 0，而排中间的「科幻」才有 2 本——
        这样若实现按有声书数重排，科幻会跑到第一、历史会被剔除，测试立刻炸。
        """
        return [{"name": "历史", "count": 9},
                {"name": "科幻", "count": 2},
                {"name": "文学", "count": 1}]

    # ---- @js 装饰器需要的面 ----
    def set_header(self, *args, **kwargs):
        pass

    def write(self, rsp):
        self.written = rsp

    def finish(self):
        pass

    def _is_same_site_origin(self, origin):
        return False


def _reset_agg(cache, ids, version=1):
    """把聚合状态直接建成与 ids 一致的基线（绕过后台线程，保持测试确定）。"""
    with agg._lock:
        categories, meta = agg._build_full(cache, set(ids))
        agg._state.update({
            "version": version,
            "ids": set(ids),
            "categories": categories,
            "book_meta": meta,
        })


def _patch_common():
    """公共 patch：书源缓存、页内 listdir、格式化。返回 (patches, bindings)。"""
    patches = [
        mock.patch.object(AudioBooksCache, "get_audio_book_ids",
                          classmethod(lambda cls: {1, 2, 3})),
        mock.patch.object(AudioBooksCache, "get_audio_book_ids_set",
                          classmethod(lambda cls: {1, 2, 3})),
        mock.patch.object(AudioBooksCache, "get_version",
                          classmethod(lambda cls: 1)),
        mock.patch.object(audio_module, "resolve_audio_dir",
                          lambda cache, bid: (None, None)),
        mock.patch.object(audio_module, "BookFormatter",
                          lambda handler, book: type("F", (), {
                              "format": staticmethod(lambda: dict(book))})()),
    ]
    return patches


class TestAudioBooksCategoryFilter(unittest.TestCase):
    def _get(self, handler, allow_range=True):
        # allow_range=False 模拟「无范围限制的普通用户」（快路全可见）
        with mock.patch.multiple(audio_module, CONF={
                "ALLOW_READ_RANGE_SETTING": allow_range}), \
             mock.patch("webserver.services.reader_group.ReaderGroupService.effective_limits",
                        staticmethod(lambda u: u["_eff"])):
            for p in _patch_common():
                p.start()
            try:
                _reset_agg(handler.calibre_db_cache, {1, 2, 3})
                asyncio.run(AudioBooks.get(handler))
            finally:
                mock.patch.stopall()
        return handler.written

    def test_category_filter(self):
        h = FakeHandler(args={"category": "科幻"})
        rsp = self._get(h, allow_range=False)
        self.assertEqual(rsp["err"], "ok")
        self.assertEqual(rsp["total"], 2)
        self.assertEqual([b["id"] for b in rsp["books"]], [2, 1])  # 倒序

    def test_unknown_category_empty_page(self):
        h = FakeHandler(args={"category": "不存在的分类"})
        rsp = self._get(h, allow_range=False)
        self.assertEqual(rsp["err"], "ok")
        self.assertEqual(rsp["total"], 0)
        self.assertEqual(rsp["books"], [])

    def test_no_category_returns_all(self):
        h = FakeHandler(args={})
        rsp = self._get(h, allow_range=False)
        self.assertEqual(rsp["total"], 3)
        self.assertEqual(len(rsp["books"]), 3)

    def test_cursor_advances_within_filtered_set(self):
        h = FakeHandler(args={"category": "科幻", "size": "1"})
        rsp = self._get(h, allow_range=False)
        self.assertEqual([b["id"] for b in rsp["books"]], [2])
        self.assertIsNotNone(rsp["next_cursor"])
        # 带游标翻页：拿到第二本，翻到底 next_cursor=None
        h2 = FakeHandler(args={"category": "科幻", "size": "1",
                               "after": rsp["next_cursor"]})
        rsp2 = self._get(h2, allow_range=False)
        self.assertEqual([b["id"] for b in rsp2["books"]], [1])
        self.assertIsNone(rsp2["next_cursor"])

    def test_guest_sees_only_unrestricted_books(self):
        """未登录 + 开启范围开关：只见无 tags/无分类的书（与 is_book_visible 同规）。"""
        h = FakeHandler(args={}, current_user=None)
        rsp = self._get(h)
        self.assertEqual([b["id"] for b in rsp["books"]], [3])
        self.assertEqual(rsp["total"], 1)


class TestTabCountsConsistency(unittest.TestCase):
    """tab count ≡ 列表 total（同一用户、同一可见集、同一分类）。"""

    def _categories_rsp(self, handler):
        with mock.patch.multiple(audio_module, CONF={
                "ALLOW_READ_RANGE_SETTING": True}), \
             mock.patch("webserver.services.reader_group.ReaderGroupService.effective_limits",
                        staticmethod(lambda u: u["_eff"])):
            for p in _patch_common():
                p.start()
            try:
                _reset_agg(handler.calibre_db_cache, {1, 2, 3})
                asyncio.run(AudioBookCategories.get(handler))
            finally:
                mock.patch.stopall()
        return handler.written

    def test_tab_count_equals_list_total(self):
        admin = FakeHandler(args={}, is_admin=True,
                            current_user={"_eff": {"read_limit": 0}})
        tab = self._categories_rsp(admin)
        self.assertEqual(tab["err"], "ok")
        names = {c["name"]: c["count"] for c in tab["categories"]}
        self.assertEqual(names["科幻"], 2)
        self.assertEqual(tab["total"], 3)
        # 逐个分类：tab count == 列表 total
        for name, cnt in names.items():
            lst = FakeHandler(args={"category": name}, is_admin=True,
                              current_user={"_eff": {"read_limit": 0}})
            rsp = self._get_by_audio(lst)
            self.assertEqual(rsp["total"], cnt, name)
        # 无分类书只出现在「全部」里
        self.assertNotIn("", names)

    def _get_by_audio(self, handler):
        with mock.patch.multiple(audio_module, CONF={
                "ALLOW_READ_RANGE_SETTING": True}), \
             mock.patch("webserver.services.reader_group.ReaderGroupService.effective_limits",
                        staticmethod(lambda u: u["_eff"])):
            for p in _patch_common():
                p.start()
            try:
                _reset_agg(handler.calibre_db_cache, {1, 2, 3})
                asyncio.run(AudioBooks.get(handler))
            finally:
                mock.patch.stopall()
        return handler.written

    def test_restricted_user_counts_shrink_together(self):
        """读者组白名单只认「太空」标签：tab 与列表同步削减。"""
        eff = {"read_limit": 1, "limit_categories": "", "limit_tags": "太空"}
        user = {"_eff": eff}

        tab_h = FakeHandler(args={}, current_user=user)
        tab = self._categories_rsp(tab_h)
        names = {c["name"]: c["count"] for c in tab["categories"]}
        self.assertEqual(names.get("科幻"), 2)
        self.assertEqual(tab["total"], 2)  # 书 3 无标签，白名单下不可见

        lst_h = FakeHandler(args={"category": "科幻"}, current_user=user)
        rsp = self._get_by_audio(lst_h)
        self.assertEqual(rsp["total"], 2)
        self.assertEqual([b["id"] for b in rsp["books"]], [2, 1])

    def test_tab_order_follows_catalog_page(self):
        """分类名与顺序必须与分类浏览页一致，不能按有声书数重排。"""
        admin = FakeHandler(args={"all": "1"}, is_admin=True,
                            current_user={"_eff": {"read_limit": 0}})
        tab = self._categories_rsp(admin)
        # 照抄分类页顺序（历史 → 科幻 → 文学），哪怕有声书最多的是科幻
        self.assertEqual([c["name"] for c in tab["categories"]],
                         ["历史", "科幻", "文学"])
        self.assertEqual([c["count"] for c in tab["categories"]], [0, 2, 0])

    def test_zero_count_hidden_by_default(self):
        """默认剔除有声书为 0 的分类（点进去只能是空页），all=1 才保留。"""
        admin = FakeHandler(args={}, is_admin=True,
                            current_user={"_eff": {"read_limit": 0}})
        tab = self._categories_rsp(admin)
        self.assertEqual([c["name"] for c in tab["categories"]], ["科幻"])
        # 每个 tab 都有图标（与分类页同一套命名规则）
        self.assertTrue(tab["categories"][0].get("icon"))

    def test_empty_categories_removed(self):
        """count 为 0 的分类不进 tab（聚合里可能有已不可见的旧桶）。"""
        # 构造一个只有书 3 可见的受限用户 → 「科幻」桶全被削减 → tab 里消失
        eff = {"read_limit": 1, "limit_categories": "", "limit_tags": "诗词"}
        user = {"_eff": eff}
        tab_h = FakeHandler(args={}, current_user=user)
        tab = self._categories_rsp(tab_h)
        self.assertEqual(tab["categories"], [])
        self.assertEqual(tab["total"], 0)


class TestCacheVersionBump(unittest.TestCase):
    """三个缓存变化入口都必须递增 version（聚合失效依赖它）。"""

    def test_mark_events_bump_version(self):
        before = AudioBooksCache.get_version()
        AudioBooksCache.mark_has_audio(424242)
        self.assertEqual(AudioBooksCache.get_version(), before + 1)
        AudioBooksCache.mark_no_audio(424242)
        self.assertEqual(AudioBooksCache.get_version(), before + 2)
        # _update_cache 走 _scan_audio_directory 桩
        with mock.patch.object(AudioBooksCache, "_scan_audio_directory",
                               classmethod(lambda cls: {1})):
            AudioBooksCache._update_cache()
        self.assertEqual(AudioBooksCache.get_version(), before + 3)
        # 清理，避免污染其它用例的缓存状态
        AudioBooksCache.mark_no_audio(1)
