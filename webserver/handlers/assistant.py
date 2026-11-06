#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import json
import logging
import tornado.websocket

import urllib.parse


def is_same_host_origin(origin, host):
    """Origin 的主机部分是否等于本次请求的 Host。

    - 浏览器发起 WebSocket 一定带 Origin，跨站页面拿用户 Cookie 建连即为
      CSWSH（跨站 WebSocket 劫持），必须校验；
    - 非浏览器客户端（脚本、原生 App）通常不带 Origin，放行——它们的鉴权
      仍依赖 secure cookie，且没有"被第三方页面驱动"的攻击面；
    - scheme 不参与比较：容器内是 http，外部可能经 nginx 终止 HTTPS，
      只比较 host:port 才能同时兼容两种入口。
    """
    if not origin:
        return True
    try:
        parts = urllib.parse.urlsplit(origin)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            return False
        return parts.netloc.lower() == (host or "").lower()
    except Exception:
        return False


class AssistantWebSocketHandler(tornado.websocket.WebSocketHandler):
    # 保存连接的实例，以便后台服务管理
    clients = set()

    def get_current_user(self):
        """从secure cookie获取当前用户"""
        user_id = self.get_secure_cookie("user_id")
        if not user_id:
            logging.error("No user found in secure cookie")
            return None
        # 这里只需要验证用户是否登录，不需要完整的用户对象
        return user_id

    def check_origin(self, origin):
        # 原实现无条件 return True，等于允许任意网站借用户 Cookie 建立 AI 会话。
        allowed = is_same_host_origin(origin, self.request.host)
        if allowed:
            logging.info("WebSocket origin accepted: %s", origin or "(none)")
        else:
            logging.warning("WebSocket origin rejected: %s (host=%s)",
                            origin, self.request.host)
        return allowed

    async def open(self):
        logging.info(f"WebSocket open called, user: {self.get_current_user()}")
        if not self.get_current_user():
            logging.warning("WebSocket connection attempt without login.")
            self.close(code=4003, reason="Authentication required")
            return

        try:
            logging.info("WebSocket assistant connection accepted")
            self.clients.add(self)

            # 获取当前请求的 cookies
            cookies = {}
            for cookie_name in self.request.cookies:
                cookie = self.request.cookies[cookie_name]
                cookies[cookie_name] = cookie.value

            logging.info(f"WebSocket cookies: {list(cookies.keys())}")

            # 为每个连接创建独立的 Agent 实例
            from webserver.assistant.ai_assistant_agent import AIAssistantMCPAgent
            self.agent = AIAssistantMCPAgent(cookies=cookies)
            await self.agent.initialize()

            self.write_message(json.dumps({"type": "status", "content": "AI助手连接成功"}))
        except Exception as e:
            logging.error(f"Failed to initialize AI agent: {e}")
            self.close(code=5000, reason="Agent initialization failed")
            return

    async def on_message(self, message):
        try:
            data = json.loads(message)
            user_input = data.get("content", "")
            if not user_input:
                return

            logging.info(f"AI Assistant Task: {user_input}")

            # 开启处理
            self.write_message(json.dumps({"type": "start"}))

            async for chunk in self.agent.process_user_input(user_input):
                self.write_message(json.dumps(chunk))

            # 处理完成
            self.write_message(json.dumps({"type": "end"}))

        except Exception as e:
            logging.error(f"Error processing AI message: {e}")
            self.write_message(json.dumps({"type": "error", "content": str(e)}))

    async def on_close(self):
        logging.info("WebSocket assistant closed")
        self.clients.discard(self)
        if hasattr(self, 'agent'):
            await self.agent.close()


def routes():
    return [
        (r"/api/assistant/ws", AssistantWebSocketHandler),
    ]
