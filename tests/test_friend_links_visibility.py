#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""友情链接对所有用户一致可见。

回归 bug：非管理员在前台侧边栏看不到友情链接。

根因：旧实现里前端用 ``showItem("friends")`` 决定显隐，它依赖
``sys.sidebar_items``。当管理员曾打开过设置页（SIDEBAR_ITEMS_MIGRATED=True）
且存下的列表是旧默认（恰好缺 friends/authors/booklists）时，
``get_sidebar_items`` 认定「管理员主动取消勾选」而原样返回，friends 被永久
吞掉——而这与用户是不是管理员无关，前台所有用户都看不到友情链接。

修法：友情链接显隐改由独立站点开关 ``ENABLE_FRIEND_LINKS``（默认 True）决定，
通过 ``sys.allow.friend_links`` 下发，前端不再看 ``sidebar_items`` 里的 friends。
这样即便 SIDEBAR_ITEMS 迁移标记为真、列表里没有 friends，前台用户照样可见。
"""

import unittest
from unittest import mock

from webserver.base import sidebar as sidebar_module
from webserver.base.sidebar import SIDEBAR_ITEMS_MIGRATED_KEY
from webserver.handlers import base as base_module
from webserver.handlers.base import BaseHandler


# 管理员保存过设置页时的旧默认列表：缺 friends/authors/booklists
LEGACY_STORED = [
    "audiobooks", "printbooks", "publishers", "folders", "tags",
    "series", "languages", "rating", "memo", "categories",
]


class TestFriendLinksVisibility(unittest.TestCase):
    def test_allow_flag_defaults_to_true_for_everyone(self):
        """开关缺省（老 auto.py 没这个键）时必须默认 True，保证可见。"""
        handler = object.__new__(BaseHandler)
        handler.require_login_enabled = mock.Mock(return_value=False)
        with mock.patch.dict(base_module.CONF, {}, clear=False):
            base_module.CONF.pop("ENABLE_FRIEND_LINKS", None)
            flags = handler.allow_flags()
            try:
                self.assertTrue(flags["friend_links"])
            finally:
                base_module.CONF["ENABLE_FRIEND_LINKS"] = True

    def test_allow_flag_honors_explicit_off(self):
        handler = object.__new__(BaseHandler)
        handler.require_login_enabled = mock.Mock(return_value=False)
        with mock.patch.dict(base_module.CONF, {"ENABLE_FRIEND_LINKS": False}):
            self.assertFalse(handler.allow_flags()["friend_links"])

    def test_friend_links_independent_of_sidebar_migration(self):
        """即便 sidebar 迁移把 friends 吞掉，友链开关依然为真——两者彻底解耦。"""
        settings = {
            "SIDEBAR_ITEMS": list(LEGACY_STORED),
            SIDEBAR_ITEMS_MIGRATED_KEY: True,
        }
        served = sidebar_module.get_sidebar_items(settings)
        # 迁移逻辑确实吞掉了 friends（这正是旧 bug 的土壤）
        self.assertNotIn("friends", served)
        # 但友链可见性由独立开关决定，不受影响
        handler = object.__new__(BaseHandler)
        handler.require_login_enabled = mock.Mock(return_value=False)
        with mock.patch.dict(base_module.CONF, {"ENABLE_FRIEND_LINKS": True}):
            self.assertTrue(handler.allow_flags()["friend_links"])

    def test_frontend_gate_uses_independent_flag(self):
        """前端源码里友链显示条件必须走 allow.friend_links，而非 showItem("friends")。"""
        import os
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "app", "src", "components", "AppHeader.vue"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("allow.friend_links", src)
        self.assertIn("this.sys.friends.length > 0", src)


if __name__ == "__main__":
    unittest.main()
