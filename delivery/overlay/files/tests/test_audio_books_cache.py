"""AudioBooksCache 的请求线程行为回归：

历史实现会在列表请求里同步遍历整个书库（每 5 分钟一次），10 万册库会
把 /api/book 拖到秒级。这里锁定两条约束：
1. 缓存新鲜时，读请求绝不触发磁盘扫描；
2. 缓存过期时，读请求立即返回旧值，扫描只能发生在后台线程。
"""

import time

import pytest

from webserver.handlers.audio import AudioBooksCache


@pytest.fixture(autouse=True)
def _reset_cache():
    saved = (
        AudioBooksCache._book_ids,
        AudioBooksCache._last_update_time,
        AudioBooksCache._need_update,
        AudioBooksCache._refreshing,
        AudioBooksCache._pending_refresh,
    )
    yield
    (AudioBooksCache._book_ids,
     AudioBooksCache._last_update_time,
     AudioBooksCache._need_update,
     AudioBooksCache._refreshing,
     AudioBooksCache._pending_refresh) = saved


def test_fresh_cache_read_does_not_scan(monkeypatch):
    calls = []

    def fake_scan(cls):
        calls.append(1)
        return {7}

    monkeypatch.setattr(AudioBooksCache, "_scan_audio_directory", classmethod(fake_scan))
    AudioBooksCache._book_ids = {7}
    AudioBooksCache._last_update_time = time.time()
    AudioBooksCache._need_update = False

    assert AudioBooksCache.get_audio_book_ids() == {7}
    assert AudioBooksCache.has_audio(7)
    assert AudioBooksCache.get_audio_book_ids_set() == {7}
    assert calls == []


def test_audio_flag_updates_are_incremental(monkeypatch):
    calls = []

    def fake_scan(cls):
        calls.append(1)
        return set()

    monkeypatch.setattr(AudioBooksCache, "_scan_audio_directory", classmethod(fake_scan))
    AudioBooksCache._book_ids = {1}
    AudioBooksCache._last_update_time = time.time()
    AudioBooksCache._need_update = False

    AudioBooksCache.mark_has_audio(2)
    assert AudioBooksCache.get_audio_book_ids() == {1, 2}

    AudioBooksCache.mark_no_audio(1)
    assert AudioBooksCache.get_audio_book_ids() == {2}

    # 全程没有触发全库扫描
    assert calls == []


def test_stale_cache_returns_immediately_and_refreshes_in_background(monkeypatch):
    def fake_scan(cls):
        return {1, 2}

    monkeypatch.setattr(AudioBooksCache, "_scan_audio_directory", classmethod(fake_scan))
    AudioBooksCache._book_ids = set()
    AudioBooksCache._last_update_time = 0
    AudioBooksCache._need_update = True
    AudioBooksCache._refreshing = False
    AudioBooksCache._pending_refresh = False

    started = time.time()
    assert AudioBooksCache.get_audio_book_ids() == set()
    assert time.time() - started < 0.5  # 不阻塞

    deadline = time.time() + 2
    while AudioBooksCache._book_ids != {1, 2} and time.time() < deadline:
        time.sleep(0.02)
    assert AudioBooksCache._book_ids == {1, 2}
