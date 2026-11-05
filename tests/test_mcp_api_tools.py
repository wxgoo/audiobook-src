#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""MCP skill-aligned tools: parity with skills/mybooks and loopback HTTP calls."""

import asyncio
import json
import os
import re
import types
import unittest

import tornado.web
from tornado.options import options, define
from tornado.testing import AsyncHTTPTestCase, gen_test

from webserver.mcp.api_tools import API_TOOLS
from webserver.mcp.mcp_service import MCPService

SKILL_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "skills", "mybooks", "scripts", "mybooks_api.py")
# 读写调用方本地文件的 skill 工具，MCP 上会变成读写服务器文件，刻意不暴露
MCP_EXCLUDED = {"book_upload", "tts_clone_upload", "tts_clone_audio"}
# skill 里有、MCP 尚未实现（book345 抓取类 + 批量维护类）。
# 这不是「测试写错了」，而是真实的已知差距：这些工具依赖 book345.com 的
# 网页结构（wuming_*）或需要跨多本书记账（library_enrich / library_audit /
# batch_edit / authors_normalize），照搬成 MCP 服务端工具要先解决鉴权与
# 幂等，工作量远大于一个 handler。这里显式登记，目的是让差距**可见**：
# 以后补实现了谁，就必须从这份名单里删掉，否则 parity 测试会红——
# 它防的就是「悄悄漏掉某个工具」这种漂移。
SKILL_ONLY_TOOLS = {
    "wuming_search", "wuming_toplist", "wuming_recent_hot",
    "wuming_detail", "wuming_guide", "wuming_tags",
    "library_audit", "library_research", "library_research_todo",
    "library_enrich", "library_enrich_apply",
    "batch_edit", "authors_normalize", "book_add_from_wuming",
}
# 会话/凭据管理，不属于「书库 API」，本来就不该出现在 API_TOOLS 里
SKILL_NON_API_TOOLS = {"sign_in"} | MCP_EXCLUDED


def skill_tool_names():
    """skill 脚本真正实现的工具名集合。

    不能用 `re.search(r"available_tools = \\[(.*?)\\]")`：那段是
    `execute_tool()` 里「未知工具」报错文案拼出来的**字符串列表**，
    只覆盖了一部分工具（wuming_*、library_*、batch_edit 等在别处注册），
    拿它当工具全集做 parity 比对必然差一堆。

    真实注册方式有两种，都要算：
    ①`AUTH_FREE_TOOLS = {...}` 字典（book345 免登录那几个）；
    ②`MyBooksAPI` 类上以 `_tool_` 前缀之外的名字存在的方法。
    这里用 AST 静态解析，不 import 那个脚本（它 import 时就会去读环境变量）。
    """
    import ast

    tree = ast.parse(open(SKILL_SCRIPT, encoding="utf-8").read())
    names = set()
    for node in ast.walk(tree):
        # ① AUTH_FREE_TOOLS 字典的键
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "AUTH_FREE_TOOLS" for t in node.targets
        ):
            if isinstance(node.value, ast.Dict):
                for key in node.value.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        names.add(key.value)
        # ② execute_tool 通过 getattr(self, tool_name) 分发的公开方法
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name.startswith("_") or item.name in ("execute_tool", "main"):
                        continue
                    names.add(item.name)
    return names


class TestToolParity(unittest.TestCase):
    def test_same_tools_as_skill(self):
        """MCP 工具集 = skill 工具集 − 会话工具 − 目录上传类 − 已知未实现。

        两边**双向**都要比对：多一个说明 MCP 暴露了 skill 没有的东西（调用方
        拿到会 404），少一个说明漏实现了（见 SKILL_ONLY_TOOLS 的说明）。
        """
        skill = skill_tool_names() - SKILL_NON_API_TOOLS - SKILL_ONLY_TOOLS
        mcp = set(API_TOOLS)
        self.assertEqual(skill - mcp, set(), "skill 有、MCP 没有（漏实现或没登记）")
        self.assertEqual(mcp - skill, set(), "MCP 有、skill 没有（调用方会拿到 404）")

    def test_known_gap_list_has_no_stale_entries(self):
        """SKILL_ONLY_TOOLS 里的名字必须仍真实存在于 skill 脚本。

        否则说明那个工具被改名/删掉了，而名单没同步——留着会让
        test_same_tools_as_skill 悄悄放过一个真正缺失的工具。
        """
        names = skill_tool_names()
        stale = SKILL_ONLY_TOOLS - names
        self.assertEqual(stale, set(), "名单里有已不存在的工具：%s" % sorted(stale))
        # 补实现的工具必须从名单里删掉，不能两头都有
        self.assertEqual(SKILL_ONLY_TOOLS & set(API_TOOLS), set(),
                         "这些工具 MCP 已实现，应从 SKILL_ONLY_TOOLS 移除")

    def test_schema_required_fields_exist(self):
        for t in API_TOOLS.values():
            for name in t.required:
                self.assertIn(name, t.properties, t.name)


class TestToolRequests(unittest.TestCase):
    def run_tool(self, name, args):
        calls = []

        async def call(method, path, params=None, json=None):
            calls.append((method, path, params, json))
            return {"err": "ok", "books": [{"id": 7}]}

        result = asyncio.run(API_TOOLS[name].func(call, args))
        return result, calls

    def test_search_books_fields(self):
        _, calls = self.run_tool("search_books", {"author": "余华", "exact": True, "page": 2, "num": 10})
        self.assertEqual(calls, [("GET", "/api/search", {"num": 10, "start": 10, "author": "余华", "exact": 1}, None)])

    def test_search_books_requires_condition(self):
        result, calls = self.run_tool("search_books", {})
        self.assertEqual(result["err"], "params.invalid")
        self.assertEqual(calls, [])

    def test_delete_requires_confirm(self):
        result, calls = self.run_tool("delete_booklist", {"booklist_id": 3})
        self.assertEqual(result["err"], "confirm.required")
        self.assertEqual([c[0] for c in calls], ["GET"])

    def test_refer_search_sends_only_given_conditions(self):
        _, calls = self.run_tool("book_refer_search", {"book_id": 42, "isbn": "9787536692930"})
        self.assertEqual(calls, [("GET", "/api/book/42/refer", {"isbn": "9787536692930"}, None)])

        _, calls = self.run_tool("book_refer_search", {"book_id": 42})
        self.assertEqual(calls, [("GET", "/api/book/42/refer", {}, None)])

    def test_refer_apply_modes(self):
        # 表单参数走 query 串（handler 用 get_argument，读不到 JSON body），三种模式各自一个 flag
        for mode, flag in (("only_meta", "only_meta"), ("only_cover", "only_cover"),
                           ("only_author_comments", "only_author_comments")):
            _, calls = self.run_tool("book_refer_apply",
                                     {"book_id": 42, "provider_key": "douban", "provider_value": "2567698", "mode": mode})
            self.assertEqual(calls, [("POST", "/api/book/42/refer",
                                      {"provider_key": "douban", "provider_value": "2567698", flag: "yes"}, None)], mode)

    def test_refer_apply_full_mode_and_metadata(self):
        candidate = {"title": "三体", "cover_url": "https://example.com/c.jpg", "provider_value": "2567698"}
        _, calls = self.run_tool("book_refer_apply",
                                 {"book_id": 42, "provider_key": "neodb", "provider_value": "2567698", "metadata": candidate})
        self.assertEqual(calls, [("POST", "/api/book/42/refer",
                                  {"provider_key": "neodb", "provider_value": "2567698",
                                   "metadata": json.dumps(candidate, ensure_ascii=False)}, None)])

    def test_refer_apply_requires_candidate(self):
        result, calls = self.run_tool("book_refer_apply", {"book_id": 42, "provider_key": "douban"})
        self.assertEqual(result["status"], "error")
        self.assertEqual(calls, [])

        result, calls = self.run_tool("book_refer_apply",
                                      {"book_id": 42, "provider_key": "douban", "provider_value": "1", "mode": "meta"})
        self.assertEqual(result["status"], "error")
        self.assertEqual(calls, [])

    def test_refer_apply_douban_needs_no_metadata(self):
        # 豆瓣源按 provider_value 重新拉取，metadata 可省
        _, calls = self.run_tool("book_refer_apply",
                                 {"book_id": 42, "provider_key": "douban", "provider_value": "2567698"})
        self.assertEqual(calls, [("POST", "/api/book/42/refer", {"provider_key": "douban", "provider_value": "2567698"}, None)])

    def test_refer_apply_metadata_required_for_other_sources(self):
        # 非豆瓣源不带候选时 handler 会退回书自身元数据并返回 ok（静默空操作），因此直接拦下
        result, calls = self.run_tool("book_refer_apply",
                                      {"book_id": 42, "provider_key": "neodb", "provider_value": "2567698"})
        self.assertEqual(result["status"], "error")
        self.assertEqual(calls, [])

    def test_epub_fix_body(self):
        _, calls = self.run_tool("epub_fix", {"book_ids": 42, "backup": True})
        self.assertEqual(calls, [("POST", "/api/toolbox/epub_fixer/repair", None, {"book_ids": [42], "backup": True})])

        _, calls = self.run_tool("epub_fix", {"book_ids": [42, 43]})
        self.assertEqual(calls, [("POST", "/api/toolbox/epub_fixer/repair", None, {"book_ids": [42, 43]})])

    def test_epub_fix_string_booleans(self):
        # handler 对 backup/reconvert 用 bool(...)，字符串 "false" 会变 True —— 必须先归一
        _, calls = self.run_tool("epub_fix", {"book_ids": [42], "backup": "false", "reconvert": "0"})
        self.assertEqual(calls, [("POST", "/api/toolbox/epub_fixer/repair", None, {"book_ids": [42], "backup": False, "reconvert": False})])

        _, calls = self.run_tool("epub_fix", {"book_ids": [42], "backup": "true", "reconvert": "yes"})
        self.assertEqual(calls, [("POST", "/api/toolbox/epub_fixer/repair", None, {"book_ids": [42], "backup": True, "reconvert": True})])

    def test_epub_fix_accepts_single_id_in_schema(self):
        # 宽松客户端会按 schema 校验；单个整数必须合法，否则单本修复在客户端就被挡下
        schema = API_TOOLS["epub_fix"].properties["book_ids"]
        self.assertEqual(schema["oneOf"], [{"type": "integer"}, {"type": "array", "items": {"type": "integer"}}])

    def test_epub_fix_progress(self):
        _, calls = self.run_tool("epub_fix_progress", {})
        self.assertEqual(calls, [("GET", "/api/toolbox/epub_fixer/progress", None, None)])

    def test_legacy_search_args(self):
        args = MCPService._legacy_search_args({"name": "三体", "rating": ">=4", "tags": "科幻,长篇"})
        self.assertEqual(args, {"name": '(title:"三体" OR authors:"三体") AND rating:>=4 AND tags:"科幻" AND tags:"长篇"'})
        self.assertEqual(MCPService._legacy_search_args({"name": "x"}), {"name": "x"})


class EchoHandler(tornado.web.RequestHandler):
    def get(self, *a):
        uid = self.get_secure_cookie("user_id")
        self.write({"err": "ok", "uid": uid.decode() if uid else None, "host": self.request.headers.get("X-Forwarded-Host"),
                    "query": {k: v[0].decode() for k, v in self.request.query_arguments.items()}})

    def post(self, *a):
        self.write({"err": "ok", "uid": self.get_secure_cookie("user_id").decode(), "body": json.loads(self.request.body or b"{}")})


class TestLoopback(AsyncHTTPTestCase):
    def get_app(self):
        return tornado.web.Application([(r"/api/(.*)", EchoHandler)], cookie_secret="test-secret")

    def setUp(self):
        super().setUp()
        for name, default, typ in (("port", 8080, int), ("host", "", str)):
            if name not in options.as_dict():
                define(name, default=default, type=typ)
        self._saved = (options.port, options.host)
        options.port, options.host = self.get_http_port(), "127.0.0.1"
        svc = MCPService.__new__(MCPService)
        svc.token = None
        svc.need_login = True
        svc.need_login_prompt = ""
        svc.authenticated_tokens = {"tk": {"user_id": 5, "username": "u", "expires_at": 9e12}}
        req = types.SimpleNamespace(headers={}, host="books.example.com", protocol="https", remote_ip="1.2.3.4")
        svc.base_handler = types.SimpleNamespace(application=self._app, request=req)
        self.svc = svc

    def tearDown(self):
        options.port, options.host = self._saved
        super().tearDown()

    async def call(self, name, args):
        return json.loads((await self.svc.call_api_tool(name, args))[0].text)

    @gen_test
    async def test_get_as_mcp_user(self):
        d = await self.call("search_books", {"token": "tk", "isbn": "978-7-5366-9293-0"})
        self.assertEqual(d["uid"], "5")
        self.assertEqual(d["host"], "books.example.com")
        self.assertEqual(d["query"]["isbn"], "978-7-5366-9293-0")

    @gen_test
    async def test_post_json_body(self):
        d = await self.call("edit_book", {"token": "tk", "book_id": 3, "title": "新书名"})
        self.assertEqual(d, {"err": "ok", "uid": "5", "body": {"title": "新书名"}})

    @gen_test
    async def test_requires_auth(self):
        d = await self.call("get_book", {"book_id": 1})
        self.assertEqual(d["status"], "error")

    @gen_test
    async def test_tools_list_contains_api_tools(self):
        names = [t.name for t in await self.svc.list_tools()]
        self.assertTrue(set(API_TOOLS) <= set(names))
        self.assertIn("login", names)

    @gen_test
    async def test_tools_list_serializes_with_protocol_camel_case(self):
        """`tools/list` 的线上 JSON 必须用协议规定的 `inputSchema`。

        这条守的是 mcp SDK 升级带来的**静默**回归：mcp>=2 把模型字段改名成
        snake_case（`input_schema`），如果序列化时不带 `by_alias=True`，
        发出去的键就是 `input_schema`，而所有 MCP 客户端按协议只读
        `inputSchema` —— 结果每个工具都被当成**无参**，调用时参数被丢弃，
        表现成「工具都列出来了，但一个都用不了」。测试里 Python 侧直接读
        `tool.input_schema` 是拿得到的，所以只能断言**序列化后的 JSON**。
        """
        self.svc.need_login = False
        rsp = await self.svc.handle_request({
            "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {},
        })
        tools = rsp["result"]["tools"]
        self.assertTrue(tools)
        for tool in tools:
            self.assertIn("inputSchema", tool, "%s 缺少 inputSchema" % tool.get("name"))
            self.assertNotIn("input_schema", tool, "%s 用了 snake_case 键" % tool.get("name"))
        # 带参数的工具，schema 不能是空的 —— 这正是「工具无参」的表现
        by_name = {t["name"]: t for t in tools}
        self.assertIn("book_id", by_name["get_book"]["inputSchema"]["properties"])


if __name__ == "__main__":
    unittest.main()
