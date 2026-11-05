"""AudioPlayback 服务端进度仲裁（4.6.0-19）的自包含单元测试。

不依赖 Tornado / 数据库：把 handlers/audio.py 里 POST 的仲裁逻辑抽成
`_decide_progress_write()`（见下），这里直接对纯函数断言。之所以不整包
起服务，是因为沙箱缺 social_sqlalchemy 等运行时依赖（见 tests/run.py 的
stub 说明）。

覆盖：
  1. 空库首次写入 → accept
  2. 更晚的时间戳 → accept
  3. 更早的时间戳 → reject，且返回服务端原值
  4. 相同时间戳 → reject（幂等重放不覆盖）
  5. 客户端不带 client_ts（老版本前端）→ accept（不能把老客户端锁死）
  6. 未来时间戳被钳制，不会永久锁死其他设备
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _clamp_client_ts(client_ts, now_ms, skew_ms=60000):
    """与 handlers/audio.py 内联逻辑保持一致：未来时间钳到当前。"""
    if client_ts > now_ms + skew_ms:
        return now_ms
    return client_ts


def _decide_progress_write(prev_ts, client_ts_raw, now_ms):
    """返回 (accept, effective_ts)。

    accept=False 表示服务端已有的进度更新，本次写入应被丢弃。
    """
    try:
        client_ts = int(float(client_ts_raw or 0))
    except (TypeError, ValueError):
        client_ts = 0
    client_ts = _clamp_client_ts(client_ts, now_ms)
    prev_ts = prev_ts or 0
    if client_ts and client_ts <= prev_ts:
        return False, prev_ts
    return True, (client_ts or now_ms)


def test_first_write_accepted():
    ok, ts = _decide_progress_write(0, 1000, 1000)
    assert ok is True
    assert ts == 1000


def test_newer_write_accepted():
    ok, ts = _decide_progress_write(1000, 2000, 2000)
    assert ok is True
    assert ts == 2000


def test_older_write_rejected_and_keeps_server_value():
    ok, ts = _decide_progress_write(2000, 1000, 3000)
    assert ok is False
    assert ts == 2000, "拒绝时必须回传服务端原时间戳，供客户端比对"


def test_same_ts_rejected_is_idempotent():
    ok, ts = _decide_progress_write(2000, 2000, 2000)
    assert ok is False
    assert ts == 2000


def test_legacy_client_without_ts_accepted():
    """老前端不发 client_ts：必须放行，否则升级后进度全丢。"""
    ok, ts = _decide_progress_write(9999, 0, 5000)
    assert ok is True
    assert ts == 5000


def test_future_ts_clamped():
    """设备时钟快了 1 小时：钳到 now，不产生「未来锁」。"""
    now = 1_000_000
    ok, ts = _decide_progress_write(0, now + 3_600_000, now)
    assert ok is True
    assert ts == now
    # 紧接着另一台正常设备（时间略晚）仍能写入
    ok2, ts2 = _decide_progress_write(ts, now + 1000, now + 1000)
    assert ok2 is True


def test_bad_ts_type_falls_back():
    ok, ts = _decide_progress_write(0, "abc", 777)
    assert ok is True
    assert ts == 777


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
