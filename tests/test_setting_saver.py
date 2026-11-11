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

    def test_reader_group_keys_are_persistable(self):
        """读者组三个键必须在白名单里。

        漏掉 READER_GROUPS 的后果（实测踩过）：设置页任意一次保存都会整份覆盖
        auto.py，把分组规则静默抹掉；叠加容器重建，表现为「分组权限每次重建后
        全部消失」。这三个键不在 ADMIN_SETTING_KEYS（设置页不直接编辑它们），
        只由 handlers/reader_group.py 通过 save_partial 写入，所以只断言
        PERSISTABLE_KEYS。
        """
        for key in ("READER_GROUPS", "READER_GROUPS_ENABLED", "READER_GROUP_STRICT"):
            self.assertIn(key, PERSISTABLE_KEYS, key)

    def test_reader_groups_survive_settings_page_save(self):
        """设置页保存无关键时，已建好的分组规则不能被抹掉。"""
        groups = {
            "儿童": {
                "mode": "whitelist",
                "categories": "文学,教育,社科",
                "tags": "绘本,童书,儿童文学",
            }
        }
        saved = self.run_partial(
            {"READER_GROUPS": groups, "READER_GROUPS_ENABLED": True,
             "READER_GROUP_STRICT": True},
            {"BOOKBARN_TOKEN": "t"},
        )
        self.assertEqual(saved["READER_GROUPS"], groups)
        self.assertTrue(saved["READER_GROUPS_ENABLED"])
        self.assertTrue(saved["READER_GROUP_STRICT"])


if __name__ == "__main__":
    unittest.main()
