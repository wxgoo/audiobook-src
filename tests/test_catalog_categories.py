"""BaseHandler.catalog_categories —— 「分类」维度的唯一定义源。

这个方法是 /api/categories（分类浏览页）与 /api/audiobooks/categories
（有声书页）共用的骨架，两页的分类名与顺序都由它决定。它一坏，两个页面
同时错，而且错法很隐蔽（分类少了 / 顺序变了 / 受限用户看到全库分类）。
所以单独锁契约，不依赖任何一条 HTTP 用例：

1. 没装 #category 自定义列 → 空列表，不抛异常；
2. 正常情况返回 [{name, count}]，顺序即 SQL 的 count 降序；
3. 阅读范围开关关闭 → 不过滤（全库分类）；
4. 开关开启 + 未登录 → 空列表（访客只读得到无分类的书）；
5. 受限用户有 scoped 聚合 → 用可见口径的 count，0 计数分类剔除并重排；
6. 书库版本变化 → 缓存失效，重新查 SQL。
"""

import asyncio
import unittest
from types import MethodType, SimpleNamespace
from unittest import mock

from webserver.constants import CALIBRE_COLUMN_CATEGORY
from webserver.handlers import base as base_module
from webserver.handlers.base import BaseHandler

ROWS = [("科幻", 9), ("历史", 5), ("文学", 2)]


class StubHandler:
    """只提供 catalog_categories 依赖的最小面（含阅读范围判定）。"""

    def __init__(self, rows=None, has_column=True, current_user=None,
                 is_admin=False, scoped=None, scope_key=None, colnum=901):
        meta = {CALIBRE_COLUMN_CATEGORY: {"colnum": colnum}} if has_column else {}
        self.calibre_db = SimpleNamespace(field_metadata=meta)
        self.current_user = current_user
        self._is_admin = is_admin
        self._rows = ROWS if rows is None else rows
        self._scoped = scoped
        self._scope_key_value = scope_key
        self._version = 1
        self.sql_calls = 0
        # 绑到实例上，模拟真实的 BaseHandler 方法
        self.catalog_categories = MethodType(BaseHandler.catalog_categories, self)
        self._filter_categories_by_reading_range = MethodType(
            BaseHandler._filter_categories_by_reading_range, self)

    def library_version(self):
        return self._version

    def _scope_key(self):
        return self._scope_key_value

    def is_admin(self):
        return self._is_admin

    async def run_calibre_sql(self, sql, params=None):
        self.sql_calls += 1
        return list(self._rows)

    async def run_calibre_read_async(self, func, *args, **kwargs):
        return self._scoped

    def scoped_counts(self, key=None):  # pragma: no cover - 由上面 stub 拦截
        return self._scoped


def _run(handler, allow_range=False):
    with mock.patch.object(base_module, "CONF", {"ALLOW_READ_RANGE_SETTING": allow_range}):
        return asyncio.run(handler.catalog_categories())


class TestCatalogCategories(unittest.TestCase):
    def setUp(self):
        BaseHandler._catalog_cache.clear()

    def test_no_custom_column_returns_empty(self):
        h = StubHandler(has_column=False)
        self.assertEqual(_run(h), [])
        self.assertEqual(h.sql_calls, 0)  # 连 SQL 都不发

    def test_returns_name_and_count_in_sql_order(self):
        h = StubHandler()
        self.assertEqual(_run(h), [
            {"name": "科幻", "count": 9},
            {"name": "历史", "count": 5},
            {"name": "文学", "count": 2},
        ])

    def test_row_tuples_are_plain_dicts(self):
        """返回值必须是纯 dict（前端与 decorate 都按 dict 读）。"""
        h = StubHandler()
        for item in _run(h):
            self.assertIsInstance(item, dict)
            self.assertEqual(set(item), {"name", "count"})

    def test_range_setting_off_keeps_all(self):
        h = StubHandler(current_user=None)
        self.assertEqual(len(_run(h, allow_range=False)), 3)

    def test_guest_with_range_setting_gets_nothing(self):
        """访客只读得到「无分类」的书 → 分类列表为空（与 is_book_visible 同规）。"""
        h = StubHandler(current_user=None)
        self.assertEqual(_run(h, allow_range=True), [])

    def test_admin_with_range_setting_keeps_all(self):
        h = StubHandler(current_user={"id": 1}, is_admin=True)
        self.assertEqual(len(_run(h, allow_range=True)), 3)

    def test_whitelist_filters_by_name(self):
        user = SimpleNamespace(read_limit=1, limit_categories="历史", limit_tags="")
        h = StubHandler(current_user=user)
        names = [c["name"] for c in _run(h, allow_range=True)]
        self.assertEqual(names, ["历史"])

    def test_blacklist_removes_by_name(self):
        user = SimpleNamespace(read_limit=2, limit_categories="科幻", limit_tags="")
        h = StubHandler(current_user=user)
        names = [c["name"] for c in _run(h, allow_range=True)]
        self.assertEqual(names, ["历史", "文学"])

    def test_scoped_counts_replace_count_and_drop_zero(self):
        """受限用户：count 换成可见口径，0 计数分类剔除并按新 count 重排。"""
        h = StubHandler(current_user={"id": 7}, scope_key=("k",),
                        scoped={"categories": {"文学": 4, "历史": 1}})
        got = _run(h, allow_range=True)
        self.assertEqual(got, [{"name": "文学", "count": 4},
                               {"name": "历史", "count": 1}])  # 科幻 0 被剔除
        self.assertEqual([c["count"] for c in got], [4, 1])  # 重排

    def test_cache_invalidated_by_library_version(self):
        h = StubHandler()
        _run(h)
        _run(h)
        self.assertEqual(h.sql_calls, 1)  # 同版本命中缓存
        h._version = 2
        _run(h)
        self.assertEqual(h.sql_calls, 2)  # 书库变了必须重查

    def test_sql_cached_across_handlers(self):
        """两个不同 handler（分类页 / 有声书页）共用同一份缓存条目。"""
        a = StubHandler(colnum=902)
        b = StubHandler(colnum=902)
        _run(a)
        _run(b)
        self.assertEqual((a.sql_calls, b.sql_calls), (1, 0))


if __name__ == "__main__":
    unittest.main()
