"""书列表 /api/audiobooks 必须随响应下发分类 tab 数据。

背景（真实事故）：本前端是 SPA 模式，`asyncData` 在客户端每次导航都会跑，
成功返回后把 `ssr_loaded=true` merge 进组件 data；`mounted()` 的
`!ssr_loaded && !inited` 守卫因此跳过 `init()`，而 `fetchAudioCategories()`
只写在 `init()` 里——分类请求永远不发，`audioCategories` 恒为 []，
`audioTabs.length > 1` 不成立，tab 静默不渲染。表现是「Console 干净、
书列表正常、手动访问 /api/audiobooks/categories 也有数据」，极易误判成
浏览器缓存。所以分类数据必须由 asyncData 能拿到的那份响应（书列表）带出。

本测试锁定：列表带 tab 数据、与独立分类接口完全一致（含顺序与图标）、
`?category=X` 时「全部」计数仍是全量、分类构造失败不拖垮书列表。

fixture 自包含（pytest 用 importlib 收集，tests/ 不在 sys.path，
不要跨测试文件 import）。
"""

import asyncio
import unittest
from unittest import mock

from webserver.base import audio_category_agg as agg
from webserver.handlers import audio as audio_module
from webserver.handlers.audio import (
    AudioBooks,
    AudioBooksCache,
    AudioBookCategories,
    build_audio_tab_categories,
)
from webserver.constants import CALIBRE_COLUMN_CATEGORY

BOOKS = {
    1: {"id": 1, "title": "三体", "tags": ["太空"], CALIBRE_COLUMN_CATEGORY: "科幻"},
    2: {"id": 2, "title": "流浪地球", "tags": ["太空"], CALIBRE_COLUMN_CATEGORY: "科幻"},
    3: {"id": 3, "title": "随笔集", "tags": [], CALIBRE_COLUMN_CATEGORY: ""},
}


class FakeUser:
    """阅读范围限制用户对象（对齐上游直读 user 字段）。"""

    def __init__(self, read_limit=0, limit_categories="", limit_tags="", **kw):
        self.read_limit = read_limit
        self.limit_categories = limit_categories
        self.limit_tags = limit_tags
        self.admin = kw.get("admin", False)
        self.id = kw.get("id", 1)


class FakeMI:
    def __init__(self, category, tags):
        self._category = category
        self.tags = tags
        self.authors = []

    def get(self, key):
        return self._category if key == CALIBRE_COLUMN_CATEGORY else None


class FakeCache:
    def __init__(self, mapping):
        self.mapping = mapping

    def get_metadata(self, book_id, get_cover=False, get_user_categories=False):
        return self.mapping.get(book_id)


class FakeHandler:
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

    def get_argument_start(self):
        return int(self.args.get("start", 0))

    def get_argument(self, key, default=""):
        return self.args.get(key, default)

    def get_books(self, ids=None):
        return [BOOKS[b] for b in (ids or []) if b in BOOKS]

    def is_admin(self):
        return self.admin_flag

    async def catalog_categories(self):
        # 顺序是「全库 count 降序」：历史/文学在有声书里为 0，只有科幻有 2 本
        return [{"name": "历史", "count": 9},
                {"name": "科幻", "count": 2},
                {"name": "文学", "count": 1}]

    def set_header(self, *args, **kwargs):
        pass

    def write(self, rsp):
        self.written = rsp

    def finish(self):
        pass

    def _is_same_site_origin(self, origin):
        return False


def _reset_agg(cache, ids, version=1):
    with agg._lock:
        categories, meta = agg._build_full(cache, set(ids))
        agg._state.update({
            "version": version, "ids": set(ids),
            "categories": categories, "book_meta": meta,
        })


def _patch_common():
    return [
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


class TestAudioBooksListCarriesTabs(unittest.TestCase):
    def _get(self, handler, allow_range=False, extra_patches=()):
        with mock.patch.multiple(audio_module, CONF={
                "ALLOW_READ_RANGE_SETTING": allow_range}):
            for p in list(_patch_common()) + list(extra_patches):
                p.start()
            try:
                _reset_agg(handler.calibre_db_cache, {1, 2, 3})
                asyncio.run(AudioBooks.get(handler))
            finally:
                mock.patch.stopall()
        return handler.written

    def _categories(self, handler):
        with mock.patch.multiple(audio_module, CONF={
                "ALLOW_READ_RANGE_SETTING": True}):
            for p in _patch_common():
                p.start()
            try:
                _reset_agg(handler.calibre_db_cache, {1, 2, 3})
                asyncio.run(AudioBookCategories.get(handler))
            finally:
                mock.patch.stopall()
        return handler.written

    def test_list_carries_tab_categories_and_total(self):
        rsp = self._get(FakeHandler(args={}))
        self.assertEqual(rsp["err"], "ok")
        self.assertIn("audioCategories", rsp)
        self.assertIn("audioTotal", rsp)
        self.assertEqual(rsp["audioTotal"], 3)  # 全量可见有声书
        names = {c["name"]: c["count"] for c in rsp["audioCategories"]}
        self.assertEqual(names.get("科幻"), 2)
        self.assertNotIn("历史", names)  # 0 计数分类不出现
        self.assertNotIn("文学", names)
        self.assertTrue(all("icon" in c for c in rsp["audioCategories"]))

    def test_list_tabs_match_categories_endpoint(self):
        """同一用户下，列表下发的 tab 与独立分类接口逐字一致（含顺序）。"""
        h = FakeHandler(args={}, is_admin=True,
                        current_user=FakeUser(read_limit=0))
        rsp = self._get(h, allow_range=True)
        tab = self._categories(h)
        self.assertEqual(rsp["audioCategories"], tab["categories"])
        self.assertEqual(rsp["audioTotal"], tab["total"])

    def test_audio_total_is_unfiltered_when_category_selected(self):
        """?category=科幻 时「全部」tab 仍显示全量数，不是筛选后的 total。"""
        rsp = self._get(FakeHandler(args={"category": "科幻"}), allow_range=False)
        self.assertEqual(rsp["total"], 2)
        self.assertEqual(rsp["audioTotal"], 3)
        self.assertEqual([c["name"] for c in rsp["audioCategories"]], ["科幻"])

    def test_category_build_failure_does_not_break_list(self):
        """分类只是增强信息，构造失败不能拖垮书列表。"""
        rsp = self._get(FakeHandler(args={}), extra_patches=[
            mock.patch.object(audio_module, "build_audio_tab_categories",
                              side_effect=RuntimeError("boom")),
        ])
        self.assertEqual(rsp["err"], "ok")
        self.assertEqual(len(rsp["books"]), 3)
        self.assertEqual(rsp["audioCategories"], [])

    def test_shared_helper_is_used_by_both(self):
        """两处 tab 必须走同一份实现，防止今后各写各的口径漂移。"""
        catalog = [{"name": "科幻", "count": 9}, {"name": "历史", "count": 9}]
        rows = build_audio_tab_categories(catalog, {"科幻": [1, 2]}, None)
        self.assertEqual([r["name"] for r in rows], ["科幻"])
        self.assertEqual(rows[0]["count"], 2)
        self.assertIn("icon", rows[0])


if __name__ == "__main__":
    unittest.main()
