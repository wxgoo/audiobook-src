# -*- coding: UTF-8 -*-
"""合集 EPUB 一键自动分册工具。

在既有「EPUB拆分」（按章节手工合成一本）之上，提供面向“套装/全集/合集”的
批量能力：

  * detect(book_id)         —— 解析目录，自动推断每一册的边界，返回候选分册
                                及扁平章节列表（供前端展示/微调）
  * batch_split(...)        —— 按用户确认（可微调）后的分册分组，一次性拆成
                                多本新书并逐本入库

每册沿用原书（合集）的作者/标签/分类/出版社/丛书信息；封面优先用该册范围内的
第一张大图，找不到则沿用原书封面。单册失败不影响其它册，结果里逐本报告。

@author: MyBooks 定制
"""
import io
import logging
import os
import threading
import time

from webserver.i18n import _
from webserver import utils
from webserver.toolbox.base_tool import BaseTool
from webserver.toolbox.epub_split_lib import SplitEpub, strip_html, get_title_of_html
from webserver.toolbox.epub_auto_split_lib import (
    detect_volumes, build_chapter_list,
)
from webserver.constants import AUTO_FILL_META
from webserver.models import Item
from webserver.services import AsyncService
from webserver.services.autofill import AutoFillService

COVER_MIN_WIDTH = 400
COVER_MIN_HEIGHT = 600


class EpubAutoSplitTool(BaseTool):
    service_item_name = "合集自动分册"

    @staticmethod
    def info() -> dict:
        return {
            "tool_id": "epub_auto_split",
            "name": "合集自动分册",
            "description": "自动识别套装/全集 EPUB 的每一册，微调后一次拆成多本新书",
            "revision": "1.0.0",
            "author": "MyBooks",
            "publish_date": "2026-11-20",
            "page": "epub_auto_split",
        }

    def _load_epub(self, book_id: int):
        books = self.api.calibre.get_data_as_dict([book_id])
        if not books:
            raise RuntimeError(_("书籍不存在：ID=%d") % book_id)
        book = books[0]
        fmts = [f.upper() for f in (book.get("available_formats") or [])]
        if "EPUB" not in fmts:
            raise RuntimeError(_("该书籍没有 EPUB 格式，无法执行拆分"))
        epub_path = self.api.calibre.format_abspath(book_id, "EPUB")
        if not epub_path or not os.path.exists(epub_path):
            raise RuntimeError(_("找不到 EPUB 文件，可能已被移除"))
        with open(epub_path, "rb") as f:
            data = f.read()
        return book, SplitEpub(io.BytesIO(data))

    @AsyncService.register_function
    def detect(self, book_id: int) -> dict:
        """解析目录并自动检测分册，返回章节列表 + 候选分册分组。"""
        book, epub = self._load_epub(book_id)
        lines = epub.get_split_lines()  # 同时填充 orig_title / orig_authors
        volumes, diag = detect_volumes(lines, epub.orig_title or book.get("title", ""))
        chapters = build_chapter_list(lines)
        return {
            "book_id": book_id,
            "title": book.get("title", ""),
            "authors": list(epub.orig_authors or []),
            "total_chapters": len(lines),
            "chapters": chapters,
            "volumes": volumes,
            "diagnostics": {k: v for k, v in diag.items() if k != "scores"},
        }

    @AsyncService.register_function
    def batch_split(self, book_id: int, volumes: list, user_id: int,
                    use_chapter_cover: bool = True, progress_callback=None) -> dict:
        """按给定的分册分组，一次拆成多本新书。

        :param volumes: [{name, start, end}, ...]，start/end 为 chapter num（含端点）
        :param progress_callback: 可选 fn(done:int, total:int, name:str)
        :return: {"total":n, "succeeded":n, "failed":n, "results":[...]}
        """
        from calibre.ebooks.metadata.book.base import Metadata

        if not volumes:
            raise RuntimeError(_("没有可拆分的分册"))

        # 重新加载原始 EPUB（每次 write_split_epub 会消费内部状态，故每册用独立实例）
        book, _ = self._load_epub(book_id)
        with open(self.api.calibre.format_abspath(book_id, "EPUB"), "rb") as f:
            raw_bytes = f.read()

        src_mi = self.get_book_metadata(book_id)
        src_cover = None
        try:
            src_cover = self.api.calibre.cover(book_id)
        except Exception as err:
            logging.warning("[EpubAutoSplit] read source cover failed: %s", err)

        languages = list(src_mi.languages) if src_mi.languages else ["zho"]
        authors = list(src_mi.authors) if src_mi.authors else ["未知"]

        work_dir = self.get_work_dir(str(book_id))
        os.makedirs(work_dir, exist_ok=True)
        results = []
        total = len(volumes)

        try:
            for idx, vol in enumerate(volumes):
                name = (vol.get("name") or f"第{idx + 1}册").strip()
                try:
                    start = int(vol["start"])
                    end = int(vol["end"])
                except (KeyError, ValueError, TypeError):
                    results.append({"name": name, "ok": False, "error": _("分册章节范围无效")})
                    if progress_callback:
                        progress_callback(idx + 1, total, name)
                    continue

                if end < start:
                    results.append({"name": name, "ok": False, "error": _("结束章节早于开始章节")})
                    if progress_callback:
                        progress_callback(idx + 1, total, name)
                    continue

                linenums = list(range(start, end + 1))
                vol_work = os.path.join(work_dir, "vol_%d" % idx)
                os.makedirs(vol_work, exist_ok=True)
                out_path = os.path.join(vol_work, "split.epub")

                try:
                    # 每册独立解析，避免状态串扰
                    epub = SplitEpub(io.BytesIO(raw_bytes))
                    epub.get_split_lines()  # 填充内部状态

                    # 该册封面：范围内第一张大图，否则原书封面
                    cover_data = None
                    if use_chapter_cover:
                        cand = epub.find_cover_candidate(linenums, COVER_MIN_WIDTH, COVER_MIN_HEIGHT)
                        if cand:
                            ext, raw = cand
                            cover_data = ("jpeg" if ext in ("jpg", "jpeg") else ext, raw)
                    if cover_data is None and src_cover:
                        cover_data = ("jpeg", src_cover)

                    with open(out_path, "wb") as f:
                        epub.write_split_epub(
                            f, linenums,
                            title=name,
                            authors=authors,
                            tags=list(src_mi.tags) if src_mi.tags else [],
                            languages=languages,
                            description=(f"{name}（拆自《{book.get('title', '')}》）"),
                            cover_data=cover_data,
                        )

                    mi = Metadata(utils.super_strip(name), authors)
                    mi.title_sort = utils.get_title_sort(mi.title)
                    mi.tags = list(src_mi.tags) if src_mi.tags else []
                    mi.publisher = src_mi.publisher
                    mi.series = src_mi.series
                    mi.languages = languages
                    if cover_data:
                        mi.cover_data = cover_data

                    new_book_id = self.api.calibre.import_book(mi, [out_path])
                    if new_book_id is None:
                        raise RuntimeError(_("导入分册失败"))

                    try:
                        item = Item()
                        item.book_id = new_book_id
                        item.collector_id = user_id
                        item.save()
                    except Exception as err:
                        logging.error("[EpubAutoSplit] create Item failed for %s: %s", new_book_id, err)

                    results.append({
                        "name": mi.title, "ok": True,
                        "book_id": new_book_id, "start": start, "end": end,
                    })
                    logging.info("[EpubAutoSplit] %s -> book_id=%s", mi.title, new_book_id)

                    # 自动填充元数据（与原拆分工具一致，异步、不阻塞）
                    if self.api.settings.get(AUTO_FILL_META, False):
                        threading.Thread(
                            target=AutoFillService().auto_fill,
                            args=(new_book_id,), daemon=True,
                        ).start()
                except Exception as err:
                    logging.exception("[EpubAutoSplit] split '%s' failed", name)
                    results.append({"name": name, "ok": False, "error": str(err)})

                if progress_callback:
                    progress_callback(idx + 1, total, name)
        finally:
            self.cleanup_work_dir(work_dir)

        succeeded = sum(1 for r in results if r.get("ok"))
        return {
            "total": total,
            "succeeded": succeeded,
            "failed": total - succeeded,
            "results": results,
        }
