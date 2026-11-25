# -*- coding: UTF-8 -*-
"""电子书标签清理（内置化自 tool_tags_cleaner v0.2.0）的测试。

覆盖三块：
1. guess_tags 全部规则用例——从外部工具 meta.py 的自测清单逐条移植；
2. 稀少标签上限（小书库保护）的钳制逻辑；
3. JobStore 原子启动/协作取消/状态展示 + handler 路由注册结构。
"""
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from webserver.toolbox.ebook_tags_cleaner_meta import RULES, guess_tags
from webserver.toolbox.ebook_tags_cleaner_jobstore import (
    JobStore, empty_stats, public_status, STATUS_IDLE, STATUS_RUNNING,
)
from webserver.services.ebook_tags_cleaner import (
    _clamp_rare_tag_count, _max_rare_tag_count, _tag_search_expression,
    EbookTagsCleaner,
)


class GuessTagsRuleTests(unittest.TestCase):
    """外部版 meta.py 自测清单逐条移植（36 例，逻辑必须与原版一致）。"""

    CASES = [
        (["小说", "文学"], ["小说", "文学"], "正常 tags 保留"),
        (["关注公众号"], [], "开头 关注"),
        (["标题：xxx"], [], "开头 标题"),
        (["制作组"], [], "开头 制作"),
        (["下载地址"], [], "开头 下载"),
        (["出版社信息"], [], "开头 出版社"),
        (["http://example.com"], [], "开头 http"),
        (["HTTP://example.com"], [], "开头 http 大写不区分"),
        (["ftp://xxx"], [], "开头 ftp"),
        (["mail:xxx@xxx.com"], [], "开头 mail"),
        (["ISBN 978-x"], [], "开头 isbn 大写不区分"),
        (["小说 精选"], [], "含空格"),
        (["扫描公众号获取"], [], "含公众号"),
        (["加微信xxx"], [], "含微信"),
        (["小说，文学"], [], "含中文逗号"),
        (["www.example.com"], [], "含 www."),
        (["访问xxx.com"], [], "含 .com"),
        (["xxx出品"], [], "含出品"),
        (["联系邮箱a@b.com"], [], "含 @"),
        (["商务印书馆藏书"], [], "含商务印书馆"),
        (["SANQIU小组"], [], "含 SANQIU"),
        (["sanqiu小组"], [], "含 sanqiu 大写不区分"),
        (["独家制作"], [], "结尾 制作"),
        (["精美印刷"], [], "结尾 印刷"),
        (["12345"], [], "纯数字"),
        (["(备注内容)"], [], "半角括号包裹"),
        (["（备注内容）"], [], "全角括号包裹"),
        (["小说", "小说"], ["小说"], "去重"),
        ([""], [], "空字符串过滤"),
        ([None], [], "None 过滤"),
        (["  小说  "], ["小说"], "首尾空格清理"),
        (["历史", "关注公众号", "小说，", "12306", "(x)", "科幻"], ["历史", "科幻"], "混合过滤"),
        (["政治改革；研究；中国；"], ["政治改革", "研究", "中国"], "分号拆分，丢弃末尾空碎片"),
        (["政治改革;研究;中国"], ["政治改革", "研究", "中国"], "半角分号拆分"),
        (["历史；中"], ["历史"], "拆分后单字符碎片被丢弃"),
        (["中"], [], "单字符 tag 本身也被丢弃"),
        (["历史；历史"], ["历史"], "拆分后按去重只保留一份"),
    ]

    def test_all_rules(self):
        for idx, (inp, exp, desc) in enumerate(self.CASES, 1):
            self.assertEqual(guess_tags(inp), exp, f"用例 #{idx} {desc}")

    def test_rules_panel_has_eight_entries(self):
        self.assertEqual(len(RULES), 8)
        for rule in RULES:
            self.assertIn("id", rule)
            self.assertIn("title", rule)
            self.assertIn("description", rule)


class RareTagLimitTests(unittest.TestCase):
    def test_small_library_cap_is_one(self):
        self.assertEqual(_max_rare_tag_count(0), 1)
        self.assertEqual(_max_rare_tag_count(99), 1)
        self.assertEqual(_max_rare_tag_count(100), 3)
        self.assertEqual(_max_rare_tag_count(148), 3)

    def test_clamp(self):
        self.assertEqual(_clamp_rare_tag_count(None, 148), 0)
        self.assertEqual(_clamp_rare_tag_count("abc", 148), 0)
        self.assertEqual(_clamp_rare_tag_count(-1, 148), 0)
        self.assertEqual(_clamp_rare_tag_count(2, 148), 2)
        self.assertEqual(_clamp_rare_tag_count(9, 148), 3)
        # 小书库上限 1
        self.assertEqual(_clamp_rare_tag_count(3, 50), 1)

    def test_tag_search_expression_escapes(self):
        expr = _tag_search_expression(['a"b', "c\\d"])
        self.assertIn('tags:"=a\\"b"', expr)
        self.assertIn('tags:"=c\\\\d"', expr)
        self.assertIn(" or ", expr)


class EbookTagsCleanerInfoTests(unittest.TestCase):
    def test_info_identity(self):
        info = EbookTagsCleaner.info()
        self.assertEqual(info["tool_id"], "ebook_tags_cleaner")
        self.assertEqual(info["name"], "电子书标签清理")

    def test_service_item_name(self):
        self.assertEqual(EbookTagsCleaner.service_item_name, "电子书标签清理")


class JobStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="ebook_tags_test_")
        # 清掉单例缓存，保证每个用例拿到全新的 store
        JobStore._instances.clear()

    def tearDown(self):
        JobStore._instances.clear()

    def test_idle_status(self):
        store = JobStore(self._tmp)
        self.assertIsNone(store.read())
        self.assertEqual(public_status(None), {"status": STATUS_IDLE})
        self.assertFalse(store.is_running())

    def test_try_start_and_public_status(self):
        store = JobStore(self._tmp)
        job = empty_stats()
        job.update({"status": STATUS_RUNNING, "total": 148})
        started, current = store.try_start(job)
        self.assertTrue(started)
        self.assertTrue(store.is_running())
        pub = public_status(store.read())
        self.assertEqual(pub["status"], STATUS_RUNNING)
        self.assertEqual(pub["total"], 148)
        # 未在 public_status 白名单里的内部键不会泄漏
        self.assertNotIn("_cancel_event", pub)

    def test_try_start_rejects_concurrent(self):
        store = JobStore(self._tmp)
        first = empty_stats()
        first.update({"status": STATUS_RUNNING})
        started, _ = store.try_start(first)
        self.assertTrue(started)
        second = empty_stats()
        second.update({"status": STATUS_RUNNING, "total": 999})
        started2, current = store.try_start(second)
        self.assertFalse(started2)
        self.assertNotEqual(current.get("total"), 999)

    def test_request_cancel(self):
        store = JobStore(self._tmp)
        self.assertFalse(store.request_cancel())
        job = empty_stats()
        job.update({"status": STATUS_RUNNING})
        store.try_start(job)
        self.assertTrue(store.request_cancel())
        self.assertTrue(store.is_cancel_requested())
        self.assertTrue(store.read()["cancel_requested"])

    def test_stale_job_marked_failed_on_restart(self):
        store = JobStore(self._tmp)
        job = empty_stats()
        job.update({"status": STATUS_RUNNING})
        store.try_start(job)
        # 把 updated_at 拨回 3 小时前，模拟进程重启后遗留的失联任务
        stale = store.read()
        stale["updated_at"] = time.time() - 3 * 3600
        store.update()
        stale["updated_at"] = time.time() - 3 * 3600
        with open(store._status_path, "w", encoding="utf-8") as f:
            import json
            json.dump(stale, f)
        # 重新构造（新进程语义）
        JobStore._instances.clear()
        store2 = JobStore(self._tmp)
        self.assertEqual(store2.read()["status"], "failed")

    def test_update_merges_fields(self):
        store = JobStore(self._tmp)
        job = empty_stats()
        job.update({"status": STATUS_RUNNING, "processed": 0})
        store.try_start(job)
        store.update(processed=5, changed=2)
        data = store.read()
        self.assertEqual(data["processed"], 5)
        self.assertEqual(data["changed"], 2)


class HandlerRoutesTests(unittest.TestCase):
    def test_routes_registered(self):
        from webserver.handlers import ebook_tags_cleaner as mod
        routes = mod.routes()
        paths = [r for r, _ in routes]
        self.assertEqual(len(routes), 5)
        for expected in ("rules", "limits", "status", "start", "cancel"):
            self.assertIn(f"/api/toolbox/ebook_tags_cleaner/{expected}", paths)


if __name__ == "__main__":
    unittest.main()
