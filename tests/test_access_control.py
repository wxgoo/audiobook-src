# -*- coding: utf-8 -*-
"""AccessControl 统一门面的契约测试。

门面承诺三件事：
1. 它收口的判定（is_admin / reading_range_of）语义正确且与上游口径一致；
2. re-export 的判定确实是已有门面的原函数（不是复制实现）；
3. BaseHandler.is_admin() 内部转调门面 —— 74 处调用点不改也能拿到统一口径。
"""

import sys
from types import SimpleNamespace

sys.path.insert(0, ".")

from webserver.services.access_control import AccessControl
from webserver.services.book_access_service import BookAccessService
from webserver.base import modules
from webserver.handlers.base import BaseHandler


def test_is_admin_handles_all_cases():
    assert AccessControl.is_admin(None) is False
    assert AccessControl.is_admin(SimpleNamespace(admin=False)) is False
    assert AccessControl.is_admin(SimpleNamespace(admin=True)) is True
    assert AccessControl.is_admin(None, superuser=True) is True
    assert AccessControl.is_admin(SimpleNamespace(admin=False), superuser=True) is True


def test_reading_range_reads_user_fields():
    user = SimpleNamespace(read_limit=1, limit_categories="历史", limit_tags="科幻")
    assert AccessControl.reading_range_of(user) == {
        "read_limit": 1, "limit_categories": "历史", "limit_tags": "科幻"
    }


def test_reading_range_global_switch_off_means_unrestricted():
    user = SimpleNamespace(read_limit=1, limit_categories="历史", limit_tags="科幻")
    assert AccessControl.reading_range_of(user, allow_range_setting=False) == {
        "read_limit": 0, "limit_categories": "", "limit_tags": ""
    }
    assert AccessControl.reading_range_of(None)["read_limit"] == 0


def test_reading_range_tolerates_missing_fields():
    assert AccessControl.reading_range_of(SimpleNamespace()) == {
        "read_limit": 0, "limit_categories": "", "limit_tags": ""
    }


def test_reexports_are_the_original_callables():
    """re-export 必须是原函数对象，不是复制实现。"""
    assert AccessControl.guest_read_allowed is BookAccessService.guest_read_allowed
    assert AccessControl.share_download_granted is BookAccessService.share_download_granted
    assert AccessControl.module_on is modules.module_enabled
    assert AccessControl.require_login_effective is modules.require_login_effective


def test_base_handler_is_admin_delegates_to_facade():
    """BaseHandler.is_admin() 转调门面：改门面语义，handler 立即跟着变。"""
    import inspect
    src = inspect.getsource(BaseHandler.is_admin)
    assert "AccessControl.is_admin" in src, "BaseHandler.is_admin 未转调门面"


def test_is_library_restricted_respects_global_switch():
    """口径一致性 bug 回归（r45 顺手修）。

    全局阅读范围开关关闭时，任何用户实际都能看全库，is_library_restricted
    必须返回 False（否则统计页被错误隐藏）。这与 is_book_visible 的前提一致。
    """
    import inspect
    from webserver.handlers import base as base_module

    src = inspect.getsource(BaseHandler.is_library_restricted)
    assert "ALLOW_READ_RANGE_SETTING" in src, (
        "is_library_restricted 未检查全局阅读范围开关，"
        "开关关闭时会把实际能看全库的用户误判为受限"
    )

    # 行为验证：构造最小 handler（开关关闭 + 受限用户）
    h = SimpleNamespace(
        get_current_user=lambda: SimpleNamespace(read_limit=1, admin=False),
        is_admin=lambda: False,
    )
    from unittest import mock
    with mock.patch.object(base_module, "CONF", {"ALLOW_READ_RANGE_SETTING": False}):
        assert BaseHandler.is_library_restricted(h) is False
    with mock.patch.object(base_module, "CONF", {"ALLOW_READ_RANGE_SETTING": True}):
        assert BaseHandler.is_library_restricted(h) is True
