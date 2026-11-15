#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""跟随上游工具的契约测试。

`scripts/upstream/follow-upstream.py` 是「跟随上游」的主力工具，它必须满足：

- **只读**：任何子命令都不许写本仓库的工作区文件（比对报告只写 ``--out`` 指定处）；
- **冲突判定不估**：三个子命令的参数与输出结构稳定，判定口径写进 docstring；
- **CRLF 归一**：Windows 检出的上游文件是 CRLF，不归一会把整个文件误判成「双方都改过」；
- **硬约束生效**：`webserver/settings.py` 必须始终出现在「禁止整体合并」清单里。

这些是**契约**（工具的行为约定），不是对某一轮具体比对的快照——上游随时会发新版，
断言不能绑死在某次结果上。
"""

import importlib.util
import os
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "upstream" / "follow-upstream.py"


def _load():
    spec = importlib.util.spec_from_file_location("follow_upstream_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestFollowUpstreamTool(unittest.TestCase):

    def setUp(self):
        self.mod = _load()

    def test_tool_exists_and_is_executable(self):
        self.assertTrue(TOOL.is_file(), "跟随上游工具必须存在")
        self.assertTrue(os.access(TOOL, os.X_OK), "工具应可执行")

    def test_only_standard_library(self):
        """只用标准库：NAS 容器里能直接跑，不需要装依赖。"""
        src = TOOL.read_text(encoding="utf-8")
        for third_party in ("import requests", "import yaml", "from requests"):
            self.assertNotIn(third_party, src, "不应依赖第三方库：%s" % third_party)

    def test_crlf_is_normalised(self):
        """CRLF 归一：否则 Windows 检出的上游文件会被整文件误判。"""
        a = "line1\nline2\n"
        b = "line1\r\nline2\r\n"
        self.assertEqual(a, self.mod._norm(b))

    def test_never_merge_whole_contains_settings_py(self):
        """硬约束：settings.py 的默认值/键名有破坏性变更，禁止整体合并。"""
        self.assertIn("webserver/settings.py", self.mod.NEVER_MERGE_WHOLE)

    def test_skip_dirs_cover_build_artifacts(self):
        """构建产物与依赖不参与比对。"""
        for d in (".git", "node_modules", "dist", "__pycache__"):
            self.assertIn(d, self.mod.SKIP_DIRS)

    def test_conflict_counter_detects_divergence(self):
        """冲突计数：双方改同一段 → 冲突；只有一方改 → 不冲突。"""
        base = "a\nb\nc\n"
        ours = "a\nB-ours\nc\n"
        theirs = "a\nB-theirs\nc\n"
        self.assertGreater(self.mod._conflict_blocks(base, ours, theirs), 0)
        self.assertEqual(self.mod._conflict_blocks(base, ours, base), 0)

    def test_docstring_states_readonly_and_no_merge_base(self):
        """工具自身的说明必须写明「只读」与「没有共同祖先」这两个关键前提。"""
        src = TOOL.read_text(encoding="utf-8")
        self.assertIn("只读", src)
        self.assertIn("merge base", src)


if __name__ == "__main__":
    unittest.main()
