#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

"""
(PoxenStudio)MyBooks MCP Multi-Transport Server
"""
import datetime
import logging
import json

from webserver import loader
from webserver.handlers.base import BaseHandler, ListHandler, js
from webserver.i18n import _
from webserver.version import VERSION


CONF = loader.get_settings()

# 日志脱敏：JSON-RPC 请求体里可能出现 token / password / cookie 等字段
SENSITIVE_FIELDS = {
    "token", "access_token", "refresh_token", "password", "api_key",
    "apikey", "authorization", "cookie", "secret", "ai_mcp_token",
}


def redact(value):
    """递归脱敏，用于日志输出。"""
    if isinstance(value, dict):
        return {
            k: ("***" if str(k).lower() in SENSITIVE_FIELDS else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


class MCPHandler(ListHandler):
    mcp_service_single = None
    mcp_service_with_token = None
    last_service_token = None

    @classmethod
    def create_mcp_service(cls, base_handler: BaseHandler = None, token: str = None):
        """
        Create and return a new MCP service instance.
        Different instances are created based on whether a token is provided.
        """
        from webserver.mcp.mcp_service import MCPService
        if token is None or token == "":
            if cls.mcp_service_single is None:
                cls.mcp_service_single = MCPService(base_handler, token=token)
            service = cls.mcp_service_single
        elif cls.last_service_token is not None and token == cls.last_service_token \
                and cls.mcp_service_with_token is not None:
            service = cls.mcp_service_with_token
        else:
            cls.mcp_service_with_token = MCPService(base_handler, token=token)
            cls.last_service_token = token
            service = cls.mcp_service_with_token
        # 服务实例被复用，但 handler 是每个请求独立的（request/session 等），需更新为当前请求
        if base_handler is not None:
            service.base_handler = base_handler
        return service

    @js
    def get(self):
        """Serve MCP client with the current version and settings."""
        response = {
            "err": "ok",
            "version": VERSION,
            "settings": {
                "base_url": CONF.get("base_url", ""),
                "mcp_version": CONF.get("mcp_version", VERSION),
            },
            "timestamp": datetime.datetime.now().isoformat(),
        }
        # 交给 @js 统一写响应：这里再 self.write 会变成 {...}{}
        return response

    def _bearer_token(self):
        """从 Authorization: Bearer 头取 token（推荐方式，不会进 access log）。"""
        header = self.request.headers.get("Authorization", "")
        if header[:7].lower() == "bearer ":
            return header[7:].strip() or None
        return None

    @js
    def post(self):
        """Handle MCP over HTTP streaming."""
        logging.info("New HTTP stream connection from MCP client")
        # 优先 Authorization 头；URL query 只在显式打开兼容开关时接受
        token = self._bearer_token()
        if not token:
            query_token = self.get_argument("token", None)
            if query_token:
                if CONF.get("ALLOW_MCP_TOKEN_IN_URL", False):
                    logging.warning(
                        "MCP token 通过 URL 传入已弃用，请改用 Authorization: Bearer 头")
                    token = query_token
                else:
                    logging.warning(
                        "拒绝 URL 携带 MCP token 的请求（已默认关闭，"
                        "如需兼容请开启 ALLOW_MCP_TOKEN_IN_URL）")
                    self.set_status(401)
                    return {"err": "auth",
                            "msg": "MCP token must be sent via Authorization: Bearer header"}

        mcp_service = self.create_mcp_service(self, token=token)
        try:
            # Read request body
            body = self.request.body
            if not body:
                self.set_status(400)
                return {"err": "params", "msg": _("No request body")}

            request_data = json.loads(body)
            logging.info("HTTP stream request: %s", redact(request_data))

            response = mcp_service.handle_request(request_data)
            return response

        except Exception as e:
            logging.error(f"Error in HTTP stream handler: {e}")
            self.set_status(500)
            return {
                "err": "ok",
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": str(e)}
            }


class MCPHealthHandler(BaseHandler):
    @js
    def get(self):
        return {"err": "ok", "status": "healthy", "server": "mybooks-mcp"}


def routes():
    return [
        (r"/api/mcp/stream", MCPHandler),
        (r"/api/mcp/health", MCPHealthHandler),
    ]
