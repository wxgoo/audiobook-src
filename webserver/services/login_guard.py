#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""登录失败锁定（r46）。

借鉴 book_share_service.verify 的失败计数模型，但只作用于**交互式登录**
（Web 的 SignIn / WAP 的 WapLogin）。设备凭据类入口（Basic Auth、token、
MCP、WebDAV、社交登录）不接入，避免合法设备被误锁。

状态存 ``Reader.extra``（JSON 列），因此：
  - 跨进程共享（Docker 多 worker / 多实例下都生效）；
  - 服务重启不丢；
  - 无需 ALTER TABLE 迁移。

计数维度为 (ip, username)：纯按账号易被恶意锁定他人，纯按 IP 易被代理绕过。
失败文案统一为「用户名或密码错误」，避免用户枚举。
"""

import hmac
import math
import threading
import time
from typing import Optional

from webserver import loader

CONF = loader.get_settings()

# 默认值；运行期从 CONF 动态读取，配置页改完即时生效。
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_LOCK_SECONDS = 600

# extra 列里的键名
KEY_FAILURES = "login_failures"
KEY_LOCKED_UNTIL = "login_locked_until"

# 更新 extra 时用进程级锁，避免同一用户并发失败导致计数丢失。
_state_lock = threading.Lock()


def _max_attempts() -> int:
    try:
        value = int(CONF.get("LOGIN_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS))
    except (TypeError, ValueError):
        value = DEFAULT_MAX_ATTEMPTS
    return max(1, value)


def _lock_seconds() -> int:
    try:
        value = int(CONF.get("LOGIN_LOCK_SECONDS", DEFAULT_LOCK_SECONDS))
    except (TypeError, ValueError):
        value = DEFAULT_LOCK_SECONDS
    return max(1, value)


def secure_equal(a: str, b: str) -> bool:
    """常数时间比较密码哈希，替代裸 ``!=``。"""
    return hmac.compare_digest((a or "").encode("utf-8"), (b or "").encode("utf-8"))


def remaining_lock_seconds(user) -> int:
    """返回用户当前剩余锁定秒数；未锁定返回 0。

    仅供登录入口调用——调用方已按 username 查出 user。锁到期视为未锁定。
    """
    if user is None:
        return 0
    extra = getattr(user, "extra", None) or {}
    try:
        locked_until = float(extra.get(KEY_LOCKED_UNTIL) or 0)
    except (TypeError, ValueError):
        locked_until = 0
    # 向上取整：只要仍在锁定期内就至少返回 1 秒，避免 0.x 秒被截成 0 而放行。
    remain = math.ceil(locked_until - time.time())
    return remain if remain > 0 else 0


def record_result(user, ok: bool) -> None:
    """记录一次登录结果。

    成功：清空失败计数与锁定时间戳。
    失败：计数 +1，达到阈值则写入锁定截止时间并清零计数。
    """
    if user is None:
        return
    with _state_lock:
        extra = user.extra
        if ok:
            extra.pop(KEY_FAILURES, None)
            extra.pop(KEY_LOCKED_UNTIL, None)
            user.save()
            return

        now = time.time()
        try:
            locked_until = float(extra.get(KEY_LOCKED_UNTIL) or 0)
        except (TypeError, ValueError):
            locked_until = 0
        # 已过期则从头计数
        if locked_until <= now:
            extra.pop(KEY_LOCKED_UNTIL, None)
            try:
                count = int(extra.get(KEY_FAILURES) or 0)
            except (TypeError, ValueError):
                count = 0
            count += 1
            if count >= _max_attempts():
                extra[KEY_LOCKED_UNTIL] = now + _lock_seconds()
                extra.pop(KEY_FAILURES, None)
            else:
                extra[KEY_FAILURES] = count
            user.save()


def clear(user) -> None:
    """管理员手动解锁等场景：清空该用户的锁定状态。"""
    if user is None:
        return
    with _state_lock:
        extra = user.extra
        extra.pop(KEY_FAILURES, None)
        extra.pop(KEY_LOCKED_UNTIL, None)
        user.save()
