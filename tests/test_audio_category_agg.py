"""audio_category_agg 共享聚合的回归。

锁定的约束（对应模块 docstring 的设计承诺）：

1. #category 形态口径：str 整串一桶（"A/B" 不拆分）、list/tuple 逐个、
   空/None 不入桶——沿用 podcast 原实现，避免 feed 内容突变；
2. version 未变 → 直接命中缓存，不再触碰元数据（O(1) 短路）；
3. 小变更（增删 ≤ DIFF_SYNC_THRESHOLD）在调用线程同步补齐，结果正确；
4. force 全量重建受 REBUILD_MIN_INTERVAL 节流：窗内返回旧版不重算；
5. categories 与 book_meta 同源：桶里的 id 必在 meta 里，反之亦然
   （受限用户的可见性判定与分类计数共用这份数据）。
"""

import pytest

from webserver.base import audio_category_agg as agg
from webserver.constants import CALIBRE_COLUMN_CATEGORY


class FakeMI:
    """calibre new_api metadata 的最小面：只支持 get("#category") 与 tags/authors。"""

    def __init__(self, category=None, tags=None, authors=None):
        self._category = category
        self.tags = tags or []
        self.authors = authors or []

    def get(self, key):
        if key == CALIBRE_COLUMN_CATEGORY:
            return self._category
        return None


class FakeCache:
    def __init__(self, books):
        self.books = books  # {book_id: FakeMI}
        self.get_calls = 0

    def get_metadata(self, book_id, get_cover=False, get_user_categories=False):
        self.get_calls += 1
        return self.books.get(book_id)


def _reset_state():
    with agg._lock:
        agg._state.update({
            "version": -1,
            "ids": set(),
            "categories": {},
            "book_meta": {},
            "lib_version": None,
            "meta_dirty": False,
            "built_at": 0.0,
            "last_kick": 0.0,
        })


@pytest.fixture(autouse=True)
def _clean_state():
    _reset_state()
    yield
    _reset_state()


def _call(cache, ids, version, **kwargs):
    return agg.get_audio_aggregation(cache, audio_ids=set(ids), version=version, **kwargs)


class TestCategoryShapes:
    """#category 形态口径——podcast feed 内容兼容性的锚。"""

    def test_str_category_one_bucket(self):
        cache = FakeCache({1: FakeMI("科幻"), 2: FakeMI("科幻")})
        rsp = _call(cache, [1, 2], 1, force=True)
        assert rsp["categories"] == {"科幻": [1, 2]}

    def test_list_category_expands(self):
        cache = FakeCache({1: FakeMI(["科幻", "小说"])})
        rsp = _call(cache, [1], 1, force=True)
        assert rsp["categories"]["科幻"] == [1]
        assert rsp["categories"]["小说"] == [1]

    def test_slash_not_split(self):
        """'A/B' 是一个自由文本分类，历史上就不拆分，不许悄悄变。"""
        cache = FakeCache({1: FakeMI("科幻/小说")})
        rsp = _call(cache, [1], 1, force=True)
        assert list(rsp["categories"].keys()) == ["科幻/小说"]

    def test_empty_and_none_excluded(self):
        cache = FakeCache({1: FakeMI(""), 2: FakeMI(None), 3: FakeMI("有效")})
        rsp = _call(cache, [1, 2, 3], 1, force=True)
        assert rsp["categories"] == {"有效": [3]}

    def test_missing_metadata_skipped(self):
        cache = FakeCache({1: FakeMI("科幻"), 999: None})
        rsp = _call(cache, [1, 999], 1, force=True)
        assert rsp["categories"] == {"科幻": [1]}
        assert 999 not in rsp["book_meta"]


class TestVersionShortCircuit:
    def test_same_version_no_refetch(self):
        books = {1: FakeMI("科幻")}
        cache = FakeCache(books)
        _call(cache, [1], 1, force=True)
        assert cache.get_calls == 1
        # version/ids 都没变：不再触碰元数据
        rsp = _call(cache, [1], 1)
        assert cache.get_calls == 1
        assert rsp["categories"] == {"科幻": [1]}

    def test_incremental_diff_syncs(self):
        books = {1: FakeMI("科幻"), 2: FakeMI("文学")}
        cache = FakeCache(books)
        _call(cache, [1, 2], 1, force=True)
        cache.get_calls = 0
        # 新增一本 + 删除一本：走同步增量
        books[3] = FakeMI("科幻")
        rsp = _call(cache, [1, 3], 2)
        assert cache.get_calls == 1  # 只取了新书
        # 文学桶因书 2 移除而消失
        assert "文学" not in rsp["categories"]
        assert rsp["categories"]["科幻"] == [1, 3]

    def test_version_change_with_same_ids_still_reconciles(self):
        books = {1: FakeMI("科幻")}
        cache = FakeCache(books)
        _call(cache, [1], 1, force=True)
        # 全扫后集合没变但 version 变了：ids diff 为空，零开销补齐
        cache.get_calls = 0
        rsp = _call(cache, [1], 2)
        assert cache.get_calls == 0
        assert rsp["categories"] == {"科幻": [1]}


class TestForceThrottle:
    def test_force_rebuild_throttled(self, monkeypatch):
        books = {1: FakeMI("科幻")}
        cache = FakeCache(books)
        _call(cache, [1], 1, force=True)
        # 全库扫描后集合大变（diff > DIFF_SYNC_THRESHOLD）+ 节流窗内：
        # force 也不重算，返回旧版（模拟导入高峰反复 bump version 的场景）
        monkeypatch.setattr(agg, "REBUILD_MIN_INTERVAL", 3600.0)
        cache.get_calls = 0
        big_ids = [1] + list(range(100, 200))  # 100 本新增，diff 必走全量分支
        rsp = _call(cache, big_ids, 2, force=True)
        assert cache.get_calls == 0
        assert rsp["categories"] == {"科幻": [1]}

    def test_force_rebuild_after_interval(self, monkeypatch):
        books = {1: FakeMI("科幻"), 2: FakeMI("文学")}
        cache = FakeCache(books)
        _call(cache, [1], 1, force=True)
        monkeypatch.setattr(agg, "REBUILD_MIN_INTERVAL", 0.0)  # 窗口归零 = 可重建
        rsp = _call(cache, [1, 2], 2, force=True)
        assert rsp["categories"] == {"科幻": [1], "文学": [2]}


class TestMetaConsistency:
    def test_meta_and_buckets_share_source(self):
        books = {
            1: FakeMI("科幻", tags=["太空"], authors=["刘慈欣"]),
            2: FakeMI(None, tags=["随笔"], authors=["鲁迅"]),
        }
        cache = FakeCache(books)
        rsp = _call(cache, [1, 2], 1, force=True)
        # meta 覆盖所有取到元数据的书（含无分类的书——可见性判定需要它）
        assert set(rsp["book_meta"].keys()) == {1, 2}
        meta = rsp["book_meta"][1]
        assert meta["tags"] == ["太空"]
        assert meta["authors"] == ["刘慈欣"]
        assert meta[CALIBRE_COLUMN_CATEGORY] == "科幻"
        # 无分类书在 meta 里有、桶里没有
        assert 2 not in [b for ids in rsp["categories"].values() for b in ids]
