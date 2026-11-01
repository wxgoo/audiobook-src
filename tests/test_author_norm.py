#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""author_norm 单元测试。

重点验证三件事：
1. L1 清洗对真实脏数据的处理（用例来自 NAS 上实际查询结果）
2. ``norm_key`` **不能**用来清洗（防止未来有人误用）
3. 别名表命中与未命中都返回安全值
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webserver.base import author_norm as an  # noqa: E402


class TestL1Clean(unittest.TestCase):
    """L1：确定性清洗。"""

    def test_region_prefix_removed(self):
        cases = {
            "(法)法布尔": "法布尔",
            "(英)齐格蒙特·鲍曼": "齐格蒙特·鲍曼",
            "[美] 加里·布莱克伍德": "加里·布莱克伍德",
            "[美]詹姆斯·霍利斯": "詹姆斯·霍利斯",
            "（美）J.D. 塞林格": "J.D. 塞林格",
            "[明] 罗贯中": "罗贯中",
        }
        for raw, want in cases.items():
            got, _ = an.clean_authors([raw])
            self.assertEqual(got, [want], "输入 %r" % raw)

    def test_duty_prefix_with_region(self):
        """职责词 + 方括号国籍，两段都要剥掉。"""
        got, _ = an.clean_authors(["插画[美国]安德鲁·格拉斯"])
        self.assertEqual(got, ["安德鲁·格拉斯"])

    def test_duty_suffix(self):
        cases = {
            "刘峥 编": "刘峥",
            "温德著": "温德",
            "韦东山 主": "韦东山",
            "莱娅·潘珀尔斯 绘": "莱娅·潘珀尔斯",
            "张三 注": "张三",
            "李四 校": "李四",
        }
        for raw, want in cases.items():
            got, _ = an.clean_authors([raw])
            self.assertEqual(got, [want], "输入 %r" % raw)

    def test_single_char_suffix_not_over_eaten(self):
        """单字后缀必须前面有空格，否则 '图图' 会被砍成 '图'。"""
        for raw in ("图图", "绘心", "文文"):
            got, _ = an.clean_authors([raw])
            self.assertEqual(got, [raw], "输入 %r 不该被改" % raw)

    def test_english_bracket_stripped(self):
        got, _ = an.clean_authors(["J·K·罗琳 (J.K.Rowling)"])
        self.assertEqual(got, ["J·K·罗琳"])

    def test_translator_goes_to_translator_list(self):
        """底层 guess_authors 的表现：作者为空、译者有值。"""
        from webserver.base.meta_helper import guess_authors
        authors, translators = guess_authors(["王学富(译)"])
        self.assertEqual(authors, [])
        self.assertEqual(translators, ["王学富"])

    def test_translator_only_falls_back_to_raw(self):
        """clean_authors 在"全被识别成译者"时回退原文，不允许吞成空/佚名。

        这是和 guess_authors 的**有意差异**：直接兜成"佚名"会让一本有作者的
        书看起来没有作者；回退原文至少保留了原始信息，让人能看见、能自己判断。
        """
        got, translators = an.clean_authors(["王学富(译)"])
        self.assertEqual(got, ["王学富(译)"])
        self.assertEqual(translators, ["王学富"])

    def test_multi_author_chinese_comma(self):
        got, _ = an.clean_authors(["王惟恒，李艳"])
        self.assertEqual(got, ["王惟恒", "李艳"])

    def test_multi_author_dunhao(self):
        got, _ = an.clean_authors(["李绍山、陈存军"])
        self.assertEqual(got, ["李绍山", "陈存军"])

    def test_initial_guard_prevents_bad_split(self):
        """Rowling,J.K. 不能拆成 ['Rowling','J.K.']。"""
        got, _ = an.clean_authors(["Rowling,J.K."])
        self.assertEqual(got, ["Rowling,J.K."])

    def test_normal_names_untouched(self):
        for raw in ("Jordan Quinn", "加里·布莱克伍德", "J·K·罗琳", "刘峥"):
            got, _ = an.clean_authors([raw])
            self.assertEqual(got, [raw], "输入 %r 不该被改" % raw)

    def test_empty_input(self):
        self.assertEqual(an.clean_authors([]), ([], []))
        self.assertEqual(an.clean_authors(None), ([], []))
        self.assertEqual(an.clean_authors([None, "  "]), ([], []))


class TestNormKey(unittest.TestCase):
    """L2：归一化键。"""

    def test_punctuation_variants_collapse(self):
        keys = {an.author_norm_key(x) for x in
                ("J·K·罗琳", "J·K. 罗琳", "J·K· 罗琳", "J.K.罗琳", "jk罗琳")}
        self.assertEqual(keys, {"jk罗琳"})

    def test_english_and_chinese_do_not_collapse(self):
        """这是设计上的已知局限，不是 bug——靠别名表或共同书规则补。"""
        self.assertNotEqual(an.author_norm_key("J.K. Rowling"),
                            an.author_norm_key("J·K·罗琳"))

    def test_key_must_not_be_used_on_raw_names(self):
        """反向断言：直接对原始名字算键会出错，证明必须先 L1。"""
        self.assertEqual(an.author_norm_key("(法)法布尔"), "法法布尔")
        cleaned, _ = an.clean_authors(["(法)法布尔"])
        self.assertEqual(an.author_norm_key(cleaned[0]), "法布尔")

    def test_loose_key_rejects_single_char(self):
        # 「张三」是 2 个字，必须保留；单个汉字才丢弃
        self.assertEqual(an.loose_author_key("张三"), "张三")
        self.assertEqual(an.loose_author_key("张"), "")
        self.assertEqual(an.loose_author_key("J·K·罗"), "")  # 只剩 1 个汉字

    def test_loose_key_empty_for_pure_english(self):
        self.assertEqual(an.loose_author_key("J.K. Rowling"), "")

    def test_loose_key_for_chinese(self):
        self.assertEqual(an.loose_author_key("J·K·罗琳"), "罗琳")


class TestAliasStore(unittest.TestCase):
    """别名表读写与命中。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "config.json")
        self.store = an.AliasStore(self.path)

    def test_miss_returns_nothing(self):
        self.store.load()
        self.assertIsNone(self.store.resolve_key("什么都不是"))

    def test_save_and_hit(self):
        self.store.save({
            "jk罗琳": {
                "name": "J·K·罗琳",
                "aliases": ["J.K. Rowling", "J·k·羅琳", "J.K.罗琳"],
            }
        })
        # 标准名自己的键要命中
        self.assertEqual(self.store.resolve_key("jk罗琳"), "jk罗琳")
        # 别名的键也要命中（这是 index 的作用）
        self.assertEqual(self.store.resolve_key("jkrowling"), "jk罗琳")
        self.assertEqual(self.store.canonical_name("jk罗琳"), "J·K·罗琳")

    def test_alias_index_cleans_before_keying(self):
        """alias 里写的是人看的原始写法，建索引前必须过 L1。"""
        self.store.save({
            "加里布莱克伍德": {"name": "加里·布莱克伍德",
                          "aliases": ["[美] 加里·布莱克伍德"]},
        })
        self.assertEqual(self.store.resolve_key("加里布莱克伍德"), "加里布莱克伍德")
        # 索引里不该出现 "美加里布莱克伍德" 这种没洗过的键
        self.assertIsNone(self.store.resolve_key("美加里布莱克伍德"))

    def test_entry_without_name_skipped(self):
        self.store.save({"x": {"name": "", "aliases": ["y"]}})
        self.assertIsNone(self.store.resolve_key("x"))

    def test_persist_roundtrip(self):
        self.store.save({"a": {"name": "A作者", "aliases": ["a作者"]}})
        fresh = an.AliasStore(self.path)
        fresh.load()
        self.assertEqual(fresh.canonical_name("a"), "A作者")

    def test_never_merge_default(self):
        self.store.load()
        self.assertTrue(self.store.is_never_merge("佚名"))
        self.assertTrue(self.store.is_never_merge("Unknown"))
        self.assertFalse(self.store.is_never_merge("罗琳"))


class TestResolve(unittest.TestCase):
    """对外主入口 resolve_alias / resolve_author_list。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = an.AliasStore(os.path.join(self.tmp, "c.json"))
        self._orig = an._STORE
        an._STORE = self.store
        self.store.save({
            "jk罗琳": {"name": "J·K·罗琳",
                    "aliases": ["J·K·罗琳", "J·K. 罗琳", "J.K. Rowling"]},
        })

    def tearDown(self):
        an._STORE = self._orig

    def test_hit_same_key(self):
        self.assertEqual(an.resolve_alias("J·K. 罗琳"), "J·K·罗琳")

    def test_hit_via_alias_index(self):
        self.assertEqual(an.resolve_alias("J.K. Rowling"), "J·K·罗琳")

    def test_miss_returns_original(self):
        self.assertEqual(an.resolve_alias("完全不认识的作者"), "完全不认识的作者")

    def test_miss_still_cleans(self):
        """没命中别名表也要做 L1，不能原样返回脏名。"""
        self.assertEqual(an.resolve_alias("(法)法布尔"), "法布尔")

    def test_never_merge_passthrough(self):
        self.assertEqual(an.resolve_alias("佚名"), "佚名")

    def test_empty(self):
        self.assertEqual(an.resolve_alias(""), "")
        self.assertEqual(an.resolve_alias(None), "")

    def test_list_dedup(self):
        got = an.resolve_author_list(["J·K. 罗琳", "J.K. Rowling", "刘峥"])
        self.assertEqual(got, ["J·K·罗琳", "刘峥"])


class TestAliasFileOnDisk(unittest.TestCase):
    """落盘格式符合设计稿 schema。"""

    def test_schema(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "config.json")
        store = an.AliasStore(path)
        store.save({"k": {"name": "标准名", "aliases": ["别名"], "note": "备注"}})
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["version"], 1)
        self.assertIn("canonical", data)
        self.assertIn("never_merge", data)
        self.assertEqual(data["canonical"]["k"]["name"], "标准名")


if __name__ == "__main__":
    unittest.main(verbosity=2)
