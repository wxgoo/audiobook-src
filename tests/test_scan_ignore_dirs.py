#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""扫描导入「忽略目录」（SCAN_IGNORE_DIRS）。

移植自上游 4.7.0（commit 0d7dc96b）。规则：**按目录名精确匹配**——
不含路径、不支持通配符；命中的目录及其子目录在扫描时跳过。

两条防线（都要有）：
1. **遍历层**：``os.walk`` 的 ``dirnames`` 里直接剔除被忽略的名字——不进入该目录，
   其后代自然排除；
2. **路径层**：``_is_ignored_scan_subpath`` 供「显式扫描路径」与「并入待处理记录」
   使用，防止库里滞留的记录绕过忽略规则重新入队。

归一化口径与前端校验、服务端清洗三处一致：非字符串忽略、strip 后为空或
``.`` / ``..`` 忽略、含 ``/ \\ : * ? " < > |`` 或控制字符忽略、去重。
"""

import os
import tempfile
import unittest
from unittest import mock

from webserver.handlers.admin import sanitize_scan_ignore_dirs
from webserver.services import scan_service as scan_module
from webserver.services.scan_service import ScanService


class TestScanIgnoreDirNormalisation(unittest.TestCase):
    """归一化：只保留合法目录名。"""

    def test_valid_names_are_kept(self):
        with mock.patch.dict(scan_module.CONF, {"SCAN_IGNORE_DIRS": ["cache", "tmp"]}):
            self.assertEqual(frozenset({"cache", "tmp"}), ScanService._scan_ignore_dir_names())

    def test_strips_whitespace(self):
        with mock.patch.dict(scan_module.CONF, {"SCAN_IGNORE_DIRS": ["  cache  "]}, clear=False):
            self.assertEqual(frozenset({"cache"}), ScanService._scan_ignore_dir_names())

    def test_rejects_path_like_and_dot_names(self):
        """含路径分隔符的、`.` / `..` 的、含非法字符的，一律忽略。"""
        bad = ["a/b", "a\\b", "..", ".", "", "  ", "a:b", "a*b", 'a"b', "a<b", "a>b", "a|b", "a?b"]
        with mock.patch.dict(scan_module.CONF, {"SCAN_IGNORE_DIRS": bad}):
            self.assertEqual(frozenset(), ScanService._scan_ignore_dir_names())

    def test_rejects_control_chars(self):
        with mock.patch.dict(scan_module.CONF, {"SCAN_IGNORE_DIRS": ["ok", "bad\x01name"]}):
            self.assertEqual(frozenset({"ok"}), ScanService._scan_ignore_dir_names())

    def test_non_list_config_is_empty(self):
        for value in ("cache", 42, None, {"a": 1}):
            with mock.patch.dict(scan_module.CONF, {"SCAN_IGNORE_DIRS": value}):
                self.assertEqual(frozenset(), ScanService._scan_ignore_dir_names())

    def test_non_string_items_are_ignored(self):
        with mock.patch.dict(scan_module.CONF, {"SCAN_IGNORE_DIRS": ["ok", 123, None]}):
            self.assertEqual(frozenset({"ok"}), ScanService._scan_ignore_dir_names())

    def test_duplicates_collapse(self):
        with mock.patch.dict(scan_module.CONF, {"SCAN_IGNORE_DIRS": ["a", "a", " a "]}):
            self.assertEqual(frozenset({"a"}), ScanService._scan_ignore_dir_names())


class TestScanIgnoreSubpath(unittest.TestCase):
    """路径层判断：只认扫描根之下的目录层级名。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="scanignore-")
        self.root = os.path.join(self.tmp, "imports")
        os.makedirs(os.path.join(self.root, "cache"))
        os.makedirs(os.path.join(self.root, "books", "tmp"))
        os.makedirs(os.path.join(self.root, "books", "keep"))
        self.ignore = frozenset({"cache", "tmp"})

    def test_dir_under_ignored_name_is_ignored(self):
        p = os.path.join(self.root, "cache")
        self.assertTrue(ScanService._is_ignored_scan_subpath(
            p, self.ignore, is_dir=True, scan_root=self.root))

    def test_nested_dir_under_ignored_name_is_ignored(self):
        p = os.path.join(self.root, "books", "tmp")
        self.assertTrue(ScanService._is_ignored_scan_subpath(
            p, self.ignore, is_dir=True, scan_root=self.root))

    def test_file_inside_ignored_dir_is_ignored(self):
        p = os.path.join(self.root, "cache", "a.epub")
        self.assertTrue(ScanService._is_ignored_scan_subpath(
            p, self.ignore, is_dir=False, scan_root=self.root))

    def test_scan_root_itself_is_not_ignored(self):
        self.assertFalse(ScanService._is_ignored_scan_subpath(
            self.root, self.ignore, is_dir=True, scan_root=self.root))

    def test_other_dir_is_not_ignored(self):
        p = os.path.join(self.root, "books", "keep")
        self.assertFalse(ScanService._is_ignored_scan_subpath(
            p, self.ignore, is_dir=True, scan_root=self.root))

    def test_path_outside_scan_root_is_not_affected(self):
        """扫描根之外的路径（上传临时目录等）不受该配置影响。"""
        p = os.path.join(self.tmp, "elsewhere", "cache")
        self.assertFalse(ScanService._is_ignored_scan_subpath(
            p, self.ignore, is_dir=True, scan_root=self.root))

    def test_file_name_equal_to_ignored_name_is_not_ignored(self):
        """普通文件名与忽略目录同名不算命中（只比目录层级）。"""
        p = os.path.join(self.root, "books", "keep", "cache")
        self.assertFalse(ScanService._is_ignored_scan_subpath(
            p, self.ignore, is_dir=False, scan_root=self.root))

    def test_empty_ignore_set_never_ignores(self):
        p = os.path.join(self.root, "cache")
        self.assertFalse(ScanService._is_ignored_scan_subpath(
            p, frozenset(), is_dir=True, scan_root=self.root))


class TestServerSideSanitise(unittest.TestCase):
    """服务端清洗（admin.py）与归一化同口径：前端校验之外的第二道保障。"""

    def test_keeps_valid_and_drops_invalid(self):
        out = sanitize_scan_ignore_dirs(["cache", " a/b ", "", "..", "b", "cache", 42])
        self.assertEqual(["cache", "b"], out)

    def test_non_list_returns_empty(self):
        for value in ("cache", 42, None, {"a": 1}):
            self.assertEqual([], sanitize_scan_ignore_dirs(value))

    def test_control_chars_rejected(self):
        self.assertEqual([], sanitize_scan_ignore_dirs(["bad\x01"]))


if __name__ == "__main__":
    unittest.main()
