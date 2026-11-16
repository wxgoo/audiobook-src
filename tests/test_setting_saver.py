#!/usr/bin/env python3

import unittest
from unittest import mock

from webserver import perf
from webserver.base import setting_saver
from webserver.base.setting_saver import ADMIN_SETTING_KEYS, PERSISTABLE_KEYS, SettingsSaver


class TestPersistableKeys(unittest.TestCase):

    def test_every_admin_key_is_persistable(self):
        self.assertTrue(set(ADMIN_SETTING_KEYS) <= PERSISTABLE_KEYS)

    def test_perf_keys_are_saved_by_admin_page(self):
        for key in perf.setting_keys():
            self.assertIn(key, ADMIN_SETTING_KEYS)

    def test_no_duplicate_admin_keys(self):
        self.assertEqual(len(ADMIN_SETTING_KEYS), len(set(ADMIN_SETTING_KEYS)))


class TestSavePartial(unittest.TestCase):

    def run_partial(self, conf, overrides):
        captured = {}

        def fake_save(self, args):
            captured.update(args)
            return {"err": "ok"}

        with mock.patch.dict(setting_saver.CONF, conf, clear=False), mock.patch.object(SettingsSaver, "save_extra_settings", fake_save):
            SettingsSaver().save_partial(overrides)
        return captured

    def test_keeps_settings_that_default_to_false(self):
        saved = self.run_partial(
            {"ENABLE_HOMEPAGE_BOOKLISTS": True, "ENABLE_FOLDER_BROWSE": True, "ENABLE_DOWNLOAD_QUOTA": True, "KEEP_UPLOAD_SOURCE_FILE": True},
            {"SYNC_LEGACY_MIGRATION_DONE": True},
        )
        for key in ("ENABLE_HOMEPAGE_BOOKLISTS", "ENABLE_FOLDER_BROWSE", "ENABLE_DOWNLOAD_QUOTA", "KEEP_UPLOAD_SOURCE_FILE"):
            self.assertIs(saved[key], True, key)
        self.assertTrue(saved["SYNC_LEGACY_MIGRATION_DONE"])

    def test_keeps_performance_settings(self):
        saved = self.run_partial({"PERFORMANCE_MODE": "lite", "LITE_GROUP_FILES": False}, {"BOOKBARN_TOKEN": "t"})
        self.assertEqual(saved["PERFORMANCE_MODE"], "lite")
        self.assertIs(saved["LITE_GROUP_FILES"], False)

    def test_computed_settings_are_not_persisted(self):
        saved = self.run_partial({"html_path": "/x", "installed_version": "v"}, {"BOOKBARN_TOKEN": "t"})
        self.assertNotIn("html_path", saved)

    def test_every_admin_key_present_in_conf_survives(self):
        conf = {key: "marker" for key in ADMIN_SETTING_KEYS}
        saved = self.run_partial(conf, {"BOOKBARN_TOKEN": "t"})
        for key in ADMIN_SETTING_KEYS:
            if key != "BOOKBARN_TOKEN":
                self.assertEqual(saved[key], "marker", key)

class TestSaveExtraSettingsCarryOver(unittest.TestCase):
    """设置页 POST 的路径：args 里只有前端提交的键。

    这是「分组又没有了」的真正现场——save_partial 会自己播种，所以
    TestSavePartial 全绿；但设置页保存走的是 admin.py 自己 new 的 loader，
    clear() 之后只填前端键，dumpfile() 整份覆盖就把其余持久化键全删了。
    """

    def save_with_only(self, conf, submitted):
        captured = {}

        def fake_dump(self):
            captured.update(dict(self))

        def fake_noop(*_a, **_kw):
            return None

        args = setting_saver.loader.SettingsLoader()
        args.clear()
        args.update(submitted)

        with mock.patch.dict(setting_saver.CONF, conf, clear=False), \
                mock.patch.object(setting_saver.loader.SettingsLoader, "dumpfile", fake_dump), \
                mock.patch.object(SettingsSaver, "update_nuxtjs_env", fake_noop), \
                mock.patch.object(SettingsSaver, "_check_restart_needed", lambda self, a: False), \
                mock.patch.object(SettingsSaver, "_apply_dynamic_settings", fake_noop), \
                mock.patch("webserver.base.modules.apply_module_switch_effects", fake_noop):
            SettingsSaver().save_extra_settings(args)
        return captured

    def test_all_persistable_keys_survive_settings_page_post(self):
        """所有「只在 PERSISTABLE_KEYS」的键都要活下来。

        历史上这类键（scan_hash_workers / site_theme 等）曾一保存设置就消失，
        这个总入口就是为防止这类丢失而加的。
        """
        conf = {key: "marker" for key in PERSISTABLE_KEYS}
        conf["site_theme"] = "light"
        saved = self.save_with_only(conf, {"BOOKBARN_TOKEN": "t"})
        missing = [k for k in PERSISTABLE_KEYS if k not in saved]
        self.assertEqual(missing, [], "这些持久化键被整份覆盖抹掉了: %s" % missing)

    def test_non_persistable_keys_are_not_carried_over(self):
        """别把运行期临时值（路径、安装标记）也写进 auto.py。"""
        saved = self.save_with_only(
            {"html_path": "/x", "installed_version": "v", "site_url": "https://a.b"},
            {"BOOKBARN_TOKEN": "t"},
        )
        self.assertNotIn("html_path", saved)
        self.assertNotIn("site_url", saved)

    def test_submitted_value_wins_over_conf(self):
        """前端这次真的提交了，就用新的（否则改设置永远不生效）。"""
        saved = self.save_with_only(
            {"scan_hash_workers": 4, "site_theme": "light"},
            {"site_theme": "dark"},
        )
        self.assertEqual(saved["site_theme"], "dark")
        self.assertEqual(saved["scan_hash_workers"], 4)


class TestDumpfileBackup(unittest.TestCase):
    """覆盖 auto.py 前要留一份上一版，否则误抹就是永久损失。"""

    def test_previous_auto_py_is_kept_as_bak(self):
        import os
        import tempfile

        d = tempfile.mkdtemp()
        try:
            s = setting_saver.loader.SettingsLoader()
            s.clear()
            s["MARKER"] = "v1"
            with mock.patch.object(
                setting_saver.loader.SettingsLoader, "set_store_path", lambda self: d
            ):
                s.dumpfile()
                s["MARKER"] = "v2"
                s.dumpfile()

            bak = os.path.join(d, "auto.py.bak")
            cur = os.path.join(d, "auto.py")
            self.assertTrue(os.path.exists(bak), "没生成 auto.py.bak")
            with open(bak, encoding="utf-8") as f:
                self.assertIn("'v1'", f.read())
            with open(cur, encoding="utf-8") as f:
                self.assertIn("'v2'", f.read())
            self.assertNotIn("'v1'", open(cur, encoding="utf-8").read())
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
