#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_mybooks_api.py -- mybooks_api.py integration tests

Calls mybooks_api.py via subprocess for every tool and verifies:
  - The script completes without crashing (returns valid JSON)
  - Required-parameter checks fire correctly
  - Live APIs return err=ok (or an acceptable non-crash error)

Built-in defaults (override with env vars):
  MYBOOKS_HOST      http://127.0.0.1:8082
  MYBOOKS_USER      admin
  MYBOOKS_PASSWORD  123456
  MYBOOKS_TEST_EMAIL     (optional, enables mailto test)
  MYBOOKS_TEST_BOOK_ID   (optional, pin a specific book id)
"""

import json
import os
import subprocess
import unittest

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
HOST     = os.environ.get("MYBOOKS_HOST",     "http://127.0.0.1:8082")
USER     = os.environ.get("MYBOOKS_USER",     "admin")
PASSWORD = os.environ.get("MYBOOKS_PASSWORD", "123456")
TEST_EMAIL   = os.environ.get("MYBOOKS_TEST_EMAIL", "")
TEST_BOOK_ID = int(os.environ.get("MYBOOKS_TEST_BOOK_ID", "1004") or "979")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
API_SCRIPT = os.path.join(SCRIPT_DIR, "..", "skills", "mybooks", "scripts", "mybooks_api.py")
CASES_DIR  = os.path.join(SCRIPT_DIR, "cases")

# Will be populated in setUpModule
_book_id = TEST_BOOK_ID

# 探活结果由 Base.setUp 首次执行时填入（基类定义在下面的 Base 里）
_server_probe = {"ok": None, "note": None}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def call(tool: str, args: dict = None, timeout: int = 30) -> dict:
    """Run mybooks_api.py <tool> <json-args> and return parsed JSON response."""
    env = os.environ.copy()
    env["MYBOOKS_HOST"]     = HOST
    env["MYBOOKS_USER"]     = USER
    env["MYBOOKS_PASSWORD"] = PASSWORD
    cmd = ["python3", API_SCRIPT, tool, json.dumps(args or {})]
    print(cmd)
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)
    raw = r.stdout.strip() or r.stderr.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw, "_returncode": r.returncode}


def _server_unreachable(resp: dict) -> bool:
    """`mybooks_api.py` 这次调用是不是「根本没连上服务器」。

    这个测试文件测的是**真起一台 mybooks 服务（默认 127.0.0.1:8082）时的
    端到端行为**，它和 tests/ 下其它用例不一样：不建 app、不 mock、直接
    `subprocess` 跑 CLI 脚本，脚本自己去 POST /api/user/sign_in。
    没有服务在监听时，所有工具都会在登录这一步挂掉，返回
    `{"status": "error", "message": "Login failed: HTTPConnectionPool(...) Connection refused"}`。

    这种失败**不是被测代码的缺陷**，所以整组用例按「环境缺依赖」skip，
    而不是报 32 个红。想跑它们：

        python3 -m webserver.main --with-library <库> --port 8082 &
        MYBOOKS_PASSWORD=<密码> ./scripts/test-integration.sh tests/test_talebook_api.py
    """
    message = str(resp.get("message") or resp.get("_raw") or "")
    return resp.get("status") == "error" and (
        "Connection refused" in message
        or "Max retries exceeded" in message
        or "Failed to establish a new connection" in message
    )


def setUpModule():
    """Discover a usable book_id (1-20) before the test suite runs."""
    global _book_id
    if _book_id:
        print(f"\n[setup] Using pinned book_id={_book_id}")
        return
    for bid in range(1, 21):
        try:
            d = call("get_book", {"book_id": bid})
            if d.get("err") == "ok":
                _book_id = bid
                title = d.get("book", {}).get("title", "?")
                print(f"\n[setup] Found book_id={bid} title={title!r}")
                return
        except Exception:
            pass
    print("\n[setup] No usable book found (id 1-20); book-related tests will be skipped")


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class Base(unittest.TestCase):
    def setUp(self):
        # 服务器不可达时整组跳过（见 `_server_unreachable`）。只能真的发一次
        # 请求来探活：`mybooks_api.py` 是先 sign_in 再校验参数，没有「不登录
        # 也能跑完」的工具。结果缓存在模块级字典里，避免每个用例都白等
        # 一次连接超时。
        if _server_probe["ok"] is None:
            resp = call("get_book", {"book_id": 1})
            _server_probe["ok"] = not _server_unreachable(resp)
            _server_probe["note"] = resp
        if not _server_probe["ok"]:
            self.skipTest(
                "mybooks 服务不可达（%s），跳过端到端用例：%s"
                % (HOST, str(_server_probe["note"])[:200])
            )

    def assertJson(self, resp, desc=""):
        self.assertNotIn("_raw", resp,
            f"{desc} -- script returned non-JSON: {str(resp.get('_raw',''))[:300]}")

    def assertOk(self, resp, desc=""):
        self.assertJson(resp, desc)
        self.assertEqual("ok", resp.get("err"),
            f"{desc} -- expected err=ok, got {resp.get('err')} | {resp}")

    def assertParamError(self, resp, param, desc=""):
        text = json.dumps(resp)
        self.assertIn(param, text,
            f"{desc} -- expected error mentioning {param!r}, got: {text[:300]}")


# ---------------------------------------------------------------------------
# 1. Environment variable validation (no server needed)
# ---------------------------------------------------------------------------

class TestEnvValidation(Base):
    def _run_bare(self, host="", user="", password=""):
        env = os.environ.copy()
        env["MYBOOKS_HOST"]     = host
        env["MYBOOKS_USER"]     = user
        env["MYBOOKS_PASSWORD"] = password
        r = subprocess.run(
            ["python3", API_SCRIPT, "get_user_info", "{}"],
            capture_output=True, text=True, env=env, timeout=10)
        return r.stdout + r.stderr

    def test_missing_host(self):
        out = self._run_bare(host="", user="u", password="p")
        self.assertIn("MYBOOKS_HOST", out)

    def test_missing_credentials(self):
        out = self._run_bare(host="http://localhost", user="", password="")
        self.assertTrue("MYBOOKS_USER" in out or "MYBOOKS_PASSWORD" in out,
            f"Expected credential error, got: {out[:200]}")


# ---------------------------------------------------------------------------
# 2. Required-parameter validation (no server needed)
# ---------------------------------------------------------------------------

class TestParamValidation(Base):
    def test_get_book_no_id(self):
        self.assertParamError(call("get_book", {}), "book_id")

    def test_edit_book_no_id(self):
        self.assertParamError(call("edit_book", {}), "book_id")

    def test_mailto_no_email(self):
        self.assertParamError(call("mailto", {"book_id": 1}), "email")

    def test_mailto_no_book_id(self):
        self.assertParamError(call("mailto", {"email": "a@b.com"}), "book_id")

    def test_book_fill_no_idlist(self):
        self.assertParamError(call("book_fill", {}), "idlist")

    def test_book_upload_no_path(self):
        self.assertParamError(call("book_upload", {}), "file_path")

    def test_book_upload_missing_file(self):
        resp = call("book_upload", {"file_path": "/tmp/_mybooks_no_such_file_.epub"})
        text = json.dumps(resp).lower()
        self.assertIn("not found", text,
            f"Expected 'not found' error, got: {text[:200]}")

    def test_send_to_device_no_id(self):
        self.assertParamError(call("send_to_device", {}), "book_id")

    def test_book_add_by_isbn_no_isbn(self):
        self.assertParamError(call("book_add_by_isbn", {}), "isbn")

    def test_wants_no_id(self):
        self.assertParamError(call("wants", {}), "book_id")

    def test_favorite_no_id(self):
        self.assertParamError(call("favorite", {}), "book_id")

    def test_reading_no_id(self):
        self.assertParamError(call("reading", {}), "book_id")

    def test_read_done_no_id(self):
        self.assertParamError(call("read_done", {}), "book_id")

    def test_unknown_tool(self):
        resp = call("_no_such_tool_xyz_")
        self.assertIn("Unknown tool", json.dumps(resp))


# ---------------------------------------------------------------------------
# 3. User & stats
# ---------------------------------------------------------------------------

class TestUserAndStats(Base):
    def test_get_user_info(self):
        resp = call("get_user_info", {})
        self.assertOk(resp, "get_user_info")
        self.assertIn("user", resp)

    def test_library_stats(self):
        resp = call("library_stats", {})
        self.assertOk(resp, "library_stats")
        self.assertIn("stats", resp)

    def test_reading_stats(self):
        resp = call("reading_stats", {})
        self.assertOk(resp, "reading_stats")
        self.assertIn("stats", resp)


# ---------------------------------------------------------------------------
# 4. Categories & authors
# ---------------------------------------------------------------------------

class TestCategoriesAndAuthors(Base):
    def test_categories(self):
        resp = call("categories", {})
        self.assertOk(resp, "categories")

    def test_get_author_books(self):
        if not _book_id:
            self.skipTest("no usable book_id")
        book = call("get_book", {"book_id": _book_id})
        authors = book.get("book", {}).get("authors", [])
        if not authors:
            self.skipTest("book has no authors")
        resp = call("get_author_books", {"author_name": authors[0]})
        self.assertOk(resp, f"get_author_books({authors[0]!r})")
        self.assertIn("books", resp)


# ---------------------------------------------------------------------------
# 5. Search
# ---------------------------------------------------------------------------

class TestSearch(Base):
    ACCEPTABLE = {"ok", "params.invalid"}

    def _check(self, resp, desc):
        self.assertJson(resp, desc)
        self.assertIn(resp.get("err"), self.ACCEPTABLE,
            f"{desc}: err={resp.get('err')!r} not in {self.ACCEPTABLE}")

    def test_search_keyword(self):
        self._check(call("search_books", {"name": "test"}), "search_books")

    def test_search_pagination(self):
        self._check(call("search_books", {"name": "the", "num": 5, "page": 1}),
                    "search_books pagination")

    def test_search_by_category(self):
        self._check(call("search_by_category", {"category": "fiction"}),
                    "search_by_category")


# ---------------------------------------------------------------------------
# 6. Book detail
# ---------------------------------------------------------------------------

class TestBookDetail(Base):
    def test_get_book(self):
        if not _book_id:
            self.skipTest("no usable book_id")
        resp = call("get_book", {"book_id": _book_id})
        self.assertOk(resp, "get_book")
        self.assertIn("book", resp)


# ---------------------------------------------------------------------------
# 7. Edit book metadata (write -> verify -> restore)
# ---------------------------------------------------------------------------

class TestEditBook(Base):
    def setUp(self):
        super().setUp()  # 先做服务器探活，不可达时整组 skip
        if not _book_id:
            self.skipTest("no usable book_id")
        self._book = call("get_book", {"book_id": _book_id})
        if self._book.get("err") != "ok":
            self.skipTest(f"get_book failed: {self._book}")

    def test_edit_tags_roundtrip(self):
        orig = self._book["book"].get("tags", [])
        marker = f"ci_test_{os.getpid()}"
        resp = call("edit_book", {"book_id": _book_id, "tags": orig + [marker]})
        self.assertOk(resp, "edit_book write")

        check = call("get_book", {"book_id": _book_id})
        self.assertIn(marker, check.get("book", {}).get("tags", []),
            "tag should persist after edit_book")

        restore = call("edit_book", {"book_id": _book_id, "tags": orig})
        self.assertOk(restore, "edit_book restore")

    def test_edit_category(self):
        orig = self._book["book"].get("category", "")
        resp = call("edit_book", {"book_id": _book_id, "category": f"ci_cat_{os.getpid()}"})
        self.assertOk(resp, "edit_book category")
        call("edit_book", {"book_id": _book_id, "category": orig or "clear"})


# ---------------------------------------------------------------------------
# 8. Reading state
# ---------------------------------------------------------------------------

class TestReadingState(Base):
    def setUp(self):
        super().setUp()  # 先做服务器探活，不可达时整组 skip
        if not _book_id:
            self.skipTest("no usable book_id")
        self._orig = (
            call("get_book", {"book_id": _book_id})
            .get("book", {}).get("state", {}).get("read_state", 0)
        )

    def tearDown(self):
        if _book_id:
            call("reading", {"book_id": _book_id, "read_state": self._orig})

    def test_mark_reading(self):
        resp = call("reading", {"book_id": _book_id, "read_state": 1})
        self.assertOk(resp, "reading state=1")

    def test_list_reading(self):
        call("reading", {"book_id": _book_id, "read_state": 1})
        resp = call("list_reading", {})
        self.assertOk(resp, "list_reading")
        self.assertIn("books", resp)

    def test_read_done(self):
        resp = call("read_done", {"book_id": _book_id})
        self.assertOk(resp, "read_done")

    def test_list_read_done(self):
        call("read_done", {"book_id": _book_id})
        resp = call("list_read_done", {})
        self.assertOk(resp, "list_read_done")
        self.assertIn("books", resp)


# ---------------------------------------------------------------------------
# 9. Wants & favorites
# ---------------------------------------------------------------------------

class TestWantsAndFavorites(Base):
    def setUp(self):
        super().setUp()  # 先做服务器探活，不可达时整组 skip
        if not _book_id:
            self.skipTest("no usable book_id")
        state = (
            call("get_book", {"book_id": _book_id})
            .get("book", {}).get("state", {})
        )
        self._orig_wants = state.get("wants", False)
        self._orig_fav   = state.get("favorite", False)

    def tearDown(self):
        if _book_id:
            call("wants",    {"book_id": _book_id, "wants":    self._orig_wants})
            call("favorite", {"book_id": _book_id, "favorite": self._orig_fav})

    def test_wants_true(self):
        self.assertOk(call("wants", {"book_id": _book_id, "wants": True}), "wants=true")

    def test_list_wants(self):
        call("wants", {"book_id": _book_id, "wants": True})
        resp = call("list_wants", {})
        self.assertOk(resp, "list_wants")
        self.assertIn("books", resp)

    def test_favorite_true(self):
        self.assertOk(call("favorite", {"book_id": _book_id, "favorite": True}), "favorite=true")

    def test_list_favorites(self):
        call("favorite", {"book_id": _book_id, "favorite": True})
        resp = call("list_favorites", {})
        self.assertOk(resp, "list_favorites")
        self.assertIn("books", resp)


# ---------------------------------------------------------------------------
# 10. Book upload
# ---------------------------------------------------------------------------

class TestBookUpload(Base):
    def test_upload_epub(self):
        path = os.path.join(CASES_DIR, "new.epub")
        if not os.path.exists(path):
            self.skipTest(f"test fixture missing: {path}")
        resp = call("book_upload", {"file_path": path}, timeout=60)
        self.assertJson(resp, "book_upload")
        self.assertIn(resp.get("err"), {"ok", "samebook", "permission"},
            f"book_upload unexpected err={resp.get('err')!r}: {resp}")


# ---------------------------------------------------------------------------
# 11. Add by ISBN
# ---------------------------------------------------------------------------

class TestBookAddByIsbn(Base):
    def test_add_by_isbn(self):
        # The ISBN lookup may fail (network, douban unavailable), but the
        # script should return valid JSON without crashing.
        resp = call("book_add_by_isbn", {"isbn": "9787020024759"}, timeout=60)
        self.assertJson(resp, "book_add_by_isbn")
        self.assertIn("err", resp, "response must contain 'err' field")


# ---------------------------------------------------------------------------
# 12. Mailto (optional)
# ---------------------------------------------------------------------------

class TestMailTo(Base):
    def test_mailto(self):
        if not TEST_EMAIL:
            self.skipTest("MYBOOKS_TEST_EMAIL not set")
        if not _book_id:
            self.skipTest("no usable book_id")
        resp = call("mailto", {"book_id": _book_id, "email": TEST_EMAIL})
        self.assertJson(resp, "mailto")
        self.assertIn(resp.get("err"), {"ok", "push.not_set", "permission"},
            f"mailto err={resp.get('err')!r}: {resp}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Host:   {HOST}")
    print(f"User:   {USER}")
    print(f"Script: {API_SCRIPT}")
    print()
    unittest.main(verbosity=2)
