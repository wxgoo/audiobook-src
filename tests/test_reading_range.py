# -*- coding: UTF-8 -*-
"""公共阅读范围判定模块测试（r47）。

web 列表 / 网页统计 / WebDAV 书目树三处共用 webserver.services.reading_range，
这里锁定其判定语义，防止任何一侧回退到各自的旧副本造成口径漂移。
本模块只依赖 webserver.constants，沙箱可直接 import。
"""
import pytest

from webserver.services import reading_range as rr


class _User:
    """最小用户对象：模拟 Reader 的相关字段。"""

    def __init__(self, admin=False, read_limit=0, limit_categories="", limit_tags="", uid=1):
        self.admin = admin
        self.read_limit = read_limit
        self.limit_categories = limit_categories
        self.limit_tags = limit_tags
        self.id = uid


def test_is_admin_matrix():
    assert rr.is_admin(None) is False
    assert rr.is_admin(_User(admin=False)) is False
    assert rr.is_admin(_User(admin=True)) is True
    assert rr.is_admin(None, superuser=True) is True


def test_reading_range_of_direct_fields():
    u = _User(read_limit=1, limit_categories="科幻,历史", limit_tags="经典")
    eff = rr.reading_range_of(u)
    assert eff == {"read_limit": 1, "limit_categories": "科幻,历史", "limit_tags": "经典"}


def test_reading_range_of_switch_off_is_unlimited():
    u = _User(read_limit=2, limit_categories="x")
    eff = rr.reading_range_of(u, allow_range_setting=False)
    assert eff["read_limit"] == 0


def test_reading_range_of_none_user():
    assert rr.reading_range_of(None)["read_limit"] == 0


@pytest.mark.parametrize(
    "read_limit,cats,tags,category,book_tags,expected",
    [
        # 不限 → 恒 True
        (0, "", "", "科幻", {"x"}, True),
        # 白名单命中分类
        (1, "科幻", "", "科幻", {"x"}, True),
        # 白名单未命中
        (1, "科幻", "", "历史", {"x"}, False),
        # 白名单命中标签
        (1, "", "经典", "历史", {"经典"}, True),
        # 白名单空条件 → 什么都不匹配（关键边界：不能错误放行全库）
        (1, "", "", "科幻", {"x"}, False),
        # 黑名单命中分类 → 拒绝
        (2, "科幻", "", "科幻", {"x"}, False),
        # 黑名单未命中 → 放行
        (2, "科幻", "", "历史", {"x"}, True),
        # 黑名单空条件 → 全库可读
        (2, "", "", "科幻", {"x"}, True),
        # 分类与标签是「或」关系：只填标签，分类不要求匹配
        (1, "", "经典", "历史", {"经典"}, True),
    ],
)
def test_book_matches_limits_dict(read_limit, cats, tags, category, book_tags, expected):
    book = {"#category": category, "tags": list(book_tags)}
    eff = {"read_limit": read_limit, "limit_categories": cats, "limit_tags": tags}
    assert rr.book_matches_limits(book, eff) is expected


class _Metadata:
    """模拟 Calibre 元数据对象（有 get() 与 .tags 属性，无 #category 键的 dict 语义）。"""

    def __init__(self, category, tags):
        self._category = category
        self.tags = tags

    def get(self, key):
        return self._category if key == "#category" else None


def test_book_matches_limits_metadata_object():
    """WebDAV 侧传的是元数据对象，判定必须与 dict 入参同结果。"""
    eff = {"read_limit": 1, "limit_categories": "科幻", "limit_tags": ""}
    assert rr.book_matches_limits(_Metadata("科幻", ["x"]), eff) is True
    assert rr.book_matches_limits(_Metadata("历史", ["x"]), eff) is False
