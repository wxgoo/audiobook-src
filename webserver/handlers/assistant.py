#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import json
import logging
import os
import tempfile
import tornado.websocket

import urllib.parse

from webserver.handlers.base import BaseHandler, js
from webserver import loader

CONF = loader.get_settings()


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


class AssistantTranscribeHandler(BaseHandler):
    """AI 助手/伴读的语音输入：接收一段麦克风录音，用本地 faster-whisper 转成文字。

    - 登录鉴权：继承 BaseHandler + get_current_user（未登录会被拦）。
    - 音频只存临时文件，转写完立即删除，不落库、不进书库。
    - 首次调用会下载 whisper small 模型（走 hf-mirror），之后复用进程内缓存。
    """
    MAX_AUDIO_BYTES = 12 * 1024 * 1024  # 12MB，够几分钟录音

    @js
    async def post(self):
        if not self.current_user:
            self.set_status(401)
            return {"err": "auth.required", "msg": "请先登录"}

        if not self.request.files or "audio" not in self.request.files:
            return {"err": "params.missing", "msg": "未收到录音文件"}

        file_meta = self.request.files["audio"][0]
        body = file_meta.get("body") or b""
        if not body:
            return {"err": "params.missing", "msg": "录音文件为空"}
        if len(body) > self.MAX_AUDIO_BYTES:
            return {"err": "too.large", "msg": "录音过大，请缩短后重试"}

        # 浏览器 MediaRecorder Usually produces webm/opus；faster-whisper 经 ffmpeg 可读。
        suffix = os.path.splitext(file_meta.get("filename") or "")[1].lower()
        if suffix not in (".webm", ".wav", ".mp3", ".m4a", ".ogg", ".mp4", ".aac"):
            suffix = ".webm"

        from webserver import utils
        from webserver.services import transcribe

        if not transcribe.whisper_available():
            return {"err": "asr.unavailable",
                    "msg": "服务器未安装语音识别引擎（faster-whisper）"}

        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(prefix="mybooks_voice_", suffix=suffix)
            with os.fdopen(fd, "wb") as f:
                f.write(body)

            # 模型由系统设置 TRANSCRIBE_MODEL 决定（「音频转写文稿」SrtMake 工具页
            # 下拉选择并保存，与此处共用同一配置），换硬件后改工具页下拉即可。
            _allowed = ("tiny", "base", "small", "medium", "large-v3", "large")
            model_size = str(CONF.get("TRANSCRIBE_MODEL", "base") or "base")
            if model_size not in _allowed:
                model_size = "base"
            if model_size == "large":
                model_size = "large-v3"
            lang = str(self.get_argument("lang", "auto") or "auto")

            text = await utils.run_in_threadpool(
                lambda: transcribe.transcribe_short(tmp_path, model_size=model_size, lang=lang))
            return {"err": "ok", "text": text}
        except Exception as e:
            logging.error("[assistant] voice transcribe failed: %s", e)
            return {"err": "asr.failed", "msg": "语音识别失败：%s" % str(e)[:200]}
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


def routes():
    return [
        (r"/api/assistant/ws", AssistantWebSocketHandler),
        (r"/api/assistant/transcribe", AssistantTranscribeHandler),
    ]
