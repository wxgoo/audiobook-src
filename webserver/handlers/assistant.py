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


def _norm_host(host: str, scheme: str = "") -> str:
    """把 host[:port] 归一化用于比较：去空白、小写、去掉默认端口。

    - 反代（群晖/NPM）常出现 Origin 带 :443/:80、而 X-Forwarded-Host 不带端口，
      或反之；默认端口一律视为等价。
    - 非默认端口（如 NAS 的 :88、:9800）必须保留，不能误放行跨站。
    """
    host = (host or "").strip().lower()
    if not host:
        return host
    # 去掉协议残留（防御性）
    if "://" in host:
        host = urllib.parse.urlsplit(host).netloc
    # IPv6 [::1]:port 与 host:port 都要能拆
    if host.startswith("["):
        end = host.find("]")
        if end >= 0:
            hostpart, rest = host[:end + 1], host[end + 1:]
            port = rest[1:] if rest.startswith(":") else ""
        else:
            hostpart, port = host, ""
    else:
        if host.count(":") == 1:
            hostpart, port = host.split(":", 1)
        else:
            hostpart, port = host, ""
    if port in ("80", "443"):
        port = ""
    return hostpart + ((":" + port) if port else "")


def _candidate_hosts(handler):
    """本次请求可信的对外 host 候选（同源校验用）。

    Tornado xheaders=True 会用 X-Forwarded-Host 覆盖 request.host，但多层反代
    下该值可能不带端口、或用 X-Forwarded-Port 单独透传。这里与 base.set_hosts
    保持同一套重建口径，全部收进候选集，任一命中即视为同源。
    """
    hosts = []
    req = getattr(handler, "request", None)
    if req is None:
        return hosts
    raw = req.headers.get("X-Forwarded-Host", "") or ""
    for part in raw.split(","):
        h = part.strip()
        if h:
            hosts.append(h)
    if getattr(req, "host", None):
        hosts.append(req.host)
    # X-Forwarded-Port 单独透传时补齐到不带端口的候选上
    xport = (req.headers.get("X-Forwarded-Port", "") or "").split(",")[0].strip()
    if xport and xport not in ("80", "443"):
        extra = []
        for h in list(hosts):
            bare = _norm_host(h)
            if ":" not in bare and not bare.startswith("["):
                extra.append(bare + ":" + xport)
        hosts.extend(extra)
    return hosts


def is_same_host_origin(origin, host, extra_hosts=None):
    """Origin 的主机部分是否等于本次请求的可信 Host 之一。

    - 浏览器发起 WebSocket 一定带 Origin，跨站页面拿用户 Cookie 建连即为
      CSWSH（跨站 WebSocket 劫持），必须校验；
    - 非浏览器客户端（脚本、原生 App）通常不带 Origin，放行——它们的鉴权
      仍依赖 secure cookie，且没有"被第三方页面驱动"的攻击面；
    - scheme 不参与比较：容器内是 http，外部可能经 nginx 终止 HTTPS；
    - host 支持候选集（request.host + X-Forwarded-Host + X-Forwarded-Port），
      兼容群晖 :88、多层反代丢端口等场景；默认端口归一化后比较。
    """
    if not origin:
        return True
    try:
        parts = urllib.parse.urlsplit(origin)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            return False
        origin_host = _norm_host(parts.netloc, parts.scheme)
        candidates = [_norm_host(h, parts.scheme) for h in ([host] + list(extra_hosts or []))]
        return origin_host in [c for c in candidates if c]
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
        # 候选集含 X-Forwarded-Host/X-Forwarded-Port，兼容群晖 :88 等反代场景
        # （否则 Origin 带端口、转发后的 host 不带端口会被误判跨站，握手 403）。
        candidates = _candidate_hosts(self)
        allowed = is_same_host_origin(origin, self.request.host, candidates)
        if allowed:
            logging.info("WebSocket origin accepted: %s (host=%s, candidates=%s)",
                         origin or "(none)", self.request.host, candidates)
        else:
            logging.warning("WebSocket origin rejected: %s (host=%s, candidates=%s)",
                            origin, self.request.host, candidates)
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


class AssistantChatHandler(BaseHandler):
    """AI 对话的 HTTP 降级通道。

    群晖/多层反代下 WebSocket 握手常被拦（403 origin 或 400 upgrade），
    前端 onerror 后自动改走本接口。语义与 WebSocket 一致：登录即可用，
    复用同一个 AIAssistantMCPAgent.process_user_input，累积事件返回纯文本。
    会话历史由前端传入（history），保持与 WS 多轮对话体验一致。
    """

    @js
    async def post(self):
        if not self.current_user:
            return {"err": "auth.required", "msg": "请先登录"}

        data = self.get_json_body() or {}
        content = str(data.get("content", "") or "").strip()
        if not content:
            return {"err": "params.missing", "msg": "请输入问题"}

        history = data.get("history") or []
        if not isinstance(history, list):
            history = []
        clean_history = []
        for item in history[-10:]:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            text = item.get("content")
            if role in ("user", "assistant") and isinstance(text, str) and text:
                # 不回传前端占位/错误气泡，避免污染上下文
                if text.startswith("ERROR:") or text.startswith("处理请求时出错"):
                    continue
                clean_history.append({"role": role, "content": text})

        try:
            from webserver.assistant.ai_assistant_agent import AIAssistantMCPAgent

            cookies = {name: cookie.value for name, cookie in self.request.cookies.items()}
            agent = AIAssistantMCPAgent(cookies=cookies)
            agent.conversation_history = clean_history
            await agent.initialize()
            try:
                texts = []
                statuses = []
                async for event in agent.process_user_input(content):
                    if event.get("type") == "content":
                        texts.append(str(event.get("content", "")))
                    elif event.get("type") == "status":
                        statuses.append(str(event.get("content", "")))
                    elif event.get("type") == "error":
                        return {"err": "chat.failed",
                                "msg": str(event.get("content", ""))[:500]}
                return {"err": "ok", "text": "".join(texts), "statuses": statuses}
            finally:
                await agent.close()
        except Exception as e:  # noqa: BLE001
            logging.exception("[assistant] HTTP chat failed")
            return {"err": "chat.failed", "msg": str(e)[:500]}


def routes():
    return [
        (r"/api/assistant/ws", AssistantWebSocketHandler),
        (r"/api/assistant/chat", AssistantChatHandler),
        (r"/api/assistant/transcribe", AssistantTranscribeHandler),
    ]
