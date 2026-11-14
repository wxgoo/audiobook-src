"""改 #category 后分类 tab 聚合必须立刻更新（r38 回归）。

真实事故：详情页把一本有声书改成「教育」，教育 tab 仍显示 2、书也不在
?category=教育 列表里，重启容器才自愈。根因：audio_category_agg 只跟随
AudioBooksCache.get_version()（有音频的书**集合**版本）失效，而改分类是
calibre 元数据变化、集合一个都没变，version 纹丝不动。

本测试锁定：
1. 不通知时快照确实旧（复现 bug）；
2. on_category_changed() 按新值即时挪桶，且不读 calibre 元数据（O(1)）；
3. 清空分类、跨分类移动、保留 tags/authors（受限用户可见性口径）；
4. 非有声书/未建好/坏输入都安全；
5. library_version() 变化或 meta_dirty 时走全量重建，**绝不**走「集合增量
   空转」——那条路 diff 为空却会把 version 推到最新，把旧元数据永久钉死；
6. 批量通知与超阈值退化。

fixture 自包含（pytest 用 importlib 收集，不要跨测试文件 import）。
"""

import pytest

from webserver.base import audio_category_agg as agg
from webserver.constants import CALIBRE_COLUMN_CATEGORY as CAT


class FakeMI:
    """calibre new_api metadata 的最小面。"""

    def __init__(self, category=None, tags=None, authors=None):
        self._category = category
        self.tags = tags or []
        self.authors = authors or []

    def get(self, key):
        return self._category if key == CAT else None


class FakeCache:
    def __init__(self, books):
        self.books = books
        self.get_calls = 0

    def get_metadata(self, book_id, get_cover=False, get_user_categories=False):
        self.get_calls += 1
        return self.books.get(book_id)

    def set_field(self, field, updates):
        """模拟 calibre 写库：之后 get_metadata 能读到新值。"""
        for bid, val in updates.items():
            if bid in self.books:
                self.books[bid]._category = val


def _state_reset():
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
    _state_reset()
    yield
    _state_reset()


def _make_cache():
    # 对照现场：教育 2 本、文学 1 本、科幻小说 4 本、社科 1 本、无分类 2 本
    return FakeCache({
        1: FakeMI("教育", tags=["教材"], authors=["甲"]),
        2: FakeMI("教育"),
        3: FakeMI("文学"),
        4: FakeMI("科幻小说"),
        5: FakeMI("科幻小说"),
        6: FakeMI("科幻小说"),
        7: FakeMI("科幻小说"),
        8: FakeMI("社科"),
        9: FakeMI(""),
        10: FakeMI(""),
    })


IDS = set(range(1, 11))


def _build(cache, version=1, lib_version=None):
    """模拟一次已完成的同步全量构建，绕开后台线程时序。"""
    with agg._lock:
        cats, meta = agg._build_full(cache, IDS)
        agg._apply_full(agg._state, IDS, cats, meta)
        agg._state.update({
            "version": version,
            "lib_version": lib_version,
            "meta_dirty": False,
            "built_at": 0.0,
            "last_kick": 0.0,
        })


class TestBugAndImmediateNotify:

    def test_without_notify_snapshot_stays_stale(self):
        """复现：DB 改了、集合版本没变、没人通知 → 聚合仍旧。"""
        cache = _make_cache()
        _build(cache)
        cache.set_field(CAT, {9: "教育"})
        rsp = agg.get_audio_aggregation(cache, audio_ids=IDS, version=1)
        assert rsp["categories"]["教育"] == [1, 2]
        assert 9 not in rsp["book_meta"] or rsp["book_meta"][9][CAT] == ""
        assert 9 not in agg.get_audio_categories(cache, IDS, 1).get("教育", [])

    def test_notify_moves_book_immediately_without_reading_db(self):
        """通知后立刻进桶，且完全不触碰 calibre 元数据。"""
        cache = _make_cache()
        _build(cache)
        cache.set_field(CAT, {9: "教育"})
        cache.get_calls = 0
        agg.on_category_changed(9, "教育")
        assert cache.get_calls == 0
        rsp = agg.get_audio_aggregation(cache, audio_ids=IDS, version=1)
        assert sorted(rsp["categories"]["教育"]) == [1, 2, 9]
        assert rsp["book_meta"][9][CAT] == "教育"
        assert agg._state["version"] == 1          # 集合版本没被误改
        assert sorted(agg.get_audio_categories(cache, IDS, 1)["教育"]) == [1, 2, 9]

    def test_move_between_buckets(self):
        cache = _make_cache()
        _build(cache)
        cache.set_field(CAT, {3: "教育"})
        agg.on_category_changed(3, "教育")
        rsp = agg.get_audio_aggregation(cache, audio_ids=IDS, version=1)
        assert sorted(rsp["categories"]["教育"]) == [1, 2, 3]
        assert "文学" not in rsp["categories"]       # 空桶被清掉
        assert rsp["book_meta"][3][CAT] == "教育"

    def test_clear_category_removes_bucket_but_keeps_tags(self):
        cache = _make_cache()
        _build(cache)
        cache.set_field(CAT, {1: ""})
        agg.on_category_changed(1, "")
        rsp = agg.get_audio_aggregation(cache, audio_ids=IDS, version=1)
        assert rsp["categories"]["教育"] == [2]
        assert rsp["book_meta"][1][CAT] == ""
        # _visible_audio_ids 靠 tags/#category 判可见，不能把 tags 弄丢
        assert rsp["book_meta"][1]["tags"] == ["教材"]
        assert rsp["book_meta"][1]["authors"] == ["甲"]

    def test_non_audio_book_ignored(self):
        cache = _make_cache()
        _build(cache)
        before = dict(agg._state["categories"])
        agg.on_category_changed(999, "教育")
        assert agg._state["categories"] == before
        assert 999 not in agg._state["book_meta"]

    def test_unbuilt_agg_is_safe_and_builds_fresh(self):
        """聚合还没建好时通知不崩；之后的首次全量构建读最新 DB。"""
        cache = _make_cache()
        cache.set_field(CAT, {9: "教育"})
        agg.on_category_changed(9, "教育")           # version=-1，应直接忽略
        rsp = agg.get_audio_aggregation(cache, audio_ids=IDS, version=1, force=True)
        assert sorted(rsp["categories"]["教育"]) == [1, 2, 9]

    def test_bad_input_never_raises(self):
        agg.on_category_changed("not-an-int", None)
        agg.on_categories_changed({"x": 1})
        agg.on_categories_changed(None)


class TestMetaDirtyRebuild:

    def test_lib_version_change_triggers_force_rebuild(self, monkeypatch):
        """库版本推进（漏通知的写入）→ 全量重建读到新分类。"""
        cache = _make_cache()
        _build(cache, lib_version=("t1", 0))
        cache.set_field(CAT, {9: "教育"})            # 故意不通知
        monkeypatch.setattr(agg, "_lib_version_of", lambda cache: ("t2", 0))
        rsp = agg.get_audio_aggregation(
            cache, audio_ids=IDS, version=1, force=True)
        assert sorted(rsp["categories"]["教育"]) == [1, 2, 9]
        assert agg._state["lib_version"] == ("t2", 0)
        assert agg._state["meta_dirty"] is False

    def test_invalidate_marks_dirty(self):
        cache = _make_cache()
        _build(cache)
        agg.invalidate()
        assert agg._state["meta_dirty"] is True

    def test_meta_dirty_never_takes_empty_diff_path(self, monkeypatch):
        """关键回归：version 变了但 ids 不变 + 元数据脏，不能走集合增量空转。

        那条分支 added/removed 都为空，会把 version 推到最新却什么都不重算，
        旧元数据就被永久钉死。必须转全量重建（这里是后台 kick）。
        """
        cache = _make_cache()
        _build(cache, lib_version=("t1", 0))
        cache.set_field(CAT, {9: "教育"})
        monkeypatch.setattr(agg, "_lib_version_of", lambda cache: ("t2", 0))
        kicked = []
        monkeypatch.setattr(agg, "_kick_rebuild",
                            lambda *a, **kw: kicked.append(a))
        rsp = agg.get_audio_aggregation(cache, audio_ids=IDS, version=2)
        assert len(kicked) == 1                    # 走的是全量重建
        assert kicked[0][2] == 2                   # (cache, ids, version, ...)
        assert agg._state["version"] == 1          # 没被增量分支偷偷推到 2
        assert 9 not in rsp["categories"]["教育"]  # 允许秒级滞后，但不许静默钉死

    def test_same_version_and_same_lib_version_short_circuits(self, monkeypatch):
        cache = _make_cache()
        _build(cache, lib_version=("t1", 0))
        monkeypatch.setattr(agg, "_lib_version_of", lambda cache: ("t1", 0))
        cache.get_calls = 0
        agg.get_audio_aggregation(cache, audio_ids=IDS, version=1)
        assert cache.get_calls == 0


class TestBatchNotify:

    def test_batch_moves_all(self):
        cache = _make_cache()
        _build(cache)
        agg.on_categories_changed({1: "文学", 2: "文学", 3: "教育"})
        rsp = agg.get_audio_aggregation(cache, audio_ids=IDS, version=1)
        assert "教育" in rsp["categories"]
        assert sorted(rsp["categories"]["教育"]) == [3]
        assert sorted(rsp["categories"]["文学"]) == [1, 2]
        assert rsp["book_meta"][1][CAT] == "文学"

    def test_batch_over_threshold_degrades_to_invalidate(self):
        cache = _make_cache()
        _build(cache)
        before = {k: list(v) for k, v in agg._state["categories"].items()}
        agg.on_categories_changed({i: "教育" for i in range(201)})
        assert agg._state["meta_dirty"] is True
        assert {k: list(v) for k, v in agg._state["categories"].items()} == before
