#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import asyncio
import base64
import json
import logging
import os
import sys
import shutil
import tempfile
import time
import unittest
import urllib
from unittest import mock

import requests
from tornado import testing, web

testdir = os.path.dirname(os.path.realpath(__file__))
projdir = os.path.realpath(testdir + "/../../")
sys.path.append(projdir)

import webserver.handlers.base
import webserver.handlers.book
from webserver import loader, main, models, plugins  # nosq: E402
from webserver.handlers.base import BaseHandler

_app = None
_mock_user = None
_mock_mail = None
_mock_service_async_mode = None
_mock_bookbarn_tags = None


class _OfflineBookBarnTags:
    """把 bookbarn 标签服务钉成「离线、查不到」。

    为什么必须钉：`BookBarnTags.TAGS_API` 指向 **mybooks.top 上的生产接口**，
    请求成功时按书名返回一整套线上标签。也就是说只要本机联网，**任何**走
    `AutoFillService.auto_fill()` 的代码路径都会把夹具里那本书的标签换成线上那套：

        tests/library/metadata.db  book 1 的 tags
          夹具:  小说/外国文学/经典/魔幻现实主义/拉美文学/诺贝尔奖/家族史/孤独/翻译文学
          线上:  值得一读/外国文学/小说/拉美文学/文学/经典/马尔克斯/魔幻现实主义

    于是同一个用例「断网跑绿、联网跑红」，`test_main.TestMeta::test_tag`
    期望 72 个标签，实测只剩 71 个。

    现在触发它的路径是 `AdminTrashBooksRestore.post()`：它恢复完书会调
    `_recreate_item_for_restored_book()` → `AutoFillService().auto_fill()`；
    `test_admin` 的恢复用例只 mock 了 `move_book_from_trash`，没管这条刮削
    路径，所以每条用例都会真跑一次线上刮削。将来别的代码路径接上
    `auto_fill()` 也一样会中招，所以在测试入口统一钉死，比逐个用例打补丁可靠。

    替代方案是关掉 CONF["auto_fill_meta"]，但那会让「恢复后自动刮削」这段逻辑
    在测试里再也不执行，等于把这个功能从覆盖范围里删掉。这里只断网、保留逻辑。
    """

    def __init__(self, token=None):
        self.token = token

    def get_tags(self, isbn, title=None, author=None):
        return None

    def normalize_title(self, title):
        return title or ""

    def normalize_author(self, author):
        return author or ""


class _NeutralTrashManager:
    """把回收站恢复/彻底删除换成空实现。

    要解决的是**内存库与磁盘库对不上**，跟标签没关系：

    `AdminTrashBooksRestore.post()` / `AdminTrashBooksPurge.post()` 里真正干活的是
    `TrashManager.restore_trash_books(cache, ids)` / `purge_trash_books(cache, ids)`，
    它内部逐本调 `cache.move_book_from_trash()` / `cache.delete_trash_entry()`。
    `test_admin` 的用例只把 `new_api.move_book_from_trash` 换成 mock，**没换
    `TrashManager`**，所以每次请求仍会走真正的方法。

    而在测试环境里，这些用例用的是**夹具库（书都完好、不带 trash 记录）**，
    `move_book_from_trash(1)` 于是抛 `A book with the id 1 already exists`——
    异常被 `TrashManager` 吞掉记进 failed，看着无害；但 `purge_trash_books`
    调的 `delete_trash_entry()` 不抛异常，它把 books 表里的行真删掉，同时把
    calibre **进程内缓存**里的 id 摘掉。

    结果：磁盘 metadata.db 还是 13 本，`db.count()`（= `View.count()`，读的是
    内存 `View._map`）变成 16 本，而且此后每个 admin 用例都会把它再撑大一点。
    下一个用例 `test_main.TestAppWithoutLogin::test_user_info` 断言
    `sys.books == 13`，拿到 16 → 失败。单跑 `test_admin.py` 自己却全绿，
    因为它自己的断言都只是 `err/count` 这类，不读总数。

    所以这里把 `TrashManager` 的两个方法钉成空实现：用例验证的是**接口契约**
    （参数校验、返回值形状、失败分支），不需要真的动库。真实实现另有
    `test_upload` / `test_book_list` 等接口级用例覆盖。
    """

    @staticmethod
    def restore_trash_books(cache, book_ids):
        return list(book_ids), {}

    @staticmethod
    def purge_trash_books(cache, book_ids):
        return list(book_ids), {}

    @staticmethod
    def list_trash_books(cache):
        return []

    @staticmethod
    def clear_trash_cache():
        return None

'''
1	EPUB	440912	Bai Nian Gu Du - Jia Xi Ya  Ma Er Ke Si
2	TXT	298421	Man Man Zi You Lu - Unknown
3	MOBI	2662851	An Tu Sheng Tong Hua - An Tu Sheng
4	AZW3	344989	Mai Ken Xi Fang Fa (Jing Guan Tu Shu De Ch - Ai Sen _La Sai Er (Ethan M.Rasiel)
5	PDF	6127496	E Yu Pa Pa Ya Yi Pa Pa - Unknown
6	EPUB	324726	Tang Shi San Bai Shou - Wei Zhi
...
13 本书见 tests/make_fixtures.py 的 BOOKS；上面只列了历史上被点名的前 6 本。
'''
BID_EPUB = 1
BID_TXT = 2
BID_MOBI = 3
BID_AZW3 = 4
BID_PDF = 5
# 「全部书」= 夹具里所有书的 id。
# 原来写死 range(1, 6)，是只有 5 本书那会儿的遗留：夹具扩到 13 本之后，
# 凡是拿 BIDS 做「对每本书都做一遍 X」的用例（/read/<id> 的重定向、
# /api/book/folder 的清空）就只覆盖了前 5 本，而
# tests/test_folder_handlers.py 里 `root_count == len(BIDS) - 2` 这种
# 「用 BIDS 反推总数」的断言就直接错位了。数量集中在 EXPECTED_BOOKS 一处。
BIDS = list(range(1, 14))


_FIXTURE_READY = False


def setup_server():
    """准备库夹具并建 app。**幂等**：重复调用不会重建库目录。

    ## 为什么必须幂等

    `tests/` 下几十个文件都以

        from tests.test_main import TestWithUserLogin, setUpModule as init
        def setUpModule(): init()

    引入本模块，于是 `setup_server()` 会在**每个**测试文件的模块级被调一次
    （pytest 会在开始跑某个文件的用例前调用它的 `setUpModule`）。

    原来这里无条件 `shutil.rmtree(libdir)` 再 `copytree`，等于把整个库目录
    （含 metadata.db / users.db / -wal / -shm）连根删掉重建一次。而
    tornado 的 `LibraryDatabase`（calibre 的 apsw 连接）和 SQLAlchemy 的
    engine 还拿着**旧 inode** 的句柄：

    * calibre 侧写库报 `apsw.ReadOnlyError: attempt to write a readonly database`
      （旧 db 文件被 unlink，句柄退化）；
    * SQLAlchemy 侧同样报 `attempt to write a readonly database`，
      并且会留下一条 `PendingRollbackError` 让后续 flush 全部失败。

    单跑一个文件看不出来（只建一次库）；`test_main → test_scan → test_upload`
    连跑就必现 —— 第三个文件的 `setUpModule()` 把前两个文件正在用的库删了。

    所以：**只建第一次**，之后只刷新 CONF（不同文件可能改选项）。想强制重建
    夹具用 `tests/make_fixtures.py`，或删掉 `tests/library/` 再跑。
    """
    global _app, _FIXTURE_READY
    # 夹具是**整个库目录**，不只是 metadata.db：calibre 把每本书的格式文件
    # 和封面存在 <库根>/<作者>/<书名 (id)>/ 下，只复制 db 的话 /api/book/1.epub
    # 会 404（库里记着有书，磁盘上没文件）。
    #
    # users.db 一定要**最后**单独覆盖，且覆盖前先删掉目标文件：
    # cases/library/ 里可能残留一个 0 字节的 users.db（早期某次测试直接
    # 在夹具目录里开库，把它建成了空文件）。copytree 会把这个空文件一起
    # 搬过去，之后 copyfile 才是真正写入真实数据 —— 但只要用户数没变，光看
    # 大小是发现不了的；而 `copyfile` 对已存在文件是原地覆写，
    # 长度不减（空文件→短文件）时 SQLite 会读到尾部残留。
    # 先删再拷最省事，也顺带把 -wal/-shm 一起断干净：残留的 WAL 会把旧事务
    # 回放到新库上，表现成「刚复制的库里表不见了」或者「凭空多出一条 items」。
    libdir = testdir + "/library"
    if not _FIXTURE_READY:
        if os.path.isdir(testdir + "/cases/library"):
            if os.path.exists(libdir):
                shutil.rmtree(libdir)
            shutil.copytree(testdir + "/cases/library", libdir,
                            ignore=shutil.ignore_patterns("users.db", "users.db-wal", "users.db-shm"))
        else:
            # 老夹具（只有两个 db 文件、没有书文件）时退回到逐文件复制
            os.makedirs(libdir, exist_ok=True)
            shutil.copyfile(testdir + "/cases/metadata.db", libdir + "/metadata.db")
        for suffix in ("", "-wal", "-shm"):
            p = libdir + "/users.db" + suffix
            if os.path.exists(p):
                os.remove(p)
        shutil.copyfile(testdir + "/cases/users.db", libdir + "/users.db")
        _FIXTURE_READY = True

    # set env
    main.options.with_library = testdir + "/library/"
    main.CONF["scan_upload_path"] = testdir + "/cases/"
    main.CONF["ALLOW_GUEST_PUSH"] = False
    main.CONF["ALLOW_GUEST_DOWNLOAD"] = False
    main.CONF["upload_path"] = "/tmp/"
    main.CONF["html_path"] = "/tmp/"
    main.CONF["settings_path"] = "/tmp/"
    main.CONF["progress_path"] = "/tmp/"
    main.CONF["extract_path"] = "/tmp/"
    main.CONF["nuxt_env_path"] = "/tmp/.env.text"
    main.CONF["installed"] = True
    main.CONF["INVITE_MODE"] = False
    # 注册开关：ALLOW_REGISTER 默认 False（生产默认关闭注册），
    # 而 TestUser.test_login / TestUserSignUp.test_signup 都要走注册流程。
    main.CONF["ALLOW_REGISTER"] = True
    main.CONF["user_database"] = "sqlite:///%s/library/users.db" % testdir
    # main.CONF["db_engine_args"] = {"echo": True}
    # 工具箱工作目录硬编码为 /data/toolbox（生产容器内可写）。本机 / WSL 普通
    # 用户没有 /data 写权限，make_app 注册工具箱路由时直接 PermissionError，
    # 于是每个文件的 setUpModule 都挂掉（全量跑时表现为几百个 error）。
    # 只在测试进程内把类属性指到临时目录，容器里仍走 /data，生产行为不变。
    from webserver.toolbox.base_tool import BaseTool

    try:
        os.makedirs(BaseTool.TOOL_DATA_ROOT, exist_ok=True)
    except OSError:
        BaseTool.TOOL_DATA_ROOT = os.path.join(tempfile.gettempdir(), "mybooks-test-toolbox")
        os.makedirs(BaseTool.TOOL_DATA_ROOT, exist_ok=True)
    if _app is None:
        _app = main.make_app()


def setup_mock_user():
    global _mock_user
    # setUpModule 会被每个测试文件各调一次（见 setup_server 的说明），
    # 每次重建 patcher 会让 setUpClass 启动的实例和 tearDownClass 停止的
    # 实例不是同一个，patch 泄漏到后面的用例，所以这些 setup 必须幂等。
    if _mock_user is None:
        _mock_user = mock.patch.object(BaseHandler, "user_id", return_value=1)


def setup_mock_sendmail():
    global _mock_mail
    if _mock_mail is None:
        _mock_mail = mock.patch("calibre.utils.smtp.sendmail", return_value="Yo")


def setup_mock_service():
    global _mock_service_async_mode
    if _mock_service_async_mode is None:
        _mock_service_async_mode = mock.patch("webserver.services.AsyncService.async_mode")


def setup_mock_trash_manager():
    """把回收站恢复/删除换成空实现，避免 admin 用例把内存库改乱（详见类注释）。"""
    from webserver.base import trash_manager as _tm

    _tm.TrashManager.restore_trash_books = _NeutralTrashManager.restore_trash_books
    _tm.TrashManager.purge_trash_books = _NeutralTrashManager.purge_trash_books


def setup_mock_bookbarn():
    """钉住 bookbarn 标签接口，避免测试机联网时把夹具标签换成线上那套（详见类注释）。

    注意两点：
    1. 必须**先 import 一次 `webserver.services.autofill`**。`mock.patch("...BookBarnTags")`
       只改源模块里的名字，`autofill.py` 顶部是 `from ... import BookBarnTags`，
       它自己那份引用在首次 import 时就固定了；如果 autofill 还没被导入就打桩，
       等它稍后被导入时又会从源模块重新绑回去，桩等于白打。
    2. 用 `create=False` 的 patch 语义对 `already-imported` 的模块名同样有效，
       所以拿到脏掉的引用后把 `autofill.BookBarnTags` 一起换掉最稳妥。
    """
    global _mock_bookbarn_tags
    if _mock_bookbarn_tags is not None:
        # 已经 start 过：重复 start 会 RuntimeError: Patch is already started
        return
    from webserver.services import autofill as _autofill

    _mock_bookbarn_tags = mock.patch(
        "webserver.plugins.meta.bookbarn_tags.BookBarnTags", _OfflineBookBarnTags
    )
    _mock_bookbarn_tags.start()
    # 双保险：直接换掉 autofill 模块里已经绑定的那份引用
    _autofill.BookBarnTags = _OfflineBookBarnTags


def get_db():
    return _app.settings["ScopedSession"]


def Q(s):
    if not isinstance(s, str):
        s = str(s)
    return urllib.parse.quote(s.encode("UTF-8"))


class FakeHandler(BaseHandler):
    def __init__(h):
        h.request = h
        h.request.headers = {}
        h.request.remote_ip = "1.2.3.4"
        h.rsp_headers = {}
        h.rsp = None
        h.cookie = {}
        h.sqlite_session = get_db()

    def write(self, rsp):
        self.rsp = rsp

    def finish(self):
        return None

    def set_header(self, k, v):
        self.rsp_headers[k] = v

    def set_secure_cookie(self, k, v):
        self.cookie[k] = v


class TestApp(testing.AsyncHTTPTestCase):
    def get_app(self):
        return _app

    def json(self, url, *args, **kwargs):
        if 'request_timeout' not in kwargs:
            kwargs['request_timeout'] = 60
        rsp = self.fetch(url, *args, **kwargs)
        self.assertEqual(rsp.code, 200)
        return json.loads(rsp.body)

    def gt(self, n, at_least):
        self.assertEqual(n, max(n, at_least))

    def assert_book_simple(self, book):
        self.assertTrue("img" in book)
        self.assertTrue("authors" in book)
        self.assertTrue("comments" in book)
        self.assertTrue("id" in book)
        self.assertTrue("publisher" in book)
        self.assertTrue("rating" in book)
        self.assertTrue("title" in book)

    def assert_book_fields(self, book):
        self.assert_book_simple(book)
        self.assertTrue("tags" in book)
        self.assertTrue("timestamp" in book)
        self.assertTrue("collector" in book)
        self.assertTrue("count_visit" in book)
        self.assertTrue("count_download" in book)
        self.assertTrue("pubdate" in book)
        self.assertTrue("series" in book)

    def assert_book(self, book):
        self.assert_book_fields(book)
        d = self.json("/api/book/%s" % book["id"])["book"]
        self.assert_book_fields(d)
        self.gt(len(d["files"]), 1)

    def assert_book_list(self, d, at_least):
        self.assertEqual(d["err"], "ok")
        self.gt(d["total"], at_least)
        n = len(d["books"])
        if n < 30:
            self.assertEqual(d["total"], n)
        self.assertTrue(n <= 30)
        for book in d["books"]:
            self.assert_book(book)


class TestAppWithoutLogin(TestApp):
    def test_index(self):
        d = self.json("/api/index?random=7&recent=9")
        self.assertEqual(len(d["new_books"]), 9)
        self.assertEqual(len(d["random_books"]), 7)
        for book in d["new_books"] + d["random_books"]:
            self.assert_book_simple(book)

        book = d["new_books"][0]
        for author in book["authors"]:
            self.json("/api/author/" + Q(author))

        self.json("/api/author/" + Q(book["author"]))
        self.json("/api/publisher/" + Q(book["publisher"]))

    def test_search(self):
        d = self.json("/api/search")
        self.assertEqual(d["err"], "params.invalid")

        d = self.json("/api/search?hack")
        self.assertEqual(d["err"], "params.invalid")

        d = self.json("/api/search?name=NotFound")
        self.assertEqual(d["err"], "ok")
        self.assertEqual(d["total"], 0)
        self.assertEqual(len(d["books"]), 0)

        d = self.json("/api/search?name=A")
        self.assert_book_list(d, 6)

    def test_search_calibre_expr_and_fields(self):
        d = self.json("/api/search?name=" + Q("title:NotFound OR id:>0"))
        self.assertEqual(d["err"], "ok")
        self.assertTrue(d["total"] > 0)

        d = self.json("/api/search?name=" + Q("id:>0 AND title:NotFound"))
        self.assertEqual(d["err"], "ok")
        self.assertEqual(d["total"], 0)

        d = self.json("/api/search?author=NotFound&publisher=NotFound")
        self.assertEqual(d["err"], "ok")
        self.assertEqual(d["total"], 0)

        d = self.json("/api/search?isbn=978-0-00-000000-0")
        self.assertEqual(d["err"], "ok")
        self.assertEqual(d["total"], 0)

        d = self.json("/api/search?name=9780000000000")
        self.assertEqual(d["err"], "ok")
        self.assertEqual(d["total"], 0)

    # def test_hot(self):
    #     d = self.json("/api/hot")
    #     self.assert_book_list(d, 0)

    def test_recent(self):
        d = self.json("/api/recent")
        self.assert_book_list(d, 10)

    def test_download(self):
        rsp = self.fetch("/api/book/1.epub", follow_redirects=False)
        self.assertEqual(rsp.code, 302)

    def _sign(self, uid=1, bid=1, fmt="epub", expire=None):
        expire = int(time.time()) + 3600 if expire is None else expire
        mac = BaseHandler._download_sign_mac(_app.settings["cookie_secret"], uid, bid, fmt, expire)
        return "%s.%s.%s" % (uid, expire, mac)

    def test_download_with_sign(self):
        rsp = self.fetch("/api/book/1.epub?dl=" + self._sign(), follow_redirects=False)
        self.assertEqual(rsp.code, 200)
        self.assertEqual(int(rsp.headers["Content-Length"]), len(rsp.body))

    def test_download_with_bad_sign(self):
        for sign in ("bogus", self._sign(bid=2), self._sign(fmt="pdf"), self._sign().replace("1.", "2.", 1), self._sign(expire=int(time.time()) - 1)):
            rsp = self.fetch("/api/book/1.epub?dl=" + sign, follow_redirects=False)
            self.assertEqual(rsp.code, 403)

    def test_download_guest_allowed_ignores_sign(self):
        main.CONF["ALLOW_GUEST_DOWNLOAD"] = True
        try:
            rsp = self.fetch("/api/book/1.epub", follow_redirects=False)
            self.assertEqual(rsp.code, 200)
        finally:
            main.CONF["ALLOW_GUEST_DOWNLOAD"] = False

    def test_push(self):
        # 接口已从 /push（mail_to）改为 /mailto（email+format），见 BookSendToMail。
        d = self.json("/api/book/1/mailto", method="POST",
                      body=json.dumps({"email": "unittest@gmail.com", "format": "epub"}))
        self.assertEqual(d["err"], "user.need_login")

    def test_user_info(self):
        d = self.json("/api/user/info")
        self.assertEqual(d["user"]["is_login"], False)
        self.assertEqual(d["user"]["is_admin"], False)
        self.assertEqual(d["sys"]["books"], 13)
        self.assertEqual(d["sys"]["epub_viewer"], main.CONF.get("EPUB_VIEWER", "MyReader"))

        d = self.json("/api/user/info?detail=1")
        self.assertEqual(d["user"]["is_login"], False)
        self.assertEqual(d["sys"], {})

    def test_whoami_not_logged_in(self):
        """未登录 + 未开放访客阅读 → need_login。

        whoami 还有个「分享访客」分支：开了 ALLOW_GUEST_READ 时，
        未登录会返回 {"err": "ok", "userId": 999999, "is_guest": True}，
        供内嵌阅读器认身份。这里显式关掉，才测得到真正未登录的情况。
        """
        with mock.patch.dict(main.CONF, {"ALLOW_GUEST_READ": False, "REQUIRE_LOGIN": False}):
            d = self.json("/api/user/whoami")
        self.assertEqual(d["err"], "user.need_login")
        self.assertNotIn("userId", d)

    def test_whoami_guest_reader(self):
        """开放访客阅读时，未登录也能拿到一个临时访客身份（userId=999999）。"""
        with mock.patch.dict(main.CONF, {"ALLOW_GUEST_READ": True, "REQUIRE_LOGIN": False}):
            d = self.json("/api/user/whoami")
        self.assertEqual(d["err"], "ok")
        self.assertEqual(d["userId"], 999999)
        self.assertTrue(d["is_guest"])

    def test_book(self):
        d = self.json("/api/book/1")
        self.assertEqual(d["err"], "ok")


class TestMeta(TestApp):
    def assert_meta(self, meta, total):
        d = self.json("/api/%s" % meta)
        self.assertEqual(len(d["items"]), total)
        for m in d["items"]:
            url = "/api/%s/%s" % (meta, Q(m["name"]))
            a = self.json(url)
            self.gt(len(a["books"]), 1)
            b = self.json(url + "?size=3")
            c = self.json(url + "?start=3")
            d = self.json(url + "?sort=timestamp")
            self.assertEqual(a["total"], b["total"])
            self.assertEqual(a["total"], c["total"])
            self.assertEqual(a["total"], d["total"])

    def test_tag(self):
        self.assert_meta("tag", 72)

    def test_author(self):
        self.assert_meta("author", 15)

    def test_series(self):
        self.assert_meta("series", 7)

    def test_publisher(self):
        self.assert_meta("publisher", 10)

    def test_rating(self):
        # 测试库中原始评分为 7/8/9（0-10 分制），按 5 星合并后 7 分和 8 分都归入 4 星，
        # 9 分归入 5 星，因此只剩 2 个星级桶。
        self.assert_meta("rating", 2)


class AutoResetPermission:
    def __init__(self, arg):
        if not arg:
            arg = models.Reader.id == 1
        self.arg = arg

    def __enter__(self):
        self.user = get_db().query(models.Reader).filter(self.arg).first()
        self.user.permission = ""
        return self.user

    def __exit__(self, type, value, trace):
        self.user.permission = ""


def mock_permission(arg=None):
    return AutoResetPermission(arg)


class TestWithUserLogin(TestApp):
    @classmethod
    def setUpClass(self):
        self.user = _mock_user.start()
        self.mail = _mock_mail.start()
        self.async_service = _mock_service_async_mode.start()
        self.user.return_value = 1
        self.mail.return_value = True
        self.async_service.return_value = False

    @classmethod
    def tearDownClass(self):
        _mock_user.stop()
        _mock_mail.stop()
        # 这里原本写的是 .start()（明明是 tearDown 却启动了一个 mock），
        # 于是「Service 异步模式 = False」这个 patch 泄漏到后面的测试类，
        # 后面 TestAppWithoutLogin 的未登录用例全被当成已登录。
        _mock_service_async_mode.stop()


class TestUser(TestWithUserLogin):
    @classmethod
    def tearDownClass(cls):
        # add_user() 会注册一个 username=active 的账号。不清理的话，
        # TestAdmin.test_admin_users 断言的「31 个用户」就会变成 32
        # ——一个测试类弄脏下一个测试类的夹具计数。
        super().tearDownClass()
        db = get_db()
        extra = db.query(models.Reader).filter(models.Reader.username == "active").first()
        if extra:
            db.delete(extra)
            db.commit()

    def test_userinfo(self):
        d = self.json("/api/user/info")
        self.assertEqual(d["err"], "ok")
        self.assertEqual(d["user"]["is_login"], True)

        d = self.json("/api/user/info?detail=1")
        self.assertEqual(d["err"], "ok")
        self.assertEqual(d["user"]["is_login"], True)
        self.assertEqual(d["sys"], {})

    def test_whoami(self):
        with mock_permission() as user:
            user.set_permission("r")
            d = self.json("/api/user/whoami")
            self.assertEqual(d["err"], "ok")
            self.assertEqual(d["userId"], user.id)
            self.assertEqual(d["username"], user.username)
            self.assertEqual(d["canRead"], True)
            self.assertEqual(d["isActive"], True)

    def test_whoami_no_read_permission(self):
        with mock_permission() as user:
            user.set_permission("R")
            d = self.json("/api/user/whoami")
            self.assertEqual(d["err"], "ok")
            self.assertEqual(d["canRead"], False)

    def add_user(self):
        self.mail.reset_mock()
        body = ("email=active@gmail.com&nickname=active&username=active"
                "&password=active66&birth_year=1990")
        d = self.json("/api/user/sign_up", method="POST", raise_error=True, body=body)
        self.assertTrue(d["err"] in ["ok", "params.username.exist"])
        # 注册出来的账号是未激活的（active=False），未激活登录会被
        # permission.inactive 挡住。本用例测的是「登录 + 权限位」，不是激活流程
        # （激活流程由 TestUserSignUp.test_signup 覆盖），这里直接置为已激活。
        user = get_db().query(models.Reader).filter(models.Reader.username == "active").first()
        if user and not user.active:
            user.active = True
            get_db().commit()

    def test_login(self):
        # rsp = self.fetch("/api/done", follow_redirects=False)
        # self.assertEqual(rsp.code, 302)
        self.add_user()

        user = get_db().query(models.Reader).filter(models.Reader.username == "active").first()
        user.permission = ""
        d = self.json("/api/user/sign_in", method="POST", body="username=active&password=active66")
        self.assertEqual(d["err"], "ok")

        user = get_db().query(models.Reader).filter(models.Reader.username == "active").first()
        user.set_permission("L")
        logging.debug("user[%s] id[%s] permission[%s]", user.username, user.id, user.permission)
        d = self.json("/api/user/sign_in", method="POST", body="username=active&password=active66")
        self.assertEqual(d["err"], "permission")

        user = get_db().query(models.Reader).filter(models.Reader.username == "active").first()
        user.set_permission("l")
        d = self.json("/api/user/sign_in", method="POST", body="username=active&password=active66")
        self.assertEqual(d["err"], "ok")


class TestFile(TestWithUserLogin):
    def test_get_cover(self):
        rsp = self.fetch("/get/cover/1.jpg", follow_redirects=False)
        self.assertEqual(rsp.code, 200)

    def test_get_thumb(self):
        rsp = self.fetch("/get/thumb_80x80/1.jpg", follow_redirects=False)
        self.assertEqual(rsp.code, 200)

    def test_get_opf(self):
        rsp = self.fetch("/get/opf/1", follow_redirects=False)
        self.assertEqual(rsp.code, 200)


class TestBook(TestWithUserLogin):
    def test_nav(self):
        rsp = self.fetch("/api/book/nav")
        self.assertEqual(rsp.code, 200)

    def test_download(self):
        rsp = self.fetch("/api/book/1.epub")
        self.assertEqual(rsp.code, 200)
        book_body = rsp.body

        rsp = self.fetch("/api/book/1.pdf")
        self.assertEqual(rsp.code, 404)

        rsp = self.fetch("/api/book/1.epub", headers={"Range": "bytes=0-0"})
        self.assertEqual(rsp.code, 206)
        self.assertEqual(len(rsp.body), 1)

        rsp = self.fetch("/api/book/1.EPUB", headers={"Range": "bytes=1-"})
        self.assertEqual(rsp.code, 206)
        self.assertEqual(rsp.body, book_body[1:])


    def test_download_permission(self):
        with mock_permission() as user:
            user.set_permission("S")  # forbid
            rsp = self.fetch("/api/book/1.epub")
            self.assertEqual(rsp.code, 403)

            user.set_permission("s")  # allow
            rsp = self.fetch("/api/book/1.epub")
            self.assertEqual(rsp.code, 200)

    def mock_convert(self):
        class MockConvertPath:
            def __init__(self, path=None):
                if not path:
                    path = testdir + "/cases/old.epub"
                self.mock1 = mock.patch("webserver.services.converter.ConverterService.get_path_of_fmt", return_value=path)
                self.mock2 = mock.patch("webserver.services.converter.ConverterService.do_ebook_convert", return_value=True)

            def __enter__(self):
                self.mock1.start()
                return self.mock2.start()

            def __exit__(self, type, value, trace):
                self.mock1.stop()
                self.mock2.stop()

        return MockConvertPath()

    def test_push(self):
        with self.mock_convert() as m:
            d = self.json("/api/book/1/mailto", method="POST",
                          body=json.dumps({"email": "unittest@gmail.com", "format": "epub"}))
            self.assertEqual(d["err"], "ok")
            self.assertTrue(m.call_count + self.mail.call_count <= 2)

    def test_push_permission(self):
        with self.mock_convert():
            with mock_permission() as user:
                # forbid
                user.set_permission("P")
                d = self.json("/api/book/1/mailto", method="POST",
                              body=json.dumps({"email": "unittest@gmail.com", "format": "epub"}))
                self.assertEqual(d["err"], "permission")

        with self.mock_convert() as m:
            with mock_permission() as user:
                # allow
                user.set_permission("p")
                d = self.json("/api/book/1/mailto", method="POST",
                              body=json.dumps({"email": "unittest@gmail.com", "format": "epub"}))
                self.assertEqual(d["err"], "ok")
                self.assertTrue(m.call_count + self.mail.call_count <= 2)

    def test_delete(self):
        global _app
        with mock.patch.object(_app.settings["legacy"], "delete_book", return_value="Yo") as m:
            # because 'delete' trigger a refresh
            with mock_permission() as user:
                # default
                d = self.json("/api/book/1/delete", method="POST", body="")
                self.assertEqual(d["err"], "ok")
                self.assertEqual(m.call_count, 1)

            with mock_permission() as user:
                user.set_permission("D")  # forbid
                d = self.json("/api/book/1/delete", method="POST", body="")
                self.assertEqual(d["err"], "permission")
                self.assertEqual(m.call_count, 1)

            with mock_permission() as user:
                user.set_permission("d")  # allow
                d = self.json("/api/book/1/delete", method="POST", body="")
                self.assertEqual(d["err"], "ok")
                self.assertEqual(m.call_count, 2)

    def test_read(self):
        """默认 EPUB_VIEWER=MyReader：MyReader 接管的格式走 /readerx/open，其余走内置阅读器。

        「MyReader 接管哪些格式」= EPUB / PDF / TXT / CBZ / FB2（见
        webserver/handlers/book.py 的 READERX_FORMATS）。以前这里按
        `bid in (BID_EPUB, BID_PDF, BID_TXT)` 硬编码，前提是「BIDS 就只有那 5 本、
        且各自格式固定」。夹具扩到 13 本后这个前提没了（第 6 本也是 EPUB），
        所以改成按每本书真实的 format 判断——判据只有一处，加书不用再改这里。
        """
        readerx_formats = {"EPUB", "PDF", "TXT", "CBZ", "FB2"}
        with mock.patch("webserver.services.converter.ConverterService.convert_and_save", return_value="Yo"):
            for bid in BIDS:
                book = self.json("/api/book/%s" % bid)["book"]
                fmts = {f["format"].upper() for f in book["files"]}
                expect_redirect = bool(fmts & readerx_formats)
                rsp = self.fetch("/read/%s" % bid, follow_redirects=False)
                self.assertEqual(
                    rsp.code, 302 if expect_redirect else 200,
                    "book %s (formats=%s)" % (bid, sorted(fmts)))

    def test_read_txt_redirects_without_conversion(self):
        """TXT-only 书的 /read/<id> 必须直跳专用阅读器，不能先转 EPUB。"""
        with mock.patch.dict(webserver.handlers.book.CONF, {"EPUB_VIEWER": "epubjs.html"}):
            with mock.patch(
                "webserver.services.converter.ConverterService.convert_and_save", return_value="Yo"
            ) as convert:
                for url in ("/read/%s" % BID_TXT, "/read/%s?format=txt" % BID_TXT):
                    rsp = self.fetch(url, follow_redirects=False)
                    self.assertEqual(rsp.code, 302)
                    self.assertEqual(rsp.headers["Location"], "/book/%s/readtxt" % BID_TXT)
                convert.assert_not_called()

    def test_read_txt_escapes_html(self):
        """TXT 正文按纯文本转义后再交给 v-html 渲染。"""
        payload = "<script>alert(1)</script>\n下一行"
        with tempfile.NamedTemporaryFile("wb", suffix=".txt", delete=False) as f:
            f.write(payload.encode("utf-8"))
            path = f.name
        try:
            orig_get_book = BaseHandler.get_book

            def fake_get_book(handler, book_id, *args, **kwargs):
                book = orig_get_book(handler, book_id, *args, **kwargs)
                if book and int(book_id) == BID_TXT:
                    book = dict(book)
                    book["fmt_txt"] = path
                return book

            with mock.patch.object(BaseHandler, "get_book", fake_get_book):
                rsp = self.fetch("/api/read/txt/%s?start=0&end=-1" % BID_TXT)
            data = json.loads(rsp.body)
            self.assertEqual(data["err"], "ok")
            self.assertNotIn("<script>", data["content"])
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", data["content"])
            self.assertIn("下一行", data["content"])
            self.assertIn("<br>", data["content"])
        finally:
            os.remove(path)

    def test_read_myreader_engine_epub(self):
        with mock_permission() as user:
            user.extra["reader_engine"] = "myreader"
            rsp = self.fetch("/read/%s" % BID_EPUB, follow_redirects=False)
            self.assertEqual(rsp.code, 302)
            self.assertEqual(
                rsp.headers["Location"],
                "/readerx/open?bookId=%s&format=epub" % BID_EPUB,
            )

    def test_read_myreader_engine_pdf(self):
        with mock_permission() as user:
            user.extra["reader_engine"] = "myreader"
            rsp = self.fetch("/read/%s" % BID_PDF, follow_redirects=False)
            self.assertEqual(rsp.code, 302)
            self.assertEqual(
                rsp.headers["Location"],
                "/readerx/open?bookId=%s&format=pdf" % BID_PDF,
            )

    def test_read_myreader_engine_unsupported_format_falls_back(self):
        # mobi/azw3/txt aren't served by the embedded MyReader entry point yet,
        # so users with reader_engine=myreader still go through the existing
        # conversion + built-in reader path for those formats.
        with mock.patch("webserver.services.converter.ConverterService.convert_and_save", return_value="Yo"):
            with mock_permission() as user:
                user.extra["reader_engine"] = "myreader"
                rsp = self.fetch("/read/%s" % BID_MOBI, follow_redirects=False)
                self.assertEqual(rsp.code, 200)

    def test_read_default_engine_is_myreader(self):
        """默认 EPUB_VIEWER 就是 MyReader，所以默认配置下 EPUB 会 302 到 /readerx/open。

        原用例名是 test_read_default_engine_ignores_myreader_redirect，断言 200，
        前提是「默认引擎 = epubjs、只有用户显式选 myreader 才跳转」。默认值改成
        MyReader 之后这个前提没了，用例名和断言一起改。
        """
        rsp = self.fetch("/read/%s" % BID_EPUB, follow_redirects=False)
        self.assertEqual(rsp.code, 302)
        self.assertEqual(
            rsp.headers["Location"],
            "/readerx/open?bookId=%s&format=epub" % BID_EPUB,
        )

    def _mock_djvu_only_book(self, fmt="djvu"):
        """测试库里没有 djvu/cbz 书籍：把 PDF 样书改造成只含该格式的书。

        BookRead.get 走的是 get_book_async（内部经 calibre 线程池取数），
        不是同步的 get_book，所以这里必须 patch 前者——patch 后者会「什么都没改」，
        测试看到的是原书的 fmt_pdf，于是 CBZ 用例跳到了 PDF 阅读器。
        """
        orig_get_book_async = BaseHandler.get_book_async

        async def fake_get_book_async(handler, book_id, *args, **kwargs):
            book = await orig_get_book_async(handler, book_id, *args, **kwargs)
            if book and int(book_id) == BID_PDF:
                book = dict(book)
                book["fmt_%s" % fmt] = book.pop("fmt_pdf")
            return book

        return mock.patch.object(BaseHandler, "get_book_async", fake_get_book_async)

    def test_read_djvu(self):
        with self._mock_djvu_only_book():
            for url in ("/read/%s" % BID_PDF, "/read/%s?format=djvu" % BID_PDF):
                rsp = self.fetch(url, follow_redirects=False)
                self.assertEqual(rsp.code, 302)
                location = rsp.headers["Location"]
                self.assertTrue(location.startswith("/static/djvureader/index.html?file="), location)
                self.assertIn(urllib.parse.quote_plus("/api/book/%s.djvu" % BID_PDF), location)

            d = self.json("/api/book/%s/read" % BID_PDF, method="POST", body=json.dumps({"format": "djvu"}))
            self.assertEqual(d["err"], "ok")
            self.assertEqual(d["data"]["status"], "ready")

    def test_read_cbz_with_myreader(self):
        with self._mock_djvu_only_book("cbz"), mock.patch.dict(webserver.handlers.book.CONF, {"EPUB_VIEWER": "MyReader"}):
            rsp = self.fetch("/read/%s?format=cbz" % BID_PDF, follow_redirects=False)
            self.assertEqual(rsp.code, 302)
            self.assertEqual(rsp.headers["Location"], "/readerx/open?bookId=%s&format=cbz" % BID_PDF)
            d = self.json("/api/book/%s/read" % BID_PDF, method="POST", body=json.dumps({"format": "cbz"}))
            self.assertEqual(d["err"], "ok")
            self.assertEqual(d["data"]["status"], "ready")

    def test_read_cbz_without_myreader(self):
        with self._mock_djvu_only_book("cbz"), mock.patch.dict(webserver.handlers.book.CONF, {"EPUB_VIEWER": "epubjs.html"}):
            d = self.json("/api/book/%s/read" % BID_PDF, method="POST", body=json.dumps({"format": "cbz"}))
            self.assertEqual(d["err"], "params.book.invalid")

    def test_edit(self):
        body = {
            "id": 5,
            "title": "老人与海",
            "rating": 8,
            "count_visit": 4,
            "count_download": 1,
            "timestamp": "2022-01-20",
            "pubdate": "1999-10-01",
            "collector": "admin",
            "authors": ["海明威"],
            "author": "海明威",
            "tags": ["海明威", "老人与海", "外国文学", "经典", "励志", "小说", "名著", "美国"],
            "author_sort": "海明威",
            "publisher": "上海译文出版社",
            "comments": "本书讲述了一个渔夫的故事。古巴老渔夫圣地亚哥在连续八十四天没捕到鱼的情况下。",
            "series": "x",
            "language": None,
            "isbn": "9787532723447",
            "is_public": True,
            "is_owner": True,
        }
        with mock.patch.object(_app.settings["legacy"], "set_metadata", return_value="Yo"):
            r = self.json("/api/book/1/edit", method="POST", raise_error=True, body=json.dumps(body))
            self.assertEqual(r["err"], "ok")

    def test_batch_remove_favorite(self):
        for bid in (1, 2):
            r = self.json("/api/book/%d/favorite" % bid, method="POST", body=json.dumps({"favorite": True}))
            self.assertEqual(r["err"], "ok")

        r = self.json("/api/favorites")
        self.assertEqual(r["err"], "ok")
        self.assertEqual(sorted(b["id"] for b in r["books"]), [1, 2])

        r = self.json("/api/books/batch-remove-state", method="POST", body=json.dumps({"book_ids": [1, 2], "action": "favorite"}))
        self.assertEqual(r["err"], "ok")
        self.assertEqual(r["count"], 2)

        r = self.json("/api/favorites")
        self.assertEqual(r["books"], [])

    def test_batch_remove_state_invalid_params(self):
        r = self.json("/api/books/batch-remove-state", method="POST", body=json.dumps({"book_ids": [1], "action": "bogus"}))
        self.assertEqual(r["err"], "params.invalid")

        r = self.json("/api/books/batch-remove-state", method="POST", body=json.dumps({"book_ids": [], "action": "favorite"}))
        self.assertEqual(r["err"], "params.invalid")


class TestSendToMailLastRecipient(TestWithUserLogin):
    """分享到邮箱：入队推送后按用户记住上次收件人（Reader.extra.last_share_email）"""

    def setUp(self):
        super().setUp()
        # 清底：负向断言（key 不存在）不依赖用例字母序的执行运气
        user = get_db().query(models.Reader).filter(models.Reader.id == 1).first()
        if user and user.extra and "last_share_email" in user.extra:
            del user.extra["last_share_email"]
            get_db().commit()

    def test_mailto_saves_last_email(self):
        d = self.json(
            "/api/book/1/mailto", method="POST",
            body=json.dumps({"email": "reader@example.com", "format": "epub"}),
        )
        self.assertEqual(d["err"], "ok")
        user = get_db().query(models.Reader).filter(models.Reader.id == 1).first()
        self.assertEqual((user.extra or {}).get("last_share_email"), "reader@example.com")
        d = self.json("/api/user/info")
        self.assertEqual(d["user"]["last_share_email"], "reader@example.com")

    def test_mailto_invalid_email_not_saved(self):
        d = self.json(
            "/api/book/1/mailto", method="POST",
            body=json.dumps({"email": "bad-email", "format": "epub"}),
        )
        self.assertEqual(d["err"], "email.invalid")
        user = get_db().query(models.Reader).filter(models.Reader.id == 1).first()
        self.assertIsNone((user.extra or {}).get("last_share_email"))



class TestRefer(TestWithUserLogin):
    @mock.patch("webserver.plugins.meta.baike.BaiduBaikeApi._metadata")
    @mock.patch("webserver.plugins.meta.baike.BaiduBaikeApi.get_cover")
    @mock.patch("webserver.plugins.meta.youshu.YoushuApi._youshu")
    def test_refer(self, m3, m2, m1):
        from tests.test_baike import BAIKE_PAGE
        from tests.test_youshu import YOUSHU_PAGE

        m1.return_value = YOUSHU_PAGE
        m2.return_value = ("jpg", b"image-body")
        m3.return_value = BAIKE_PAGE

        d = self.json("/api/book/1/refer")
        self.assertEqual(d["err"], "ok")

        global _app
        with mock.patch.object(_app.settings["legacy"], "set_metadata", return_value="Yo"):
            for book in d["books"]:
                body = "provider_key=%(provider_key)s&provider_value=%(provider_value)s" % book
                r = self.json("/api/book/1/refer", method="POST", raise_error=True, body=body)
                self.assertEqual(r["err"], "ok")


class TestUserSignUp(TestWithUserLogin):
    @classmethod
    def setUpClass(self):
        self.user = _mock_user.start()
        self.user.return_value = 1
        self.mail = _mock_mail.start()
        self.mail.return_value = True
        self.async_service = _mock_service_async_mode.start()
        self.async_service.return_value = False

    @classmethod
    def tearDownClass(self):
        # 父类的 stop() 一个都不能少：原先只停了 mail，user / async_mode 的
        # patch 会泄漏到后面的测试类，下一个 TestWithAdminUser.setUpClass
        # 再 start 同一个 patcher 就报 RuntimeError: Patch is already started。
        super().tearDownClass()
        self.delete_user()

    @classmethod
    def get_user(self):
        return get_db().query(models.Reader).filter(models.Reader.username == "unittest")

    @classmethod
    def delete_user(self):
        self.get_user().delete()
        get_db().commit()

    def test_signup(self):
        self.delete_user()
        self.mail.reset_mock()

        d = self.json("/api/user/sign_up", method="POST", raise_error=True, body="")
        self.assertEqual(d["err"], "params.invalid")

        body = ("email=unittest@gmail.com&nickname=unittest&username=unittest"
                "&password=Unittest66&birth_year=1990")
        d = self.json("/api/user/sign_up", method="POST", raise_error=True, body=body)
        self.assertEqual(d["err"], "ok")
        self.assertEqual(self.mail.call_count, 1)

        user = self.get_user().first()
        self.assertEqual(user.name, "unittest")
        self.assertEqual(user.email, "unittest@gmail.com")
        self.assertEqual(user.active, False)

        code = "123456"
        rsp = self.fetch("/api/active/%s/%s" % ("unittest", code))
        self.assertEqual(rsp.code, 403)

        code = user.get_active_code()
        rsp = self.fetch("/api/active/%s/%s" % ("unittest", code), follow_redirects=False)
        self.assertEqual(rsp.code, 302)
        user = self.get_user().first()
        self.assertEqual(user.active, True)

        self.user.return_value = user.id
        d = self.json("/api/user/active/send")
        self.assertEqual(d["err"], "ok")
        self.assertEqual(self.mail.call_count, 2)

        # build fake auth header unittest:unittest
        f = FakeHandler()
        f.request.headers["Authorization"] = "xxxxx"
        self.assertEqual(False, BaseHandler.process_auth_header(f))

        f.request.headers["Authorization"] = self.auth("username:password")
        self.assertEqual(False, BaseHandler.process_auth_header(f))

        f.request.headers["Authorization"] = self.auth("unittest:password")
        self.assertEqual(False, BaseHandler.process_auth_header(f))

        ts = int(time.time())
        f.request.headers["Authorization"] = self.auth("unittest:Unittest66")
        self.assertEqual(True, BaseHandler.process_auth_header(f))
        self.assertTrue(int(f.cookie["invited"]) >= ts)
        self.assertTrue(int(f.cookie["lt"]) >= ts)
        self.assertTrue(int(f.cookie["lt"]) >= ts)

        self.delete_user()

    def auth(self, s):
        return "Basic " + base64.encodebytes(s.encode("ascii")).decode("ascii")

class TestWithAdminUser(TestApp):
    @classmethod
    def setUpClass(self):
        self.user = _mock_user.start()
        self.user.return_value = 1

    @classmethod
    def tearDownClass(self):
        _mock_user.stop()


class TestAdmin(TestWithAdminUser):
    def test_admin_users(self):
        d = self.json("/api/admin/users")
        self.assertEqual(d["err"], "ok")
        self.assertEqual(d["users"]["total"], 31)

    def test_admin_settings(self):
        d = self.json("/api/admin/settings")
        self.assertEqual(d["err"], "ok")
        self.assertTrue(len(d["settings"]) > 10)

        with mock.patch.object(loader.SettingsLoader, "set_store_path", return_value="/tmp/"):
            req = {"site_title": "abc", "not_work": "en"}
            d = self.json("/api/admin/settings", method="POST", body=json.dumps(req))
            self.assertEqual(d["err"], "ok")
            self.assertEqual(d["rsp"]["site_title"], "abc")
            self.assertTrue("not_work" not in d["rsp"])


class TestOpds(TestWithUserLogin):
    def parse_xml(self, text):
        from xml.parsers.expat import ParserCreate

        ParserCreate()

    def test_opds(self):
        rsp = self.fetch("/opds/")
        self.assertEqual(rsp.code, 200)
        self.parse_xml(rsp.body)

    def test_opds_nav(self):
        rsp = self.fetch("/opds/nav/4e617574686f7273?offset=1")
        self.assertEqual(rsp.code, 200)
        self.parse_xml(rsp.body)

    def test_opds_nav2(self):
        main.CONF["opds_max_ungrouped_items"] = 2
        navs = [
                b'Nauthors',
                b'Nlanguages',
                b'Npublisher',
                b'Nrating',
                b'Nseries',
                b'Ntags',
                b'Onewest',
                b'Otitle',
        ]
        groups = [
            2,
            main.CONF["opds_max_ungrouped_items"],
        ]
        for nav in navs:
            url = "/opds/nav/%s" % nav.hex()
            for g in groups:
                main.CONF["opds_max_ungrouped_items"] = g
                rsp = self.fetch(url)
                self.assertEqual(rsp.code, 200)
                self.parse_xml(rsp.body)

    def test_opds_category(self):
        a = b'tags'.hex()
        b = b'I71:tags'.hex()
        rsp = self.fetch("/opds/category/%s/%s" % (a,b))
        self.assertEqual(rsp.code, 200)
        self.parse_xml(rsp.body)

    @unittest.skip("category里的search功能暂时搞不懂，以后考虑删掉")
    def test_opds_category_search(self):
        b = ("I"+urllib.parse.quote("韩寒")+":authors").encode("UTF-8").hex()
        a = b"search".hex()
        b = b'I5:authors'.hex()
        b = "I文学:tags".encode("UTF-8").hex()
        rsp = self.fetch("/opds/category/%s/%s" % (a, b))
        self.assertEqual(rsp.code, 200, rsp.body)
        self.parse_xml(rsp.body)

    def test_opds_category_group(self):
        a = b'tags'.hex()
        b = b'C'.hex()
        rsp = self.fetch("/opds/categorygroup/%s/%s" % (a,b))
        self.assertEqual(rsp.code, 200)
        self.parse_xml(rsp.body)

    def test_opds_search(self):
        rsp = self.fetch("/opds/search/%s" % urllib.parse.quote("韩寒"))
        self.assertEqual(rsp.code, 200)
        self.parse_xml(rsp.body)

    def test_opds_search_not_found(self):
        rsp = self.fetch("/opds/search/%s" % urllib.parse.quote("豪士"))
        self.assertEqual(rsp.code, 404)

    def test_opds_without_login(self):
        main.CONF["INVITE_MODE"] = True
        rsp = self.fetch("/opds/nav/%s" % b'Otitle'.hex())
        self.assertEqual(rsp.code, 401)
        main.CONF["INVITE_MODE"] = False


class TestJsonResponse(TestApp):
    def raise_(self, err):
        raise err

    def assertHeaders(self, headers):
        """没有 Origin 请求头时不该发任何 CORS 响应头。

        原断言要求恒发 `Access-Control-Allow-Origin: *` + `Allow-Credentials: true`，
        那是「任意网页都能带着用户 Cookie 读本站 API」的经典配置。现在的实现只对
        同源 Origin 回显，跨站一律不发，所以无 Origin 的请求只剩 Cache-Control。
        """
        self.assertEqual(headers, {"Cache-Control": "max-age=0"})

    def test_cors_headers_only_for_same_origin(self):
        """同源发头、跨源不发——这是上面那条断言的另一半，缺了就等于没测。"""
        from webserver.handlers.base import BaseHandler

        def run(origin, host):
            f = FakeHandler()
            f.request.headers = {"origin": origin} if origin else {}
            f.request.host = host
            with mock.patch("traceback.format_exc", return_value=""):
                handler = webserver.handlers.base.js(lambda x: {"ok": True})
                asyncio.get_event_loop().run_until_complete(handler(f))
            return f.rsp_headers

        same = run("http://example.com", "example.com")
        self.assertEqual(same["Access-Control-Allow-Origin"], "http://example.com")
        self.assertEqual(same["Access-Control-Allow-Credentials"], "true")

        evil = run("http://evil.com", "example.com")
        self.assertNotIn("Access-Control-Allow-Origin", evil)
        self.assertNotIn("Access-Control-Allow-Credentials", evil)

    @testing.gen_test
    async def test_err(self):
        f = FakeHandler()
        with mock.patch("traceback.format_exc", return_value=""):
            handler = webserver.handlers.base.js(lambda x: self.raise_(RuntimeError()))
            await handler(f)
        self.assertTrue(isinstance(f.rsp["msg"], str))
        self.assertEqual(f.rsp["err"], "exception")
        self.assertHeaders(f.rsp_headers)

    @testing.gen_test
    async def test_finish(self):
        f = FakeHandler()
        with mock.patch("traceback.format_exc", return_value=""):
            handler = webserver.handlers.base.js(lambda x: self.raise_(web.Finish()))
            await handler(f)
        self.assertEqual(f.rsp, "")
        self.assertHeaders(f.rsp_headers)


class TestInviteMode(TestApp):
    def setUp(self):
        main.CONF["INVITE_MODE"] = True
        TestApp.setUp(self)

    def tearDown(self):
        main.CONF["INVITE_MODE"] = False
        TestApp.tearDown(self)

    def test_index(self):
        d = self.json("/api/index")
        self.assertEqual(d["err"], "not_invited")

        d = self.json("/api/book/1")
        self.assertEqual(d["err"], "not_invited")

        r = self.fetch("/api/book/1.epub")
        self.assertEqual(r.code, 401)

    def test_opds_index(self):
        r = self.fetch("/opds/")
        self.assertEqual(r.code, 401)

        r = self.fetch("/opds/nav/4e617574686f7273?offset=1")
        self.assertEqual(r.code, 401)


def setUpModule():
    os.environ["ASYNC_TEST_TIMEOUT"] = "60"
    setup_server()
    setup_mock_user()
    setup_mock_sendmail()
    setup_mock_service()
    setup_mock_bookbarn()
    setup_mock_trash_manager()


if __name__ == "__main__":
    '''
    logging.basicConfig(
        level=logging.DEBUG,
        datefmt="%Y-%m-%d %H:%M:%S",
        filename="/data/log/unittest.log",
        format="%(asctime)s %(levelname)7s %(pathname)s:%(lineno)d %(message)s",
    )'''
    unittest.main()
