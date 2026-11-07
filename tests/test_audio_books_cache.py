"""AudioBooksCache 的请求线程行为回归。

历史实现会在列表请求里同步遍历整个书库（每 5 分钟一次），10 万册库会
把 /api/book 拖到秒级。这里锁定四条约束：

1. 缓存新鲜时，读请求绝不触发磁盘扫描；
2. 缓存过期时，读请求立即返回旧值，扫描只能发生在后台线程；
3. 刷新并发单飞：并发读只触发一次扫描，期间的重复请求不会各起一个线程；
4. 刷新失败时保留旧缓存，不把「有音频」误降级成「没有音频」。

**确定性说明**：后台刷新线程与请求线程是真实线程，所以这里不靠 sleep 或
放宽断言，而是给 `_scan_audio_directory` 装一个 `threading.Event` 闸门——
扫描进入后必须等测试显式放行才返回。于是「读请求返回时扫描仍在进行」是
确定事实（旧值必然还在），「放行后缓存切成新值」也是确定事实。
"""

import threading

import pytest

from webserver.handlers import audio as audio_module
from webserver.handlers.audio import AudioBooksCache

SCAN_TIMEOUT = 5.0  # 闸门最长等待，超时视为「请求线程同步扫盘」的实现回归


class ScanGate:
    """可控的假扫描：进入即挂起，直到测试调用 release()。

    记录调用次数与扫描发生的线程，便于断言「扫描只发生一次」且
    「扫描不在请求线程里」。
    """

    def __init__(self, result):
        self.result = result
        self.entered = threading.Event()
        self.release = threading.Event()
        self.calls = 0
        self.thread_ids = []
        self.timed_out = False

    def __call__(self, cls):
        self.calls += 1
        self.thread_ids.append(threading.get_ident())
        self.entered.set()
        if not self.release.wait(SCAN_TIMEOUT):
            self.timed_out = True
            raise RuntimeError("扫描闸门超时：疑似请求线程在同步扫盘")
        return self.result


def _wait_until(predicate, timeout=5.0):
    """等待状态真正迁移（不是 sleep 掩盖）：超时即判失败。"""
    done = threading.Event()
    timer = threading.Timer(timeout, done.set)
    timer.daemon = True
    timer.start()
    try:
        while not done.is_set():
            if predicate():
                return True
            done.wait(0.005)
        return predicate()
    finally:
        timer.cancel()


@pytest.fixture(autouse=True)
def _reset_cache():
    """每个用例前后清空/还原类级状态，并等后台线程收尾。

    后台刷新线程是真实线程，若不收尾，上一用例的线程会写坏下一用例的
    类变量——这也是原测试偶发失败的次要原因。
    """
    saved = (
        AudioBooksCache._book_ids,
        AudioBooksCache._last_update_time,
        AudioBooksCache._need_update,
        AudioBooksCache._refreshing,
        AudioBooksCache._pending_refresh,
    )
    _wait_until(lambda: not AudioBooksCache._refreshing)
    AudioBooksCache._book_ids = set()
    AudioBooksCache._last_update_time = 0
    AudioBooksCache._need_update = True
    AudioBooksCache._refreshing = False
    AudioBooksCache._pending_refresh = False

    yield

    assert _wait_until(lambda: not AudioBooksCache._refreshing), \
        "后台刷新线程未在超时内收尾，用例留下了悬挂线程"
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
    # 关掉 6 小时兜底，让「新鲜」只由 _need_update 决定，不依赖真实时钟
    monkeypatch.setattr(audio_module, "AUDIO_CACHE_REFRESH_SECONDS", 0)
    AudioBooksCache._book_ids = {7}
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
    monkeypatch.setattr(audio_module, "AUDIO_CACHE_REFRESH_SECONDS", 0)
    AudioBooksCache._book_ids = {1}
    AudioBooksCache._need_update = False

    AudioBooksCache.mark_has_audio(2)
    assert AudioBooksCache.get_audio_book_ids() == {1, 2}

    AudioBooksCache.mark_no_audio(1)
    assert AudioBooksCache.get_audio_book_ids() == {2}

    # 全程没有触发全库扫描
    assert calls == []


def test_stale_read_returns_old_value_then_switches_after_refresh(monkeypatch):
    """过期读返回旧值 → 刷新完成后切到新值。两条断言都由闸门保证。"""
    gate = ScanGate({1, 2})
    monkeypatch.setattr(AudioBooksCache, "_scan_audio_directory", classmethod(gate))
    AudioBooksCache._book_ids = set()
    AudioBooksCache._need_update = True

    # 扫描被闸门挡住时读到旧值 —— 说明请求线程没有等扫描
    assert AudioBooksCache.get_audio_book_ids() == set()
    assert not gate.release.is_set()
    assert not gate.timed_out

    # 后台线程确实进入了扫描，且不在请求线程上
    assert gate.entered.wait(SCAN_TIMEOUT)
    assert gate.thread_ids[0] != threading.get_ident()

    # 刷新进行中，读请求仍然只拿旧值，且不会重复起线程
    assert AudioBooksCache.get_audio_book_ids() == set()
    assert gate.calls == 1

    gate.release.set()
    assert _wait_until(lambda: not AudioBooksCache._refreshing)
    assert AudioBooksCache._book_ids == {1, 2}
    assert gate.calls == 1
    assert not gate.timed_out


def test_reads_during_blocked_refresh_do_not_start_another_scan(monkeypatch):
    """刷新进行中再并发读：全部立即拿到旧值，且不会多起扫描线程。"""
    gate = ScanGate({3})
    monkeypatch.setattr(AudioBooksCache, "_scan_audio_directory", classmethod(gate))
    AudioBooksCache._book_ids = set()
    AudioBooksCache._need_update = True

    # 主线程先触发一次刷新，并确认后台线程已经停在闸门里（此时 _refreshing 必为 True）
    assert AudioBooksCache.get_audio_book_ids() == set()
    assert gate.entered.wait(SCAN_TIMEOUT)
    assert not gate.timed_out

    results = []
    lock = threading.Lock()

    def read():
        value = AudioBooksCache.get_audio_book_ids()
        with lock:
            results.append(value)

    readers = [threading.Thread(target=read) for _ in range(8)]
    for t in readers:
        t.start()
    for t in readers:
        t.join(SCAN_TIMEOUT)

    assert len(results) == 8
    assert all(value == set() for value in results)
    assert not any(t.is_alive() for t in readers)
    assert gate.calls == 1          # 闸门未放行，扫描数不可能增长——确定事实
    assert len(set(gate.thread_ids)) == 1
    assert not gate.timed_out

    gate.release.set()
    assert _wait_until(lambda: not AudioBooksCache._refreshing)
    assert AudioBooksCache._book_ids == {3}
    assert gate.calls == 1
    assert not gate.timed_out


def test_cold_start_concurrent_reads_start_one_refresh_thread(monkeypatch):
    """冷启动就并发：8 个读全部立即返回旧值，扫描只落在同一个后台线程。"""
    gate = ScanGate({4})
    monkeypatch.setattr(AudioBooksCache, "_scan_audio_directory", classmethod(gate))
    AudioBooksCache._book_ids = set()
    AudioBooksCache._need_update = True

    results = []
    lock = threading.Lock()
    start = threading.Barrier(8)

    def read():
        start.wait(SCAN_TIMEOUT)     # 让 8 个读尽量同时进入过期判断
        value = AudioBooksCache.get_audio_book_ids()
        with lock:
            results.append(value)

    readers = [threading.Thread(target=read) for _ in range(8)]
    for t in readers:
        t.start()
    for t in readers:
        t.join(SCAN_TIMEOUT)

    assert len(results) == 8
    assert all(value == set() for value in results)
    assert not any(t.is_alive() for t in readers)
    # 等扫描线程真正进入闸门后，扫描数必然是 1（多起线程会立刻体现为 >1）
    assert gate.entered.wait(SCAN_TIMEOUT)
    assert gate.calls == 1
    assert not gate.timed_out

    gate.release.set()
    assert _wait_until(lambda: not AudioBooksCache._refreshing)
    assert AudioBooksCache._book_ids == {4}
    # 允许竞态窗口里登记一次「补扫」（实现语义），但扫描线程必须只有一个
    assert len(set(gate.thread_ids)) == 1
    assert not gate.timed_out


def test_failed_refresh_keeps_old_cache(monkeypatch):
    """扫描异常时保留旧缓存，并让下一次读继续尝试刷新。"""
    calls = []

    def boom(cls):
        calls.append(1)
        raise RuntimeError("scan failed")

    monkeypatch.setattr(AudioBooksCache, "_scan_audio_directory", classmethod(boom))
    AudioBooksCache._book_ids = {9}
    AudioBooksCache._need_update = True

    assert AudioBooksCache.get_audio_book_ids() == {9}
    assert _wait_until(lambda: not AudioBooksCache._refreshing)

    # 旧缓存原样保留，没有降级成空集；标志仍为需要刷新（便于下次重试）
    assert AudioBooksCache._book_ids == {9}
    assert AudioBooksCache._need_update is True
    assert calls == [1]


def test_successful_empty_scan_clears_cache(monkeypatch):
    """扫描成功但确实没有音频时，缓存才允许变空（与异常路径区分开）。"""
    gate = ScanGate(set())
    monkeypatch.setattr(AudioBooksCache, "_scan_audio_directory", classmethod(gate))
    AudioBooksCache._book_ids = {9}
    AudioBooksCache._need_update = True

    # 扫描卡在闸门里 → 读到旧值 {9} 是确定事实，而不是「碰巧线程还没写完」
    assert AudioBooksCache.get_audio_book_ids() == {9}
    assert gate.entered.wait(SCAN_TIMEOUT)
    assert AudioBooksCache._book_ids == {9}
    assert AudioBooksCache._need_update is True
    assert not gate.timed_out

    gate.release.set()
    assert _wait_until(lambda: not AudioBooksCache._refreshing)
    assert AudioBooksCache._book_ids == set()
    assert AudioBooksCache._need_update is False
    assert gate.calls == 1
