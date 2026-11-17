# -*- coding: UTF-8 -*-
"""登录失败锁定（r46）测试。

login_guard 的状态存 Reader.extra，这里用最小的假 user 对象（extra + save）
验证计数、锁定到期、成功清零等纯逻辑，避免依赖 social_sqlalchemy 环境。
"""

import time
from types import SimpleNamespace
from unittest import mock

import pytest

from webserver.services import login_guard


class FakeUser:
    """只实现 login_guard 需要的 extra / save 接口。"""

    def __init__(self):
        self.extra = {}
        self.save_calls = 0

    def save(self):
        self.save_calls += 1


@pytest.fixture(autouse=True)
def _clean_lock():
    """每个用例用独立假用户，锁定状态互不干扰；配置恢复默认。"""
    with mock.patch.dict(
        login_guard.CONF,
        {
            "LOGIN_MAX_ATTEMPTS": login_guard.DEFAULT_MAX_ATTEMPTS,
            "LOGIN_LOCK_SECONDS": login_guard.DEFAULT_LOCK_SECONDS,
        },
    ):
        yield


def test_success_clears_failures():
    user = FakeUser()
    login_guard.record_result(user, ok=False)
    login_guard.record_result(user, ok=False)
    assert user.extra.get(login_guard.KEY_FAILURES) == 2

    login_guard.record_result(user, ok=True)
    assert login_guard.KEY_FAILURES not in user.extra
    assert login_guard.KEY_LOCKED_UNTIL not in user.extra
    assert login_guard.remaining_lock_seconds(user) == 0


def test_lockout_after_repeated_failures():
    with mock.patch.dict(login_guard.CONF, {"LOGIN_MAX_ATTEMPTS": 3, "LOGIN_LOCK_SECONDS": 600}):
        user = FakeUser()
        login_guard.record_result(user, ok=False)  # 1
        login_guard.record_result(user, ok=False)  # 2
        assert login_guard.remaining_lock_seconds(user) == 0

        login_guard.record_result(user, ok=False)  # 3 -> lock
        remain = login_guard.remaining_lock_seconds(user)
        assert 0 < remain <= 600
        # 达阈值后失败计数清零，改存锁定截止时间
        assert login_guard.KEY_FAILURES not in user.extra
        assert user.extra[login_guard.KEY_LOCKED_UNTIL] > time.time()


def test_correct_password_during_lockout_is_still_locked():
    """锁定期内即使密码正确，remaining_lock_seconds 仍 > 0，登录入口会拦截。

    （record_result(ok=True) 本身会解锁；入口逻辑是先检查 remain 再校验密码，
    因此这里只断言 remain 语义，不模拟入口绕过。）
    """
    with mock.patch.dict(login_guard.CONF, {"LOGIN_MAX_ATTEMPTS": 2, "LOGIN_LOCK_SECONDS": 600}):
        user = FakeUser()
        login_guard.record_result(user, ok=False)
        login_guard.record_result(user, ok=False)
        assert login_guard.remaining_lock_seconds(user) > 0


def test_lockout_expires():
    with mock.patch.dict(login_guard.CONF, {"LOGIN_MAX_ATTEMPTS": 2, "LOGIN_LOCK_SECONDS": 1}):
        user = FakeUser()
        login_guard.record_result(user, ok=False)
        login_guard.record_result(user, ok=False)
        assert login_guard.remaining_lock_seconds(user) > 0
        # 把锁定时间推到过去
        user.extra[login_guard.KEY_LOCKED_UNTIL] = time.time() - 1
        assert login_guard.remaining_lock_seconds(user) == 0


def test_clear_unlocks():
    with mock.patch.dict(login_guard.CONF, {"LOGIN_MAX_ATTEMPTS": 1, "LOGIN_LOCK_SECONDS": 600}):
        user = FakeUser()
        login_guard.record_result(user, ok=False)
        assert login_guard.remaining_lock_seconds(user) > 0
        login_guard.clear(user)
        assert login_guard.remaining_lock_seconds(user) == 0
        assert login_guard.KEY_FAILURES not in user.extra
        assert login_guard.KEY_LOCKED_UNTIL not in user.extra


def test_none_user_is_noop():
    assert login_guard.remaining_lock_seconds(None) == 0
    login_guard.record_result(None, ok=False)  # 不抛异常
    login_guard.clear(None)


def test_secure_equal():
    assert login_guard.secure_equal("abc", "abc") is True
    assert login_guard.secure_equal("abc", "abd") is False
    assert login_guard.secure_equal("", "") is True


def test_config_clamped():
    with mock.patch.dict(login_guard.CONF, {"LOGIN_MAX_ATTEMPTS": "x", "LOGIN_LOCK_SECONDS": -5}):
        assert login_guard._max_attempts() == login_guard.DEFAULT_MAX_ATTEMPTS
        assert login_guard._lock_seconds() == 1
