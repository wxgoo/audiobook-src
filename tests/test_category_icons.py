#!/usr/bin/env python3
"""分类图标映射的回归测试（webserver/base/category_icons.py）。

分类是自由文本，图标全靠名称规则推断，容易被后来的规则调整弄乱：
这里锁住几条实际书库在用的分类名，以及「未命中也要有稳定图标」的兜底行为。
"""

import unittest

from webserver.base import category_icons


class TestIconRules(unittest.TestCase):

    def test_radio_categories_use_radio_icon(self):
        # 「演播:李慧敏」这类分类名走电台图标——这是管理员明确要求的形态
        for name in ("演播:李慧敏", "有声书", "电台", "广播剧", "听书"):
            icon, _ = category_icons.icon_for_category(name)
            self.assertEqual(icon, "mdi-radio-tower", name)

    def test_specific_rule_wins_over_generic(self):
        # 「科幻小说」必须命中科幻，而不是被后面的「小说」抢走
        icon, _ = category_icons.icon_for_category("科幻小说")
        self.assertEqual(icon, "mdi-rocket-launch-outline")

    def test_known_categories(self):
        cases = {
            "文学": "mdi-book-open-variant",
            "儿童": "mdi-baby-face-outline",
            "历史": "mdi-bank-outline",
            "计算机": "mdi-laptop",
        }
        for name, expected in cases.items():
            icon, _ = category_icons.icon_for_category(name)
            self.assertEqual(icon, expected, name)

    def test_empty_name_falls_back_to_default(self):
        icon, color = category_icons.icon_for_category("")
        self.assertEqual(icon, category_icons.DEFAULT_ICON)
        self.assertEqual(color, category_icons.DEFAULT_COLOR)

    def test_unknown_category_is_stable_and_distinct(self):
        # 未命中关键词时按名字哈希取备选图标：同名稳定（刷新不会跳变）
        first = category_icons.icon_for_category("哈利波特中文版")
        second = category_icons.icon_for_category("哈利波特中文版")
        self.assertEqual(first, second)
        # 备选池够大，两个差别很大的名字不该撞在一起（极小概率，选固定样本）
        self.assertNotEqual(
            category_icons.icon_for_category("哈利波特中文版"),
            category_icons.icon_for_category("某某冷门分类"),
        )

    def test_icon_and_color_are_non_empty(self):
        for name in ("文学", "科幻", "未知分类名"):
            icon, color = category_icons.icon_for_category(name)
            self.assertTrue(icon.startswith("mdi-"), name)
            self.assertTrue(color, name)


class TestDecorate(unittest.TestCase):

    def test_decorate_keeps_name_and_count(self):
        categories = [{"name": "文学", "count": 12}, {"name": "演播:李慧敏", "count": 3}]
        category_icons.decorate(categories)
        self.assertEqual([c["name"] for c in categories], ["文学", "演播:李慧敏"])
        self.assertEqual([c["count"] for c in categories], [12, 3])
        for item in categories:
            self.assertTrue(item["icon"].startswith("mdi-"))
            self.assertTrue(item["color"])

    def test_decorate_tolerates_missing_name(self):
        categories = [{"count": 1}]
        category_icons.decorate(categories)
        self.assertEqual(categories[0]["icon"], category_icons.DEFAULT_ICON)


if __name__ == "__main__":
    unittest.main()
