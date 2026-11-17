# -*- coding: UTF-8 -*-
"""WebDAV 每用户隔离与阅读范围口径一致性（r46）测试。

沙箱无 wsgidav，无法直接 import dav_provider.py。沿用项目惯例：把关键判定
按源码原样复刻成纯函数断言，另有源码核对测试确保 dav_provider.py 的关键
改动没有被改掉/漂移。

覆盖三件事：
  1. 每用户的 sync 物理目录按 user_id 分（/data/reader/<id>/），互不重叠。
  2. 阅读范围全局开关关闭时 WebDAV 全放行（r46 修复），与 web 侧一致。
  3. read_limit 白名单(=1)/黑名单(=2) 判定正确，管理员豁免。
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAV_PROVIDER = os.path.join(ROOT, "webserver", "webdav", "dav_provider.py")
SETTINGS = os.path.join(ROOT, "webserver", "settings.py")


# ---- 源码同构的纯函数 ----

def user_sync_path(base, sync_folder_name, user_id):
    """与 _get_user_sync_path 同构：f"{base}/{name}/{id}/"。"""
    return "%s/%s/%s/" % (base.rstrip("/"), sync_folder_name, user_id)


def effective_reading_range(conf, user, allow_range_key="ALLOW_READ_RANGE_SETTING"):
    """与 _get_user_reading_range 同构（含 r46 的全局开关修复）。

    返回 (read_limit, cats_set, tags_set)。全局开关关闭 / 管理员 / 无用户
    都返回 (0, set(), set())，即全放行。
    """
    if not conf.get(allow_range_key, False):
        return 0, set(), set()
    if not user:
        return 0, set(), set()
    if user.get("admin", False):
        return 0, set(), set()
    read_limit = user.get("read_limit", 0) or 0
    cats = set(filter(None, (user.get("limit_categories") or "").split(",")))
    tags = set(filter(None, (user.get("limit_tags") or "").split(",")))
    return read_limit, cats, tags


def is_book_in_range(mi, read_limit, cats, tags):
    """与 _is_book_in_reading_range 同构。"""
    if read_limit == 0:
        return True
    book_category = str(mi.get("category") or "")
    book_tags = set(mi.get("tags") or [])
    matched = (bool(cats) and book_category in cats) or bool(tags and book_tags & tags)
    return matched if read_limit == 1 else not matched


# ---- 行为测试 ----

def test_each_user_has_isolated_sync_path():
    a = user_sync_path("/data", "reader", 101)
    b = user_sync_path("/data", "reader", 202)
    assert a == "/data/reader/101/"
    assert b == "/data/reader/202/"
    assert a != b
    assert not a.startswith(b) and not b.startswith(a)


def test_global_switch_off_allows_all():
    user = {"admin": False, "read_limit": 2, "limit_categories": "科幻", "limit_tags": ""}
    limit, cats, tags = effective_reading_range({"ALLOW_READ_RANGE_SETTING": False}, user)
    assert (limit, cats, tags) == (0, set(), set())


def test_global_switch_on_applies_user_range():
    user = {"admin": False, "read_limit": 1, "limit_categories": "科幻", "limit_tags": ""}
    limit, cats, tags = effective_reading_range({"ALLOW_READ_RANGE_SETTING": True}, user)
    assert limit == 1 and cats == {"科幻"} and tags == set()


def test_admin_exempt():
    admin = {"admin": True, "read_limit": 2, "limit_categories": "x", "limit_tags": ""}
    assert effective_reading_range({"ALLOW_READ_RANGE_SETTING": True}, admin) == (0, set(), set())


def test_whitelist_blacklist_matching():
    books = [
        {"category": "科幻", "tags": {"太空"}},
        {"category": "历史", "tags": {"考古"}},
    ]
    # 白名单：只放行科幻
    visible = [b for b in books if is_book_in_range(b, 1, {"科幻"}, set())]
    assert visible == [books[0]]
    # 黑名单：放行非科幻
    visible = [b for b in books if is_book_in_range(b, 2, {"科幻"}, set())]
    assert visible == [books[1]]
    # 无限制：全放行
    assert all(is_book_in_range(b, 0, set(), set()) for b in books)


def test_tag_matching():
    b = {"category": "其他", "tags": {"有声", "经典"}}
    assert is_book_in_range(b, 1, set(), {"经典"}) is True
    assert is_book_in_range(b, 1, set(), {"不存在"}) is False


# ---- 源码核对（防漂移）----

def test_source_has_global_switch_guard():
    src = open(DAV_PROVIDER, encoding="utf-8").read()
    assert 'CONF.get("ALLOW_READ_RANGE_SETTING", False)' in src, \
        "_get_user_reading_range 缺少 r46 的全局开关判断"


def test_source_has_per_user_sync_path():
    src = open(DAV_PROVIDER, encoding="utf-8").read()
    assert "sync_folder_name" in src and "user_id" in src, \
        "sync 目录未按 user_id 隔离"


def test_settings_has_default_folder_name():
    src = open(SETTINGS, encoding="utf-8").read()
    assert '"WEBDAV_SYNC_FOLDER_NAME": "reader"' in src, \
        "settings.py 缺少 WEBDAV_SYNC_FOLDER_NAME 默认值"
