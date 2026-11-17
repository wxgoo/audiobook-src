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


# ---- r47：完全隔离 / 越权出口修复的源码核对 ----

def test_unified_user_resolution():
    """r47：统一从 environ 解析用户，同时支持 Reader 对象与用户名字符串回退。"""
    src = open(DAV_PROVIDER, encoding="utf-8").read()
    assert "def _get_reader_from_environ" in src
    assert "environ.get('mybooks.user')" in src, "未优先读 auth 写入的 Reader 对象"
    assert "wsgidav.auth.user_name" in src, "缺少用户名字符串回退查库"


def test_fail_closed_when_no_user():
    """r47：解析不到用户时拒绝（fail-closed），不能退回全放行。"""
    src = open(DAV_PROVIDER, encoding="utf-8").read()
    assert "if user is None:" in src and "return False" in src, \
        "_can_access_book 缺少无用户拒绝分支"


def test_all_direct_book_branches_guarded():
    """r47：8 个直接定位单本的分支都必须过 _can_access_book。"""
    src = open(DAV_PROVIDER, encoding="utf-8").read()
    # 8 个 handle 分支各一处 + 作者枚举内一处（collect 循环）
    count = src.count("if not self._can_access_book(environ, book_id")
    assert count >= 8, f"直接定位分支的出口校验不足 8 处（实际 {count}）"


def test_download_exit_guarded_before_charge():
    """r47：get_content() 下载出口必须过校验，且在下载配额扣费之前。"""
    src = open(DAV_PROVIDER, encoding="utf-8").read()
    guard = src.find("self._dav_provider._can_access_book(self.environ, self.id")
    charge = src.find("DownloadQuotaService.charge")
    assert guard >= 0, "get_content() 缺少统一出口校验"
    assert charge >= 0
    assert guard < charge, "可见性校验必须在下载配额扣费之前（否则越界访问被误扣费）"


def test_admin_exempt_in_exit_guard():
    """r47：管理员在出口校验里全放行，避免合法访问被误拦。"""
    src = open(DAV_PROVIDER, encoding="utf-8").read()
    assert "if _is_admin(user):" in src and "return True" in src
    assert "_is_admin" in src, "未从公共模块引入管理员豁免"


def test_book_matches_limits_is_shared():
    """r47：WebDAV 与 web 侧的阅读范围判定都转调公共模块，杜绝两份口径漂移。"""
    src = open(DAV_PROVIDER, encoding="utf-8").read()
    assert "from webserver.services.reading_range import" in src
    assert "book_matches_limits as _book_matches_limits_shared" in src
    # _is_book_in_reading_range 内部应转调公共函数而非自己复刻分类/标签匹配
    assert "_book_matches_limits_shared" in src


def test_path_traversal_guard():
    """r47：虚拟路径层拒绝 '..' 穿越段。"""
    src = open(DAV_PROVIDER, encoding="utf-8").read()
    assert "posixpath.normpath" in src
    assert "'..'" in src or '".."' in src, "缺少 '..' 段拒绝"


def test_authors_dimension_filtered():
    """r47：作者维度只枚举可见书的作者，不泄露越界书作者名。"""
    src = open(DAV_PROVIDER, encoding="utf-8").read()
    # handle_authors 内应先解析用户、再逐本过可见性收集作者
    pos = src.find("def handle_authors")
    segment = src[pos:pos + 1800]
    assert "_get_reader_from_environ" in segment
    assert "_can_access_book" in segment
