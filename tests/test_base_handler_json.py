# -*- coding: utf-8 -*-
"""BaseHandler.get_json_body 单元测试。

背景：toolbox.py 的 SRT 模型管理 API（start/model_download/model_delete/hf_mirror）
约定调用 self.get_json_body()，但 BaseHandler 一直没有这个方法，
NAS 实测点击「删除模型」报 AttributeError: 'AdminSrtToolModelDelete'
object has no attribute 'get_json_body'。本文件锁定该辅助方法的行为。
"""
import json
from unittest.mock import MagicMock

from tornado import web

from webserver.handlers.base import BaseHandler


def _handler_with_body(raw):
    h = BaseHandler.__new__(BaseHandler)
    req = MagicMock()
    req.body = raw
    h.request = req
    return h


class TestGetJsonBody:
    def test_dict_body(self):
        h = _handler_with_body(json.dumps({"model": "small", "n": 1}).encode())
        assert h.get_json_body() == {"model": "small", "n": 1}

    def test_empty_body_returns_empty_dict(self):
        assert _handler_with_body(b"").get_json_body() == {}
        assert _handler_with_body(None).get_json_body() == {}

    def test_invalid_json_raises_400(self):
        h = _handler_with_body(b"{not-json")
        try:
            h.get_json_body()
        except web.HTTPError as e:
            assert e.status_code == 400
        else:
            raise AssertionError("非法 JSON 未抛 HTTPError")

    def test_non_dict_body_returns_empty_dict(self):
        # 合法 JSON 但不是对象：防御性返回 {}，调用方的 .get() 不会炸
        for raw in (b"[1,2]", b'"str"', b"123", b"null"):
            assert _handler_with_body(raw).get_json_body() == {}

    def test_or_pattern_callers_safe(self):
        # 复现 4 个调用点的用法：data = self.get_json_body() or {}
        h = _handler_with_body(b"")
        data = h.get_json_body() or {}
        assert data.get("model") or "" == ""

    def test_method_exists_on_base_handler(self):
        # 防回归：4 个 SRT handler 依赖 BaseHandler.get_json_body
        assert callable(getattr(BaseHandler, "get_json_body", None))
