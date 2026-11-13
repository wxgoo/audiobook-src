#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
(PoxenStudio)资源服务，负责下载和管理好友链接及资源链接的 favicon
"""
import logging
import requests
import os
import time
from urllib.parse import urlparse
from webserver.services import AsyncService
from webserver.constants import CHROME_HEADERS

# Favicon 存储根目录
RESOURCES_DIR = "/data/books/resources"
FRIENDS_FAVICON_DIR = os.path.join(RESOURCES_DIR, "friends")
AUTHOR_AVATAR_DIR = os.path.join(RESOURCES_DIR, "author_avatar")


class ResourceService(AsyncService):
    _last_check_times: dict[int, float] = {}
    _checking: bool = False

    def __init__(self):
        super().__init__()
        os.makedirs(FRIENDS_FAVICON_DIR, exist_ok=True)
        os.makedirs(AUTHOR_AVATAR_DIR, exist_ok=True)

    @staticmethod
    def get_favicon_path(domain, ext=".ico"):
        return os.path.join(FRIENDS_FAVICON_DIR, "%s%s" % (domain, ext))

    @staticmethod
    def check_favicon(uri):
        if uri.startswith("http://") or uri.startswith("https://"):
            domain = urlparse(uri).netloc
        else:
            domain = uri

        is_svg = False
        path = ResourceService.get_favicon_path(domain)
        if not os.path.exists(path):
            path = ResourceService.get_favicon_path(domain, ".svg")
            if not os.path.exists(path):
                return None
            is_svg = True

        if os.path.getsize(path) == 0:
            return ""
        return "/api/favicon/%s.%s" % (domain, "svg" if is_svg else "ico")

    @staticmethod
    def clear_favicons():
        """清掉无效图标文件：0 字节标记，以及「假图标」——抓取时把流地址
        （电台友链常见 /stream.m3u8、/radio.mp3）当图片存下来的非图片内容。
        存量假图标几百字节到几 MB 不等，只按大小阈值清不掉，按内容魔数判。"""
        for filename in os.listdir(FRIENDS_FAVICON_DIR):
            path = os.path.join(FRIENDS_FAVICON_DIR, filename)
            if not os.path.isfile(path) or not os.path.exists(path):
                continue
            with open(path, "rb") as f:
                head = f.read(16)
            is_svg = filename.lower().endswith(".svg")
            if not ResourceService._sniff_image(head, "image/svg+xml" if is_svg else ""):
                size = os.path.getsize(path)
                os.remove(path)
                logging.info("Removed invalid favicon file: %s (%d bytes)", filename, size)

    @staticmethod
    def _sniff_image(content, content_type=""):
        """按魔数判断内容是不是浏览器 <img> 能解码的图片。
        返回 'svg' / 'img' / None。只看头部最多 16 字节。"""
        if content.startswith(b"\x00\x00\x01\x00"):  # .ico
            return "img"
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return "img"
        if content.startswith(b"GIF8"):
            return "img"
        if content.startswith(b"\xff\xd8\xff"):  # jpeg
            return "img"
        if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
            return "img"
        if content_type.lower().startswith("image/svg") or content.lstrip()[:4] in (b"<svg", b"<?xm"):
            return "svg"
        return None

    @AsyncService.register_service
    def load_favicons(self, urls, flag=0):
        if self._checking:
            logging.info("Favicon check skipped due to checking in progress")
            return
        if flag not in self._last_check_times:
            self._last_check_times[flag] = 0

        if time.time() - self._last_check_times[flag] < 3600:
            logging.info("Favicon check skipped (checked recently)")
            return

        self._checking = True
        if time.time() - self._last_check_times[flag] >= 3600:
            ResourceService.clear_favicons()
        self._last_check_times[flag] = time.time()

        for url in urls:
            domain = urlparse(url).netloc
            if not domain:
                continue
            if os.path.exists(ResourceService.get_favicon_path(domain)):
                continue
            ResourceService.fetch_favicon(domain)
        self._checking = False

    @staticmethod
    def fetch_favicon(domain):
        """抓单个域名的 favicon 并落盘。返回 'saved' / 'empty'。

        纯同步、无装饰器，便于单测直接调用（load_favicons 外面套了
        @AsyncService.register_service，测试里会被丢进线程池）。
        """
        # favicon 一律取域名根：带路径的友链地址多是流媒体/页面
        # （电台常见 /stream.m3u8、/radio.mp3），拿它当图片请求只会把
        # m3u8 文本或音频字节存成「假图标」——文件非空即被认为抓到，
        # 前端 <img> 解码失败又不回落，于是大面积永久空白。
        favicon_url = "https://%s/favicon.ico" % domain
        path = ResourceService.get_favicon_path(domain)
        logging.info("Downloading favicon from: %s", favicon_url)
        try:
            resp = requests.get(
                favicon_url,
                timeout=10,
                headers=CHROME_HEADERS,
                allow_redirects=True,
            )
            kind = (
                ResourceService._sniff_image(resp.content, resp.headers.get("Content-Type", ""))
                if resp.status_code == 200 and resp.content
                else None
            )
            if kind:
                path = ResourceService.get_favicon_path(domain, ".svg" if kind == "svg" else ".ico")
                with open(path, "wb") as f:
                    f.write(resp.content)
                logging.info("Saved favicon for %s (%d bytes)", domain, len(resp.content))
                return "saved"
            # 非图片内容 / 非 200：写 0 字节标记。check_favicon 视标记为「无图标」，
            # 前端回落类型图标；标记会被下次 1h 节流的 clear_favicons 清掉再重试。
            logging.info(
                "No usable favicon for %s (status=%s, bytes=%d), created empty marker",
                domain, resp.status_code, len(resp.content),
            )
        except Exception as e:
            # 网络失败同样落空标记，避免每次列表请求都去超时重试
            logging.warning("Failed to download favicon for %s: %s", domain, e)
        with open(path, "wb") as f:
            pass
        return "empty"
