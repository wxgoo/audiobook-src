#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""友链 favicon 抓取与清理的回归测试。

现场事故（r29）：电台类友链的 href 带路径（`/stream.m3u8`、`/radio.mp3`），
旧实现在 `urlparse(url).path` 非空时**把流地址本身当图片去请求**，把 m3u8 文本
或音频字节存成 `.ico`。文件非空 → 后端认为「抓到了」；前端 <img> 解码失败后只隐藏
不回落 → 整格空白，且因为「文件已存在」永不重抓，属于永久性损坏。

本测试锁住三条：
1. `_sniff_image` 只认真正的图片魔数（流列表/音频/HTML 一律 None）；
2. `clear_favicons` 按内容判，能清掉存量假图标（几百字节到几 MB 的 m3u8/mp3 都清），
   同时保留真 ico 与 svg；
3. 抓取一律取域名根 favicon，不再对流地址发请求（用 mock 断言请求 URL）。
"""

import os
import pathlib
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlparse

from webserver.services import resource_service
from webserver.services.resource_service import ResourceService

ICO = b"\x00\x00\x01\x00" + b"\x00" * 128
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128
GIF = b"GIF89a" + b"\x00" * 128
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 128
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 128
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'
M3U8 = b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=128000\nhttp://x/a.m3u8\n"
MP3 = b"ID3\x04\x00" + b"\x00" * 200
HTML = b"<html><head><title>404</title></head></html>"


class TestSniffImage(unittest.TestCase):
    def test_real_images_recognized(self):
        for content in (ICO, PNG, GIF, JPEG, WEBP):
            with self.subTest(head=content[:8]):
                self.assertEqual(ResourceService._sniff_image(content), "img")

    def test_svg_by_content_type_and_by_prefix(self):
        self.assertEqual(ResourceService._sniff_image(SVG, "image/svg+xml"), "svg")
        self.assertEqual(ResourceService._sniff_image(SVG), "svg")

    def test_non_image_payloads_rejected(self):
        """现场那批假图标正是这三类。"""
        for content, ctype in ((M3U8, "application/vnd.apple.mpegurl"),
                               (MP3, "audio/mpeg"),
                               (HTML, "text/html")):
            with self.subTest(head=content[:12]):
                self.assertIsNone(ResourceService._sniff_image(content, ctype))

    def test_empty_content_rejected(self):
        self.assertIsNone(ResourceService._sniff_image(b""))


class TestClearFavicons(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="favicon-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        patcher = mock.patch.object(resource_service, "FRIENDS_FAVICON_DIR", self.tmp)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _write(self, name, content):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def test_removes_fake_icons_and_empty_markers(self):
        # 存量假图标：m3u8 文本（>128 字节，旧实现按大小阈值清不掉）、音频字节
        self._write("radio.example.ico", M3U8 * 20)
        self._write("stream.example.ico", MP3)
        self._write("nothing.example.ico", b"")          # 0 字节标记
        keep_ico = self._write("real.example.ico", ICO)
        keep_svg = self._write("vector.example.svg", SVG)

        ResourceService.clear_favicons()

        left = sorted(os.listdir(self.tmp))
        self.assertEqual(left, sorted([os.path.basename(keep_ico), os.path.basename(keep_svg)]))

    def test_keeps_valid_svg_despite_text_payload(self):
        """svg 是文本文件，不能因为「不是二进制魔数」被误删。"""
        keep = self._write("v.example.svg", SVG)
        ResourceService.clear_favicons()
        self.assertTrue(os.path.exists(keep))

    def test_tolerates_missing_dir_entries(self):
        """目录里出现子目录时不应抛异常。"""
        os.makedirs(os.path.join(self.tmp, "subdir"), exist_ok=True)
        self._write("real.example.ico", ICO)
        ResourceService.clear_favicons()
        self.assertEqual(sorted(os.listdir(self.tmp)), ["real.example.ico", "subdir"])


class TestFaviconRequestTarget(unittest.TestCase):
    """带路径的友链（电台流）不能再把流地址当图片请求。

    直接测 fetch_favicon（纯同步）；load_favicons 外层有
    @AsyncService.register_service，会把调用丢进线程池，不宜在单测里驱动。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="favicon-req-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        patcher = mock.patch.object(resource_service, "FRIENDS_FAVICON_DIR", self.tmp)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _requested_url(self, domain, response):
        with mock.patch.object(resource_service, "requests") as fake_requests:
            fake_requests.get.return_value = response
            ResourceService.fetch_favicon(domain)
            self.assertTrue(fake_requests.get.called, "未发起下载请求")
            return fake_requests.get.call_args[0][0]

    @staticmethod
    def _resp(content, status=200, ctype="image/x-icon"):
        return mock.Mock(status_code=status, content=content, headers={"Content-Type": ctype})

    def test_plain_host_requests_domain_root(self):
        url = self._requested_url("plain.example", self._resp(ICO))
        self.assertEqual(url, "https://plain.example/favicon.ico")

    def test_domain_from_stream_link_requests_root(self):
        """电台友链 href 带 /stream.m3u8，favicon 仍应取域名根。"""
        domain = urlparse("https://radio.example/stream.m3u8").netloc
        url = self._requested_url(domain, self._resp(ICO))
        self.assertEqual(url, "https://radio.example/favicon.ico")
        self.assertNotIn("stream.m3u8", url)

    def test_domain_from_page_path_requests_root(self):
        """友链指向子页面时，favicon 依然在域名根，不应请求子页面。"""
        domain = urlparse("https://blog.example/about/me").netloc
        url = self._requested_url(domain, self._resp(ICO))
        self.assertEqual(url, "https://blog.example/favicon.ico")

    def test_saved_when_payload_is_image(self):
        with mock.patch.object(resource_service, "requests") as fake_requests:
            fake_requests.get.return_value = self._resp(ICO)
            self.assertEqual(ResourceService.fetch_favicon("ok.example"), "saved")
        path = ResourceService.get_favicon_path("ok.example")
        self.assertTrue(os.path.exists(path))
        self.assertEqual(os.path.getsize(path), len(ICO))

    def test_svg_saved_with_svg_suffix(self):
        state = {"calls": 0}

        def fake_get(*a, **kw):
            state["calls"] += 1
            return self._resp(SVG, ctype="image/svg+xml")

        with mock.patch.object(resource_service, "requests") as fake_requests:
            fake_requests.get.side_effect = fake_get
            self.assertEqual(ResourceService.fetch_favicon("vec.example"), "saved")
        self.assertTrue(os.path.exists(ResourceService.get_favicon_path("vec.example", ".svg")))

    def test_non_image_response_leaves_empty_marker_not_fake_icon(self):
        """服务端返回 m3u8 时落 0 字节标记（回落类型图标），不落假图标。"""
        with mock.patch.object(resource_service, "requests") as fake_requests:
            fake_requests.get.return_value = self._resp(
                M3U8, ctype="application/vnd.apple.mpegurl")
            st = ResourceService.fetch_favicon("radio.example")

        self.assertEqual(st, "empty")
        path = ResourceService.get_favicon_path("radio.example")
        self.assertTrue(os.path.exists(path))
        self.assertEqual(os.path.getsize(path), 0, "非图片内容不应写入字节")

    def test_audio_payload_rejected(self):
        with mock.patch.object(resource_service, "requests") as fake_requests:
            fake_requests.get.return_value = self._resp(MP3, ctype="audio/mpeg")
            self.assertEqual(ResourceService.fetch_favicon("audio.example"), "empty")
        self.assertEqual(os.path.getsize(ResourceService.get_favicon_path("audio.example")), 0)

    def test_http_error_leaves_empty_marker(self):
        with mock.patch.object(resource_service, "requests") as fake_requests:
            fake_requests.get.return_value = self._resp(HTML, status=404, ctype="text/html")
            self.assertEqual(ResourceService.fetch_favicon("missing.example"), "empty")
        self.assertEqual(os.path.getsize(ResourceService.get_favicon_path("missing.example")), 0)

    def test_network_error_leaves_empty_marker(self):
        with mock.patch.object(resource_service, "requests") as fake_requests:
            fake_requests.get.side_effect = OSError("boom")
            self.assertEqual(ResourceService.fetch_favicon("down.example"), "empty")
        path = ResourceService.get_favicon_path("down.example")
        self.assertTrue(os.path.exists(path))
        self.assertEqual(os.path.getsize(path), 0)


class TestCheckFaviconContract(unittest.TestCase):
    """check_favicon 的返回值约定：None=无文件、""=空标记、路径=可用图标。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="favicon-chk-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        patcher = mock.patch.object(resource_service, "FRIENDS_FAVICON_DIR", self.tmp)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_missing_returns_none(self):
        self.assertIsNone(ResourceService.check_favicon("https://nofile.example"))

    def test_empty_marker_returns_empty_string(self):
        open(os.path.join(self.tmp, "empty.example.ico"), "wb").close()
        self.assertEqual(ResourceService.check_favicon("https://empty.example"), "")

    def test_valid_icon_returns_api_path(self):
        with open(os.path.join(self.tmp, "ok.example.ico"), "wb") as f:
            f.write(ICO)
        self.assertEqual(ResourceService.check_favicon("https://ok.example"),
                         "/api/favicon/ok.example.ico")

    def test_svg_only_domain_returns_svg_path(self):
        with open(os.path.join(self.tmp, "vec.example.svg"), "wb") as f:
            f.write(SVG)
        self.assertEqual(ResourceService.check_favicon("https://vec.example"),
                         "/api/favicon/vec.example.svg")


class TestFrontendFallbackContract(unittest.TestCase):
    """前端必须回落到类型图标，而不是隐藏 img 后留空白（AppHeader.vue）。"""

    SRC = pathlib.Path(__file__).resolve().parent.parent / "app" / "src" / "components" / "AppHeader.vue"

    def test_image_error_falls_back_instead_of_hiding(self):
        text = self.SRC.read_text(encoding="utf-8")
        self.assertIn("onFaviconError(link)", text,
                      "favicon 加载失败必须走回落方法，不能直接隐藏")
        self.assertNotIn("style.display='none'", text,
                         "隐藏 img 会留下整格空白，应切换回 mdi 兜底图标")
        self.assertIn("_iconFailed", text, "缺少失败状态标记，v-else 兜底分支不会渲染")


if __name__ == "__main__":
    unittest.main()
