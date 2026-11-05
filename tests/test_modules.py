#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""功能模块开关（webserver/base/modules.py）回归测试。

覆盖：开关读取与依赖折算 / 关掉模块写哪些主开关 / 重开模块恢复什么 /
安装场景与保存场景的差别 / 配置键登记完整（防止 dumpfile 抹掉开关）。
"""

import unittest

from webserver.base import modules as m
from webserver.base.setting_saver import ADMIN_SETTING_KEYS, PERSISTABLE_KEYS


class ModuleSwitchTest(unittest.TestCase):
    def test_unknown_module_counts_as_enabled(self):
        """没登记的模块算开启。

        这条是刻意的取舍：新功能忘了登记时，宁可多显示一块，也不要让它
        凭空消失 —— 消失的问题用户根本报不出来，多显示至少看得见。
        """
        self.assertTrue(m.module_enabled("no_such_module", {}))

    def test_default_on_when_key_missing(self):
        self.assertTrue(m.module_enabled(m.MODULE_PHYSICAL, {}))

    def test_off_when_switch_false(self):
        conf = {"ENABLE_MODULE_PHYSICAL": False}
        self.assertFalse(m.module_enabled(m.MODULE_PHYSICAL, conf))

    def test_snapshot_reports_every_module(self):
        snap = m.snapshot({})
        self.assertEqual(set(snap), set(m.MODULES))
        self.assertTrue(all(snap.values()))


class ModuleSwitchEffectsTest(unittest.TestCase):
    def test_turning_off_community_writes_off_switch(self):
        old = {"ENABLE_MODULE_COMMUNITY": True, "ENABLE_USER_MEMOS": True}
        new = dict(old, ENABLE_MODULE_COMMUNITY=False)
        m.apply_module_switch_effects(new, old_settings=old)
        self.assertFalse(new["ENABLE_USER_MEMOS"])

    def test_turning_off_multiuser_forces_login(self):
        old = {"ENABLE_MODULE_MULTIUSER": True, "REQUIRE_LOGIN": False,
               "ALLOW_GUEST_READ": True}
        new = dict(old, ENABLE_MODULE_MULTIUSER=False)
        m.apply_module_switch_effects(new, old_settings=old)
        self.assertTrue(new["REQUIRE_LOGIN"])
        self.assertFalse(new["ALLOW_GUEST_READ"])
        self.assertFalse(new["ALLOW_REGISTER"])

    def test_turning_on_does_not_reopen_guest_access(self):
        """重开多用户不能把私人站点重新变成访客可读。

        `MODULE_ON_SWITCHES` 里只有 REQUIRE_LOGIN，访客权限/注册**故意**
        不恢复。这条是安全边界，不是遗漏。
        """
        old = {"ENABLE_MODULE_MULTIUSER": False, "REQUIRE_LOGIN": True,
               "ALLOW_GUEST_READ": False, "ALLOW_REGISTER": False}
        new = dict(old, ENABLE_MODULE_MULTIUSER=True)
        m.apply_module_switch_effects(new, old_settings=old)
        self.assertTrue(new["REQUIRE_LOGIN"])
        self.assertFalse(new["ALLOW_GUEST_READ"])
        self.assertFalse(new["ALLOW_REGISTER"])

    def test_turning_on_shared_reading_restores_share_link(self):
        old = {"ENABLE_MODULE_SHARED_READING": False, "ENABLE_SHARE_LINK": False}
        new = dict(old, ENABLE_MODULE_SHARED_READING=True)
        m.apply_module_switch_effects(new, old_settings=old)
        self.assertTrue(new["ENABLE_SHARE_LINK"])

    def test_install_scenario_only_applies_off_effects(self):
        """安装场景 old_settings=None：开着的模块一个字段都不该被动到。"""
        args = {"ENABLE_MODULE_AI": True, "AI_MODEL": "gpt-4o"}
        before = dict(args)
        m.apply_module_switch_effects(args, old_settings=None)
        self.assertEqual(args, before)

    def test_install_scenario_applies_off_for_disabled_module(self):
        args = {"ENABLE_MODULE_AI": False, "AI_ENABLED": True}
        m.apply_module_switch_effects(args, old_settings=None)
        self.assertFalse(args["AI_ENABLED"])


class ModuleSettingKeysTest(unittest.TestCase):
    def test_every_module_key_is_persistable(self):
        """模块开关必须同时进 ADMIN_SETTING_KEYS 与 PERSISTABLE_KEYS。

        漏了前者：设置页看不到这个开关。
        漏了后者：保存其它设置时 `dumpfile()` 整份覆盖 auto.py，开关被静默
        抹回默认值 —— 用户会发现「关掉的模块自己又开了」，且没有任何报错。
        """
        for module_id, spec in m.MODULES.items():
            key = spec["key"]
            self.assertIn(key, ADMIN_SETTING_KEYS, "%s 未进 ADMIN_SETTING_KEYS" % module_id)
            self.assertIn(key, PERSISTABLE_KEYS, "%s 未进 PERSISTABLE_KEYS" % module_id)

    def test_module_ids_are_round_trip(self):
        for module_id, spec in m.MODULES.items():
            self.assertEqual(m.setting_key(module_id), spec["key"])
            self.assertTrue(m.is_known(module_id))


if __name__ == "__main__":
    unittest.main()
