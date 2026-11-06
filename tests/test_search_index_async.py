"""cached_search_async 的线程化回归：FTS 查询不允许阻塞事件循环。

build.20 之前 `get_search_index().search(query)` 直接跑在 ioloop 线程上，
索引大、查询复杂时会把这个进程里所有请求一起卡住。这里用「可控阻塞的
FTS 查询 + 心跳协程」证明检索在工作线程里进行，且慢检索期间事件循环
仍然能推进（不是靠读代码保证）。

语义约束（与改造前一致）：结果顺序原样返回、不排序不去重；FTS 返回
None 时回退 calibre；异常照常向上抛且不写缓存。
"""

import asyncio
import threading

from webserver.handlers import base as base_module
from webserver.handlers.base import BaseHandler

GATE_TIMEOUT = 5.0


class _FakeCache:
    """只实现 cached_search_async 用到的 get/put。"""

    def __init__(self):
        self.data = {}
        self.puts = 0

    def get(self, query, version):
        return self.data.get((query, version))

    def put(self, query, version, ids):
        self.puts += 1
        self.data[(query, version)] = ids


class _FakeHandler:
    """只实现 cached_search_async 依赖的接口，避免拉起完整 Tornado 请求。"""

    def __init__(self, cache=None, calibre_result=()):
        self.cache = cache if cache is not None else _FakeCache()
        self.calibre_result = calibre_result
        self.calibre_calls = 0
        outer = self

        class _CalibreCache:
            def search(self, query):
                outer.calibre_calls += 1
                return outer.calibre_result

        self.calibre_db_cache = _CalibreCache()

    def library_version(self):
        return 1

    def search_cache(self):
        return self.cache

    async def run_calibre_read_async(self, func, *args, **kwargs):
        return func(*args, **kwargs)

    async def search(self, query):
        return await BaseHandler.cached_search_async(self, query)


def _patch_index(monkeypatch, search_impl):
    class FakeIndex:
        search = staticmethod(search_impl)

    monkeypatch.setattr(base_module, "get_search_index", lambda: FakeIndex())


def test_slow_fts_search_does_not_block_event_loop(monkeypatch):
    """FTS 卡住时：其它协程照常推进，检索本身在非事件循环线程上执行。"""
    calls = []
    worker_threads = []
    entered = threading.Event()
    release = threading.Event()

    def slow_search(query):
        calls.append(query)
        worker_threads.append(threading.get_ident())
        entered.set()
        if not release.wait(GATE_TIMEOUT):
            raise RuntimeError("FTS 闸门超时：检索没有在独立工作线程上执行")
        return [3, 1, 2]     # 故意不是升序，用于断言顺序原样返回

    _patch_index(monkeypatch, slow_search)
    handler = _FakeHandler()

    async def scenario():
        ticks = 0
        heartbeat_done = asyncio.Event()

        async def heartbeat():
            nonlocal ticks
            while not heartbeat_done.is_set():
                ticks += 1
                await asyncio.sleep(0.001)

        async def wait_entered():
            while not entered.is_set():
                await asyncio.sleep(0.001)

        hb = asyncio.create_task(heartbeat())
        search_task = asyncio.create_task(handler.search("慢查询"))
        try:
            await asyncio.wait_for(wait_entered(), GATE_TIMEOUT)
            # FTS 已进入工作线程并停在闸门里，请求协程在等它
            assert not search_task.done()
            assert worker_threads[0] != threading.get_ident(), "FTS 仍在事件循环线程上执行"
            assert ticks > 0

            # 事件循环在慢检索期间继续跑：心跳计数必须继续增长
            before = ticks
            await asyncio.sleep(0.05)
            assert ticks > before, "慢检索期间事件循环被阻塞，心跳没有推进"
            assert not search_task.done()

            release.set()
            assert await asyncio.wait_for(search_task, GATE_TIMEOUT) == [3, 1, 2]
        finally:
            release.set()
            heartbeat_done.set()
            await hb

    asyncio.run(scenario())

    # 结果整串写入缓存：顺序保留、未排序未去重
    assert handler.cache.puts == 1
    assert handler.cache.get("慢查询", 1) == (3, 1, 2)
    assert handler.calibre_calls == 0

    # 第二次读命中缓存，不再触发检索
    assert asyncio.run(handler.search("慢查询")) == [3, 1, 2]
    assert calls == ["慢查询"]
    assert len(set(worker_threads)) == 1


def test_fts_none_falls_back_to_calibre(monkeypatch):
    """FTS 返回 None（索引缺失/高级语法）时回退 calibre，语义与改造前一致。"""
    _patch_index(monkeypatch, lambda query: None)
    handler = _FakeHandler(calibre_result=("b", "a"))

    assert asyncio.run(handler.search("q")) == ["b", "a"]
    assert handler.calibre_calls == 1
    assert handler.cache.puts == 1


def test_fts_exception_propagates_and_is_not_cached(monkeypatch):
    """改造前异常直接向上抛；线程化后仍是同一条路径，且不写缓存。"""
    def boom(query):
        raise RuntimeError("fts broke")

    _patch_index(monkeypatch, boom)
    handler = _FakeHandler(calibre_result=("x",))

    try:
        asyncio.run(handler.search("q"))
    except RuntimeError as exc:
        assert str(exc) == "fts broke"
    else:  # pragma: no cover - 失败时给出明确原因
        raise AssertionError("FTS 异常被吞掉了，回退语义发生变化")

    assert handler.cache.puts == 0
    assert handler.calibre_calls == 0
