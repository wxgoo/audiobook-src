#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""阅读范围判定公共模块（唯一口径来源，无 Tornado / wsgidav 依赖）。

为什么有这个文件
----------------
判定本体 ``_book_matches_limits`` 历史上内联在 ``handlers/base.py``，r46 时
WebDAV 侧（``webdav/dav_provider.py``）又复刻了一份 ``_is_book_in_reading_range``。
两份口径靠人肉同步，已在 r46 发生过一次漂移（全局开关检查遗漏）。r47 把判定
本体抽到这个只依赖 ``webserver.constants`` 的纯模块：

  * ``handlers/base.py`` 的 ``_book_matches_limits`` 改为转调本模块；
  * ``webdav/dav_provider.py`` 的 ``_is_book_in_reading_range`` 也转调本模块。

这样「网页列表 / 网页统计 / WebDAV 书目树」三处共用同一份判定，改一处全站生效。

入参兼容两种书对象：
  * web 侧是 dict（``book.get("#category")`` / ``book.get("tags")``）；
  * WebDAV 侧是 Calibre 元数据对象（``mi.get("#category")`` / ``mi.tags``）。
分类键统一用 ``constants.CALIBRE_COLUMN_CATEGORY``（"#category"），杜绝字面量漂移。
"""

from webserver import constants


def is_admin(user, superuser: bool = False) -> bool:
    """用户是否为管理员（None/匿名一律 False；superuser 是运维快捷身份）。

    与 services/access_control.py 的 AccessControl.is_admin 同语义；门面转调这里，
    保证 WebDAV（不 import 门面）与 web 侧共用同一份豁免判定。
    """
    if superuser:
        return True
    return bool(getattr(user, "admin", False)) if user is not None else False


def reading_range_of(user, allow_range_setting: bool = True) -> dict:
    """用户阅读范围，返回 {read_limit, limit_categories, limit_tags}（上游 4.7.0 口径：
    直接读用户自己的三个字段，读者组定制层已随 r45 移除）。

    allow_range_setting=False 时视为不限（全局开关关闭的快路）。
    """
    if not allow_range_setting or user is None:
        return {"read_limit": 0, "limit_categories": "", "limit_tags": ""}
    return {
        "read_limit": getattr(user, "read_limit", 0) or 0,
        "limit_categories": getattr(user, "limit_categories", "") or "",
        "limit_tags": getattr(user, "limit_tags", "") or "",
    }


def book_matches_limits(book, eff: dict) -> bool:
    """判定一本书在给定「阅读范围限制」下是否可读——全站唯一口径来源。

    从 handlers/base.py 迁来（上游 4.7.0 无此函数，它把等价逻辑内联）。比上游
    内联版多处理两个边界，语义更严谨：
      * 白名单空条件 → 什么都匹配不上（False）；黑名单空条件 → 全库可读（True）。
        上游内联版对两者都返回 not matched，白名单空时会错误放行全库。
      * 分类与标签是「或」关系：只填一边时不要求另一边也匹配。

    eff 含 read_limit / limit_categories / limit_tags 三个键（值为用户字段或缓存签名）。
    """
    read_limit = int(eff.get("read_limit") or 0)
    if read_limit == 0:
        return True
    limit_categories = set(filter(None, (eff.get("limit_categories") or "").split(",")))
    limit_tags = set(filter(None, (eff.get("limit_tags") or "").split(",")))
    if not limit_categories and not limit_tags:
        return read_limit != 1

    # 兼容 dict（web 侧）与 Calibre 元数据对象（WebDAV 侧）
    if isinstance(book, dict):
        category = book.get(constants.CALIBRE_COLUMN_CATEGORY)
        tags = book.get("tags") or []
    else:
        getter = getattr(book, "get", None)
        category = getter(constants.CALIBRE_COLUMN_CATEGORY) if callable(getter) else None
        tags = getattr(book, "tags", None) or []
    book_category = str(category) if category else ""
    book_tags = set(tags or [])
    matched = (limit_categories and book_category in limit_categories) or bool(
        limit_tags and book_tags & limit_tags
    )
    return matched if read_limit == 1 else not matched
