#!/usr/bin/env python3
"""分类图标：按分类名给出 Material Design 图标与主题色。

分类是 calibre 自定义列（#category）的自由文本，管理员怎么命名都行，
本身不带图标。这个模块用「关键词 → 图标」的规则表兜住常见命名
（科幻、历史、儿童、演播:某人……），未命中的分类按名字做确定性哈希，
从一组备用图标里挑一个——同一分类每次刷新都稳定，不同分类看起来也不一样。

前端 `pages/categories.vue` 直接把 icon / color 渲染成 <v-icon>。
"""
import zlib
from typing import Dict, Tuple

DEFAULT_ICON = "mdi-tag-outline"
DEFAULT_COLOR = "blue-grey"

# 顺序敏感：先命中的规则生效，所以「科幻」必须排在「小说」之前，
# 「演播:某人」这类（含"演播"）要排在最前面，走电台图标。
_RULES = (
    # 有声/电台：演播:李慧敏、有声书、广播剧、播客……统一用电台塔图标
    (("有声", "电台", "广播", "播客", "演播", "音频", "朗读", "听书"),
     "mdi-radio-tower", "deep-purple"),
    (("科幻", "星云", "太空"), "mdi-rocket-launch-outline", "indigo"),
    (("奇幻", "魔幻", "魔法"), "mdi-auto-fix", "deep-purple"),
    (("武侠", "仙侠", "玄幻", "江湖"), "mdi-sword", "brown"),
    (("言情", "爱情", "情感", "婚恋"), "mdi-heart-outline", "pink"),
    (("悬疑", "推理", "侦探", "惊悚", "罪案"), "mdi-magnify", "blue-grey"),
    (("恐怖", "灵异", "鬼怪"), "mdi-ghost-outline", "grey darken-2"),
    (("历史", "史记", "通史", "断代", "野史"), "mdi-bank-outline", "brown"),
    (("传记", "人物", "回忆录", "自传"), "mdi-account-tie-outline", "teal"),
    (("哲学", "思想", "伦理", "逻辑"), "mdi-thought-bubble-outline", "deep-orange"),
    (("宗教", "佛", "禅", "道教", "圣经", "神学"), "mdi-hands-pray", "amber darken-2"),
    (("心理", "情绪", "认知"), "mdi-brain", "purple"),
    (("社科", "社会", "人类学", "民俗", "文化"), "mdi-account-group-outline", "teal darken-1"),
    (("政治", "军事", "战争", "战略", "兵器"), "mdi-shield-outline", "red darken-2"),
    (("经济", "金融", "投资", "理财", "商业", "管理", "职场", "营销"), "mdi-chart-line", "green darken-2"),
    (("教育", "教学", "教材", "学习", "考试", "辅导", "教辅"), "mdi-school-outline", "blue"),
    (("儿童", "少儿", "童书", "绘本", "亲子", "幼儿"), "mdi-baby-face-outline", "orange"),
    (("科普", "科学", "自然", "天文", "物理", "化学", "生物", "数学", "地理"),
     "mdi-flask-outline", "cyan darken-1"),
    (("计算机", "编程", "程序", "软件", "网络", "互联网", "技术", "人工智能", "算法"),
     "mdi-laptop", "blue-grey darken-1"),
    (("医学", "中医", "健康", "养生", "医案", "临床"), "mdi-medical-bag", "red"),
    (("艺术", "绘画", "美术", "摄影", "设计", "建筑", "音乐", "乐器", "书法"),
     "mdi-palette-outline", "pink darken-1"),
    (("外语", "英语", "日语", "语言", "词汇", "语法", "翻译"), "mdi-translate", "indigo darken-1"),
    (("法律", "法规", "法学", "司法"), "mdi-gavel", "blue-grey darken-2"),
    (("旅游", "游记", "地图", "旅行"), "mdi-map-marker-outline", "light-green darken-1"),
    (("美食", "烹饪", "菜谱", "饮食", "烘焙"), "mdi-food-outline", "orange darken-1"),
    (("体育", "运动", "健身", "球"), "mdi-basketball", "deep-orange darken-1"),
    (("古籍", "国学", "经史", "四书", "诗词", "唐诗", "宋词", "文言"),
     "mdi-book-open-page-variant", "brown darken-1"),
    (("励志", "成功", "自我提升", "成长"), "mdi-lightbulb-on-outline", "amber darken-3"),
    (("漫画", "图鉴", "画集", "插画"), "mdi-image-multiple-outline", "purple darken-1"),
    (("工具书", "辞典", "词典", "百科", "参考"), "mdi-library-shelves", "blue-grey"),
    (("杂志", "期刊", "报纸"), "mdi-newspaper-variant-outline", "grey darken-1"),
    (("小说", "文学", "散文", "随笔", "诗歌", "文集"), "mdi-book-open-variant", "teal darken-2"),
)

# 未命中关键词时的备选池：按分类名哈希取一个，保证「同一分类稳定、不同分类有区别」
_FALLBACK = (
    ("mdi-bookmark-outline", "blue"),
    ("mdi-label-outline", "teal"),
    ("mdi-folder-outline", "amber"),
    ("mdi-library", "brown"),
    ("mdi-shape-outline", "purple"),
    ("mdi-bookmark-multiple-outline", "cyan"),
)


def _stable_index(name: str, size: int) -> int:
    """按分类名取稳定的下标（不用 Python 内置 hash：它带随机种子，重启会变）。"""
    return zlib.crc32(name.encode("utf-8")) % size


def icon_for_category(name: str) -> Tuple[str, str]:
    """返回 (图标名, 主题色)。name 为空时给默认图标。"""
    text = (name or "").strip()
    if not text:
        return DEFAULT_ICON, DEFAULT_COLOR
    for keywords, icon, color in _RULES:
        for kw in keywords:
            if kw in text:
                return icon, color
    return _FALLBACK[_stable_index(text, len(_FALLBACK))]


def decorate(categories) -> list:
    """给 [{name, count}] 列表补上 icon / color，原地修改并返回列表。

    只加两个展示字段，不动 name/count——前端按老结构读取的地方不受影响。
    """
    for item in categories:
        icon, color = icon_for_category(item.get("name", ""))
        item["icon"] = icon
        item["color"] = color
    return categories
