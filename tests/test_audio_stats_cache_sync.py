"""统计接口实时扫盘必须把结果同步进有声书缓存，分类 tab 才能跟上。

事故背景（用户实测）：用户手工往某本书的 .audio/ 目录塞了音频后，
左侧菜单「有声书 N」立刻 +1（BaseHandler.get_audio_books_count 每次实时扫盘），
但 /api/audiobooks 的书列表与分类 tab 读的是 AudioBooksCache（事件驱动 +
6 小时兜底扫描），手工塞文件没有任何事件通知。于是「统计加了 1、文学分类
还是不出来」，最长要等兜底扫描才自愈。

修复：统计接口反正已经扫过盘，顺手 AudioBooksCache.sync_from_scan(...)；
集合真变化才 +version，下游 audio_category_agg 会增量补齐，分类 tab 立刻
反映新书。本测试锁定这条链路与三个边界（空扫盘 / 重复同步 / 统计入口）。

fixture 自包含（pytest 用 importlib 收集，tests/ 不在 sys.path，
不要跨测试文件 import）。
"""

import time

import pytest
from unittest import mock

from webserver.base import audio_category_agg as agg
from webserver.handlers import audio as audio_module
from webserver.handlers.audio import AudioBooksCache, build_audio_tab_categories
from webserver.handlers.base import BaseHandler
from webserver.constants import CALIBRE_COLUMN_CATEGORY as CAT


class FakeMI:
    def __init__(self, category):
        self.category = category
        self.tags = []
        self.authors = []

    def get(self, key):
        return self.category if key == CAT else None


class FakeCache:
    def __init__(self, mapping):
        self.mapping = mapping

    def get_metadata(self, book_id, get_cover=False, get_user_categories=False):
        return self.mapping.get(book_id)


# 与用户库一致：文学在分类浏览页有 12 本，但一开始没有一本带音频
CATALOG = [
    {"name": "文学", "count": 12},
    {"name": "教育", "count": 10},
    {"name": "科幻小说", "count": 3},
    {"name": "演播:李慧敏", "count": 2},
    {"name": "科幻", "count": 1},
]

BASE_IDS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11}
BASE_CATS = {
    1: "教育", 2: "教育",
    3: "科幻小说", 4: "科幻小说", 5: "科幻小说",
    6: "演播:李慧敏", 7: "演播:李慧敏", 8: "演播:李慧敏",
    9: "科幻", 10: "", 11: "",
    # 99 是那本「文学」书：用户刚手工给它加了音频
    99: "文学",
}


def _make_cache():
    return FakeCache({bid: FakeMI(cat) for bid, cat in BASE_CATS.items()})


def _tabs(cache):
    cat_map = agg.get_audio_aggregation(cache)["categories"]
    return [(r["name"], r["count"])
            for r in build_audio_tab_categories(CATALOG, cat_map, None)]


@pytest.fixture(autouse=True)
def _reset_state():
    """隔离类级全局状态，并关掉后台兜底扫描，保证测试确定性。"""
    saved_cache = {
        "_book_ids": AudioBooksCache._book_ids,
        "_version": AudioBooksCache._version,
        "_last_update_time": AudioBooksCache._last_update_time,
        "_need_update": AudioBooksCache._need_update,
    }
    with agg._lock:
        saved_agg = dict(agg._state)
    AudioBooksCache._book_ids = set(BASE_IDS)
    AudioBooksCache._version = 1
    AudioBooksCache._last_update_time = time.time()
    AudioBooksCache._need_update = False
    with agg._lock:
        cats, meta = agg._build_full(_make_cache(), set(BASE_IDS))
        agg._state.update({
            "version": 1, "ids": set(BASE_IDS),
            "categories": cats, "book_meta": meta,
            "built_at": time.time(),
        })
    yield
    for k, v in saved_cache.items():
        setattr(AudioBooksCache, k, v)
    with agg._lock:
        agg._state.clear()
        agg._state.update(saved_agg)


def test_stats_scan_syncs_new_audio_book_into_tabs():
    """统计扫盘发现新书 → 缓存同步 → 分类 tab 立刻多出「文学 (1)」。"""
    cache = _make_cache()
    assert ("文学", 1) not in _tabs(cache), "前置：文学在无音频时不该出现在 tab"

    live_ids = set(BASE_IDS) | {99}
    assert len(live_ids) == 12, "前置：左侧菜单统计应 +1"
    AudioBooksCache.sync_from_scan(live_ids)

    assert AudioBooksCache.get_audio_book_ids_set() == live_ids
    assert AudioBooksCache.get_version() == 2
    tabs = _tabs(cache)
    assert ("文学", 1) in tabs, "同步后文学分类必须立刻出现在 tab"
    assert tabs[0] == ("文学", 1), "catalog 顺序照抄分类浏览页，文学在最前"


def test_repeated_sync_does_not_bump_version():
    """集合没变就别 +version，否则每次统计请求都让派生缓存失效重建。"""
    AudioBooksCache.sync_from_scan(set(BASE_IDS))
    assert AudioBooksCache.get_version() == 1

    AudioBooksCache.sync_from_scan(set(BASE_IDS) | {99})
    v = AudioBooksCache.get_version()
    AudioBooksCache.sync_from_scan(set(BASE_IDS) | {99})
    AudioBooksCache.sync_from_scan(set(BASE_IDS) | {99})
    assert AudioBooksCache.get_version() == v


def test_empty_scan_keeps_old_cache():
    """一次偶发 listdir 失败不能把缓存清空（与 _update_cache 同规）。"""
    AudioBooksCache.sync_from_scan([])
    assert AudioBooksCache.get_audio_book_ids_set() == set(BASE_IDS)
    assert AudioBooksCache.get_version() == 1


def test_bad_ids_are_ignored():
    AudioBooksCache.sync_from_scan([1, "not-an-int", None])
    assert AudioBooksCache.get_audio_book_ids_set() == set(BASE_IDS)
    assert AudioBooksCache.get_version() == 1


def test_get_audio_books_count_feeds_cache():
    """统计接口必须真的调用 sync_from_scan，且返回长度不受影响。"""
    live = {bid: "/fake/.audio" for bid in (set(BASE_IDS) | {99})}
    with mock.patch("webserver.base.audio_dir.find_audios_by_scanning_library",
                    return_value=live), \
         mock.patch.object(AudioBooksCache, "sync_from_scan") as sync:
        n = BaseHandler.get_audio_books_count(mock.Mock())
    assert n == 12
    sync.assert_called_once()
    assert set(sync.call_args[0][0]) == set(live), "喂进缓存的必须是书 id 集合"


def test_sync_failure_does_not_break_stats():
    """同步失败是旁支，不能让统计接口 500。"""
    live = {bid: "/fake/.audio" for bid in BASE_IDS}
    with mock.patch("webserver.base.audio_dir.find_audios_by_scanning_library",
                    return_value=live), \
         mock.patch.object(AudioBooksCache, "sync_from_scan",
                           side_effect=RuntimeError("boom")):
        n = BaseHandler.get_audio_books_count(mock.Mock())
    assert n == len(BASE_IDS)
