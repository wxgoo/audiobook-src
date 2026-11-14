#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import datetime
import logging
import os
import re
import shutil
import threading
import time
import traceback
import urllib.parse
from webserver.services.book_access_service import BookAccessService
import uuid
import zipfile
from webserver.i18n import _
from webserver.version import VERSION

import tornado
from tornado import web
from tornado.iostream import StreamClosedError

from webserver import loader
from webserver import constants
from webserver.base.formatter import BookFormatter
from webserver.base.pagination import encode_cursor, parse_id_cursor
from webserver.base import audio_category_agg
from webserver.base import category_icons
from webserver.base.audio_dir import (
    audio_dir_for_read,
    audio_dir_for_write,
    find_audios_by_scanning_library,
)
from webserver.handlers.base import BaseHandler, auth, js, is_admin
from webserver.models import BizKey, ReaderPaidBook, ReaderLog, Message, AudioPlayback
from webserver.worker.epub2audio_worker import EpubToAudioWorker
from webserver.constants import ENABLE_VIP_QUOTA_KEY, SUPPORTED_AUDIO_FORMATS, SUPPORTED_SUBTITLE_FORMATS
from webserver.services.background_service import BackgroundService, BackgroundTask
from email.utils import formatdate


CONF = loader.get_settings()
# map of conversion workers, key is book id, value is instance of the worker
ConversionWorkerMap: dict = {}
# 每日下载记录，格式: {(user_id, book_id): datetime}
DailyDownloadMap: dict = {}
# DailyDownloadMap 只在有下载时插入、从不清理的话会随使用无限膨胀；
# 超过上限时把两天前的旧记录顺手清掉（在写入路径上做，无需后台任务）。
DAILY_DOWNLOAD_MAP_MAX = 4096


def _record_daily_download(user_id, book_id):
    if len(DailyDownloadMap) >= DAILY_DOWNLOAD_MAP_MAX:
        cutoff = datetime.datetime.now() - datetime.timedelta(days=2)
        stale = [k for k, ts in DailyDownloadMap.items() if ts < cutoff]
        for k in stale:
            DailyDownloadMap.pop(k, None)
    DailyDownloadMap[(user_id, book_id)] = datetime.datetime.now()


ALLOW_MAX_RUNNING_WORKERS = CONF.get("BOOK2AUDIO_MAX_WORKERS", 2)
SKIP_AUDIO_FILE_PREFIX = "图书在版编目CIP数据"
MAX_FREE_AUDIO_FILES = 6
# 全库兜底扫描间隔。默认 5 分钟：正常情况下导入/转码/删除都会通过事件
# 增量更新缓存；此外统计接口（左侧菜单「有声书 N」计数）每次实时扫盘后会把
# 结果同步进来（见 sync_from_scan），所以用户手工往 .audio/ 塞文件通常
# 刷新一次页面就生效。这条只兜底「既没有统计请求、也没有事件」的极端情况。
# 设为 0 可关闭（只剩启动预热 + 事件更新 + 统计同步）；超大书库可调大。
AUDIO_CACHE_REFRESH_SECONDS = int(CONF.get("AUDIO_CACHE_REFRESH_SECONDS", 300))


def natural_sort_key(filename):
    return [int(chunk) if chunk.isdigit() else chunk.lower() for chunk in re.split(r"(\d+)", filename)]


def resolve_audio_dir(db, book_id):
    """解析某本书的音频目录：书目录内的 .audio/。

    4.6.0-15 起旧布局 audios/<id>/ 已移除，这里没有回退分支。
    书不在 calibre library 里时返回 (None, False)，调用方按「没有音频」处理。

    返回 (path, is_legacy)，is_legacy 恒为 False（保留是为了兼容老调用方）。
    """
    try:
        return audio_dir_for_read(db, book_id)
    except Exception as err:
        logging.warning("[AUDIO] resolve dir for book %s failed: %s", book_id, err)
        return None, False


def resolve_audio_dir_or_404(db, book_id):
    """同上，但拿不到目录时抛 404（供「只可能读」的场景直接用）。"""
    audio_dir, _legacy = resolve_audio_dir(db, book_id)
    if not audio_dir or not os.path.isdir(audio_dir):
        logging.warning("[AUDIO] audio dir missing for book %s (resolved: %s)",
                        book_id, audio_dir)
        raise web.HTTPError(404, "Audio directory not found")
    return audio_dir


class AudioBooksCache:
    """音频书籍目录缓存工具类。

    刷新只允许发生在后台线程：请求线程里的 get_audio_book_ids()/has_audio()
    只做 O(1) 的过期判断并触发一次后台刷新，然后立即返回当前缓存。
    10 万册库的 listdir 全库遍历不再阻塞任何 API 请求。
    """

    _book_ids = set()
    _last_update_time = 0
    _update_lock = threading.Lock()
    _state_lock = threading.Lock()
    _need_update = True
    _refreshing = False
    _pending_refresh = False
    # 缓存内容版本号：集合每次实际变化 +1。
    # 供下游派生缓存（如 audio_category_agg 的分类聚合）做失效判断，
    # 派生方只比对版本号即可，不必各自维护 TTL（双缓存漂移的教训见 podcast）。
    _version = 0

    @classmethod
    def get_version(cls):
        """当前缓存内容版本号（读方用于派生缓存失效判断）。"""
        return cls._version

    @classmethod
    def _scan_audio_directory(cls):
        """扫描 library，收集所有带音频的书（书目录内 .audio/）。

        4.6.0-14 之前只扫旧布局 audios/<数字>/，而导入端早就把音频写进
        library/<作者>/<书名> (id)/.audio/ 了。旧目录是空的，于是全库被判成
        「没有有声书」——前端不显示有声书标识，播放页也拿不到音频和字幕。
        4.6.0-15 起旧布局彻底移除，这里只认 .audio/。
        """
        start_time = time.time()
        try:
            book_ids = set(find_audios_by_scanning_library().keys())
            logging.info("Audio scan: %d books with audio (.audio/)", len(book_ids))
        except Exception as e:
            logging.error(f"Error scanning library for audio: {e}")
            book_ids = set()

        elapsed_time = time.time() - start_time
        logging.info(
            f"Audio directory scan completed in {elapsed_time:.3f} seconds, found {len(book_ids)} audio books"
        )

        return book_ids

    @classmethod
    def _should_update(cls):
        """判断是否需要更新缓存。

        事件驱动的增量更新是主路径；这里的兜底扫描默认 6 小时一次，
        可用 AUDIO_CACHE_REFRESH_SECONDS=0 关闭。
        """
        if cls._need_update:
            return True
        if AUDIO_CACHE_REFRESH_SECONDS <= 0:
            return False
        return (time.time() - cls._last_update_time) > AUDIO_CACHE_REFRESH_SECONDS

    @classmethod
    def get_audio_book_ids(cls):
        """获取有音频的书籍ID列表（请求路径上永不扫盘）。"""
        cls._ensure_background_refresh()
        return cls._book_ids.copy()

    @classmethod
    def _update_cache(cls):
        """扫描全库并替换缓存。只允许在后台线程调用。"""
        try:
            book_ids = cls._scan_audio_directory()
            with cls._state_lock:
                cls._book_ids = book_ids
                cls._last_update_time = time.time()
                cls._need_update = False
                cls._version += 1
            logging.info("Audio cache updated with %d books", len(book_ids))
        except Exception:
            # 扫描失败保留旧缓存，避免把「有音频」误降级成「没有音频」
            logging.exception("Error updating audio cache")

    @classmethod
    def mark_need_update(cls):
        """标记需要全库兜底扫描（下一次后台刷新会重新扫盘）"""
        cls._need_update = True
        logging.info("Audio cache marked for update")

    @classmethod
    def mark_has_audio(cls, book_id):
        """事件驱动：某本书新增了音频（导入/转码/TTS 完成时调用）。

        只改一个 id，不动全库；替换 set 而不是原地修改，读方拿到的旧集合仍然有效。
        """
        bid = int(book_id)
        with cls._state_lock:
            if bid not in cls._book_ids:
                cls._book_ids = cls._book_ids | {bid}
                cls._version += 1
                logging.info("Audio cache +1 book: %s", bid)

    @classmethod
    def mark_no_audio(cls, book_id):
        """事件驱动：某本书的音频被删除。"""
        bid = int(book_id)
        with cls._state_lock:
            if bid in cls._book_ids:
                cls._book_ids = cls._book_ids - {bid}
                cls._version += 1
                logging.info("Audio cache -1 book: %s", bid)

    @classmethod
    def sync_from_scan(cls, book_ids):
        """把一次「实时全库扫盘」的结果同步进缓存（统计接口调用）。

        §统计与列表同源§
        左侧菜单的「有声书 N」来自 BaseHandler.get_audio_books_count()，它每次
        都 find_audios_by_scanning_library() 实时扫盘；而书列表和分类 tab 读的是
        本缓存（事件驱动 + 兜底扫描）。用户手工往书目录 .audio/ 塞文件时没有任何
        事件通知，于是「统计立刻 +1，列表 / 分类 tab 纹丝不动」，最长要等兜底
        扫描才自愈——用户实测反馈过「加了音频、统计加了 1、文学分类还是不出来」。

        统计接口反正已经扫过盘了，顺手把结果喂进来即可：集合真变化才 +version，
        下游 audio_category_agg 会跟着增量补齐，分类 tab 立刻反映新书。
        空结果不同步，避免一次偶发 listdir 失败把缓存清空（与 _update_cache
        的「扫描失败保留旧缓存」同规）。
        """
        try:
            ids = {int(b) for b in book_ids}
        except (TypeError, ValueError):
            logging.warning("Audio cache: bad ids from live scan, skip sync")
            return
        if not ids and cls._book_ids:
            logging.warning("Audio cache: live scan is empty, skip sync to keep old cache")
            return
        with cls._state_lock:
            if ids == cls._book_ids:
                return
            added = ids - cls._book_ids
            removed = cls._book_ids - ids
            cls._book_ids = ids
            cls._version += 1
            cls._last_update_time = time.time()
            cls._need_update = False
            logging.info("Audio cache synced from live scan: %d books (+%d/-%d)",
                         len(ids), len(added), len(removed))

    @classmethod
    def _ensure_background_refresh(cls):
        """过期时触发一次后台刷新，然后立即返回。

        请求线程只做布尔判断；_refreshing 保证全库扫描同一时刻最多一个，
        并发请求不会各自起一个扫描线程。
        """
        if not cls._should_update() or cls._refreshing:
            return
        cls.async_update()

    @classmethod
    def async_update(cls):
        """异步更新缓存（单飞：同一时刻最多一个扫描线程）。"""
        with cls._update_lock:
            if cls._refreshing:
                # 正在扫的那一轮结束后再补扫一次，保证事件都能被看见
                cls._pending_refresh = True
                return
            cls._refreshing = True

        thread = threading.Thread(
            target=cls._refresh_loop, name="audio-cache-refresh", daemon=True)
        thread.start()

    @classmethod
    def _refresh_loop(cls):
        while True:
            cls._update_cache()
            with cls._update_lock:
                if cls._pending_refresh:
                    cls._pending_refresh = False
                    continue
                cls._refreshing = False
                return

    @classmethod
    def get_audio_book_ids_set(cls):
        """获取有音频的书籍ID集合（用于批量查询）。"""
        cls._ensure_background_refresh()
        return cls._book_ids

    @classmethod
    def has_audio(cls, book_id):
        """查询指定book_id是否有音频。"""
        cls._ensure_background_refresh()
        return int(book_id) in cls._book_ids


class AudioUtils:
    site_url = ""

    @staticmethod
    def get_running_worker_count():
        """Get the count of currently running audio conversion workers."""
        return sum(1 for worker in ConversionWorkerMap.values() if worker.is_running())

    @staticmethod
    def get_audios(bid, uid=None, db=None):
        """Get audio files for a book.

        db 传入 calibre 元数据缓存时走 resolve_audio_dir（O(1)），不再全库扫描；
        未传（旧调用方）时才回退扫描兜底。
        """
        if uid is None:
            return {"status": "unavailable", "msg": _("登录后才能查看音频"), "count": 0}

        if not AudioUtils.site_url:
            AudioUtils.site_url = BaseHandler.get_site_url()

        book_id = int(bid)
        audio_dir = None
        try:
            dirs = AudioUtils.audio_dirs_of(book_id, db)
            audio_dir = dirs[0] if dirs else None
        except Exception as err:
            logging.debug("[AUDIO] resolve audio dir failed: %s", err)
        if not audio_dir or not os.path.exists(audio_dir):
            return {
                "status": "unavailable",
                "msg": _("没有发现音频文件目录"),
                "count": 0,
            }

        worker = ConversionWorkerMap.get(book_id)
        audio_files = [f for f in os.listdir(audio_dir) if f.endswith(tuple(SUPPORTED_AUDIO_FORMATS))]
        if not audio_files:
            if worker:
                return {
                    "status": worker.get_status(),
                    "progress": worker.get_progress(),
                    "audio_dir": audio_dir,
                    "audios": [],
                    "count": 0,
                }
            else:
                return {
                    "status": "unavailable",
                    "msg": _("没有发现音频文件"),
                    "count": 0,
                }

        file_urls = []
        for file in sorted(audio_files, key=natural_sort_key):
            file_path = os.path.join(audio_dir, file)
            file_size = os.path.getsize(file_path)
            if file_size <= 1024:  # Ignore files smaller than 1K
                continue
            file_urls.append(
                {
                    "filename": os.path.splitext(file)[0],
                    "url": f"/api/audio/{book_id}/{file}",
                    "size": file_size,
                }
            )

        if worker and not worker.is_completed():
            # If conversion is in progress, return worker status
            return {
                "status": worker.get_status(),
                "progress": worker.get_progress(),
                "audio_dir": audio_dir,
                "audios": file_urls,
                "count": len(file_urls),
            }
        else:
            return {
                "status": EpubToAudioWorker.STATUS_CONVERTED,
                "audio_dir": audio_dir,
                "audios": file_urls,
                "count": len(file_urls),
            }

    @staticmethod
    def audio_dirs_of(bid, db=None):
        """算出某本书的音频目录（可能为空列表）。供删除流程在线程池外先算好。

        calibre 的 Cache 不是线程安全的，删除走线程池时要在当前线程把路径算成
        字符串再传进去，别让子线程自己调 field_for。
        """
        try:
            book_id = int(bid)
        except (TypeError, ValueError):
            return []
        audio_dir, _legacy = resolve_audio_dir(db, book_id)
        if not audio_dir:
            audio_dir = find_audios_by_scanning_library().get(book_id)
        return [audio_dir] if audio_dir else []

    @staticmethod
    def clear_audio(book_id, extra_dirs=None):
        """Clear audio files for a book.

        只删书目录内的 .audio/ 这一层，书目录本身和电子书文件都不动。
        extra_dirs 供调用方传入「在线程外预先算好的目录」，避免子线程碰 calibre。
        """
        dirs = list(extra_dirs or [])
        if not dirs:
            dirs = AudioUtils.audio_dirs_of(book_id)

        removed = False
        for audio_dir in dirs:
            if not audio_dir or not os.path.exists(audio_dir):
                continue
            try:
                shutil.rmtree(audio_dir)
                removed = True
            except OSError as e:
                logging.error(f"Error deleting audio directory {audio_dir}: {e}")
                return False, f"音频文件删除遇到错误: {e}"
        if removed:
            AudioBooksCache.mark_no_audio(book_id)
            return True, _("音频文件删除成功")
        return True, _("音频文件不存在")


class AudioDetail(BaseHandler):
    def _extract_m4b_chapters(self, file_path, file_size, book_id, file):
        try:
            from mutagen.mp4 import MP4
            audio = MP4(file_path)
            if not audio.chapters:
                return None
            chapter_urls = []
            total_duration = audio.info.length if audio.info else 0
            for i, chapter in enumerate(audio.chapters):
                title = getattr(chapter, 'title', f"Chapter {i + 1}")
                start = getattr(chapter, 'start', 0)
                if i + 1 < len(audio.chapters):
                    end = getattr(audio.chapters[i + 1], 'start', total_duration)
                else:
                    end = total_duration

                # Estimate size for the chapter based on duration
                chapter_duration = end - start
                chapter_size = int((chapter_duration / total_duration) * file_size) if total_duration > 0 else file_size

                chapter_urls.append(
                    {
                        "filename": title,
                        "url": f"/api/audio/{book_id}/{file}",
                        "size": chapter_size,
                        "start_time": start,
                        "end_time": end
                    }
                )
            return chapter_urls
        except Exception as e:
            logging.error(f"Error parsing chapters from {file}: {e}")
            return None

    @js
    def get(self, book_id):
        # get the audio file path from the book id, if not found, check the book id in the worker map,
        # if found, return the worker status, otherwise return not found status.
        try:
            book_id = int(book_id)
            book = self.get_book(book_id, fully=True, raise_exception=False)
            if not book:
                return {"err": "params.book.invalid", "msg": _("书籍未找到")}

            enable_vip_quota = CONF.get(ENABLE_VIP_QUOTA_KEY, False)

            # Check if audio file already exists
            # 音频在书目录内的 .audio/（4.6.0-15 起唯一布局）
            audio_dir, _legacy = resolve_audio_dir(self.calibre_db, book_id)
            if os.path.exists(audio_dir) and os.listdir(audio_dir):
                audio_files = [
                    f
                    for f in os.listdir(audio_dir)
                    if f.lower().endswith(tuple(SUPPORTED_AUDIO_FORMATS))
                ]
                if audio_files:
                    user = self.get_current_user()
                    is_paid = False
                    if user:
                        if enable_vip_quota:
                            # 检查用户是否已购买此书
                            paid_record = (
                                self.sqlite_session.query(ReaderPaidBook)
                                .filter_by(reader_id=user.id, book_id=book_id)
                                .first()
                            )
                            is_paid = paid_record is not None
                        else:
                            is_paid = True

                    # Generate download URLs for audio files
                    # 扫描同目录下的字幕文件（与音频同名，如 0001_第一章.wav -> 0001_第一章.srt）
                    subtitle_map = {}
                    for sub in sorted(os.listdir(audio_dir)):
                        stem, ext = os.path.splitext(sub)
                        if ext.lower() in SUPPORTED_SUBTITLE_FORMATS and stem not in subtitle_map:
                            subtitle_map[stem] = sub

                    file_urls = []
                    for file in sorted(audio_files, key=natural_sort_key):
                        # find()>0 恰好放过以该前缀开头的文件（find 返回 0），
                        # 语义按常量名来：文件名以 CIP 前缀开头的跳过。
                        if file.startswith(SKIP_AUDIO_FILE_PREFIX):
                            continue

                        file_path = os.path.join(audio_dir, file)
                        file_size = os.path.getsize(file_path)

                        if file.lower().endswith('.m4b'):
                            chapter_urls = self._extract_m4b_chapters(file_path, file_size, book_id, file)
                            if chapter_urls:
                                # m4b 内嵌章节共享同一个外部字幕文件
                                sub_file = subtitle_map.get(os.path.splitext(file)[0])
                                for chapter_url in chapter_urls:
                                    if sub_file:
                                        chapter_url["subtitle"] = f"/api/audio/{book_id}/{sub_file}"
                                file_urls.extend(chapter_urls)
                                continue  # Skip adding the whole m4b file

                        audio_item = {
                            "filename": os.path.splitext(file)[0],
                            "url": f"/api/audio/{book_id}/{file}",
                            "size": file_size,
                        }
                        sub_file = subtitle_map.get(audio_item["filename"])
                        if sub_file:
                            audio_item["subtitle"] = f"/api/audio/{book_id}/{sub_file}"
                        file_urls.append(audio_item)
                    # 播放页要靠 status 决定显示「取消生成 / 重新生成」还是「删除」。
                    # 正在转换时 worker 还没产出文件，file_urls 可能为空，
                    # 这里必须把 processing/failed 透出去，否则前端只能看到 unavailable。
                    _worker = ConversionWorkerMap.get(book_id)
                    _status = _worker.get_status() if _worker else "converted"
                    return {
                        "err": "ok",
                        "status": _status,
                        "audio_dir": audio_dir,
                        "audios": file_urls,
                        "total_files": len(audio_files),
                        "is_paid": is_paid,
                    }

            # Check if conversion is in progress
            worker = ConversionWorkerMap.get(book_id)
            if worker:
                progress = worker.get_progress()
                return {"err": "ok", "msg": _("已经在生成音频中"), "data": progress}

            return {"err": "audio.not_found", "msg": _("没有发现音频文件")}

        except ValueError:
            return {"err": "params.invalid", "msg": _("无效的书籍ID")}
        except Exception as e:
            logging.error(f"Error in AudioDetail.get: {e}")
            return {"err": "server.error", "msg": str(e)}


def _visible_audio_ids(handler):
    """当前用户可见的有声书 id 集；返回 None 表示无范围限制（快路，全可见）。

    口径必须与 get_books → _merge_books → is_book_visible 完全一致：
      - 阅读范围开关关闭 / 管理员 → None（调用方按全可见处理）；
      - 未登录 → 只有无 tags 且无 #category 的书（与 is_book_visible 的访客分支同规）；
      - 受限用户 → 逐本 book_matches_limits（统计侧与列表侧共用的唯一口径来源），
        判定所需的 tags/#category 来自共享聚合的 book_meta，不再逐本取元数据。
    冷启动聚合未建完时受限用户可能短暂看到空列表，聚合后台建好后自愈——
    这是「请求路径零阻塞」的既定代价，见 audio_category_agg 模块注释。
    """
    if not CONF.get(constants.ALLOW_READ_RANGE_SETTING, False):
        return None
    user = handler.current_user
    meta = audio_category_agg.get_audio_aggregation(handler.calibre_db_cache)["book_meta"]
    if not user:
        return {
            bid for bid, m in meta.items()
            if not m.get("tags") and not m.get(constants.CALIBRE_COLUMN_CATEGORY)
        }
    if handler.is_admin():
        return None
    from webserver.services.reader_group import ReaderGroupService, book_matches_limits
    eff = ReaderGroupService.effective_limits(user)
    if not eff.get("read_limit"):
        return None
    return {bid for bid, m in meta.items() if book_matches_limits(m, eff)}


class AudioBooks(BaseHandler):
    @js
    async def get(self):
        """获取有音频的书籍列表。

        键集分页：`after` 游标（兼容旧的 `start`/`size`），响应带 `next_cursor`。
        书籍 ID 来自 AudioBooksCache（事件驱动 + 兜底刷新），请求路径不再全库扫盘；
        每个请求只对当前页的书目录做 listdir 统计音频数量。

        可选 `category` 参数：按 #category 自定义列过滤（值来自
        /api/audiobooks/categories 的分类 tab），先过滤后分页，游标机制不受影响。
        total 现在按当前用户可见口径计算——此前受限用户看到的 total 是全量数，
        每页实际书数却少于 size，两处数字对不上。
        """
        try:
            start = self.get_argument_start()
            size = int(self.get_argument("size", 60))
            size = max(size, 1)
            cursor = self.get_argument("after", "") or self.get_argument("cursor", "")
            category = (self.get_argument("category", "") or "").strip()

            audio_book_ids = sorted(AudioBooksCache.get_audio_book_ids(), reverse=True)

            visible = _visible_audio_ids(self)
            if visible is not None:
                audio_book_ids = [i for i in audio_book_ids if i in visible]

            # 「全部」tab 的计数是全量可见有声书，不能用按 category 过滤后的 total
            all_visible_total = len(audio_book_ids)

            if category:
                allowed = set(audio_category_agg.get_audio_categories(
                    self.calibre_db_cache).get(category, []))
                audio_book_ids = [i for i in audio_book_ids if i in allowed]

            total = len(audio_book_ids)

            pos = start
            last_id = parse_id_cursor(cursor, "audio")
            if last_id is not None:
                pos = total
                for i, v in enumerate(audio_book_ids):
                    if v < last_id:
                        pos = i
                        break

            paginated_ids = audio_book_ids[pos : pos + size]
            next_cursor = None
            if paginated_ids and pos + size < total:
                next_cursor = encode_cursor({"k": "audio", "id": paginated_ids[-1]})

            # 只统计当前页的音频数量，不扫全库
            audios_cnt_map = {}
            for book_id in paginated_ids:
                audio_dir, _legacy = resolve_audio_dir(self.calibre_db_cache, book_id)
                if not audio_dir:
                    continue
                try:
                    audios_cnt_map[book_id] = len([
                        f for f in os.listdir(audio_dir)
                        if f.lower().endswith(tuple(SUPPORTED_AUDIO_FORMATS))
                    ])
                except OSError:
                    audios_cnt_map[book_id] = 0

            # 获取书籍信息，参考 base.py 中的 get_books 函数进行权限过滤
            books = []
            if paginated_ids:
                books = self.get_books(ids=paginated_ids)

            # 按书籍ID倒排
            books.sort(key=lambda x: x["id"], reverse=True)

            books_result = []
            for book in books:
                book_data = BookFormatter(self, book).format()
                book_data["has_audio"] = True
                book_data["audio_count"] = audios_cnt_map.get(book["id"], 0)
                books_result.append(book_data)

            # 分类 tab 随书列表一起下发：SPA 模式下 asyncData 会把这两个 key merge 进
            # 组件 data 的 audioCategories/audioTotal，tab 才有数据可渲染。
            # 不能只放在 init()→fetchAudioCategories() 里——asyncData 成功会置
            # ssr_loaded=true，mounted 的 !ssr_loaded 守卫会跳过 init()，分类请求
            # 永远不发，tab 静默不显示（Console 干净、列表正常，极易误判成缓存）。
            tab_categories = []
            try:
                catalog = await self.catalog_categories()
                cat_map = audio_category_agg.get_audio_aggregation(
                    self.calibre_db_cache)["categories"]
                tab_categories = build_audio_tab_categories(catalog, cat_map, visible)
            except Exception as e:
                # 分类只是增强信息，失败不能拖垮书列表
                logging.warning(f"AudioBooks: build category tabs failed: {e}")

            return {
                "err": "ok",
                "title": _("有声书"),
                "books": books_result,
                "total": total,
                "next_cursor": next_cursor,
                "audioCategories": tab_categories,
                "audioTotal": all_visible_total,
            }

        except Exception as e:
            logging.error(f"Error in AudioBooks.get: {e}")
            return {"err": "server.error", "msg": str(e)}


def build_audio_tab_categories(catalog, cat_map, visible, keep_empty=False):
    """生成有声书页分类 tab 的 rows，供 /api/audiobooks 与
    /api/audiobooks/categories 共用。

    分类名与顺序照抄 catalog_categories()（分类浏览页骨架），count 用
    _visible_audio_ids() 的可见口径，图标由 category_icons.decorate 补齐。
    两处必须走同一份实现，否则「列表页 tab」和「独立分类接口」会漂移。

    visible=None 表示无范围限制（快路）；keep_empty=True 用于 ?all=1 核对。
    """
    rows = []
    for c in catalog:  # 顺序照抄分类浏览页，不按有声书数重排
        ids = cat_map.get(c["name"]) or []
        n = (len([b for b in ids if b in visible])
             if visible is not None else len(ids))
        if n <= 0 and not keep_empty:
            continue
        rows.append({"name": c["name"], "count": n})
    return category_icons.decorate(rows)


class AudioBookCategories(BaseHandler):
    """有声书页的分类 tab：{err, total, categories:[{name,count,icon,color}]}。

    §分类必须与分类浏览页一致§
    分类名、顺序、图标全部来自 catalog_categories()——与 /api/categories
    同一份骨架，两页 tab 长得一模一样，只有数字换成「该分类下的有声书数」。
    各算各的（只统计有声书里出现过的分类）会让两页分类对不上，用户实测
    反馈过「跟分类里面的分类不一致」，所以这里刻意不做二次排序。

    count 与 /api/audiobooks?category=X 的列表共用同一个可见集（_visible_audio_ids），
    tab 显示几本，点进去就是几本，绝不允许两个口径。
    有声书数为 0 的分类默认不出（点进去只能是空页）；带 ?all=1 保留，
    用于核对两页分类是否完全一致。
    """

    @js
    async def get(self):
        try:
            catalog = await self.catalog_categories()
            cat_map = audio_category_agg.get_audio_aggregation(
                self.calibre_db_cache)["categories"]
            audio_ids = AudioBooksCache.get_audio_book_ids_set()
            visible = _visible_audio_ids(self)
            keep_empty = str(self.get_argument("all", "")).lower() in ("1", "true", "yes")
            total = len(visible & audio_ids) if visible is not None else len(audio_ids)

            rows = build_audio_tab_categories(catalog, cat_map, visible, keep_empty)
            return {"err": "ok", "total": total, "categories": rows}
        except Exception as e:
            logging.error(f"Error in AudioBookCategories.get: {e}")
            return {"err": "server.error", "msg": str(e)}


class AudioConversion(BaseHandler):
    @staticmethod
    def get_progress(bid):
        try:
            book_id = int(bid)
            worker = ConversionWorkerMap.get(book_id)
            if worker:
                return worker.get_progress()
            else:
                return None
        except Exception as e:
            logging.error(f"Error in AudioConversion.get_progress: {e}")
            return None

    @js
    def get(self, bid):
        # get the conversion status, check it in the worker map,
        # return the status json if found it in the map, otherwise, return not found status.
        try:
            book_id = int(bid)
            progress = self.get_progress(bid)
            if progress:
                if progress["status"] == EpubToAudioWorker.STATUS_CONVERTED:
                    # remove the book id from ConversionWorkerMap
                    ConversionWorkerMap.pop(book_id, None)
                    return {"err": "ok", "msg": _("转换完成"), "data": progress}
                elif progress["status"] == EpubToAudioWorker.STATUS_FAILED:
                    return {
                        "err": "audio.conversion_failed",
                        "msg": _("转换失败"),
                        "data": progress,
                    }
                else:
                    return {
                        "err": "ok",
                        "msg": EpubToAudioWorker.STATUS_PROCESSING,
                        "data": progress,
                    }
            else:
                return {
                    "err": "audio.no_conversion",
                    "msg": _("没有发现转换任务"),
                    "data": None,
                }
        except ValueError:
            return {"err": "params.invalid", "msg": _("无效的书籍ID")}
        except Exception as e:
            logging.error(f"Error in AudioConversion.get: {e}")
            return {"err": "server.error", "msg": str(e)}

    @js
    @is_admin
    async def post(self, bid):
        if not self.is_admin():
            return {
                "err": "permission.not_admin",
                "msg": _("只有管理员可以进行有声书转换"),
            }

        # 获取当前用户，用于后续消息发送
        user = self.get_current_user()
        if not user:
            return {"err": "auth.required", "msg": _("需要登录")}

        try:
            if AudioUtils.get_running_worker_count() >= ALLOW_MAX_RUNNING_WORKERS:
                return {
                    "err": "audio.too_many_conversions",
                    "msg": _("当前转换任务超过2项, 请稍后再试"),
                }

            book_id = int(bid)
            req = tornado.escape.json_decode(self.request.body)
            voice_name = req.get("voice", "zh-CN-YunjianNeural")
            language = req.get("language", "zh-CN")

            logging.info(
                f"Starting audio conversion for book {book_id} with voice {voice_name} and language {language}"
            )

            # Check if book exists
            book = self.get_book(book_id)
            if not book:
                return {"err": "params.book.invalid", "msg": _("书籍未找到")}

            # Check if conversion is already running
            if book_id in ConversionWorkerMap:
                worker = ConversionWorkerMap[book_id]
                if worker.is_running():
                    return {
                        "err": "audio.already_converting",
                        "msg": _("转换已经在进行中"),
                    }
                else:
                    # Remove stale worker
                    ConversionWorkerMap.pop(book_id, None)

            # Get EPUB file path
            epub_path = book.get("fmt_epub")
            if not epub_path:
                return {"err": "params.book.no_epub", "msg": _("书籍没有EPUB格式")}

            # Validate that the EPUB file actually exists
            if not os.path.exists(epub_path):
                return {"err": "params.book.epub_missing", "msg": _("未找到EPUB文件")}

            # Write the metadata
            # save_book_meta 会把整本 EPUB 读进内存再写回（含封面），大书可到
            # 秒级~分钟级，放在 ioloop 上会冻住全站——丢进 calibre 池执行。
            meta_result = await self.run_calibre_async(
                lambda: self.save_book_meta(book_id, fmt="epub"))
            if isinstance(meta_result, dict) and meta_result.get("err") == "book.not_found":
                return {"err": "params.book.invalid", "msg": _("书籍未找到")}

            # Create output directory（书目录内的 .audio/）
            output_dir = audio_dir_for_write(self.calibre_db, book_id)
            if not output_dir:
                return {
                    "err": "audio.no_output_dir",
                    "msg": _("无法确定音频输出目录（书籍未进入书库）"),
                }

            # Save the cover image to the output dir
            try:
                cover_data = self.calibre_db.cover(book_id, index_is_id=True)
                if cover_data:
                    cover_path = os.path.join(output_dir, "cover.jpg")
                    with open(cover_path, "wb") as f:
                        f.write(cover_data)
                    logging.info(
                        f"Saved cover image for book {book_id} to {cover_path}"
                    )
            except Exception as e:
                logging.error(f"Failed to save cover image for book {book_id}: {e}")

            # Create new worker and start conversion
            epub_to_audio_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "epub_to_audio", "main.py"
            )
            worker = EpubToAudioWorker(main_py_path=epub_to_audio_path)
            ConversionWorkerMap[book_id] = worker

            # 创建后台任务
            task_id = None
            try:
                service_item = f"[{book_id}]{book.get('title', f'Book {book_id}')}"
                task = BackgroundService().update_task(
                    service_type=BackgroundTask.SERVICE_TYPE_AUDIO,
                    service_item=service_item,
                    book_id=book_id,
                    progress=0,
                    progress_data={
                        "book_id": book_id,
                        "voice": voice_name,
                        "language": language,
                    },
                )
                task_id = task.id
            except Exception as e:
                logging.error(f"Failed to create background task: {e}")

            # Start conversion in background thread
            def start_conversion():
                logging.info(
                    f"Starting conversion for book {book_id} in background thread"
                )
                logging.info(
                    f"EPUB path: {epub_path}, Output dir: {output_dir}, Voice: {voice_name}, Language: {language}"
                )
                proxy = CONF.get("BOOK2AUDIO_PROXY", None)
                output_srt = CONF.get("ENABLE_AUDIO_SUBTITLE", True)
                try:
                    result = worker.convert_epub_to_audio(
                        epub_path=epub_path,
                        output_dir=output_dir,
                        voice_name=voice_name,
                        language=language,
                        tts="edge",
                        worker_count=2,
                        no_prompt=True,
                        show_output=False,
                        proxy=proxy,
                        output_srt=output_srt,
                    )
                    if result["success"]:
                        worker.progress_data["status"] = (
                            EpubToAudioWorker.STATUS_PROCESSING
                        )
                        # 事件驱动：只把这一本书标记为「有音频」，不再全库扫描
                        AudioBooksCache.mark_has_audio(book_id)
                        # 更新任务为完成
                        if task_id:
                            try:
                                BackgroundService().complete_task(task_id=task_id)
                            except Exception as e:
                                logging.error(f"Failed to complete task: {e}")
                        # 发送成功消息给用户
                        try:
                            book_title = book.get("title", f"书籍{book_id}")
                            success_msg = _(f"《{book_title}》的音频转换已完成")
                            Message.cleanup_messages(user.id, success_msg)
                            msg = Message(user.id, "success", success_msg)
                            msg.save()
                            logging.info(
                                f"Sent success message to user {user.id} for book {book_id}"
                            )
                        except Exception as e:
                            logging.error(f"Failed to send success message: {e}")
                    else:
                        logging.error(
                            f"Conversion failed for book {book_id}: {result.get('error', 'Unknown error')}"
                        )
                        worker.progress_data["status"] = EpubToAudioWorker.STATUS_FAILED
                        worker.progress_data["error_message"] = result.get(
                            "error", "Unknown error"
                        )
                        # 更新任务为失败
                        if task_id:
                            try:
                                BackgroundService().complete_task(
                                    task_id=task_id,
                                    error_message=result.get("error", "Unknown error"),
                                )
                            except Exception as e:
                                logging.error(f"Failed to complete task: {e}")
                        # 发送失败消息给用户
                        try:
                            book_title = book.get("title", f"书籍{book_id}")
                            error_msg = _(
                                f"《{book_title}》的音频转换失败：{result.get('error', 'Unknown error')}"
                            )
                            Message.cleanup_messages(user.id, error_msg)
                            msg = Message(user.id, "error", error_msg)
                            msg.save()
                            logging.info(
                                f"Sent failure message to user {user.id} for book {book_id}"
                            )
                        except Exception as e:
                            logging.error(f"Failed to send failure message: {e}")
                except Exception as e:
                    logging.error(
                        f"Exception during conversion for book {book_id}: {e}"
                    )
                    # Mark worker as failed and clean up
                    worker.progress_data["status"] = EpubToAudioWorker.STATUS_FAILED
                    worker.progress_data["error_message"] = str(e)
                    # 更新任务为失败
                    if task_id:
                        try:
                            BackgroundService().complete_task(
                                task_id=task_id, error_message=str(e)
                            )
                        except Exception as e:
                            logging.error(f"Failed to complete task: {e}")
                    # 发送异常消息给用户
                    try:
                        book_title = book.get("title", f"书籍{book_id}")
                        error_msg = _(f"《{book_title}》的音频转换出现异常：{str(e)}")
                        Message.cleanup_messages(user.id, error_msg)
                        msg = Message(user.id, "error", error_msg)
                        msg.save()
                        logging.info(
                            f"Sent error message to user {user.id} for book {book_id}"
                        )
                    except Exception as msg_error:
                        logging.error(f"Failed to send error message: {msg_error}")
                finally:
                    # Clean up completed or failed workers after some time
                    def cleanup_worker():
                        time.sleep(60)  # Wait 1 minute before cleanup
                        if (
                            book_id in ConversionWorkerMap
                            and not ConversionWorkerMap[book_id].is_running()
                        ):
                            ConversionWorkerMap.pop(book_id, None)

                    cleanup_thread = threading.Thread(target=cleanup_worker)
                    cleanup_thread.daemon = True
                    cleanup_thread.start()

            thread = threading.Thread(target=start_conversion)
            thread.daemon = True
            thread.start()

            logging.info(f"Conversion started for book {book_id} in background thread")
            worker_checker = ConversionWorkerMap.get(book_id)
            if worker_checker:
                return {
                    "err": "ok",
                    "msg": _("开始转换"),
                    "data": worker_checker.get_progress(),
                    "task_id": task_id,
                }
            else:
                logging.error(
                    f"Worker for book {book_id} not found after starting conversion"
                )

            return {"err": "ok", "msg": _("开始转换"), "task_id": task_id}

        except ValueError:
            return {"err": "params.invalid", "msg": _("无效的书籍ID")}
        except Exception as e:
            logging.error(f"Error in AudioConversion.post: {e}")
            return {"err": "server.error", "msg": str(e)}


class AudioConversionCancel(BaseHandler):
    @js
    @is_admin
    def post(self, book_id):
        # cancel the conversion for the book id, if the worker exists, stop it and remove it from the map.
        if not self.is_admin():
            return {
                "err": "permission.not_admin",
                "msg": _("只有管理员可以取消有声书转换"),
            }

        try:
            book_id = int(book_id)
            worker = ConversionWorkerMap.get(book_id)
            if worker:
                worker.stop()
                ConversionWorkerMap.pop(book_id, None)

                # 不 sleep：stop() 只是发停止信号，这里同步睡 1 秒纯粹把
                # 事件循环冻住 1 秒（原实现）。worker 停没停由它的进程自己收尾。
                return {
                    "err": "ok",
                    "msg": _("转换已取消, 可以使用恢复生成功能继续转换"),
                }
            else:
                return {
                    "err": "audio.no_conversion",
                    "msg": _("没有发现转换任务"),
                    "data": None,
                }
        except ValueError:
            return {"err": "params.invalid", "msg": _("无效的书籍ID")}
        except Exception as e:
            logging.error(f"Error in AudioConversionCancel.post: {e}")
            return {"err": "server.error", "msg": str(e)}


class AudioDelete(BaseHandler):
    @js
    @is_admin
    def post(self, book_id):
        # delete the audio file for the book id, if the file exists, remove it.
        # if not found, return not found status.
        if not self.is_admin():
            return {
                "err": "permission.not_admin",
                "msg": _("只有管理员可以删除音频文件"),
            }

        try:
            book_id = int(book_id)
            logging.info(f"AudioDelete requested: book_id={book_id}")
            # Check if conversion is running and stop it first
            worker = ConversionWorkerMap.get(book_id)
            if worker:
                if worker.is_running():
                    return {
                        "err": "audio.conversion_running",
                        "msg": _("无法在转换进行时删除"),
                    }
                ConversionWorkerMap.pop(book_id, None)

            # Delete audio directory（只删 .audio/ 这一层，不动书目录里的书）
            audio_dir, _legacy = resolve_audio_dir(self.calibre_db, book_id)
            if not audio_dir or not os.path.exists(audio_dir):
                return {"err": "audio.not_found", "msg": _("未找到要删除的音频文件")}
            try:
                logging.info(f"AudioDelete requested, audio path:{audio_dir}")
                shutil.rmtree(audio_dir)
                # 事件驱动：只摘掉这一本书的「有音频」标志
                AudioBooksCache.mark_no_audio(book_id)

                # 检查当前书籍是否没有任何格式的文件了，如果是，则删除书籍元数据
                book = self.get_book(book_id, raise_exception=False)
                if book:
                    available_fmts = self.get_all_fmts(book)
                    if not available_fmts:
                        self.delete_book(book_id, book.get("title", ""))
                return {"err": "ok", "msg": _("音频文件删除成功")}
            except OSError as e:
                logging.error(f"Error deleting audio directory {audio_dir}: {e}")
                return {"err": "server.error", "msg": f"清理音频文件遇到错误: {e}"}
        except ValueError:
            return {"err": "params.invalid", "msg": _("无效的书籍ID")}
        except Exception as e:
            logging.error(f"Error in AudioDelete.post: {e}")
            return {"err": "server.error", "msg": str(e)}


class AudioFile(BaseHandler):
    # 异步读盘的分块大小：太大占用内存，太小增加线程池往返次数
    STREAM_CHUNK_SIZE = 128 * 1024

    async def _stream_file(self, file_path, start, length):
        """把文件片段分块读出并异步写回客户端。

        历史实现是在 Tornado 事件循环里同步 `f.read(8192)` + `self.write`：
        一个慢客户端（手机端缓冲、跨公网拖动进度条）就能把整个站点的主循环
        卡住。这里把「读盘」放进线程池，并按块 await flush() 施加背压，
        每连接只保留一个块的内存。
        """
        loop = tornado.ioloop.IOLoop.current()
        with open(file_path, "rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = await loop.run_in_executor(
                    None, fh.read, min(self.STREAM_CHUNK_SIZE, remaining)
                )
                if not chunk:
                    break
                self.write(chunk)
                remaining -= len(chunk)
                # 客户端读得慢时停在这里，避免把整个文件堆进内存
                await self.flush()

    async def get(self, book_id, filename):
        """提供音频文件的静态文件服务"""
        logging.info(f"AudioFile requested: book_id={book_id}, filename={filename}")
        if not BookAccessService.guest_read_allowed(self, book_id):
            user = self.get_current_user()
            if not user:
                raise web.HTTPError(401, "未登录")
        try:
            book_id = int(book_id)

            # URL解码文件名
            filename = urllib.parse.unquote(filename)
            enable_vip_quota = CONF.get(ENABLE_VIP_QUOTA_KEY, False)
            if enable_vip_quota:
                user = self.get_current_user_sync()
            else:
                user = self.get_current_user()

            if enable_vip_quota:
                # 检查当前用户是否已购买此书
                paid_record = (
                    self.sqlite_session.query(ReaderPaidBook)
                    .filter_by(reader_id=user.id, book_id=book_id)
                    .first()
                )

                # 如果未购买，检查是否为免费音频
                if not paid_record:
                    try:
                        # 从文件名中提取序号，文件名格式为0000_xxxxxx, 前四个是序号
                        serial_number = int(filename.split("_")[0])
                        if serial_number > MAX_FREE_AUDIO_FILES:
                            raise web.HTTPError(403, "未购买音频，无法播放此章节")
                    except (ValueError, IndexError):
                        # 如果无法解析序号，则不允许播放
                        raise web.HTTPError(403, "无效的音频文件格式")

            # 安全检查: 确保文件名不包含路径遍历
            if ".." in filename or "/" in filename:
                raise web.HTTPError(403, "Invalid filename")

            # 音频（含同名字幕）都在书目录内的 .audio/ 下，没有第二处可找。
            audio_dir = resolve_audio_dir_or_404(self.calibre_db, book_id)
            file_path = os.path.join(audio_dir, filename)
            if not os.path.exists(file_path):
                logging.warning("[AUDIO] file not found: %s (dir: %s)",
                                filename, audio_dir)
                raise web.HTTPError(404, "Audio file not found")

            # 设置适当的Content-Type
            ext = os.path.splitext(filename)[1].lower()
            content_types = {
                ".mp3": "audio/mpeg",
                ".wav": "audio/wav",
                ".m4a": "audio/mp4",
                ".m4b": "audio/mp4",
                ".opus": "audio/opus",
                ".wma": "audio/x-ms-wma",
                ".srt": "application/x-subrip",
                ".vtt": "text/vtt",
            }
            self.set_header("Content-Type", content_types.get(ext, "audio/mpeg"))

            # 支持范围请求 (Range requests) 用于音频播放
            self.set_header("Accept-Ranges", "bytes")

            # 获取文件大小
            file_size = os.path.getsize(file_path)

            # §缓存校验头§ 没有 ETag/Last-Modified 时，浏览器每次 seek 完都要
            # 重新走一遍完整请求；更糟的是配了 max-age=0 后连内存缓存都不复用，
            # 同一个音频在短时间内被反复整段重新请求。音频是只读静态文件，
            # 用 etag = 大小-修改时间即可，命中后浏览器直接本地取。
            try:
                st = os.stat(file_path)
                self.set_header(
                    "ETag", '"%x-%x"' % (int(st.st_size), int(st.st_mtime))
                )
                self.set_header(
                    "Last-Modified",
                    formatdate(st.st_mtime, usegmt=True),
                )
                # 私有缓存 1 小时：音频内容不会变（换章节就是换文件名）
                self.set_header("Cache-Control", "private, max-age=3600")
            except OSError:
                pass

            # §HEAD 请求不能带 body§ BaseHandler.head() 直接转调 get()，会把
            # 整个音频文件当成 HEAD 响应体写出去：既浪费带宽，又让浏览器/
            # 播放器拿到一个「有 body 的 HEAD」，部分实现会据此判为异常响应并
            # 重新发起请求，表现为音频反复重载、进度条不动。
            if self.request.method == "HEAD":
                self.set_header("Content-Length", str(file_size))
                self.set_status(200)
                return

            # 处理范围请求
            range_header = self.request.headers.get("Range")
            if range_header:
                range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
                if range_match:
                    start = int(range_match.group(1))
                    end = (
                        int(range_match.group(2))
                        if range_match.group(2)
                        else file_size - 1
                    )

                    if start >= file_size:
                        # RFC 7233：416 必须带 Content-Range: bytes */size
                        self.set_status(416)  # Range Not Satisfiable
                        self.set_header("Content-Range", f"bytes */{file_size}")
                        return
                    # 客户端可能给超出文件末尾的 end（如 bytes=0-999999999），
                    # 不夹紧就会写出比实际内容多的 Content-Length，浏览器读不满
                    # 会一直等，表现为「卡住不动」。
                    if end >= file_size:
                        end = file_size - 1
                    if end < start:
                        self.set_status(416)
                        self.set_header("Content-Range", f"bytes */{file_size}")
                        return

                    self.set_status(206)  # Partial Content
                    self.set_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                    self.set_header("Content-Length", str(end - start + 1))

                    await self._stream_file(file_path, start, end - start + 1)
                    return

            # 正常文件传输
            self.set_header("Content-Length", str(file_size))
            await self._stream_file(file_path, 0, file_size)
        except StreamClosedError:
            # 客户端拖动进度条/切歌时会主动断开，写失败属正常现象，不必报错
            logging.debug("AudioFile client closed early: book_id=%s", book_id)
            return
        except ValueError:
            raise web.HTTPError(400, "Invalid book ID")
        except Exception as e:
            logging.error(f"Error in AudioFile.get: {e}")
            raise web.HTTPError(500, "内部错误")


class AudioCollection(BaseHandler):
    def create_biz_key(self):
        user = self.get_current_user()
        # 生成32位随机key
        download_key = uuid.uuid4().hex
        # 保存key到BizKey表，设置过期时间为24小时
        expire_time = datetime.datetime.now() + datetime.timedelta(hours=24)
        biz_key = BizKey(
            user.id, key=download_key, expire=expire_time, type=BizKey.TYPE_DOWNLOAD
        )
        try:
            biz_key.save()
        except Exception as e:
            logging.error(f"Error saving BizKey: {e}")
            return None
        return download_key

    @js
    @auth
    def get(self, book_id):
        """音频合集下载接口"""
        try:
            book_id = int(book_id)

            # 获取当前用户
            user = self.get_current_user()
            if not user:
                return {"err": "auth.required", "msg": _("需要登录")}

            db_log = ReaderLog(
                user.id, ReaderLog.ACTION_COLLECTION_DOWNLOAD, user.id, revision=VERSION
            )
            db_log.set_extra("book_id", book_id)

            # 检查书籍是否存在
            book = self.get_book(book_id)
            if not book:
                db_log.set_extra("result", -1)
                db_log.set_extra("reason", "book.not_found")
                db_log.save()
                return {"err": "book.not_found", "msg": _("书籍未找到")}

            enable_vip_quota = CONF.get(ENABLE_VIP_QUOTA_KEY, False)
            if enable_vip_quota:
                # 检查用户是否已购买此书
                paid_record = (
                    self.sqlite_session.query(ReaderPaidBook)
                    .filter_by(reader_id=user.id, book_id=book_id)
                    .first()
                )

                if not paid_record:
                    db_log.set_extra("result", -1)
                    db_log.set_extra("reason", "not.purchased")
                    db_log.save()
                    return {
                        "err": "not.purchased",
                        "msg": _("您还未购买此音频，请先购买"),
                    }

                # 检查每日下载限制
                download_key = (user.id, book_id)
                today = datetime.datetime.now().date()

                if download_key in DailyDownloadMap:
                    last_download = DailyDownloadMap[download_key]
                    if last_download.date() == today:
                        db_log.set_extra("result", -1)
                        db_log.set_extra("reason", "daily.limit.exceeded")
                        db_log.save()
                        return {
                            "err": "daily.limit.exceeded",
                            "msg": _("今日已下载过此音频合集，请明天再试"),
                        }

            # 检查音频目录
            audio_dir, _legacy = resolve_audio_dir(self.calibre_db, book_id)
            if not audio_dir or not os.path.exists(audio_dir):
                logging.error(f"Audio directory does not exist: {audio_dir}")
                return {"err": "audio.not_found", "msg": _("音频文件不存在")}

            audio_files = [
                f
                for f in os.listdir(audio_dir)
                if f.lower().endswith(tuple(SUPPORTED_AUDIO_FORMATS))
            ]
            if not audio_files:
                return {"err": "audio.not_found", "msg": _("音频文件不存在")}

            # 检查zip文件是否已存在
            zip_filename = f"audio_collection_{book_id}.zip"
            zip_path = os.path.join(audio_dir, zip_filename)

            # 如果zip不存在，创建它
            if not os.path.exists(zip_path):
                try:
                    # 字幕文件一并打包（与音频同名）
                    subtitle_files = [
                        f
                        for f in os.listdir(audio_dir)
                        if f.lower().endswith(tuple(SUPPORTED_SUBTITLE_FORMATS))
                    ]
                    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                        for audio_file in sorted(audio_files, key=natural_sort_key):
                            # 同上：以 CIP 前缀开头的文件跳过
                            if audio_file.startswith(SKIP_AUDIO_FILE_PREFIX):
                                continue
                            file_path = os.path.join(audio_dir, audio_file)
                            zipf.write(file_path, audio_file)
                        for sub_file in sorted(subtitle_files):
                            sub_path = os.path.join(audio_dir, sub_file)
                            if os.path.exists(sub_path):
                                zipf.write(sub_path, sub_file)
                except Exception as e:
                    logging.error(f"Error creating zip file: {e}")
                    return {"err": "server.error", "msg": _("创建压缩文件失败")}

            # 查询是否已有未过期的下载key
            existing_key = (
                self.sqlite_session.query(BizKey)
                .filter_by(reader_id=user.id, type=BizKey.TYPE_DOWNLOAD)
                .filter(BizKey.expire > datetime.datetime.now())
                .first()
            )
            if existing_key:
                download_key = existing_key.key
            else:
                # 创建下载key，不需要扣减VIP配额
                download_key = self.create_biz_key()

            if not download_key:
                return {"err": "server.error", "msg": _("内部处理错误")}

            # 记录下载时间
            _record_daily_download(user.id, book_id)

            # 生成下载链接
            download_url = f"/api/audios/{book_id}/collection/download?key={download_key}"

            # 保存日志
            db_log.set_extra("result", 0)
            db_log.set_extra("reason", "success")
            db_log.save()

            return {
                "err": "ok",
                "download_url": download_url,
                "message": "下载链接已生成",
            }
        except ValueError:
            return {"err": "params.invalid", "msg": _("无效的书籍ID")}
        except Exception as e:
            logging.error(f"Error in AudioCollectionDownload.get: {e}")
            logging.error(f"Stack trace: {traceback.format_exc()}")

            return {"err": "server.error", "msg": str(e)}


class AudioCollectionDownloadFile(BaseHandler):
    def get(self, book_id):
        """音频合集文件下载接口"""
        try:
            logging.info(f"AudioCollectionDownloadFile called for book_id: {book_id}")
            book_id = int(book_id)
            download_key = self.get_argument("key", "")

            if not download_key:
                raise web.HTTPError(400, "Missing download key")

            # 验证下载key
            biz_key = (
                self.sqlite_session.query(BizKey)
                .filter_by(key=download_key, type=BizKey.TYPE_DOWNLOAD)
                .first()
            )
            if not biz_key:
                raise web.HTTPError(403, "Invalid download key")

            if biz_key.expire < datetime.datetime.now():
                # 清理过期的key
                biz_key.delete()
                raise web.HTTPError(403, "Download key expired")

            # key 与书是分开传的：一张有效 key 原本可以下载任意书的合集。
            # 开启 VIP 配额时在这里按 key 属主补一次购买校验——否则买过 A 书
            # 的用户拿同一个 key 就能绕过付费检查拉走 B 书的合集。
            if CONF.get(ENABLE_VIP_QUOTA_KEY, False):
                paid = (
                    self.sqlite_session.query(ReaderPaidBook)
                    .filter_by(reader_id=biz_key.reader_id, book_id=book_id)
                    .first()
                )
                if not paid:
                    raise web.HTTPError(403, "Book not purchased")

            # 检查zip文件
            audio_dir = resolve_audio_dir_or_404(self.calibre_db, book_id)
            zip_filename = f"audio_collection_{book_id}.zip"
            zip_path = os.path.join(audio_dir, zip_filename)
            uid = biz_key.reader_id

            db_log = ReaderLog(
                uid, ReaderLog.ACTION_COLLECTION_DOWNLOAD_START, uid, revision=VERSION
            )
            db_log.set_extra("book_id", book_id)
            db_log.save()

            if not os.path.exists(zip_path):
                raise web.HTTPError(404, "合集文件不存在")

            # 获取书籍信息用于文件名
            book = self.get_book(book_id)
            safe_title = "".join(
                c
                for c in (
                    book.get("title", f"book_{book_id}") if book else f"book_{book_id}"
                )
                if c.isalnum() or c in (" ", "-", "_")
            ).rstrip()

            # 构建文件名，处理中文字符
            filename_base = f"{safe_title}_音频合集.zip"
            # URL编码文件名以支持中文
            encoded_filename = urllib.parse.quote(filename_base.encode("utf-8"))

            # 设置响应头
            self.set_header("Content-Type", "application/zip")
            # 使用 RFC 5987 标准来支持非ASCII字符的文件名
            self.set_header(
                "Content-Disposition",
                f"attachment; filename*=UTF-8''{encoded_filename}",
            )

            # 获取文件大小
            file_size = os.path.getsize(zip_path)
            self.set_header("Content-Length", str(file_size))

            # 传输文件
            start = time.time()
            chunk_size = 2 * 1024 * 1024  # 2MB
            with open(zip_path, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    self.write(chunk)
            duration = int(time.time() - start)

            try:
                db_log = ReaderLog(
                    uid,
                    ReaderLog.ACTION_COLLECTION_DOWNLOAD_FINISHED,
                    uid,
                    revision=VERSION,
                )
                db_log.set_extra("book_id", book_id)
                db_log.set_extra("duration", duration)
                db_log.save()
                # 删除使用过的key
                self.sqlite_session.delete(biz_key)
                self.sqlite_session.commit()
            except Exception as e:
                logging.error(f"Error deleting BizKey after download: {e}")
        except ValueError:
            raise web.HTTPError(400, "Invalid book ID")
        except Exception as e:
            logging.error(f"Error in AudioCollectionDownloadFile.get: {e}")
            raise web.HTTPError(500, "Internal server error")


class AudioPurchase(BaseHandler):
    @js
    @auth
    def post(self, book_id):
        """音频购买接口"""
        try:
            book_id = int(book_id)

            # 获取当前用户
            user = self.get_current_user_sync()
            if not user:
                return {"err": "auth.required", "msg": _("需要登录")}

            # 检查书籍是否存在
            book = self.get_book(book_id)
            if not book:
                return {"err": "book.not_found", "msg": _("书籍未找到")}

            # 检查是否启用VIP配额功能
            enable_vip_quota = CONF.get(ENABLE_VIP_QUOTA_KEY, False)

            if enable_vip_quota:
                # 检查VIP是否过期
                if not user.vipexpire or user.vipexpire < datetime.datetime.now():
                    # 读取VIP说明文件
                    vip_notes_path = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                        "app",
                        "public",
                        "vip_notes.txt",
                    )
                    vip_notes = ""
                    try:
                        if os.path.exists(vip_notes_path):
                            with open(vip_notes_path, "r", encoding="utf-8") as f:
                                vip_notes = f.read()
                    except Exception as e:
                        logging.error(f"Error reading vip_notes.txt: {e}")
                        vip_notes = _("无法读取VIP说明文件")

                    return {
                        "err": "vip.expired",
                        "msg": _("非VIP用户或VIP已过期，无法购买音频"),
                        "vipexpired": (
                            user.vipexpire.strftime("%Y-%m-%d %H:%M:%S")
                            if user.vipexpire
                            else ""
                        ),
                        "notes": vip_notes,
                    }

                # 检查VIP配额
                if user.vipquota <= 0:
                    # 读取VIP说明文件
                    vip_notes_path = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                        "app",
                        "public",
                        "vip_notes.txt",
                    )
                    vip_notes = ""
                    try:
                        if os.path.exists(vip_notes_path):
                            with open(vip_notes_path, "r", encoding="utf-8") as f:
                                vip_notes = f.read()
                    except Exception as e:
                        logging.error(f"Error reading vip_notes.txt: {e}")
                        vip_notes = _("无法读取VIP说明文件")

                    return {
                        "err": "vip.quota_insufficient",
                        "msg": _("购买的额度不足"),
                        "notes": vip_notes,
                    }

            # 检查是否已经购买过
            existing_purchase = (
                self.sqlite_session.query(ReaderPaidBook)
                .filter_by(reader_id=user.id, book_id=book_id)
                .first()
            )

            if existing_purchase:
                return {"err": "already.purchased", "msg": _("您已经购买过此音频")}

            # 检查音频是否存在
            audio_dir, _legacy = resolve_audio_dir(self.calibre_db, book_id)
            if not audio_dir or not os.path.exists(audio_dir):
                return {"err": "audio.not_found", "msg": _("音频文件不存在")}

            audio_files = [
                f
                for f in os.listdir(audio_dir)
                if f.endswith((".mp3", ".wav", ".m4a", ".opus"))
            ]
            if not audio_files:
                return {"err": "audio.not_found", "msg": _("音频文件不存在")}

            # 创建购买记录
            # 生成订单ID
            import uuid

            order_id = uuid.uuid4().hex

            # 这里可以设置音频的价格，暂时设为1（可以从配置或书籍信息中获取）
            price = CONF.get("audio_price", 1)

            paid_book = ReaderPaidBook(
                reader_id=user.id, book_id=book_id, order_id=order_id, price=price
            )

            try:
                paid_book.save()

                # 如果启用VIP配额功能，则扣减用户VIP配额
                if enable_vip_quota:
                    try:
                        user.vipquota -= 1
                        user.save()
                    except Exception as e:
                        logging.error(f"Error updating user quota after purchase: {e}")
                        # 如果配额扣减失败，回滚购买记录
                        try:
                            self.sqlite_session.delete(paid_book)
                            self.sqlite_session.commit()
                        except:
                            pass
                        return {
                            "err": "server.error",
                            "msg": _("购买失败，配额扣减出错"),
                        }

                # 记录购买日志
                log = ReaderLog(user.id, ReaderLog.ACTION_PURCHASE, user.id)
                log.set_extra("book_id", book_id)
                log.set_extra("order_id", order_id)
                log.set_extra("price", price)
                log.save()

                return {"err": "ok", "msg": _("购买成功"), "order_id": order_id}
            except Exception as e:
                logging.error(f"Error saving purchase record: {e}")
                return {"err": "server.error", "msg": _("购买失败，请稍后重试")}

        except ValueError:
            return {"err": "params.invalid", "msg": _("无效的书籍ID")}
        except Exception as e:
            logging.error(f"Error in AudioPurchase.post: {e}")
            return {"err": "server.error", "msg": str(e)}


def _now_ms():
    """毫秒时间戳。多设备进度仲裁用整数比较，避免 ISO 字符串各自带时区/
    精度差异（前端 Date.parse 再比，误差按毫秒算也不该由字符串格式决定）。"""
    return int(time.time() * 1000)


class AudioPlaybackProgress(BaseHandler):
    """有声书播放进度的服务端存取（4.6.0-19）。

    此前进度只存浏览器 localStorage：换设备/换浏览器/清缓存即丢，服务器
    完全不参与。语义与前端播放器对齐：track_index=播放列表序号，
    position=该集内秒数（audio.currentTime）。前端每 ~15s 和暂停/切集/
    离开页面上报一次；GET 返回 null 表示这本书还没播过。
    """

    @js
    @auth
    def get(self, book_id):
        try:
            book_id = int(book_id)
        except (TypeError, ValueError):
            return {"err": "params.invalid", "msg": _("无效的书籍ID")}
        user = self.get_current_user()
        if not user:
            return {"err": "auth.required", "msg": _("需要登录")}
        row = (
            self.sqlite_session.query(AudioPlayback)
            .filter_by(reader_id=user.id, book_id=book_id)
            .first()
        )
        return {"err": "ok", "data": row.format_dict() if row else None, "ts": _now_ms()}

    @js
    @auth
    def post(self, book_id):
        try:
            book_id = int(book_id)
        except (TypeError, ValueError):
            return {"err": "params.invalid", "msg": _("无效的书籍ID")}
        user = self.get_current_user()
        if not user:
            return {"err": "auth.required", "msg": _("需要登录")}

        try:
            data = tornado.escape.json_decode(self.request.body or b"{}")
        except Exception:
            return {"err": "params.invalid", "msg": _("参数错误")}

        # §多设备仲裁§ 客户端带上「这次进度产生的时刻」client_ts（毫秒）。
        # 两台设备交替播放时，晚到的请求不一定包含更新的位置（另一台可能
        # 还停在旧位置又心跳了一次）。只接受严格更新的时间戳，旧的一律丢弃，
        # 并把服务端当前值回给客户端，让它知道自己的值没被采纳。
        try:
            client_ts = int(float(data.get("client_ts") or 0))
        except (TypeError, ValueError):
            client_ts = 0
        # 未来时间（设备时钟快/恶意）钳到当前时刻，否则这台设备会「永久」锁死
        # 其他设备的所有写入。
        if client_ts > _now_ms() + 60000:
            client_ts = _now_ms()
        try:
            track_index = int(data.get("track_index") or 0)
            position = float(data.get("position") or 0)
            duration = data.get("duration")
            duration = float(duration) if duration is not None else None
        except (TypeError, ValueError):
            return {"err": "params.invalid", "msg": _("进度参数必须是数字")}
        # 钳制：负值/异常巨大的值一律拉回合法范围，避免脏数据
        track_index = max(0, min(track_index, 100000))
        position = max(0.0, min(position, 86400 * 14))
        if duration is not None:
            duration = max(0.0, min(duration, 86400 * 14))

        try:
            row = (
                self.sqlite_session.query(AudioPlayback)
                .filter_by(reader_id=user.id, book_id=book_id)
                .first()
            )
            if row:
                prev_ts = getattr(row, "client_ts", None) or 0
                if client_ts and client_ts <= prev_ts:
                    # 旧写入，丢弃但不报错（客户端心跳不必重试）
                    logging.info(
                        "[AUDIO] progress ignored (older client_ts %s <= %s) user=%s book=%s",
                        client_ts, prev_ts, user.id, book_id,
                    )
                    return {"err": "ok", "data": row.format_dict(), "ts": _now_ms()}
                row.track_index = track_index
                row.position = position
                row.duration = duration
                row.updated_at = datetime.datetime.now()
                row.client_ts = client_ts or _now_ms()
                row.save()
                return {"err": "ok", "data": row.format_dict(), "ts": _now_ms()}
            row = AudioPlayback(user.id, book_id, track_index, position, duration)
            row.client_ts = client_ts or _now_ms()
            row.save()
            return {"err": "ok", "data": row.format_dict(), "ts": _now_ms()}
        except Exception as e:
            logging.error(f"Error saving audio playback progress: {e}")
            return {"err": "server.error", "msg": _("保存进度失败")}


def routes():
    return [
        (r"/api/audio/([0-9]+)", AudioDetail),
        (r"/api/audio/([0-9]+)/conversion", AudioConversion),
        (r"/api/audio/([0-9]+)/cancel", AudioConversionCancel),
        (r"/api/audio/([0-9]+)/delete", AudioDelete),
        (r"/api/audio/([0-9]+)/purchase", AudioPurchase),  # 音频购买接口
        (r"/api/audio/([0-9]+)/progress", AudioPlaybackProgress),  # 播放进度（跨设备续播）
        (r"/api/audiobooks/categories", AudioBookCategories),  # 有声书页分类 tab（须在 /api/audiobooks 之前注册）
        (r"/api/audiobooks", AudioBooks),  # 音频书籍列表
        (r"/api/audio/([0-9]+)/([^/]+)", AudioFile),
        (r"/api/audios/([0-9]+)/collection", AudioCollection),  # 音频合集下载接口
        (r"/api/audios/([0-9]+)/collection/download", AudioCollectionDownloadFile),
    ]
