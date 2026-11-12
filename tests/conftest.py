# -*- coding: utf-8 -*-
"""pytest 全局夹具（只放「每个测试文件都需要」的东西）。

## 为什么要在这里建 event loop

Python 3.12 起 `asyncio.get_event_loop()` 不再「没有就顺手给你建一个」：
当前线程没有 set 过 loop、也没有正在运行的 loop 时，它直接抛

    RuntimeError: There is no current event loop in thread 'MainThread'

而 `tests/` 下一批用例用的是老写法：

    loop = asyncio.get_event_loop()
    loop.run_until_complete(coro)

（test_sync.py 里三十来处、test_cfi_gen.py 的 `run()`、test_main.py 的一处）

单跑这些文件时往往是绿的 —— 因为同一次进程里别人（tornado / 别家测试）
已经建过 loop 并 set 上了。但全量跑时执行顺序一变，某个用例
`loop.close()` 之后没人再 set，下一个文件就撞在这个 RuntimeError 上。
表现是「单跑绿、整跑红」，而且红的文件每次都换，很难定位。

已有就不动，避免顶掉别人正在用的那个（比如 tornado 自己建的）。
"""

import asyncio

import pytest

# 夹具缺件现场生成（tests/cases/library/、old.epub、new.epub 都不入库）。
# 放在 import 期做，是因为 test_cfi_gen.py 在**模块级**就按
# `os.path.exists(tests/cases/old.epub)` 决定要不要跳过用例，那时任何
# fixture 都还没跑。生成失败不在这里抛：让真正依赖它的用例自己报错，
# 否则连「不需要夹具」的测试文件都跑不起来。
try:
    from tests.fixtures_gen import ensure_fixtures

    ensure_fixtures()
except Exception as _e:  # pragma: no cover - 环境缺 calibre 等
    print("[fixtures] 生成失败，依赖夹具的用例会红：%r" % (_e,))


@pytest.fixture(autouse=True)
def _ensure_event_loop():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    if loop.is_closed():
        # 被前面的用例 close 掉了：换一个新的，否则 run_until_complete 会炸
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    yield
