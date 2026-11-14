#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import asyncio
import bisect
import contextlib
import base64
import datetime
import hashlib
import hmac
import logging
import os
import random
import re
import time
import traceback
from collections import defaultdict
from urllib.parse import quote, urlparse
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import func as sql_func
from sqlalchemy import inspect as sa_inspect
from tornado import web
from tornado.escape import utf8

from webserver.i18n import _, choose_language, set_language
from webserver import loader, perf, site_time, utils
from webserver.base import calibre_fast
from webserver.base.book_data_cascade import cascade_delete_book_data
from webserver.base.formatter import BookFormatter
from webserver.base.pagination import decode_cursor, encode_cursor, parse_id_cursor
from webserver.base.query_cache import VersionedCache, library_version
from webserver.base.global_state import get_global_state
from webserver.base.sidebar import get_sidebar_items
from webserver.services.resource_service import ResourceService
from webserver.services.perf_monitor import PerfMonitor
from webserver.services.book_access_service import BookAccessService
from webserver.services.book_share_service import BookShareService
from webserver.services import book_takedown
from webserver.services.search_index import get_search_index
from webserver.models import Item, Message, Reader
from webserver import constants
from webserver.version import VERSION
from webserver.constants import UPGRABLE_REVISION

messages = defaultdict(list)
CONF = loader.get_settings()

# 「必须登录才能访问」(REQUIRE_LOGIN) 开启后，仍然允许匿名访问的路径。
# 原则：只放行"没有登录就进不来"的必需品（登录/注册/激活/安装、登录页静态资源），
# 以及带自己凭据、网页登录没法覆盖的设备协议入口（播客 token、MCP token、WebDAV Basic）。
# 分享链接独立于 REQUIRE_LOGIN：分享页与分享 API 放行，书籍内容再按逐本分享授权放行
# （见 BaseHandler.share_grant_allows_path）。公开书单仍不放行。
LOGIN_GATE_ALLOW_EXACT = frozenset({
    "/login",
    "/logout",
    "/signup",
    "/welcome",
    "/install",
    "/starting",
    "/api/user/info",
    "/api/user/sign_in",
    "/api/user/sign_up",
    "/api/user/reset",
    "/api/user/sign_out",
    "/api/done",           # 社交登录 OAuth 回调（回调里才建立会话，必须先放行）
    "/api/access",
    "/api/admin/install",
    "/wap/login",
    "/wap/welcome",
    "/favicon.ico",
    "/robots.txt",
    "/site.webmanifest",
    "/apple-touch-icon.png",
})

LOGIN_GATE_ALLOW_PREFIX = (
    "/api/active/",        # 邮箱激活链接（实际路由 /api/active/<username>/<code>）
    "/api/mcp/",           # MCP 工具调用自带 AI_MCP_TOKEN
    "/api/share/",         # 分享链接信息/验证接口：分享功能优先于 REQUIRE_LOGIN
    "/s/",                 # 分享落地页（SPA）：页面本身不含书籍内容，内容仍逐本校验授权
    "/api/favicon/",       # 站点图标（登录页标签页要显示）
    "/books",              # WebDAV：裸 RequestHandler，不走本门禁；自带 Basic 认证
    "/_nuxt/",             # SPA 资源，登录页自身要能渲染
    "/logo/",
    "/avatar/",
    "/favicon",
    "/manifest",
)


LOGIN_GATE_ALLOW_SUFFIX = (
    ".js", ".mjs", ".css", ".map", ".json",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".woff", ".woff2", ".ttf", ".eot",
)

# 播客路由里只有「路径带用户 podcast_token」的那几条才能在匿名下工作：
#   /podcast/<token>、/podcast/<token>/book/<id>、/podcast/audio/<id>/<token>/<file>
# 其余（/podcast/all、/podcast/book/<id>、/podcast/category|tag|author/...）是公开目录，
# 会把有声书的书名/作者/简介匿名暴露，必须按普通页面拦掉。
_PODCAST_PUBLIC_SEGMENTS = frozenset({"all", "book", "category", "tag", "author"})
_PODCAST_TOKEN_RE = re.compile(r"^[A-Za-z0-9]+$")


def _podcast_token_path(path):
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2 or parts[0] != "podcast":
        return False
    if parts[1] == "audio":
        # /podcast/audio/<book_id>/<token>/<filename>
        return len(parts) >= 5 and parts[3].isalnum()
    seg = parts[1]
    if seg in _PODCAST_PUBLIC_SEGMENTS:
        return False
    return bool(_PODCAST_TOKEN_RE.match(seg))


# 分享链接允许匿名访问的书籍内容入口：命中时再按 book_id 校验分享授权（见
# BaseHandler.share_grant_allows_path）。分享页与分享 API 不在此表，按前缀直接放行。
_SHARE_READ_PATH_PATTERNS = (
    re.compile(r"^/read/(\d+)/?$"),
    re.compile(r"^/api/book/(\d+)/read/?$"),
    re.compile(r"^/get/extract/(\d+)(?:/.*)?$"),
    re.compile(r"^/api/read/txt/(\d+)/?$"),
    re.compile(r"^/api/book/(\d+)/filepath/?$"),
)

# 不针对具体书籍的阅读附属接口（阅读器里的词典、朗读）：没有 book_id 可校验，只要持有
# 任意一本有效分享的阅读授权就放行，与 BookAccessService.guest_read_allowed(handler, None)
# 保持一致——否则分享访客能读正文，却查不了词、用不了朗读。
# 生词本（/vocab）不在此列：它是写操作、且走站点共享 token，分享访客没有账号，保持登录后可用。
_SHARE_ANY_READ_PATH_PATTERNS = (
    re.compile(r"^/api/reader/dict-config$"),
    re.compile(r"^/api/reader/dict/[A-Za-z0-9_-]{1,32}/(?:query|res)(?:/|$)"),
    re.compile(r"^/api/tts/edge$"),
)

# 内嵌阅读器（MyReader）的身份桥接端点：MyReader 服务端把浏览器 Cookie 转发到
# GET /api/user/whoami 换取身份。分享访客没有账号，WhoAmI 会按「持任意有效分享授权」
# 返回 guest 身份（user.py 的 is_guest 分支）；若门禁不把这条路径放给分享访客，
# 就会出现"分享落地页能开、点在线阅读后 MyReader 却卡在'请先登录'"的割裂
# （设计见 myreader 仓库的 document/MyReader_Embedded_WebApp.md §5）。
_SHARE_BRIDGE_PATHS = frozenset({"/api/user/whoami"})

# 分享落地页在用户输入提取码之前就要显示封面（分享 API 直接返回封面/缩略图地址），
# 所以这类图片只对"确实存在有效分享"的书籍放行，避免顺带公开未分享书籍的封面。
_SHARE_COVER_PATH_RE = re.compile(r"^/get/(?:cover|thumb(?:_\d+_\d+)?)/(\d+)(?:\.[A-Za-z0-9]+)?$")

# 分享页的下载按钮直接指向 /api/book/<id>.<fmt>；是否真有下载权限由 BookDownload 再校验。
_SHARE_DOWNLOAD_PATH_RE = re.compile(r"^/api/book/(\d+)\.[A-Za-z0-9]+$")


def share_read_book_id(path):
    """从分享阅读相关路径中取出 book_id；不属于这些入口时返回 None。"""
    for pattern in _SHARE_READ_PATH_PATTERNS:
        match = pattern.match(path)
        if match:
            return int(match.group(1))
    return None


def login_gate_allowed(path):
    """REQUIRE_LOGIN 开启时，这个路径是否允许匿名访问。"""
    if not path:
        return False
    # 尾斜杠归一化：/login/ 与 /login 是同一个页面（StaticFileHandler 还会把 /login 301 到
    # /login/ 并丢掉 ?next=），不放行会让用户登完停在登录页。
    path = path.rstrip("/") or "/"
    if path in LOGIN_GATE_ALLOW_EXACT:
        return True
    if path.startswith(LOGIN_GATE_ALLOW_PREFIX):
        return True
    if path.startswith("/podcast"):
        return _podcast_token_path(path)
    # /api/* 与 /get/*（封面、书籍文件、EPUB 解包）只认白名单，绝不按扩展名放行。
    if path.startswith(("/api/", "/get/")):
        return False
    # 前端构建产物（_nuxt/*、logo、图标、字体）登录页自身要用。
    # 严格说这些由 SpaStaticHandler 直出、根本不经过本门禁，这里只是兜底。
    return path.endswith(LOGIN_GATE_ALLOW_SUFFIX)


def day_format(value, format="%Y-%m-%d"):
    try:
        return value.strftime(format)
    except Exception:
        return "1990-01-01"


def website_format(value):
    links = []
    for link in value.split(";"):
        if link.startswith("douban://"):
            douban_id = link.split("//")[-1]
            links.append(
                "<a target='_blank' href='https://book.douban.com/subject/%s/'>豆瓣</a> "
                % douban_id
            )
        elif link.startswith("isbn://"):
            douban_id = link.split("//")[-1]
            links.append(
                "<a target='_blank' href='https://book.douban.com/isbn/%s/'>豆瓣</a> "
                % douban_id
            )
        elif link.startswith("http://"):
            links.append("<a target='_blank' href='%s'>参考链接</a> " % link)
    return ";".join(links)


def js(func):
    async def do(self, *args, **kwargs):
        try:
            rsp = func(self, *args, **kwargs)
            if asyncio.iscoroutine(rsp):
                rsp = await rsp
            if rsp is None:
                rsp = {}
            result = rsp.get("msg", None)
            if result is not None:
                rsp["msg"] = result
        except Exception as e:
            logging.error(traceback.format_exc())
            # 完整 traceback 含服务器路径/库版本，只给管理员看（排障用）；
            # 其余用户只回类型+消息，避免被构造参数批量探测服务器内部信息
            try:
                admin_view = bool(getattr(self, "current_user", None)) and self.is_admin()
            except Exception:
                admin_view = False
            if admin_view:
                msg = (
                    'Exception:<br><pre style="white-space:pre-wrap;word-break:keep-all">%s</pre>'
                    % traceback.format_exc()
                )
            else:
                msg = "Exception: %s: %s" % (type(e).__name__, e)
            rsp = {"err": "exception", "msg": msg}
            if isinstance(e, web.Finish):
                rsp = ""
        origin = self.request.headers.get("origin")
        # CORS：只回显同站点 Origin（SPA 与后端同源部署）。
        # 原实现把任意 Origin 原样回显且带 Allow-Credentials，等于给任何
        # 恶意网页开了「带着用户 Cookie 读本站 API」的口子。
        if origin and self._is_same_site_origin(origin):
            self.set_header("Access-Control-Allow-Origin", origin)
            self.set_header("Access-Control-Allow-Credentials", "true")
        self.set_header("Cache-Control", "max-age=0")
        self.write(rsp)
        self.finish()
        return

    return do


class HeavyGate:
    inflight = 0
    per_user = {}

    @classmethod
    def enter(cls, user_key):
        limit = int(CONF.get("LITE_THROTTLE_LIMIT", 4))
        if cls.inflight >= limit or (user_key is not None and cls.per_user.get(user_key, 0) >= 1):
            return False
        cls.inflight += 1
        if user_key is not None:
            cls.per_user[user_key] = cls.per_user.get(user_key, 0) + 1
        return True

    @classmethod
    def leave(cls, user_key):
        cls.inflight = max(0, cls.inflight - 1)
        if user_key is not None:
            left = cls.per_user.get(user_key, 0) - 1
            if left > 0:
                cls.per_user[user_key] = left
            else:
                cls.per_user.pop(user_key, None)


def throttle(per_user=False, write=False):
    def decorator(func):
        async def do(self, *args, **kwargs):
            if not perf.lite_on("LITE_THROTTLE"):
                rsp = func(self, *args, **kwargs)
                return await rsp if asyncio.iscoroutine(rsp) else rsp
            user_key = (self.user_id() or self.request.remote_ip) if per_user else None
            if not HeavyGate.enter(user_key):
                self.set_status(503)
                self.set_header("Retry-After", "2")
                busy = {"err": "busy", "msg": _("服务器繁忙，请稍后重试")}
                if write:
                    self.write(busy)
                    return None
                return busy
            try:
                rsp = func(self, *args, **kwargs)
                return await rsp if asyncio.iscoroutine(rsp) else rsp
            finally:
                HeavyGate.leave(user_key)

        return do

    return decorator


def auth(func):
    def do(self, *args, **kwargs):
        if not self.current_user:
            return {"err": "user.need_login", "msg": _("请先登录")}
        return func(self, *args, **kwargs)

    return do


def is_admin(func):
    def do(self, *args, **kwargs):
        if not self.current_user:
            return {"err": "user.need_login", "msg": _("请先登录")}
        if not self.admin_user:
            return {
                "err": "permission.not_admin",
                "msg": _("当前用户非管理员, 无权限操作"),
            }
        return func(self, *args, **kwargs)

    return do


class BaseHandler(web.RequestHandler):
    _path_to_env = {}
    _query_fallback_cache = {}
    _physical_books_count_cache: int = 0
    _physical_books_count_cache_time: float = 0.0
    _all_readers_cache: dict = {}
    _all_readers_cache_time: float = 0.0
    site_url = ""
    db_lock = None  # 数据库访问锁，在应用启动时初始化

    @staticmethod
    def get_site_url():
        return BaseHandler.site_url

    def _sanitize_uploaded_filename(self, name):
        """Normalize untrusted upload filename to a safe basename."""
        if not name:
            return ""
        normalized = name.replace("\\", "/")
        normalized = normalized.split("/")[-1]
        normalized = normalized.strip().replace("\x00", "")
        if normalized in ("", ".", ".."):
            return ""
        # Most filesystems cap filenames at 255 bytes; truncate stem to fit.
        stem, ext = os.path.splitext(normalized)
        max_stem_bytes = 255 - len(ext.encode("utf-8"))
        if max_stem_bytes <= 0:
            return ""
        stem_bytes = stem.encode("utf-8")
        if len(stem_bytes) > max_stem_bytes:
            stem = stem_bytes[:max_stem_bytes].decode("utf-8", errors="ignore")
        return stem + ext

    def _safe_upload_path(self, filename):
        """Join filename to upload dir and enforce it stays within upload dir."""
        base_dir = os.path.realpath(CONF["upload_path"])
        candidate = os.path.realpath(os.path.join(base_dir, filename))
        if os.path.commonpath([base_dir, candidate]) != base_dir:
            raise ValueError("invalid upload path")
        return candidate

    def _request_summary(self) -> str:
        # Use cached values to avoid detached instance errors after session closes
        userid = self._cached_user_id or 0
        username = self._cached_username or "-"

        return '%s %s (%s) "%d %s"' % (
            self.request.method,
            self.request.uri,
            self.request.remote_ip,
            userid,
            username,
        )

    def get_argument(self, name, default=None, strip=True):
        value = super().get_argument(name, default, strip)
        if value == "null":
            return default
        return value

    def get_secure_cookie(self, key):
        if not self.cookies_cache.get(key, ""):
            self.cookies_cache[key] = super(BaseHandler, self).get_secure_cookie(key)
        return self.cookies_cache[key]

    def get_secure_cookie_timestamp(self, key):
        """
        Extract the timestamp embedded in a Tornado secure_cookie raw value.
        Returns the timestamp as int, or None if not found.
        """
        cookie = self.request.cookies.get(key)
        if not cookie:
            return None
        raw = cookie.value
        if not raw or "|" not in raw:
            return None
        # segments are length-prefixed (len:data)
        for segment in raw.split("|"):
            if ":" not in segment:
                continue
            length_str, data = segment.split(":", 1)
            if not length_str.isdigit():
                continue
            length = int(length_str)
            # timestamp should be numeric and reasonably long (e.g., >=8 digits)
            if length >= 8 and len(data) == length and data.isdigit():
                try:
                    return int(data)
                except ValueError:
                    return None
        return None

    def set_secure_cookie(self, key, val):
        self.cookies_cache[key] = val
        super(BaseHandler, self).set_secure_cookie(key, val)
        return None

    def head(self, *args, **kwargs):
        return self.get(*args, **kwargs)

    def get_os(self):
        # get the host os from the user agent
        user_agent = self.request.headers.get("User-Agent", "")
        if "Windows" in user_agent:
            return "Windows"
        elif "Macintosh" in user_agent:
            return "MacOS"
        elif "Linux" in user_agent:
            return "Linux"
        elif "Android" in user_agent:
            return "Android"
        elif "iPhone" in user_agent or "iPad" in user_agent:
            return "iOS"
        else:
            return "Unknown"

    def mark_invited(self):
        self.set_secure_cookie("invited", str(int(time.time())))

    def require_login_enabled(self):
        """站点是否开启了「必须登录才能访问」（私人图书馆标准模式）。"""
        return bool(CONF.get("REQUIRE_LOGIN", False))

    def allow_flags(self):
        """下发给前端的站点开关（sys.allow）。

        必须登录时访客各项一律上报 False：前端有大量 "allow.read / allow.download"
        分支（详情页访客可读、"访客可读"徽章、顶栏入口…），只靠后端拦会把 UI
        留在"访客还能读"的错误状态。分享链接例外：它优先于必须登录，只看自身开关。
        """
        require_login = self.require_login_enabled()
        return {
            "register": CONF["ALLOW_REGISTER"],
            "require_login": require_login,
            "download": False if require_login else CONF["ALLOW_GUEST_DOWNLOAD"],
            "push": False if require_login else CONF["ALLOW_GUEST_PUSH"],
            "read": False if require_login else CONF["ALLOW_GUEST_READ"],
            "upload": False if require_login else CONF.get("ALLOW_GUEST_UPLOAD", False),
            "share_link": CONF.get("ENABLE_SHARE_LINK", True),
            "physical_books": CONF.get("ENABLE_PHYSICAL_BOOKS", True),
            "folder": CONF.get("ENABLE_FOLDER_BROWSE", False),
            "download_quota": CONF.get("ENABLE_DOWNLOAD_QUOTA", False),
            "server_import": CONF.get("ENABLE_SERVER_FILE_IMPORT", False),
            "sync": CONF.get("ENABLE_DATA_SYNC", False),
            "book_review": CONF.get("ENABLE_BOOK_REVIEW", True),
            "user_memos": CONF.get("ENABLE_USER_MEMOS", True),
            "book_recommend": CONF.get("ENABLE_BOOK_RECOMMEND_TO_OTHERS", True),
            "shared_notes": CONF.get("ENABLE_SHARED_NOTES", True),
        }

    def need_invited(self):
        # 必须登录是比访问码更强的门：开启后访问码检查整体让位，
        # 否则会变成「先输访问码、再登录」的两段式，且 /login 自身会被访问码拦住。
        if self.require_login_enabled():
            return False
        if not CONF.get("INVITE_MODE", False):
            return False
        if CONF.get("INVITE_CODE", ""):
            return True
        return False

    def invited_code_is_ok(self):
        t = self.get_secure_cookie("invited")
        if t and int(float(t)) > int(time.time()) - 7 * 86400:
            return True
        return False

    def process_auth_header(self):
        auth_header = self.request.headers.get("Authorization", "")
        if not auth_header.startswith("Basic "):
            return False
        # 凭据是客户端可控的：base64 非法、非 UTF-8、缺冒号都会抛异常。
        # 这里必须当成"认证失败"，否则畸形头会变成 500，OPDS 客户端也拿不到 401 挑战。
        try:
            auth_decoded = base64.decodebytes(auth_header[6:].encode("ascii")).decode(
                "UTF-8"
            )
            username, password = auth_decoded.split(":", 1)
        except (ValueError, UnicodeDecodeError):
            logging.info("Malformed Basic authorization header ignored")
            return False
        user = (
            self.sqlite_session.query(Reader)
            .filter(Reader.username == username)
            .first()
        )
        if not user:
            return False
        if user.get_secure_password(password) != str(user.password):
            return False
        if not user.active:
            return False
        self.mark_invited()
        self.login_user(user)
        return True

    TOKEN_LOGIN_SAVE_INTERVAL = 300
    _token_login_at = {}

    def process_auth_token(self):
        token = self.get_argument("token", None) or self.request.headers.get(
            "X-MYBOOKS-TOKEN", None
        )
        if not token:
            return False
        user = (
            self.sqlite_session.query(Reader)
            .filter(Reader.podcast_token == token)
            .first()
        )
        if not user or not user.active:
            logging.warning("Not login yet")
            return False
        # 用 user_id()（只读 cookie）判断"是否已有网页会话"，不能读 self.current_user：
        # 那会触发 Tornado 的 _current_user 缓存，在 login 之前缓存成 None，
        # 导致整个 handler 里 current_user 变成匿名（播客目录页会因此丢掉 token 链接）。
        # 先看有没有 user_id cookie 再解析：没有 cookie 时不必走 user_id() 的过期判定。
        cookie_uid = self.user_id() if self.get_secure_cookie("user_id") else None
        if cookie_uid and str(cookie_uid) != str(user.id):
            # 已登录 A 又拿来 B 的 token：会让"授权按 A、数据归属按 B"分裂，直接忽略
            logging.info("Ignore podcast token of another user for the current session")
            return False
        now = time.time()
        recent = BaseHandler._token_login_at.get(user.id, 0) > now - self.TOKEN_LOGIN_SAVE_INTERVAL
        if not recent:
            BaseHandler._token_login_at[user.id] = now
        self._login_via_token = not cookie_uid
        # token 身份不种 cookie（否则一次 curl 就能换到 7 天整站会话），
        # 但仍保留原有的"同一用户 5 分钟内只落一次库"的节流语义。
        self.login_user(user, persist=not recent, set_cookie=False)
        # 让 Tornado 的缓存与本次身份一致（login_user 不会动 current_user）
        self.current_user = user
        return True

    DOWNLOAD_SIGN_MAX_AGE_SECONDS = 10

    @staticmethod
    def _download_sign_mac(secret, user_id, book_id, fmt, expire):
        msg = ("dl|%s|%s|%s|%s" % (user_id, book_id, fmt.lower(), expire)).encode("utf-8")
        return hmac.new(utf8(secret), msg, hashlib.sha256).hexdigest()[:32]

    def make_download_sign(self, user_id, book_id, fmt):
        expire = int(time.time()) + self.DOWNLOAD_SIGN_MAX_AGE_SECONDS
        mac = self._download_sign_mac(self.application.settings["cookie_secret"], user_id, book_id, fmt, expire)
        return "%s.%s.%s" % (user_id, expire, mac)

    def parse_download_sign(self, sign, book_id, fmt):
        """校验下载签名，返回签名绑定的 user_id；签名无效、过期或与书籍/格式不符时返回 None"""
        parts = sign.split(".")
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            return None
        uid, expire, mac = parts
        if int(expire) < time.time():
            return None
        expected = self._download_sign_mac(self.application.settings["cookie_secret"], uid, book_id, fmt, expire)
        if not hmac.compare_digest(mac, expected):
            return None
        return int(uid)

    def send_error_of_not_invited(self):
        self.write({"err": "not_invited"})
        self.set_status(200)
        raise web.Finish()

    def should_be_invited(self):
        if self.need_invited():
            if not self.invited_code_is_ok():
                return self.send_error_of_not_invited()

    def share_grant_allows_path(self, path):
        """该路径是否属于分享链接入口，且当前请求可匿名访问。

        - 分享页封面/缩略图：分享开关打开，且该书确实有有效分享（落地页在拿到授权前就要显示封面）；
        - 阅读内容入口：必须是当前请求持有该书的有效分享授权。
        """
        if path.startswith(("/s/", "/api/share/")):
            return BookAccessService.share_link_enabled()
        for pattern in _SHARE_ANY_READ_PATH_PATTERNS:
            if pattern.match(path):
                return BookAccessService.share_any_read_granted(self)
        if path in _SHARE_BRIDGE_PATHS:
            # 内嵌阅读器身份桥接（/api/user/whoami）：分享访客持任意有效分享授权即可
            # 匿名调用，WhoAmI 会据此返回 guest 身份，供 MyReader 建立只读会话。
            return BookAccessService.share_any_read_granted(self)
        match = _SHARE_COVER_PATH_RE.match(path)
        if match:
            if not BookAccessService.share_link_enabled():
                return False
            return int(match.group(1)) in BookShareService.shared_book_ids()
        match = _SHARE_DOWNLOAD_PATH_RE.match(path)
        if match:
            return BookAccessService.share_download_granted(self, int(match.group(1)))
        book_id = share_read_book_id(path)
        if book_id is None and path == "/api/book/txt/parser":
            # TXT 目录接口把 book_id 放在查询参数里（/api/book/txt/parser?id=123）
            try:
                book_id = int(self.get_argument("id", ""))
            except (TypeError, ValueError):
                book_id = None
        if book_id is None:
            return False
        return BookAccessService.share_read_granted(self, book_id)

    def _is_same_site_origin(self, origin):
        """Origin 是否指向本站（scheme + host[:port] 与请求的 Host 一致）。

        CORS 响应头只对浏览器有意义；本站 SPA 与后端同源部署，跨站一律不发
        Allow-Origin，恶意网页即使带着用户 Cookie 发起请求也读不到响应。
        """
        import urllib.parse

        try:
            parts = urllib.parse.urlsplit(origin or "")
            if parts.scheme not in ("http", "https") or not parts.netloc:
                return False
            return parts.netloc.lower() == (self.request.host or "").lower()
        except Exception:
            return False

    def is_opds_acquisition(self, path):
        """OPDS 目录里的下载直链：形如 /api/book/<id>.<fmt>?from=opds（见 opds.py ACQUISITION_ENTRY）。

        消费者是阅读器下载器：必须登录时这类直链要回 401 + WWW-Authenticate 挑战，
        不能走 /api/ 的 200 JSON——否则下载器会把 JSON 当成下载成功存成假书。
        """
        if not _SHARE_DOWNLOAD_PATH_RE.match(path):
            return False
        return self.get_argument("from", "") == "opds"

    def should_be_logged_in(self):
        """REQUIRE_LOGIN 开启时的登录门禁：未登录且路径不在放行名单 → 一律拦下。

        - /api/* 回 200 {"err": "user.need_login"}：前端 $backend 有该错误的统一跳转；
        - /get/* 回 401：消费者是 <img>、EPUB 解包器、下载器，200 JSON 会被当成资源解析；
        - OPDS 目录与 OPDS 下载直链回 401 + WWW-Authenticate：客户端靠这个头弹 Basic 认证，
          配了账号即可通过（process_auth_header 已把 Basic 凭据换成 current_user），否则必须
          登录。下载直链挂在 /api/book/ 下，必须排在 /api/ 那条之前判定，否则阅读器会收到
          200 + JSON 并当成下载成功（上游 8ccab741）；
        - 其它页面（WAP 等）跳登录页，带上 next 便于回跳。
        放行时返回 False；拦下时不返回（写响应后 raise web.Finish）。
        """
        if not self.require_login_enabled():
            return False
        path = (self.request.path or "/").rstrip("/") or "/"
        # 只有 cookie 会话算"已登录"：?token=/X-MYBOOKS-TOKEN 走的是长期 podcast_token，
        # 它出现在 RSS URL、日志、Referer 里，不能当整站通行证用；但播客自己的页面/目录
        # 允许它（订阅页要把"我的收藏/待读"渲染出来，且链接里带的就是这个 token）。
        if self.current_user:
            if not getattr(self, "_login_via_token", False):
                return False
            if path.startswith("/podcast"):
                return False
        if login_gate_allowed(path):
            return False
        # 分享链接优先于 REQUIRE_LOGIN：分享页/分享 API 已在上面的放行名单里，
        # 书籍内容入口（阅读页、EPUB 解包、TXT 读取等）再按 book_id 校验分享授权。
        if self.share_grant_allows_path(path):
            return False
        # 带下载签名的书籍直链（formatter 给登录用户生成、10 秒有效、绑定用户+书+格式）：
        # 下载器(aria2/IDM)没有 cookie，但签名本身就是凭据，交给 BookDownload 自己校验。
        if path.startswith("/api/book/"):
            filename = path.rsplit("/", 1)[-1]
            if "." in filename and self.get_argument("dl", ""):
                bid, fmt = filename.split(".", 1)
                if self.parse_download_sign(self.get_argument("dl", ""), bid, fmt):
                    return False
        if path.startswith("/opds") or self.is_opds_acquisition(path):
            self.set_header("WWW-Authenticate", 'Basic realm="MyBooks"')
            self.set_status(401)
            raise web.Finish()
        if path.startswith("/api/"):
            self.write({"err": "user.need_login", "msg": _("请先登录")})
            self.set_status(200)
            raise web.Finish()
        if path.startswith("/get/"):
            self.set_status(401)
            raise web.Finish()
        # path 上面已归一化尾斜杠：/wap/ 会变成 /wap，所以必须同时覆盖无斜杠入口，
        # 否则 WAP 首页会掉到下面的 /login/（Nuxt SPA 登录页，老设备跑不动）。
        if path == "/wap" or path.startswith("/wap/"):
            self.redirect("/wap/login?next=" + quote(self.request.uri, safe=""))
            raise web.Finish()
        # 用 /login/（带尾斜杠）而不是 /login：后者会先被 StaticFileHandler 301 到 /login/，
        # 那个 301 只带路径、会把 ?next= 丢掉，用户登录后回不到原页面。
        self.redirect("/login/?next=" + quote(self.request.uri, safe=""))
        raise web.Finish()

    def should_be_installed(self):
        if CONF.get("installed", None) is False:
            self.write({"err": "not_installed"})
            self.set_status(200)
            raise web.Finish()

    def set_hosts(self):
        # site_url为完整路径，用于发邮件等 — 无条件信任反代透传的 Host / Proto（见 plan 域A）
        # 兼容多层 Nginx：优先取 X-Forwarded-Host（若含端口则直接使用），否则按 X-Forwarded-Port 补齐端口
        host = self.request.headers.get("X-Forwarded-Host", self.request.host).split(",")[0].strip()
        # 若 Host 未带端口但上游通过 X-Forwarded-Port 单独透传端口（如 NPM 的 $server_port），则补齐
        # 需兼容 IPv6： "[::1]" 无端口但含 ":"，"[::1]:50006" 含 "]:"
        if host.startswith("["):
            has_port = "]:" in host
        else:
            has_port = ":" in host
        if not has_port:
            x_port = self.request.headers.get("X-Forwarded-Port", "").split(",")[0].strip()
            if x_port and x_port not in ("80", "443"):
                # 仅当非标准端口时追加，避免 https://host:443 这类冗余
                host = f"{host}:{x_port}"
        proto = self.request.headers.get("X-Forwarded-Proto", self.request.headers.get("X-Scheme", self.request.protocol)).split(",")[0].strip()
        self.site_url = proto + "://" + host

        # 默认情况下，访问站内资源全部采用相对路径
        self.api_url = ""  # API动态请求地址
        self.cdn_url = ""  # 可缓存的资源，图片，文件

        # 如果设置有static_host配置，则改为绝对路径
        if CONF["static_host"]:
            self.api_url = proto + "://" + host
            self.cdn_url = proto + "://" + CONF["static_host"]
        CONF["site_url"] = self.site_url

        # 供不持有当前请求 handler 的代码（如后台任务里的 CoreAPI）读取最近一次请求算出的
        # cdn_url/api_url，见 webserver/base/global_state.py 顶部说明。
        get_global_state().update(cdn_url=self.cdn_url, api_url=self.api_url)

    def prepare(self):
        # 性能分析：记录请求开始时间
        from webserver.constants import ENABLE_PROFILE

        if CONF.get(ENABLE_PROFILE) is True:
            self._request_start_time = time.time()

        self.set_hosts()
        self.set_i18n()
        self.process_auth_header()
        self.process_auth_token()
        self.should_be_installed()
        self.should_be_invited()
        # 版权下架优先于登录门禁：下架书的内容请求（阅读/下载/推送/正文分片/音频）
        # 一律直接看到版权声明，不再跳登录页或走 401 Basic 认证。判定必须在任何
        # X-Accel-Redirect 设置之前完成，否则 nginx 直出后 Python 拦不住。
        book_takedown.check_path(self)
        self.should_be_logged_in()

    def set_i18n(self):
        accept = self.request.headers.get("Accept-Language", "")
        site_lang = CONF.get("site_language", "")
        lang = choose_language(site_language=site_lang, accept_language=accept)
        set_language(lang)

    def initialize(self):
        # 初始化数据库及calibre backends连接, 在main.py中构建
        ScopedSession = self.settings["ScopedSession"]
        self.sqlite_session = ScopedSession()  # new sql session
        self.calibre_db = self.settings["legacy"]  # calibre db backend
        self.calibre_db_cache = self.calibre_db.new_api  # calibre db cache backend
        self.build_time = self.settings["build_time"]
        self.default_cover = self.settings["default_cover"]
        self.admin_user = None
        self.cookies_cache = {}
        self._cached_user_id = None
        self._cached_username = None
        self._login_via_token = False  # 身份是否来自 ?token=/X-MYBOOKS-TOKEN（见 should_be_logged_in）
        self._request_start_time = None  # 用于性能分析

    def on_finish(self):
        # 性能分析：记录请求耗时
        from webserver.constants import ENABLE_PROFILE

        if CONF.get(ENABLE_PROFILE) is True and self._request_start_time is not None:
            try:
                duration = time.time() - self._request_start_time
                endpoint = self.request.path
                method = self.request.method

                # 记录到ProfileService
                from webserver.services.profile_service import get_profile_service

                profile_service = get_profile_service()
                profile_service.record_request(endpoint, method, duration)
            except Exception as e:
                logging.error(f"Failed to record profiling data: {e}")

        ScopedSession = self.settings["ScopedSession"]
        self.sqlite_session.close()
        ScopedSession.remove()

    def data_received(self, chunk):
        pass

    def static_url(self, path, **kwargs):
        if path.endswith("/"):
            prefix = self.settings.get("static_url_prefix", "/static/")
            return self.cdn_url + prefix + path
        else:
            return self.cdn_url + super(BaseHandler, self).static_url(path, **kwargs)

    def user_id(self):
        login_time = self.get_secure_cookie("lt")
        if not login_time:
            login_time = self.get_secure_cookie_timestamp("user_id")
        if not login_time or int(login_time) < int(time.time()) - 7 * 86400:
            # Double check with user_id cookie, 飞牛应用中Docker登录会使用旧的lt cookie
            login_time = self.get_secure_cookie_timestamp("user_id")
            if not login_time or int(login_time) < int(time.time()) - 7 * 86400:
                logging.info(
                    "Login time cookie is missing or expired. login_time: %s",
                    login_time,
                )
                return None
        uid = self.get_secure_cookie("user_id")
        return int(uid) if uid and uid.isdigit() else None

    def is_guest(self):
        return self.current_user is None

    def get_current_user(self):
        user_id = self.user_id()
        if user_id:
            user_id = int(user_id)
        user = self.sqlite_session.get(Reader, user_id) if user_id else None

        # Cache user id and username for logging to avoid detached instance errors
        if user:
            self._cached_user_id = user.id
            self._cached_username = user.username

        admin_id = self.get_secure_cookie("admin_id")
        if admin_id:
            self.admin_user = self.sqlite_session.get(Reader, int(admin_id))
        elif user and user.is_admin():
            self.admin_user = user
        return user

    def get_current_user_sync(self):
        if not self.current_user:
            return None
        user_id = self.user_id()
        if user_id:
            user_id = int(user_id)
        self.sqlite_session.expunge(self.current_user)
        user = self.sqlite_session.query(Reader).filter(Reader.id == user_id).first()
        return user

    def is_admin(self):
        if self.admin_user:
            return True
        if not self.current_user:
            return False
        return self.current_user.is_admin()

    def login_user(self, user, persist=True, set_cookie=True):
        # set_cookie=False 用于 ?token= 这类"凭据即身份"的场景：token 会出现在 RSS URL、
        # 日志、Referer 里，绝不能因为它给客户端种下 7 天有效的整站会话 cookie。
        if set_cookie:
            self.set_secure_cookie("user_id", str(user.id))
            self.set_secure_cookie("lt", str(int(time.time())))
        if not persist:
            return
        logging.info(
            "LOGIN: %s - %d - %s" % (self.request.remote_ip, user.id, user.username)
        )
        # 确保user对象在当前会话中，避免"already attached to session"错误
        user = self.sqlite_session.merge(user)
        user.access_time = datetime.datetime.now()
        user.extra["login_ip"] = self.request.remote_ip
        try:
            user.save()
        except Exception as e:
            logging.error("Failed to save user login info: %s" % str(e))
        pass

    def add_msg(self, status, msg):
        Message.cleanup_messages(self.user_id(), msg)
        m = Message(self.user_id(), status, msg)
        if m.reader_id:
            m.save()

    def pop_messages(self):
        if not self.current_user:
            return []
        messages = self.sqlite_session.query(Message).filter(Message.reader_id == self.current_user.id).all()
        for m in messages:
            self.sqlite_session.expunge(m)
        self.sqlite_session.query(Message).filter(Message.reader_id == self.current_user.id).delete(synchronize_session=False)
        self.sqlite_session.commit()
        return messages

    def _attached_user(self):
        user = self.current_user
        if user is not None and sa_inspect(user).detached:
            user = self.sqlite_session.merge(user)
            self.current_user = user
        return user

    def user_history(self, action, book):
        if not self.user_id():
            return
        user = self._attached_user()
        extra = user.extra
        history = extra.get(action, [])
        for val in history[:12]:
            if val["id"] == book["id"]:
                return
        val = {
            "id": book["id"],
            "title": book["title"],
            "timestamp": int(time.time()),
        }
        history.insert(0, val)
        # an item is about 100Byte, sqlite's max length is 32KB
        # we have five type of history, so make a average limit of max history
        ITEM_COUNT_LIMIT = 60  # = 32KB/100B/5
        extra[action] = history[:ITEM_COUNT_LIMIT]
        user.extra.update(extra)
        try:
            user.save()
        except Exception as e:
            logging.error("Failed to save user history: %s" % str(e))
        pass

    def increase_history_count(self, key):
        if not self.user_id():
            return
        if not key.endswith("_count"):
            key = key + "_count"
        user = self._attached_user()
        extra = user.extra
        count = extra.get(key, 0) + 1
        extra[key] = count
        user.extra.update(extra)
        try:
            user.save()
        except Exception as e:
            logging.error("Failed to save user history count: %s" % str(e))
        pass

    def last_modified(self, updated):
        """
        Generates a locale independent, english timestamp from a datetime
        object
        """
        lm = updated.strftime("day, %d month %Y %H:%M:%S GMT")
        day = {0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat"}
        lm = lm.replace("day", day[int(updated.strftime("%w"))])
        month = {
            1: "Jan",
            2: "Feb",
            3: "Mar",
            4: "Apr",
            5: "May",
            6: "Jun",
            7: "Jul",
            8: "Aug",
            9: "Sep",
            10: "Oct",
            11: "Nov",
            12: "Dec",
        }
        return lm.replace("month", month[updated.month])

    def sort(self, items, field, order):
        from calibre.library.caches import SortKey, SortKeyGenerator  # noqa: E0401

        class CSSortKeyGenerator(SortKeyGenerator):
            def __init__(self, fields, fm, db_prefs):
                SortKeyGenerator.__init__(self, fields, fm, None, db_prefs)

            def __call__(self, record):
                values = tuple(self.itervals(record))
                return SortKey(self.orders, values)

        field = self.calibre_db.data.sanitize_sort_field_name(field)
        if field not in self.calibre_db.field_metadata.sortable_field_keys():
            raise web.HTTPError(400, "%s is not a valid sort field" % field)

        keyg = CSSortKeyGenerator(
            [(field, order)], self.calibre_db.field_metadata, self.calibre_db.prefs
        )
        items.sort(key=keyg)

    def get_template_path(self):
        """获取模板路径"""
        return CONF.get("resource_path", "templates")

    def create_template_loader(self, template_path):
        """根据template_path创建相对应的Jinja2 Environment"""
        temp_path = template_path
        if isinstance(template_path, (list, tuple)):
            temp_path = template_path[0]

        env = BaseHandler._path_to_env.get(temp_path)
        if not env:
            logging.debug("create template env for [%s]" % template_path)
            _loader = FileSystemLoader(template_path)
            env = Environment(loader=_loader)
            env.filters["day"] = day_format
            env.filters["website"] = website_format
            # env.globals['gettext'] = _
            BaseHandler._path_to_env[temp_path] = env
        return env

    def get_audio_books_count(self):
        """Get the total count of books with audio files (书目录内 .audio/).

        这里是「实时全库扫盘」口径（左侧菜单的「有声书 N」）。书列表与分类 tab
        用的是 AudioBooksCache（事件驱动 + 兜底扫描），两者不同步时会出现
        「手工往 .audio/ 加了音频、统计立刻 +1、分类 tab 却不变」。盘既然已经
        扫过了，顺手把结果同步进缓存即可：集合真变化才 +version，下游聚合会
        跟着增量补齐，用户刷新一次页面就能看到新分类。同步失败不影响统计本身。
        """
        try:
            from webserver.base.audio_dir import find_audios_by_scanning_library
            found = find_audios_by_scanning_library()
            try:
                from webserver.handlers.audio import AudioBooksCache
                AudioBooksCache.sync_from_scan(found.keys())
            except Exception:
                logging.debug("sync audio cache from stats failed", exc_info=True)
            return len(found)
        except Exception:
            logging.exception("count audio books failed")
            return 0

    def reset_physical_books_count_cache(self):
        BaseHandler._physical_books_count_cache_time = 0

    def get_physical_books_count(self):
        # 统计实体书数量, 通过自定义栏位CALIBRE_COLUMN_BOOK_TYPE来统计，缓存5分钟
        now = time.time()
        if now - BaseHandler._physical_books_count_cache_time < 300:
            return BaseHandler._physical_books_count_cache
        from webserver.constants import CALIBRE_COLUMN_BOOK_TYPE, BOOK_TYPE_PHYSICAL

        try:
            result = self.calibre_db_cache.search(
                f"{CALIBRE_COLUMN_BOOK_TYPE}:={BOOK_TYPE_PHYSICAL}"
            )
            BaseHandler._physical_books_count_cache = len(result)
            BaseHandler._physical_books_count_cache_time = now
            return BaseHandler._physical_books_count_cache
        except Exception:
            logging.error(traceback.format_exc())
            return BaseHandler._physical_books_count_cache

    def get_all_readers(self):
        from webserver.models import Reader
        now = time.time()
        if now - BaseHandler._all_readers_cache_time < 180 and BaseHandler._all_readers_cache:
            return BaseHandler._all_readers_cache

        try:
            users = self.sqlite_session.query(Reader).all()
            user_list = {u.id: u.username for u in users}
            BaseHandler._all_readers_cache = user_list
            BaseHandler._all_readers_cache_time = now
            return user_list
        except Exception as e:
            logging.error("Get all readers failed: %s", e)
            return BaseHandler._all_readers_cache

    def render_string(self, template_name, **kwargs):
        """使用Jinja2模板引擎"""
        env = self.create_template_loader(self.get_template_path())
        t = env.get_template(template_name)
        namespace = self.get_template_namespace()
        namespace.update(kwargs)
        return t.render(**namespace)

    def html_page(self, template, *args, **kwargs):
        self.set_header("Cache-Control", "max-age=0")
        request = self.request
        request.user = self.current_user
        request.user_extra = {}
        request.admin_user = self.admin_user
        if request.user:
            request.user_extra = self.current_user.extra
            if not request.user.avatar:
                request.user.avatar = (
                    "//tva1.sinaimg.cn/default/images/default_avatar_male_50.gif"
                )
            else:
                request.user.avatar = request.user.avatar.replace("http://", "//")

        last_week = datetime.datetime.now() - datetime.timedelta(days=7)
        page_vars = {
            "db": self.calibre_db,
            "messages": self.pop_messages(),
            "count_all_users": self.sqlite_session.query(
                sql_func.count(Reader.id)
            ).scalar(),
            "count_hot_users": self.sqlite_session.query(sql_func.count(Reader.id))
            .filter(Reader.access_time > last_week)
            .scalar(),
            "IMG": self.cdn_url,
            "SITE_TITLE": CONF["site_title"],
        }
        vals = dict(*args, **kwargs)
        vals.update(page_vars)
        vals.update(vars())
        del vals["self"]
        self.write(self.render_string(template, **vals))

    async def run_calibre_read_async(self, func, *args, **kwargs):
        """只读 calibre 调用：不持 db_lock，读之间可并行，仍受 calibre 自带读写锁约束。

        只能用于 Cache 层的读 API（search、get_data_as_dict 等）；直接执行 backend.conn
        原生 SQL 的调用必须走 run_calibre_async，由 db_lock 串行。
        """
        return await self._run_calibre(func, args, kwargs, locked=False)

    async def run_calibre_async(self, func, *args, **kwargs):
        """在工作线程执行阻塞的 calibre 调用（get_data_as_dict / get_metadata 等）。

        导入、刮削等后台任务持有 calibre 独占写锁期间，ioloop 线程上的同步 calibre
        调用会排队等锁，连带冻住全站请求（包括不碰 calibre 的 /api/user/info）。
        跨线程正确性由 calibre Cache 自带的读写锁保证；db_lock 是与 static_files.
        ImageHandler 等线程化 calibre 访问共用的串行纪律（写者优先场景下避免读请求
        无序插队），不是正确性依赖。走 calibre_pool 专用池，与联网长任务隔离。
        func 内只允许 calibre 侧操作，绝不能触碰 sqlite_session（线程本地）。
        请求上下文（contextvars，含 i18n 请求语言）经 bind_threadpool_call 显式带入。
        """
        return await self._run_calibre(func, args, kwargs, locked=True)

    async def run_calibre_sql(self, sql, params=None):
        """在 Calibre 专用线程池中执行原生 SQL，避免在 ioloop 等待 db_lock。"""
        conn = self.calibre_db_cache.backend.conn
        if params is None:
            return await self.run_calibre_async(conn.get, sql)
        return await self.run_calibre_async(conn.get, sql, params)

    async def run_sqlite_async(self, func, *args, **kwargs):
        """在工作线程执行 func(session, *args, **kwargs)：重查询不占 ioloop。

        scoped_session 是线程本地的，工作线程里必须用自己的 session（用完 remove），
        绝不能带上 handler 的 self.sqlite_session 或绑在它上面的 ORM 对象——传 id，
        在 func 里重新查。func 只允许读；需要写库的请求仍留在 ioloop 线程。
        """
        scoped = self.settings["ScopedSession"]

        def _runner():
            try:
                return func(scoped(), *args, **kwargs)
            finally:
                scoped.remove()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(utils.calibre_pool, utils.bind_threadpool_call(_runner))

    async def _run_calibre(self, func, args, kwargs, locked):
        call = utils.bind_threadpool_call(func, *args, **kwargs)
        name = getattr(func, "__name__", "calibre_call")
        submitted = time.monotonic()
        monitor = PerfMonitor.instance()

        def _runner():
            with self.db_lock if locked else contextlib.nullcontext():
                started = time.monotonic()
                try:
                    return call()
                finally:
                    monitor.record_calibre(name, (started - submitted) * 1000.0, (time.monotonic() - started) * 1000.0)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(utils.calibre_pool, _runner)

    def get_book(self, book_id, fully=False, raise_exception=True):
        if fully:
            books = self.get_books(ids=[int(book_id)])
        else:
            books = self.get_books_simple(ids=[int(book_id)])
        if not books:
            if raise_exception:
                self.write({"err": "not_found", "msg": _("抱歉，这本书不存在")})
                self.set_status(200)
                raise web.Finish()
            else:
                return None
        return books[0]

    async def get_book_async(self, book_id, fully=False, raise_exception=True):
        """get_book 的非阻塞版：calibre 查询与 Item/收藏者合并都在工作线程，ioloop 只做内存合并。"""
        _ts = time.time()
        book_id = int(book_id)
        books = await self.run_calibre_read_async(self.calibre_db.get_data_as_dict, ids=[book_id])
        item_maps = await self._item_maps_async([book_id])
        if fully:
            books = self._merge_books_full(books, _ts, item_maps)
        else:
            books = self._merge_books_simple(books, _ts, item_maps)
        if not books:
            if raise_exception:
                self.write({"err": "not_found", "msg": _("抱歉，这本书不存在")})
                self.set_status(200)
                raise web.Finish()
            else:
                return None
        return books[0]

    def check_book_owner(self, book_id, msg=None):
        """管理员或书籍所有者才通过；无权限时返回前端错误 dict，否则返回 None。"""
        if not self.is_admin() and not self.is_book_owner(book_id, self.user_id()):
            return {"err": "user.no_permission", "msg": msg or _("无权限")}
        return None

    def require_book(self, book_id, owner=True, full=False,
                     not_found_err="params.book.invalid", not_found_msg=None):
        """取书 + 权限校验的公共前置。

        返回 (book, None) 表示通过；(None, 错误响应) 表示调用方应直接返回该响应。
        """
        book = self.get_book(book_id, fully=full, raise_exception=False)
        if not book:
            return None, {"err": not_found_err, "msg": not_found_msg or _("书籍不存在")}
        err = self.check_book_owner(book_id) if owner else None
        return (None, err) if err else (book, None)

    async def require_book_async(self, book_id, owner=True, full=False,
                                not_found_err="params.book.invalid", not_found_msg=None):
        """require_book 的非阻塞版（calibre 查询放工作线程）。"""
        book = await self.get_book_async(book_id, fully=full, raise_exception=False)
        if not book:
            return None, {"err": not_found_err, "msg": not_found_msg or _("书籍不存在")}
        err = self.check_book_owner(book_id) if owner else None
        return (None, err) if err else (book, None)

    def get_book_files(self, book_id):
        formats = self.calibre_db_cache.formats(book_id)
        return formats

    def is_book_owner(self, book_id, user_id):
        query = self.sqlite_session.query(Item)
        query = query.filter(Item.book_id == book_id)
        query = query.filter(Item.collector_id == user_id)
        return query.count() > 0

    def _build_custom_column_map(self):
        # The custom column is returned as int key, e.g. { 1: 'value' }
        # We need to convert it to { '#field': 'value' }
        if not hasattr(self, "_custom_column_map"):
            self._custom_column_map = {}
            for key, meta in self.calibre_db.field_metadata.items():
                if meta["is_custom"]:
                    self._custom_column_map[meta["colnum"]] = key

    def get_books_for_list(self, **kwargs):
        return self.get_books(**calibre_fast.list_kwargs(), **kwargs)

    async def get_books_for_list_async(self, **kwargs):
        _ts = time.time()
        books = await self.run_calibre_read_async(self.calibre_db.get_data_as_dict, **calibre_fast.list_kwargs(), **kwargs)
        item_maps = await self._item_maps_async([book["id"] for book in books])
        return self._merge_books_full(books, _ts, item_maps)

    def get_books(self, *args, **kwargs):
        _ts = time.time()
        books = self.calibre_db.get_data_as_dict(*args, **kwargs)
        logging.debug(
            "[%5d ms] select books from library (count = %d)"
            % (int(1000 * (time.time() - _ts)), len(books))
        )
        return self._merge_books_full(books, _ts)

    def _item_maps_offloaded(self, ids):
        scoped = self.settings["ScopedSession"]
        try:
            return self._item_maps(ids, scoped())
        finally:
            scoped.remove()

    async def _item_maps_async(self, ids):
        return await asyncio.get_running_loop().run_in_executor(utils.calibre_pool, utils.bind_threadpool_call(self._item_maps_offloaded, ids))

    def _item_maps(self, ids, session=None):
        session = session or self.sqlite_session
        stage = PerfMonitor.instance().stage
        empty_item = Item().to_dict()
        rows = []
        if ids:
            table = Item.__table__
            with stage("list.items_execute"):
                result = session.execute(table.select().where(table.c.book_id.in_(ids)))
            with stage("list.items_fetch"):
                rows = [dict(r._mapping) for r in result]
        needs_default = len(rows) < len(set(ids))
        collector_ids = {r["collector_id"] for r in rows if r["collector_id"] is not None}
        collectors = {}
        if collector_ids:
            with stage("list.collectors"):
                collectors = {
                    reader.id: reader.to_dict() for reader in session.query(Reader).filter(Reader.id.in_(collector_ids)).all()
                }
        maps = {}
        for row in rows:
            collector = collectors.get(row["collector_id"])
            if collector is None:
                needs_default = True
            maps[row["book_id"]] = (row, collector)
        if needs_default:
            empty_item["collector"] = (
                session.query(Reader).order_by(Reader.id).first()
            )
        result = {}
        for book_id, (row, collector) in maps.items():
            row["collector"] = dict(collector) if collector is not None else empty_item["collector"]
            result[book_id] = row
        return result, empty_item

    def _merge_books(self, books, _ts=None, item_maps=None, *,
                     rename_custom=True, drop_sole=False, mark_audio=False,
                     apply_read_range=False):
        """书籍 dict 与本站 Item 合并的公共实现（原三份合并逻辑的唯一来源）。

        rename_custom: 把 calibre 自定义列的数字 colnum 键改名为字段名
        drop_sole:    剔除「被他人设为独有」的书
        mark_audio:   命中音频书时打 has_audio=1
        apply_read_range: 按读者范围过滤（仍受 ALLOW_READ_RANGE_SETTING 开关约束）
        """
        if _ts is None:
            _ts = time.time()
        merge_start = time.perf_counter()

        if rename_custom:
            self._build_custom_column_map()

        audio_book_ids = set()
        if mark_audio:
            try:
                from webserver.handlers.audio import AudioBooksCache

                audio_book_ids = AudioBooksCache.get_audio_book_ids_set()
            except Exception as e:
                logging.error(f"Error getting audio book ids: {e}")

        maps, empty_item = item_maps or self._item_maps([book["id"] for book in books])

        soled_books = set()
        for book in books:
            if rename_custom:
                for colnum, key in self._custom_column_map.items():
                    if colnum in book:
                        book[key] = book.pop(colnum)
            # Check audio in the same loop to reduce iterations
            if book["id"] in audio_book_ids:
                book["has_audio"] = 1
            book_item = maps.get(book["id"], empty_item)
            # logging.info("book %d, sole = %s, collector = %s" % (book["id"], book_item["sole"], book_item["collector_id"]))
            if drop_sole and book_item["sole"] and book_item["collector_id"] != self.user_id():
                soled_books.add(book["id"])
            else:
                book.update(book_item)

        if len(soled_books) > 0 and len(books) > 0:
            books = [b for b in books if b["id"] not in soled_books]

        # Apply per-user reading range filter (only when read_limit is set)
        if apply_read_range and CONF.get(constants.ALLOW_READ_RANGE_SETTING, False):
            books = [b for b in books if self.is_book_visible(b)]

        PerfMonitor.instance().record_stage("list.merge_total", (time.perf_counter() - merge_start) * 1000)
        logging.debug(
            "[%5d ms] select books from database (count = %d)"
            % (int(1000 * (time.time() - _ts)), len(books))
        )
        return books

    def _merge_books_full(self, books, _ts=None, item_maps=None):
        return self._merge_books(
            books, _ts, item_maps, drop_sole=True, mark_audio=True, apply_read_range=True
        )

    def get_books_simple(self, *args, **kwargs):
        _ts = time.time()
        books = self.calibre_db.get_data_as_dict(*args, **kwargs)
        return self._merge_books_simple(books, _ts)

    def _merge_books_simple(self, books, _ts=None, item_maps=None):
        """get_books_simple 的 sqlite 合并段（同 _merge_books_full，只碰 sqlite_session）。"""
        return self._merge_books(books, _ts, item_maps)

    def get_all_fmts(self, book):
        fmts = []
        for fmt in constants.ACCEPTED_BOOK_FORMATS:
            fmt_key = f"fmt_{fmt}"
            if fmt_key in book and book[fmt_key]:
                fmts.append(fmt)
        return fmts

    @staticmethod
    def cascade_delete_book_data(db, book_id: int, commit: bool = True) -> None:
        cascade_delete_book_data(db, book_id, commit=commit)

    def delete_book(self, book_id, book_title):
        result = True
        try:
            self.cascade_delete_book_data(self.sqlite_session, book_id, commit=False)
            self.sqlite_session.commit()
        except Exception as e:
            self.sqlite_session.rollback()
            logging.error(f"删除ID为{book_id},名为《{book_title}》的书籍关联记录失败: {e}")
        try:
            self.calibre_db.delete_book(book_id)
            self.purge_book_thumbs(book_id)
            user_name = self.current_user.name if self.current_user else ""
            self.add_msg("success", _("%s删除了书籍《%s》") % (user_name, book_title))
            return {"err": "ok", "msg": _("删除成功")}
        except Exception as e:
            logging.error(f"删除书籍《{book_title}》失败: {e}")
            result = False
        return result

    @staticmethod
    def purge_book_thumbs(book_id):
        from webserver.handlers.static_files import ImageHandler
        cache = ImageHandler.thumb_cache()
        if cache:
            try:
                cache.remove_book(book_id)
            except Exception as e:
                logging.warning("purge thumbs of book %s failed: %s", book_id, e)

    async def delete_book_async(self, book_id, book_title):
        user_name = self.current_user.name if self.current_user else ""
        try:
            self.cascade_delete_book_data(self.sqlite_session, book_id, commit=False)
            self.sqlite_session.commit()
        except Exception as e:
            self.sqlite_session.rollback()
            logging.error(f"删除ID为{book_id},名为《{book_title}》的书籍关联记录失败: {e}")
        try:
            await self.run_calibre_async(self.calibre_db.delete_book, book_id)
        except Exception as e:
            logging.error(f"删除书籍《{book_title}》失败: {e}")
            return False
        await asyncio.get_running_loop().run_in_executor(utils.calibre_pool, self.purge_book_thumbs, book_id)
        self.add_msg("success", _("%s删除了书籍《%s》") % (user_name, book_title))
        return True

    def invalidate_recommendation(self):
        service = self.settings.get("recommend")
        if service is not None and self.user_id():
            service.invalidate_reader(self.user_id())

    def is_features_visible(self, features) -> bool:
        """Reading-range check for a recommendation BookFeatures."""
        return self.is_book_visible({"tags": features.tags, constants.CALIBRE_COLUMN_CATEGORY: features.category})

    def is_book_visible(self, book) -> bool:
        """Reading-range visibility of a book dict (needs "tags" and the category column) for the current user."""
        if not CONF.get(constants.ALLOW_READ_RANGE_SETTING, False):
            return True
        user = self.current_user
        if not user:
            # For guests, only show books without categories and tags
            return not book.get("tags") and not book.get(constants.CALIBRE_COLUMN_CATEGORY)
        # 管理员永远全可见：分类列表那边原本就有 is_admin() 豁免
        # （见本类 _filter_categories_by_reading_range），但这里漏了，
        # 导致管理员自己也被读者组拦下——详情页四个按钮全灰、书架缺书，
        # 表现出来非常像"权限系统坏了"，实际只是漏了这行。
        if self.is_admin():
            return True
        # v4.7 读者组：用生效限制判断（自身显式设置优先，否则回退组配置）。
        # 不再拿 read_limit 做前置判断：白名单+空条件的「严格模式」靠一份
        # 永不匹配的哨兵条件表达，read_limit 虽然有值，也必须走完整判定。
        from webserver.services.reader_group import ReaderGroupService
        if ReaderGroupService.effective_limits(user)["read_limit"] > 0:
            return self.is_book_in_reading_range(book, user)
        return True

    def is_library_restricted(self) -> bool:
        """当前登录用户是否被读者范围限制（v4.7 读者组）。

        书库统计（/api/library/stats*）是全库口径的数字：受限用户点开
        首页看到的「图书总数/作者数」与 unlimited 用户完全一样，等于把
        白名单外的藏书规模也泄露了。统计页对这类用户直接关闭（返回
        restricted 标记，前端隐藏面板），而不是给一份「过滤后的假数字」
        ——按人重算每月入库/空间占用代价太大，且数字本身就是全库事实。
        游客保持旧行为（本来就能看，与受限无关）。
        """
        user = self.get_current_user()
        if not user or self.is_admin():
            return False
        from webserver.services.reader_group import ReaderGroupService
        return ReaderGroupService.effective_limits(user)["read_limit"] > 0

    def is_book_in_reading_range(self, book, user) -> bool:
        """Check whether a book is accessible for the given user based on their reading range.

        read_limit values:
            0 - no restriction (always accessible)
            1 - whitelist: only books matching limit_categories or limit_tags are accessible
            2 - blacklist: books matching limit_categories or limit_tags are blocked

        v4.7 读者组：用户自己没显式设置限制时，回退到所属读者组的配置
        （见 services/reader_group.py）。
        """
        # 判定本体收敛到 services.reader_group.book_matches_limits：
        # 统计侧（左侧树 / 分类 / 标签云）也调它，保证「看到的数字」与
        # 「点进去能读到的书」是同一套规则。
        from webserver.services.reader_group import ReaderGroupService, book_matches_limits

        return book_matches_limits(book, ReaderGroupService.effective_limits(user))

    def search_for_books(self, query):
        self.search_restriction = ""
        return self.calibre_db.search_getting_ids(
            (query or "").strip(),
            self.search_restriction,
            sort_results=False,
            use_virtual_library=False,
        )

    def _filter_tags(self, tags):
        user = self.current_user
        if not user:
            return {}  # 未登录用户：隐藏所有标签
        # 管理员不过滤（与 is_book_visible 的豁免保持一致）：
        # 否则管理员侧边栏少一半标签，看起来像书目丢了。
        if user.is_admin():
            return tags
        # 必须走 effective_limits：以前只读 user.limit_tags，绕过了读者组，
        # 组员自身字段是 0 时标签云完全不过滤（meta.py 的 MetaList 早改过，
        # 这里漏了）。两处判定口径必须与 is_book_in_reading_range 一致。
        from webserver.services.reader_group import ReaderGroupService

        eff = ReaderGroupService.effective_limits(user)
        read_limit = int(eff.get("read_limit") or 0)
        if read_limit == 0:
            return tags
        limit_tags = set(filter(None, (eff.get("limit_tags") or "").split(",")))
        if not limit_tags:
            return tags
        if read_limit == 1:
            return {
                tag: count for tag, count in tags.items() if tag in limit_tags
            }  # 白名单
        return {
            tag: count for tag, count in tags.items() if tag not in limit_tags
        }  # 黑名单

    def query_all_tags_with_count(self):
        """全库标签计数，不做阅读范围过滤；查询失败直接抛异常。"""
        sql = """SELECT tags.name, count(distinct book) as count
        FROM tags left join books_tags_link on tags.id = books_tags_link.tag
        group by tags.id order by count desc"""
        version = self.library_version()
        tags = BaseHandler._catalog_cache.get("all_tags_with_count", version)
        if tags is None:
            with self.db_lock:
                tags = dict(
                    (i[0], i[1]) for i in self.calibre_db_cache.backend.conn.get(sql)
                )
            BaseHandler._catalog_cache.put("all_tags_with_count", version, tags)
        return dict(tags)

    async def query_all_tags_with_count_async(self):
        """全库标签计数的非阻塞版本。"""
        version = self.library_version()
        tags = BaseHandler._catalog_cache.get("all_tags_with_count", version)
        if tags is None:
            sql = """SELECT tags.name, count(distinct book) as count
            FROM tags left join books_tags_link on tags.id = books_tags_link.tag
            group by tags.id order by count desc"""
            tags = dict((row[0], row[1]) for row in await self.run_calibre_sql(sql))
            BaseHandler._catalog_cache.put("all_tags_with_count", version, tags)
        return dict(tags)

    def filter_tags_by_read_range(self, tags):
        if CONF.get(constants.ALLOW_READ_RANGE_SETTING, False):
            return self._filter_tags(tags)
        return tags

    def all_tags_with_count(self):
        # 受限用户直接取可见口径：全库 SQL 的 count(distinct book) 会把
        # 他读不到的书也数进去，标签云显示「小说 328」点进去只有 12 本。
        # 这里提前返回，也避免把个人口径写进类级 _query_fallback_cache。
        scoped = self.scoped_counts()
        if scoped:
            return {t: c for t, c in scoped["tag"].items() if c}
        cache_key = "all_tags_with_count"
        try:
            tags = self.query_all_tags_with_count()
            BaseHandler._query_fallback_cache[cache_key] = tags
        except Exception as e:
            tags = BaseHandler._query_fallback_cache.get(cache_key, {})
            logging.error("all_tags_with_count query failed: %s", str(e))
            if tags:
                logging.warning(
                    "all_tags_with_count fallback to cache, count=%d", len(tags)
                )

        # 过滤掉不在当前用户阅读范围的标签
        return self.filter_tags_by_read_range(tags)

    async def all_tags_with_count_async(self):
        # 权限签名在请求线程算，全库聚合丢线程池，避免首次命中时冻住 ioloop。
        key = self._scope_key()
        if key is not None:
            scoped = await self.run_calibre_read_async(self.scoped_counts, key)
            if scoped:
                return {t: c for t, c in scoped["tag"].items() if c}
        cache_key = "all_tags_with_count"
        try:
            tags = await self.query_all_tags_with_count_async()
            BaseHandler._query_fallback_cache[cache_key] = tags
        except Exception as e:
            tags = BaseHandler._query_fallback_cache.get(cache_key, {})
            logging.error("all_tags_with_count query failed: %s", str(e))
            if tags:
                logging.warning(
                    "all_tags_with_count fallback to cache, count=%d", len(tags)
                )
        return self.filter_tags_by_read_range(tags)

    def get_category_with_count(self, field, scope_key=None):
        orig_field = field  # language 分支会把 field 改成 lang_code，取聚合表要用原名
        # scope_key 由 async 入口在请求线程预先算好传进来，这里就不碰
        # current_user / cookie 了（本方法跑在 calibre 线程池里）。
        scoped = self.scoped_counts(scope_key)
        table = field if field in ["series"] else field + "s"
        name_column = "A.name"
        if field == "rating":
            name_column = "A.rating as name"
        elif field == "language":
            name_column = "A.lang_code as name"
            field = "lang_code"

        cache_key = f"get_category_with_count:{table}:{field}:{name_column}"
        args = {"table": table, "field": field, "name_column": name_column}
        sql = (
            """SELECT A.id, %(name_column)s, count(distinct book) as count
            FROM %(table)s as A left join books_%(table)s_link as B
            on A.id = B.%(field)s group by A.id"""
            % args
        )
        logging.debug(sql)
        try:
            with self.db_lock:
                rows = self.calibre_db_cache.backend.conn.get(sql)
            if scoped:
                # 保留数据库 id，只把 count 换成「该用户可见的书数」，并丢掉
                # 计数为 0 的条目（黑名单下整类都读不到时不该还列在那儿）。
                # 个人口径绝不写进类级 fallback 缓存，否则会串给别的用户。
                counts = scoped.get(orig_field) or {}
                items = [
                    {"id": a, "name": b, "count": counts.get(str(b), 0)}
                    for a, b, c in rows if counts.get(str(b), 0) > 0
                ]
                return items
            items = [{"id": a, "name": b, "count": c} for a, b, c in rows]
            BaseHandler._query_fallback_cache[cache_key] = items
            return items
        except Exception as e:
            if scoped:
                # 宁可空列表，也不把全库数字当成「我能读到的」发给受限用户
                return []
            cached = BaseHandler._query_fallback_cache.get(cache_key, [])
            logging.error("get_category_with_count query failed for %s: %s", cache_key, str(e))
            if cached:
                logging.warning(
                    "get_category_with_count fallback to cache for %s, count=%d",
                    cache_key,
                    len(cached),
                )
            return cached

    async def get_category_with_count_async(self, field):
        """Non-blocking counterpart to get_category_with_count()."""
        key = self._scope_key()
        return await self.run_calibre_async(self.get_category_with_count, field, key)

    def get_folder_count(self):
        """Return the number of distinct top-level folders in #folder."""
        from webserver.base.folder_helper import folder_counts, top_level_count

        with self.db_lock:
            return top_level_count(folder_counts(self.calibre_db_cache))

    def get_custom_category_count(self):
        """Return the number of distinct #category values **that books actually use**.

        §为什么要 JOIN§
        `custom_column_<n>` 是 calibre 的**值字典**，一本书从某分类移走后
        字典记录仍在（calibre 不清理）。原来用 `count(*)` 数的是字典行数，
        会把孤儿值算进去——用户实测「分类」显示的数字比真实分类多，
        而且和同一行的 tags / authors（`all_tags()` / `all_authors()` 都是
        「有书在用」的语义）对不上。

        口径必须与书籍侧判定（`book_category in limit_categories`）一致，
        否则管理员看到「5 个分类」，进读者组下拉只有 2 个，会以为漏了。
        """
        from webserver.constants import CALIBRE_COLUMN_CATEGORY

        if CALIBRE_COLUMN_CATEGORY not in self.calibre_db.field_metadata:
            return 0

        meta = self.calibre_db.field_metadata[CALIBRE_COLUMN_CATEGORY]
        colnum = meta["colnum"]
        table = f"custom_column_{colnum}"
        link_table = f"books_{table}_link"
        sql = (
            f"SELECT count(DISTINCT d.id) FROM {table} d "
            f"JOIN {link_table} l ON l.value = d.id "
            f"WHERE d.value IS NOT NULL AND d.value != ''"
        )
        cache_key = f"get_custom_category_count:{table}"
        try:
            with self.db_lock:
                rows = self.calibre_db_cache.backend.conn.get(sql)
            count = rows[0][0] if rows else 0
            BaseHandler._query_fallback_cache[cache_key] = count
            return count
        except Exception as e:
            cached = BaseHandler._query_fallback_cache.get(cache_key, 0)
            logging.error("get_custom_category_count query failed: %s", str(e))
            return cached

    def _filter_categories_by_reading_range(self, categories):
        """按当前用户的阅读范围过滤分类列表，管理员和未登录用户不过滤。

        迁自 book.py：有声书页的分类 tab 也用同一套分类，两处各写一份迟早
        出现「分类浏览页没有的分类、有声书页却有」的割裂。
        """
        user = self.current_user
        if not user:
            # 未登录用户只能看到未设置分类的书籍，因此只能看到一个空分类
            return []
        if self.is_admin():
            return categories
        # v4.7 读者组：自身未显式设置时回退组配置
        from webserver.services.reader_group import ReaderGroupService

        eff = ReaderGroupService.effective_limits(user)
        read_limit = eff["read_limit"]
        if read_limit == 0:
            return categories
        limit_cats = set(filter(None, eff["limit_categories"].split(',')))
        if not limit_cats:
            return categories
        if read_limit == 1:
            return [c for c in categories if c["name"] in limit_cats]
        # read_limit == 2: 黑名单
        return [c for c in categories if c["name"] not in limit_cats]

    async def catalog_categories(self):
        """全库分类骨架 `[{name, count}]`：可见口径计数，count 降序。

        §唯一口径§
        「分类」这个维度在全站只在这里定义一次：
          - /api/categories（分类浏览页）  → 直接用 + 补图标
          - /api/audiobooks/categories     → 用它定**分类名与顺序**，
            只把 count 换成「该分类下的有声书数」
        两页共用一份骨架，分类名、排序、图标才会天然一致；各算各的迟早
        对不上（用户实测反馈过「两个页面的分类不一样」）。
        调用方负责 category_icons.decorate，这里只管 name/count。
        """
        from webserver.constants import CALIBRE_COLUMN_CATEGORY

        if CALIBRE_COLUMN_CATEGORY not in self.calibre_db.field_metadata:
            return []

        meta = self.calibre_db.field_metadata[CALIBRE_COLUMN_CATEGORY]
        table = f"custom_column_{meta['colnum']}"
        link_table = f"books_{table}_link"

        sql = f"""
            SELECT t.value, count(l.book) as count
            FROM {table} t
            JOIN {link_table} l ON t.id = l.value
            GROUP BY t.id
            ORDER BY count DESC
        """

        version = self.library_version()
        rows = BaseHandler._catalog_cache.get(("categories", sql), version)
        if rows is None:
            rows = [(row[0], row[1]) for row in await self.run_calibre_sql(sql)]
            BaseHandler._catalog_cache.put(("categories", sql), version, rows)
        categories = [{"name": row[0], "count": row[1]} for row in rows]

        # 分类页每个 tab 后面的 (N) 以前是全库 SQL 的 count(l.book)，
        # 只按名字过滤了条目、没重算数字；读者组成员点进去看到的书
        # 远少于括号里的数。这里统一换成「可见口径」的计数。
        key = self._scope_key()
        scoped = (await self.run_calibre_read_async(self.scoped_counts, key)
                  if key is not None else None)
        if scoped:
            counts = scoped.get("categories") or {}
            # 注意：categories 里是 dict，不能用 `for name, _ in categories`——
            # 那样解包到的是键名 "name"/"count"，counts.get 永远取不到，
            # 受限用户的分类列表会被整段清空（历史 bug，测试 test_scoped_* 锁定）。
            filtered = []
            for item in categories:
                name = item["name"]
                n = counts.get(str(name), 0)
                if n > 0:
                    filtered.append({"name": name, "count": n})
            filtered.sort(key=lambda c: c["count"], reverse=True)
            categories = filtered
        elif CONF.get(constants.ALLOW_READ_RANGE_SETTING, False):
            categories = self._filter_categories_by_reading_range(categories)
        return categories

    def get_authors_book_ids_map(self):
        """返回 {author_name: set(book_id)}，基于calibre的authors表/link表。"""
        sql = """
            SELECT A.name, B.book
            FROM authors A
            JOIN books_authors_link B ON A.id = B.author
        """
        try:
            with self.db_lock:
                rows = self.calibre_db_cache.backend.conn.get(sql)
        except Exception as e:
            logging.error("get_authors_book_ids_map query failed: %s", str(e))
            return {}
        result = {}
        for name, book_id in rows:
            result.setdefault(name, set()).add(book_id)
        return result

    def get_translators_map(self):
        """返回 {book_id: [translator_name, ...]}，基于自定义字段#translators（逗号分隔）。"""
        if constants.CALIBRE_COLUMN_TRANSLATORS not in self.calibre_db.field_metadata:
            return {}
        meta = self.calibre_db.field_metadata[constants.CALIBRE_COLUMN_TRANSLATORS]
        table = f"custom_column_{meta['colnum']}"
        link_table = f"books_{table}_link"
        sql = f"""
            SELECT l.book, t.value
            FROM {table} t
            JOIN {link_table} l ON t.id = l.value
        """
        try:
            with self.db_lock:
                rows = self.calibre_db_cache.backend.conn.get(sql)
        except Exception as e:
            logging.error("get_translators_map query failed: %s", str(e))
            return {}
        result = {}
        for book_id, value in rows:
            names = [n.strip() for n in (value or "").split(",") if n.strip()]
            if names:
                result[book_id] = names
        return result

    def get_translator_book_ids(self, name):
        """返回#translators字段中含有指定译者姓名的书籍id集合。"""
        translators_map = self.get_translators_map()
        return {book_id for book_id, names in translators_map.items() if name in names}

    _catalog_cache = VersionedCache(max_items=32)
    _search_cache = VersionedCache(ttl=10, max_items=128)
    _search_cache_lite = VersionedCache(ttl=60, max_items=256)
    _home_cache = VersionedCache(ttl=60, max_items=64)

    @classmethod
    def search_cache(cls):
        return cls._search_cache_lite if perf.lite_on("LITE_HOME_CACHE") else cls._search_cache

    def library_version(self):
        return library_version(self.calibre_db_cache.backend)

    def _query_books_by_id(self):
        sql = "SELECT id FROM books order by id desc"
        with self.db_lock:
            return tuple(v[0] for v in self.calibre_db_cache.backend.conn.get(sql))

    def books_by_id(self):
        version = self.library_version()
        ids = BaseHandler._catalog_cache.get("books_by_id", version)
        if ids is None:
            ids = self._query_books_by_id()
            BaseHandler._catalog_cache.put("books_by_id", version, ids)
        return list(ids)

    async def books_by_id_async(self):
        version = self.library_version()
        ids = BaseHandler._catalog_cache.get("books_by_id", version)
        if ids is None:
            ids = await self.run_calibre_async(self._query_books_by_id)
            BaseHandler._catalog_cache.put("books_by_id", version, ids)
        return list(ids)

    def cached_search(self, query):
        version = self.library_version()
        cache = self.search_cache()
        ids = cache.get(query, version)
        if ids is None:
            # 先用独立的中文 FTS5 索引；索引不可用或查询含 calibre 高级语法时回退
            ids = get_search_index().search(query)
            if ids is None:
                ids = tuple(self.calibre_db_cache.search(query) or ())
            else:
                ids = tuple(ids)
            cache.put(query, version, ids)
        return list(ids)

    async def cached_search_async(self, query):
        version = self.library_version()
        cache = self.search_cache()
        ids = cache.get(query, version)
        if ids is None:
            # FTS 检索是同步 SQLite 读：查询长、索引大时会占住 ioloop，把同进程所有请求
            # 一起冻住。挪到 blocking_pool（联网长任务池）执行；search() 每次调用都新建
            # 独立的只读连接（SearchIndexService._connect_read，mode=ro）并在 finally 关闭，
            # 不复用、不跨线程共享连接，因此线程池执行是安全的。
            ids = await utils.run_in_threadpool(lambda: get_search_index().search(query))
            if ids is None:
                ids = tuple(await self.run_calibre_read_async(self.calibre_db_cache.search, query) or ())
            else:
                ids = tuple(ids)
            cache.put(query, version, ids)
        return list(ids)

    def get_argument_start(self):
        start = self.get_argument("start", 0)
        try:
            start = int(start)
        except:
            start = 0
        return max(0, start)

    def get_user_upload_cnt(self, user_id):
        return (
            self.sqlite_session.query(sql_func.count(Item.collector_id))
            .filter(Item.collector_id == user_id)
            .scalar()
        )

    def find_phy_books_by_isbn(self, isbn):
        """
        根据ISBN号查找已存在的实体书
        返回包含匹配图书ID的集合，如果没有找到则返回空集合
        """
        if not isbn or not isbn.strip():
            return set()

        isbn = isbn.strip()
        existing_books = set()

        query = f"(isbn:={isbn} OR isbn13:={isbn} OR isbn10:={isbn}) AND #book_type:=1"

        try:
            result = self.calibre_db_cache.search(query)
            if result:
                existing_books.update(result)
        except Exception as e:
            logging.error(f"Search query '{query}' failed: {e}")
        return existing_books

    def save_book_meta(self, book_id, fmt=None, cover=None):
        book = self.get_book(book_id, raise_exception=False)
        if not book:
            return {"err": "book.not_found", "msg": _("书籍不存在")}

        logging.info(f"[SAVE_META] save meta for book id:{book_id}, fmt:{fmt if fmt else 'ALL'}")

        # 检查是否有支持的格式（可按 fmt 过滤）
        supported_formats = []
        for f in utils.meta_writable_formats():
            if fmt and f != fmt.lower():
                continue
            fmt_key = f"fmt_{f}"
            if fmt_key in book:
                supported_formats.append((f, book[fmt_key]))

        if not supported_formats:
            if fmt:
                return {
                    "err": "format.not_supported",
                    "msg": _("书籍没有指定的格式：%s") % fmt.upper(),
                }
            return {
                "err": "format.not_supported",
                "msg": _("书籍没有支持的格式（需要 EPUB、AZW3、PDF、DJVU、CBZ 或 FB2）"),
            }
        try:
            from calibre.ebooks.metadata.meta import set_metadata

            # 获取当前书籍的元数据
            mi = self.calibre_db.get_metadata(book_id, index_is_id=True)
            if not mi:
                return {"err": "book.meta.not_found", "msg": _("无法获取书籍元数据")}

            success_formats = []
            failed_formats = []

            for f, file_path in supported_formats:
                try:
                    if not os.path.exists(file_path):
                        logging.warning(f"[SAVE_META] File not found: {file_path}")
                        failed_formats.append(f.upper())
                        continue

                    if mi.title:
                        mi.title_sort = utils.super_strip(mi.title)
                    if mi.authors:
                        mi.author_sort = utils.super_strip(mi.authors[0])
                    if not mi.comments:
                        mi.comments = "<>"
                    # 获取封面数据（cover 方法直接返回字节数据）
                    if cover:
                        cover_data = cover
                    else:
                        cover_data = self.calibre_db.cover(book_id, index_is_id=True)
                    if cover_data:
                        mi.cover_data = ("jpeg", cover_data)
                        logging.info(
                            f"[SAVE_META] Cover data added for {f.upper()}, size: {len(cover_data)} bytes"
                        )

                    # 将元数据写入文件（包含封面）
                    with open(file_path, "rb+") as stream:
                        set_metadata(stream, mi, stream_type=f)
                        if f == "fb2":
                            from webserver.base.book_files import supplement_fb2_fields

                            supplement_fb2_fields(stream, mi)

                    logging.info(
                        f"[SAVE_META] Successfully saved metadata to {f.upper()} file for book {book_id}"
                    )
                    success_formats.append(f.upper())
                except Exception as e:
                    logging.error(
                        f"[SAVE_META] Failed to save metadata to {f.upper()} file for book {book_id}: {e}"
                    )
                    logging.error(traceback.format_exc())
                    failed_formats.append(f.upper())

            if success_formats:
                msg = _("成功将元数据同步到文件：%s") % ", ".join(success_formats)
                if failed_formats:
                    msg += _("；失败：%s") % ", ".join(failed_formats)
                return {
                    "err": "ok",
                    "msg": msg,
                    "success_formats": success_formats,
                    "failed_formats": failed_formats,
                }
            else:
                return {
                    "err": "save.failed",
                    "msg": _("同步元数据失败：%s") % ", ".join(failed_formats),
                    "success_formats": [],
                    "failed_formats": failed_formats,
                }

        except Exception as e:
            logging.error(f"[SAVE_META] Error saving metadata for book {book_id}: {e}")
            logging.error(traceback.format_exc())
            return {"err": "internal", "msg": _("同步元数据时发生错误: %s") % str(e)}

    def _build_friends_with_favicon(self):
        """构建带有 favicon 图标信息的友情链接列表"""
        friends = CONF.get("FRIENDS", [])
        result = []
        need_loading_urls = []

        for friend in friends:
            href = friend.get("href", "")
            parsed = urlparse(href)
            domain = parsed.netloc
            # type 必须透传：前端 getFriendMeta 靠它决定图标与点击行为（电台=播放，其余=外链）
            # favicon 存网站真实图标 URL（前端 <img> 优先用它；取不到时回退 mdi 图标）
            # icon 字段保留兼容旧前端（同样为 favicon URL）
            item = {
                "text": friend.get("text", ""),
                "href": href,
                "type": friend.get("type", "website"),
                "icon": "",
                "favicon": "",
            }

            if domain:
                icon = ResourceService.check_favicon(domain)
                if icon is None:
                    # 文件不存在，需要加载
                    need_loading_urls.append(href)
                elif icon:
                    item["icon"] = icon
                    item["favicon"] = icon

            result.append(item)

        if need_loading_urls:
            ResourceService().load_favicons(need_loading_urls)

        return result

    _stats_cache = VersionedCache(ttl=60, max_items=4)
    # 受限用户的「可见口径」聚合，按 (用户, 生效规则, 书库版本) 缓存。
    # 组规则改了但书库没动时 library_version 不变，故额外给 120s TTL 兜底。
    _scoped_cache = VersionedCache(ttl=120, max_items=64)

    def _scope_key(self):
        """当前用户是否受阅读范围限制：受限返回可缓存签名，否则 None（走全库快路）。

        游客保持既有行为（is_library_restricted 同样不拦游客），管理员永远全库。
        """
        if not CONF.get(constants.ALLOW_READ_RANGE_SETTING, False):
            return None
        user = self.current_user
        if not user or self.is_admin():
            return None
        from webserver.services.reader_group import ReaderGroupService

        eff = ReaderGroupService.effective_limits(user)
        if eff["read_limit"] == 0:
            return None
        return (self.user_id(), eff["read_limit"],
                eff["limit_categories"] or "", eff["limit_tags"] or "")

    def _build_scoped_counts(self, key):
        """按「这个用户真正读得到的书」重算所有统计口径。

        以前统计走全库 SQL（count(distinct book)），列表走 is_book_visible，
        分组成员登录后左侧树显示全库规模、点进去却只有白名单里的几本。
        这里一次性遍历书库、用与列表同源的 book_matches_limits 判定，
        再从可见书籍聚合出左侧树与各类元数据列表需要的数字。
        只碰 calibre 侧对象，可被 run_calibre_read_async 丢进线程池执行。
        """
        from collections import Counter
        from webserver.base.folder_helper import split_folder
        from webserver.constants import (
            CALIBRE_COLUMN_CATEGORY, CALIBRE_COLUMN_FOLDER,
            CALIBRE_COLUMN_BOOK_TYPE, BOOK_TYPE_PHYSICAL,
        )
        from webserver.services.reader_group import book_matches_limits

        _uid, read_limit, cats, tags = key
        eff = {"read_limit": read_limit, "limit_categories": cats, "limit_tags": tags}

        ids = list(self.calibre_db_cache.all_book_ids())
        books = (self.calibre_db.get_data_as_dict(ids=ids, **calibre_fast.list_kwargs())
                 if ids else [])
        # get_data_as_dict 用整数 colnum 作自定义列的 key，判定函数认字段名。
        cmap = {m["colnum"]: k for k, m in self.calibre_db.field_metadata.items()
                if m["is_custom"]}

        tag_c, author_c, series_c, publisher_c = Counter(), Counter(), Counter(), Counter()
        category_c, language_c, rating_c, folder_c = Counter(), Counter(), Counter(), Counter()
        visible_ids = set()
        for b in books:
            for colnum, name in cmap.items():
                if colnum in b and name not in b:
                    b[name] = b[colnum]
            if not book_matches_limits(b, eff):
                continue
            bid = b["id"]
            visible_ids.add(bid)
            for t in (b.get("tags") or []):
                tag_c[t] += 1
            for a in (b.get("authors") or []):
                author_c[a] += 1
            if b.get("series"):
                series_c[b["series"]] += 1
            if b.get("publisher"):
                publisher_c[b["publisher"]] += 1
            cat = b.get(CALIBRE_COLUMN_CATEGORY) or ""
            if cat:
                category_c[str(cat)] += 1
            for lang in (b.get("languages") or []):
                language_c[lang] += 1
            if b.get("rating") is not None:
                rating_c[str(b["rating"])] += 1
            fld = b.get(CALIBRE_COLUMN_FOLDER) or ""
            parts = split_folder(fld) if fld else []
            if parts:
                folder_c[parts[0]] += 1

        try:
            physical_ids = set(self.calibre_db_cache.search(
                f"{CALIBRE_COLUMN_BOOK_TYPE}:={BOOK_TYPE_PHYSICAL}") or [])
        except Exception:
            physical_ids = set()
        try:
            from webserver.handlers.audio import AudioBooksCache
            audio_ids = set(AudioBooksCache.get_audio_book_ids_set() or ())
        except Exception:
            audio_ids = set()

        stats = {
            "books": len(visible_ids),
            "tags": len(tag_c),
            "authors": len(author_c),
            "audiobooks": len(audio_ids & visible_ids),
            "publishers": len(publisher_c),
            "series": len(series_c),
            "categories": len(category_c),
            "folders": len(folder_c),
            "physicals": len(physical_ids & visible_ids),
            "mtime": self.calibre_db.last_modified().strftime("%Y-%m-%d"),
        }
        return {
            "stats": stats,
            "book_ids": frozenset(visible_ids),
            "tag": dict(tag_c),
            "author": dict(author_c),
            "series": dict(series_c),
            "publisher": dict(publisher_c),
            "categories": dict(category_c),
            "language": dict(language_c),
            "rating": dict(rating_c),
            "folder": dict(folder_c),
        }

    def scoped_counts(self, key=None):
        """受限用户返回可见口径聚合，不受限返回 None。命中缓存时是纯内存操作。"""
        if key is None:
            key = self._scope_key()
        if key is None:
            return None
        version = self.library_version()
        cached = BaseHandler._scoped_cache.get(key, version)
        if cached is not None:
            return cached
        try:
            result = self._build_scoped_counts(key)
        except Exception:
            # 统计是旁支，任何异常都降级回全库口径，绝不能让 /api/user/info 500。
            logging.exception("[scoped-counts] aggregate failed, fallback to global stats")
            return None
        BaseHandler._scoped_cache.put(key, version, result)
        return result

    def _library_stats(self):
        db = self.calibre_db
        return {
            "books": db.count(),
            "tags": len(db.all_tags()),
            "authors": len(db.all_authors()),
            "audiobooks": self.get_audio_books_count(),
            "publishers": len(db.all_publishers()),
            "series": len(db.all_series()),
            "categories": self.get_custom_category_count(),
            "folders": self.get_folder_count(),
            "physicals": self.get_physical_books_count(),
            "mtime": db.last_modified().strftime("%Y-%m-%d"),
        }

    def _sys_info_with(self, stats):
        from sqlalchemy import func

        last_week = datetime.datetime.now() - datetime.timedelta(days=7)
        count_all_users = self.sqlite_session.query(func.count(Reader.id)).scalar()
        count_hot_users = (
            self.sqlite_session.query(func.count(Reader.id))
            .filter(Reader.access_time > last_week)
            .scalar()
        )
        info = dict(stats, users=count_all_users, version=VERSION, active=count_hot_users, performanceMode=perf.CONF.get("PERFORMANCE_MODE", "normal"), lite={"homeCollapse": perf.lite_on("LITE_HOME_COLLAPSE")})
        info.update(
            {
                "installed": CONF.get("installed", False),
                "upgrable": CONF.get(UPGRABLE_REVISION, ""),
                "title": CONF["site_title"] if "site_title" in CONF else "MyBooks",
                "language": CONF["site_language"] if "site_language" in CONF else "",
                # 站点时区的**解析结果**（不是设置项原文）：前端要把「今天」按同一时区算，
                # 否则浏览器与服务端时区不同（如站点设为 UTC）时热力图/日历会高亮错一格。
                # timezone 是 IANA 名给 Intl 用，timezoneLabel 是给界面显示的现成串。
                "timezone": site_time.resolve_timezone_name(),
                "timezoneLabel": site_time.timezone_label(),
                "theme": CONF["site_theme"] if "site_theme" in CONF else "light",
                # 管理员配置的「网站默认访问链接」（反代/内网访问时让对外链接指向对外域名）：
                # 非空时前端生成分享链接、二维码与 OPDS/WebDAV 说明页地址用它，
                # 留空则回退到当前访问地址
                "siteUrl": utils.normalize_site_url(CONF.get("SITE_URL", "")),
                "maxUploadSize": (
                    CONF["MAX_UPLOAD_SIZE"] if "MAX_UPLOAD_SIZE" in CONF else "100MB"
                ),
                "chunkUploadSize": (
                    CONF["CHUNK_UPLOAD_SIZE"] if "CHUNK_UPLOAD_SIZE" in CONF else "0MB"
                ),
                "icon": CONF["site_icon"] if "site_icon" in CONF else "favicon_1",
                "socials": CONF["SOCIALS"],
                "friends": self._build_friends_with_favicon(),
                "footer": CONF["FOOTER"] if "FOOTER" in CONF else "",
                "footer_watermark": CONF.get("FOOTER_WATERMARK", ""),
                "header": CONF["HEADER"] if "HEADER" in CONF else "",
                "allow": self.allow_flags(),
                "indexPage": CONF.get("INDEX_PAGE_TYPE", "index"),
                "epub_viewer": CONF.get("EPUB_VIEWER", "MyReader"),
                "defaultPageSize": CONF.get("DEFAULT_PAGE_SIZE", 60),
                "aiEnabled": CONF.get("AI_ENABLED", False),
                "standalone": CONF.get("STANDALONE", False),
                "hide_project_links": CONF.get("HIDE_PROJECT_LINKS", False),
                # 「反馈」弹窗内容（build.22 起管理员可改）：notice 为空时前端回退默认文案
                "feedback_qr_url": CONF.get("FEEDBACK_QR_URL", "/logo/link_gongzhonghao.jpg"),
                "feedback_notice": CONF.get("FEEDBACK_NOTICE", ""),
                "feedback_github_url": CONF.get("FEEDBACK_GITHUB_URL", "https://github.com/PoxenStudio/mybooks/issues"),
                "enable_podcast_service": CONF.get("ENABLE_PODCAST_SERVICE", False),
                # 书单卡片封面条是否自动轮播（站长级总开关，默认开）
                "booklist_cover_scroll": CONF.get("ENABLE_BOOKLIST_COVER_SCROLL", True),
                "enable_opds_service": CONF.get("ENABLE_OPDS_SERVICE", True),
                "enable_webdav_service": CONF.get("ENABLE_WEBDAV_SERVICE", True),
                # 读取期下发：迁移标记未置位时补齐旧默认缺的 authors/friends/booklists，
                # 置位后以 stored 为权威原样返回；两种情况都不改写用户存的配置（见 sidebar.py）
                "sidebar_items": get_sidebar_items(CONF),
                "invited_enabled": self.need_invited(),
                "showUserInfo": CONF.get("ENABLE_AUTHOR_INFO", False),
                "mynexus_enabled": CONF.get("ENABLE_MYNEXUS", False),
            }
        )
        return info

    def get_sys_info(self):
        # 受限用户不能吃全库共享缓存：左侧树那些 count 必须按他自己读得到的书算，
        # 否则「标签 328 / 作者 156」与点进去的列表永远对不上。
        key = self._scope_key()
        if key is not None:
            scoped = self.scoped_counts(key)
            if scoped:
                return self._sys_info_with(scoped["stats"])
        return self._sys_info_with(self._library_stats())

    async def get_sys_info_async(self):
        version = self.library_version()
        key = self._scope_key()
        if key is not None:
            scoped = await self.run_calibre_read_async(self.scoped_counts, key)
            stats = scoped["stats"] if scoped else await self.run_calibre_read_async(self._library_stats)
        else:
            stats = BaseHandler._stats_cache.get("stats", version)
            if stats is None:
                stats = await self.run_calibre_read_async(self._library_stats)
                BaseHandler._stats_cache.put("stats", version, stats)
        return self._sys_info_with(stats)


class ListHandler(BaseHandler):
    def get_item_books(self, category, name, max_count=0, extra_ids=None):
        item_id = self.calibre_db_cache.get_item_id(category, name)
        ids = set(self.calibre_db.get_books_for_category(category, item_id)) if item_id else set()
        if extra_ids:
            ids |= set(extra_ids)
        return self.load_books_by_ids(ids, max_count)

    def load_books_by_ids(self, ids, max_count=0):
        if not ids:
            return []

        if (max_count > 0) and (len(ids) > max_count):
            ids = set(random.sample(list(ids), max_count))
        books = self.calibre_db.get_data_as_dict(ids=ids, **calibre_fast.list_kwargs())

        # 合并逻辑收敛到 _merge_books：原来这里先查一遍 sole 书籍、再查一遍
        # 剩余书籍的 Item（同一个 Item 查两次），现在复用 _item_maps 一次取齐。
        # 自定义列改名与阅读范围过滤仍只在 ALLOW_READ_RANGE_SETTING 开启时生效。
        read_range = CONF.get(constants.ALLOW_READ_RANGE_SETTING, False)
        return self._merge_books(
            books,
            rename_custom=read_range,
            drop_sole=True,
            apply_read_range=read_range,
        )

    def do_sort(self, items, field, ascending):
        items.sort(key=lambda x: x[field], reverse=not ascending)

    def sort_books(self, items, field):
        fm = self.calibre_db.field_metadata
        keys = frozenset(fm.sortable_field_keys())
        if field in keys:
            ascending = fm[field]["datatype"] not in (
                "rating",
                "datetime",
                "series",
                "timestamp",
            )
            self.do_sort(items, field, ascending)
        else:
            self.do_sort(items, "id", False)
        return None

    def _sort_ids_by_title(self, ids):
        sort_map = self.calibre_db_cache.all_field_for("sort", ids, "")
        return sorted(ids, key=lambda i: sort_map.get(i) or "")

    def _sort_keys_by_title(self, ids):
        """返回 (排序键, id) 升序对，供键集分页定位下一页边界。"""
        sort_map = self.calibre_db_cache.all_field_for("sort", ids, "")
        return sorted((sort_map.get(i) or "", i) for i in ids)

    async def get_book_list(
        self, all_books, ids=None, title=None, sort_fields=None, include_comments=True
    ):
        """Get a list of books.

        分页兼容两种方式：
        - 旧：`start`/`size`（offset），不传游标时行为完全不变；
        - 新：`after`（不透明游标，也接受 `cursor` 作为别名），响应带 `next_cursor`。
        键集分页只在按 id / title 排序时生效，因为它们有稳定的全序。
        """
        start = self.get_argument_start()
        cursor = self.get_argument("after", "") or self.get_argument("cursor", "")
        next_cursor = None
        page_size = CONF.get("DEFAULT_PAGE_SIZE", 60)
        max_size = int(CONF.get("MAX_PAGE_SIZE", 200))
        if perf.lite_on("LITE_PAGE_SIZE"):
            max_size = min(max_size, 60)
        if perf.lite_on("LITE_LIST_SLIM"):
            include_comments = False
        try:
            size = int(self.get_argument("size", "0").strip())
        except (TypeError, ValueError):
            # 公开列表接口，size 来自 URL：非法值按默认分页处理，不要抛 ValueError
            size = 0
        size = min(max(size, 0), max_size)
        delta = min(size if size > 0 else max(page_size, 60), max_size)

        if ids:
            ids = list(ids)
            count = len(ids)
            count = await self._adjust_total_excluding_sole(ids, count)
            if count > 3 * size and sort_fields == "title":
                sort_fields = "id"

            if sort_fields == "id":
                # 按照id从大到小排列（降序）
                ids.sort(reverse=True)
                pos = start
                last_id = parse_id_cursor(cursor, "id")
                if last_id is not None:
                    # ids 降序，找第一个小于上一页末尾的 id
                    pos = len(ids)
                    for i, v in enumerate(ids):
                        if v < last_id:
                            pos = i
                            break
                page_ids = ids[pos : pos + delta]
                books = await self.get_books_for_list_async(ids=page_ids)
                self.do_sort(books, "id", False)
                if books and pos + delta < len(ids):
                    next_cursor = encode_cursor({"k": "id", "id": books[-1]["id"]})
            elif sort_fields == "title":
                # 按 (排序键, id) 升序排列，排序键相同的书也能稳定翻页
                pairs = await self.run_calibre_read_async(self._sort_keys_by_title, ids)
                pos = start
                cur = decode_cursor(cursor)
                if cur and cur.get("k") == "title":
                    try:
                        last_key = (cur.get("s") or "", int(cur.get("id")))
                    except (TypeError, ValueError):
                        last_key = None
                    if last_key is not None:
                        pos = bisect.bisect_right(pairs, last_key)
                page_pairs = pairs[pos : pos + delta]
                page_ids = [pid for _key, pid in page_pairs]
                by_id = {b["id"]: b for b in await self.get_books_for_list_async(ids=page_ids)}
                books = [by_id[i] for i in page_ids if i in by_id]
                if page_pairs and pos + delta < len(pairs):
                    key, pid = page_pairs[-1]
                    next_cursor = encode_cursor({"k": "title", "s": key, "id": pid})
            else:
                # 按照输入的ids顺序排序（相关度等无稳定全序的场景，不支持游标）
                page_ids = ids[start : start + delta]
                by_id = {b["id"]: b for b in await self.get_books_for_list_async(ids=page_ids)}
                books = [by_id[i] for i in page_ids if i in by_id]
        else:
            count = len(all_books)
            books = all_books[start : start + delta]

        return {
            "err": "ok",
            "title": title,
            "total": count,
            "next_cursor": next_cursor,
            "books": [self.fmt(b, include_comments=include_comments, strip_comments=True) for b in books],
        }

    _sole_hidden_cache = {}

    async def _adjust_total_excluding_sole(self, ids, count):
        """修正 total：`_merge_books_full` 会把「他人独占」的书从当页剔除，
        但 total 仍按原始 id 数算，导致受限用户看到多出来的尾页、点进去是空白。
        这里只做独占这一项（一条 SQL + 30s 缓存），阅读范围过滤需要 tags/category，
        代价随全库行数增长，留待实测后再决定是否进程内预计算。
        """
        hidden = await self._sole_hidden_ids()
        if not hidden:
            return count
        removed = 0
        for book_id in ids:
            if book_id in hidden:
                removed += 1
        return max(0, count - removed)

    def _query_sole_hidden_ids(self, session, user_id):
        """他人独占的 book id 集合（只读）。

        用 book_id 而不是 book：Item 模型的主键列名是 book_id，写成 Item.book 会抛
        AttributeError，被上层 except 吞掉后修正静默失效（total 一直没扣）。
        签名遵循 run_sqlite_async 约定（session 由调用方传入，工作线程用自己的 session）。
        """
        query = session.query(Item.book_id).filter(Item.sole == 1)
        if user_id:
            query = query.filter(Item.collector_id != user_id)
        return {row[0] for row in query.all()}

    async def _sole_hidden_ids(self):
        """他人独占的 book id 集合；按 (用户, 库版本) 缓存 30s。

        查询走 run_sqlite_async（工作线程 + 独立 session），不占 ioloop：
        10 万级 items 表上这条 ORM 查询实测 5ms（进程内首次 ~90ms），
        留在事件循环里会直接卡住同一进程的其它请求。缓存只在 ioloop 读写。
        查询失败返回 None，让调用方退回未修正的 total（不要因为统计失败影响列表本身）。
        """
        try:
            version = self.library_version()
        except Exception:
            version = None
        key = (self.user_id(), version)
        now = time.time()
        cached = self._sole_hidden_cache.get(key)
        if cached and now - cached[0] < 30:
            return cached[1]
        try:
            hidden = await self.run_sqlite_async(self._query_sole_hidden_ids, self.user_id())
        except Exception as exc:
            logging.debug("query sole hidden ids failed: %s", exc)
            return None
        if len(self._sole_hidden_cache) > 64:
            self._sole_hidden_cache.clear()
        self._sole_hidden_cache[key] = (now, hidden)
        return hidden

    async def render_book_list(self, all_books, ids=None, title=None, sort_fields=None):
        # 不要在这里再套 @js：调用方（RecentBook/SearchBook）本身就是 @js 的 async get，
        # 内外两层都写响应会让外层在 finish() 之后再 write()，每个请求都抛一次
        # "Cannot write() after finish()"（客户端数据正常，日志里是 Uncaught exception）。
        return await self.get_book_list(all_books, ids, title, sort_fields)

    def fmt(self, b, include_comments=True, strip_comments=False):
        return BookFormatter(self, b).format(include_comments=include_comments, strip_comments=strip_comments)
