#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import hashlib
import logging
import os
import shutil
import subprocess
import time
import traceback

from webserver import loader, utils, constants
from webserver.i18n import _
from webserver.models import ScanFile, Item
from webserver.services import AsyncService
from webserver.services.background_service import BackgroundService, BackgroundTask
from webserver.services.scan_service import ScanService
from webserver.base.meta_helper import guess_authors
from webserver.base.author_norm import resolve_alias  # 4.6.0-9 作者归一化

CONF = loader.get_settings()

AUDIO_IMPORT_DIR = os.path.join(CONF.get("scan_upload_path", "/data/books/imports/"), constants.AUDIO_BOOK_IMPORTS)
AUDIO_OUTPUT_DIR = CONF.get("audio_output_folder", "/data/books/audios/")

COVER_NAMES = {"cover.jpg", "cover.jpeg", "cover.png"}


def _link_to_existing_enabled():
    """是否启用「同名电子书存在时把音频挂上去」的行为（设置项可关）。

    默认开启：这是修掉「同一本书出现两条记录」的开关。
    关掉恢复旧行为，供书名重复严重、想每批音频都独立成书的场景使用。
    """
    value = CONF.get("AUDIO_LINK_TO_EXISTING_BOOK", True)
    if isinstance(value, str):
        return value.strip().lower() not in ("0", "false", "no", "off", "")
    return bool(value)


def _find_cover(dir_path):
    try:
        for fname in os.listdir(dir_path):
            if fname.lower() in COVER_NAMES:
                return os.path.join(dir_path, fname)
    except OSError:
        pass
    return None


def _read_cover_data(cover_path):
    try:
        with open(cover_path, "rb") as f:
            data = f.read()
        ext = os.path.splitext(cover_path)[1].lstrip(".").lower()
        if ext in ("jpg", "jpeg"):
            ext = "jpeg"
        return ext, data
    except OSError:
        return None, None


def _get_dest_filename(filename):
    """Get the destination filename, converting .wma to .mp3 extension."""
    name, ext = os.path.splitext(filename)
    if ext.lower() == ".wma":
        return name + ".mp3"
    return filename


def _convert_wma_to_mp3(src_path, dst_path):
    """Convert a WMA file to MP3 using ffmpeg."""
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", src_path, "-codec:a", "libmp3lame", "-q:a", "2", dst_path],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logging.info("[AUDIO_IMPORT] Converted WMA to MP3: %s -> %s", src_path, dst_path)
        return True
    except FileNotFoundError:
        logging.error("[AUDIO_IMPORT] ffmpeg not found. Please install ffmpeg to convert WMA files.")
        return False
    except subprocess.CalledProcessError as e:
        logging.error("[AUDIO_IMPORT] ffmpeg conversion failed for %s: %s", src_path, e)
        return False


def _copy_or_convert_file(src_path, dst_dir):
    """Copy a file to dst_dir. If it's a WMA file, convert to MP3 instead."""
    filename = os.path.basename(src_path)
    dest_filename = _get_dest_filename(filename)
    dst_path = os.path.join(dst_dir, dest_filename)

    if os.path.exists(dst_path):
        return

    if filename.lower().endswith(".wma"):
        # remove original wma file if existed
        try:
            dst_wma_file = os.path.join(dst_dir, filename)
            if os.path.exists(dst_wma_file):
                os.remove(dst_wma_file)
        except Exception:
            pass
        _convert_wma_to_mp3(src_path, dst_path)
    else:
        shutil.copy2(src_path, dst_path)


def _extract_audio_metadata(audio_path, fallback_title):
    try:
        import mutagen
        audio = mutagen.File(audio_path, easy=True)
        if audio is None:
            return fallback_title, None
        title = None
        author = None
        if hasattr(audio, "tags") and audio.tags:
            title_tag = audio.tags.get("album") or audio.tags.get("title")
            author_tag = audio.tags.get("artist") or audio.tags.get("albumartist")
            if title_tag:
                title = str(title_tag[0]).strip() if isinstance(title_tag, list) else str(title_tag).strip()
            if author_tag:
                author = str(author_tag[0]).strip() if isinstance(author_tag, list) else str(author_tag).strip()

        # Fallback for some m4b files (e.g. lavf) where easy=True doesn't map the tags
        if not title or not author:
            raw_audio = mutagen.File(audio_path, easy=False)
            if hasattr(raw_audio, "tags") and raw_audio.tags:
                if not title:
                    title_tag = raw_audio.tags.get("\x00\x00\x00\x01")
                    if title_tag:
                        title = str(title_tag[0]).strip() if isinstance(title_tag, list) else str(title_tag).strip()
                if not author:
                    author_tag = raw_audio.tags.get("\x00\x00\x00\x02")
                    if author_tag:
                        author = str(author_tag[0]).strip() if isinstance(author_tag, list) else str(author_tag).strip()

        logging.debug("[AUDIO_IMPORT] Extracted metadata from %s: title=%s, author=%s", audio_path, title, author)
        return title or fallback_title, author
    except Exception as e:
        logging.warning("[AUDIO_IMPORT] Failed to read audio metadata from %s: %s", audio_path, e)
        return fallback_title, None


class AudioBookImporter(AsyncService):
    static_is_running = False
    static_status = {
        "total": 0,
        "imported": 0,
        "exist": 0,
        "skipped": 0,
        # linked: 音频被挂到已有电子书上（没有新建 calibre 记录）的数量
        "linked": 0,
    }

    @staticmethod
    def is_running():
        return AudioBookImporter.static_is_running

    @staticmethod
    def get_status():
        return AudioBookImporter.static_status.copy()

    def save_or_rollback(self, row):
        try:
            row.save()
            self.session.commit()
            return True
        except Exception as err:
            logging.error("[AUDIO_IMPORT] save error: %s", err)
            self.session.rollback()
            return False

    def _add_new_book(self, user_id, mi, cover_path):
        logging.debug("[AUDIO_IMPORT] Adding new book: title=%s, author=%s", mi.title, mi.authors[0] if mi.authors else "N/A")
        book_id = None
        try:
            if cover_path:
                ext, cover_data = _read_cover_data(cover_path)
                if cover_data:
                    mi.cover_data = (ext, cover_data)
            book_id = self.db.create_book_entry(mi)
        except Exception as err:
            logging.error("[AUDIO_IMPORT] error creating book entry for %s: %s", mi.title, err)
            logging.error(traceback.format_exc())
            return None

        if not book_id:
            return None

        # Add a Item record
        try:
            item = Item()
            item.book_id = book_id
            item.collector_id = user_id
            item.save()
        except Exception as err:
            logging.error("[AUDIO_IMPORT] error updating book_type for book_id %s: %s", book_id, err)
            logging.error(traceback.format_exc())
            self.db.session.rollback()

        return book_id

    def _check_audio_exists(self, book_id):
        audio_dir = os.path.join(AUDIO_OUTPUT_DIR, str(book_id))
        if not os.path.isdir(audio_dir):
            return False
        audio_files = [f for f in os.listdir(audio_dir) if f.lower().endswith(tuple(constants.SUPPORTED_AUDIO_FORMATS))]
        if audio_files:
            return True
        return False

    def _pick_linkable_book(self, ids):
        """同名电子书已存在但没有音频时，挑一本书把音频挂上去。

        选择优先级（都满足「书名相同」这个前提）：
          1. `library/` 里确实有实体文件的书（真正的电子书）—— 最理想
          2. 若有多本，优先「实体书类型」以外的，避免挂到纸质书条目
          3. 实在分不出来就取 book_id 最小的（最早建的那本，通常是正主）

        返回 book_id 或 None（None 表示无法确定，调用方会新建）。
        """
        if not ids:
            return None
        try:
            candidates = sorted(ids)
        except TypeError:
            candidates = list(ids)

        # 优先找 library 目录里真有格式文件的那本
        for bid in candidates:
            try:
                if self._book_has_ebook_file(bid):
                    return bid
            except Exception as err:
                logging.debug("[AUDIO_IMPORT] check ebook file for %s failed: %s", bid, err)

        # 都查不到实体文件（可能是 calibre 库路径不同/权限问题），退而取第一本。
        # 这里不返回 None：宁可挂到已有条目上，也不要平白多出一条重复书。
        return candidates[0]

    def _book_has_ebook_file(self, book_id):
        """这本书在 calibre library 里是否有实体电子书文件（epub/pdf/mobi...）。"""
        try:
            data = self.db.get_data_as_dict(book_ids=[book_id])
            if not data:
                return False
            row = data[0] if isinstance(data, (list, tuple)) else data.get(book_id)
            if not row:
                return False
            # available_formats 是扩展名列表（EPUB/PDF），formats 是实际文件路径
            fmts = row.get("available_formats")
            if fmts:
                return True
            paths = row.get("formats") or []
            if isinstance(paths, str):
                paths = [paths]
            return any(p and os.path.exists(str(p)) for p in paths)
        except Exception:
            return False

    def _synch_audio_files(self, src_dir, dest_dir):
        logging.debug(f"[AUDIO_IMPORT] Synchronizing audio files from {src_dir} to {dest_dir}")
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
        for fname in os.listdir(src_dir):
            src = os.path.join(src_dir, fname)
            if os.path.isfile(src):
                _copy_or_convert_file(src, dest_dir)

    @AsyncService.register_service
    def do_import(self, user_id):
        with ScanService.task_claim_lock:
            if AudioBookImporter.static_is_running:
                logging.error("[AUDIO_IMPORT] already running, skip")
                return
            if ScanService.is_bulk_deleting():
                # 二道闸：handler 检查与异步入队之间存在窗口，服务线程入口再拦一次
                logging.error("[AUDIO_IMPORT] bulk deleting is running, skip")
                self.add_msg(user_id=user_id, status="error", msg=_("已有批量删除任务正在运行，请稍后再试"))
                return
            AudioBookImporter.static_is_running = True

        AudioBookImporter.static_status = {
            "total": 0,
            "imported": 0,
            "exist": 0,
            "skipped": 0,
            "linked": 0,
        }

        task_id = None
        try:
            task = BackgroundService().update_task(
                service_type=BackgroundTask.SERVICE_TYPE_AUDIO_IMPORT,
                service_item=_("导入有声书"),
                progress=0,
                progress_data={"total": 0, "imported": 0, "exist": 0},
            )
            task_id = task.id
        except Exception as e:
            logging.error("[AUDIO_IMPORT] Failed to create background task: %s", e)

        try:
            self._do_import_internal(user_id, task_id)
            if task_id:
                BackgroundService().complete_task(task_id=task_id)
            logging.info("[AUDIO_IMPORT] completed")
        except Exception as err:
            logging.error("[AUDIO_IMPORT] failed: %s", err)
            logging.error(traceback.format_exc())
            if task_id:
                BackgroundService().complete_task(task_id=task_id, error_message=str(err))
        finally:
            AudioBookImporter.static_is_running = False

    def _do_import_internal(self, user_id, task_id=None):
        from calibre.ebooks.metadata.book.base import Metadata
        import_dir = AUDIO_IMPORT_DIR
        output_dir = AUDIO_OUTPUT_DIR

        if not os.path.isdir(import_dir):
            logging.warning("[AUDIO_IMPORT] import dir does not exist: %s", import_dir)
            return

        subdirs = sorted([
            d for d in os.listdir(import_dir)
            if os.path.isdir(os.path.join(import_dir, d))
        ])

        total = len(subdirs)
        AudioBookImporter.static_status["total"] = total
        imported_ids = []
        imported_without_cover = []

        for idx, dir_name in enumerate(subdirs):
            dir_path = os.path.join(import_dir, dir_name)
            dir_hash = "audiodir:" + hashlib.md5(dir_path.encode("utf-8")).hexdigest()
            logging.info("[AUDIO_IMPORT] Processing directory %d/%d: %s", idx + 1, total, dir_path)

            existing = self.session.query(ScanFile).filter(ScanFile.hash == dir_hash).first()
            if existing and existing.status in (ScanFile.IMPORTED, ScanFile.EXIST):
                # 存在已导入有声书时，检查当前音频目录中相对对应的有声书目录(/data/books/audios/<book_id>)是否有新增的音频文件
                if existing.status == ScanFile.IMPORTED:
                    book_id = existing.book_id
                    if book_id and self._check_audio_exists(book_id):
                        self._synch_audio_files(dir_path, os.path.join(output_dir, str(book_id)))

                AudioBookImporter.static_status["skipped"] += 1
                self._update_progress(task_id, idx + 1, total)
                continue

            logging.info("[AUDIO_IMPORT] new record for %s, will attempt to import", dir_path)
            audio_files = sorted([
                f for f in os.listdir(dir_path) if f.lower().endswith(tuple(constants.SUPPORTED_AUDIO_FORMATS))
            ])
            if not audio_files:
                logging.info("[AUDIO_IMPORT] no audio files in %s, skipping", dir_path)
                AudioBookImporter.static_status["skipped"] += 1
                self._update_progress(task_id, idx + 1, total)
                continue

            first_audio = os.path.join(dir_path, audio_files[0])
            title, author = _extract_audio_metadata(first_audio, dir_name)
            if not author:
                author = _("佚名")
            title = utils.super_strip(title) if title else dir_name
            author = utils.super_strip(author) if author else _("佚名")
            # 4.6.0-9：有声书是作者名最脏的来源——ID3 的 artist 字段里
            # 常见 "某某听书"、"酷我音乐"、多歌手用逗号连写、带国籍前缀等。
            # 这里做两步：先 L1 清洗（去前缀后缀、拆多人后取第一个），
            # 再查别名表统一到标准名。有声书固定用单作者，不拆多人。
            # 清洗结果为空时回退原文，避免把有作者的书标成"佚名"。
            # ⚠️ 不能用 "_" 接收译者列表：本模块的 "_" 是 i18n 函数，
            # 覆盖后后面所有 _("...") 都会崩。
            _cleaned, _cleaned_trans = guess_authors([author])
            author = _cleaned[0] if _cleaned else author
            author = resolve_alias(author) or author

            cover_path = _find_cover(dir_path)
            has_cover = cover_path is not None

            row = existing or ScanFile(dir_path, dir_hash, 0)
            row.import_type = constants.IMPORT_TYPE_AUDIOBOOK
            row.title = title
            row.author = author

            mi = Metadata(title, [author])
            mi.title_sort = utils.get_title_sort(title)

            try:
                ids = self.db.books_with_same_title(mi)
                book_id = None
                status = ScanFile.IMPORTED
                audio_exists = False
                linked_to_existing = False
                if ids:
                    # 先看有没有「同名且已经有音频」的书 —— 这就是增量加音频的场景
                    for bid in ids:
                        if self._check_audio_exists(bid):
                            audio_exists = True
                            book_id = bid
                            status = ScanFile.EXIST
                            break
                    # 没有音频目录，但有同名电子书：把音频挂到这本书上复用同一个 book_id，
                    # 而不是新建一条 calibre 记录。
                    # 原实现只看「有没有音频目录」，导致「电子书在 library/、音频后加」
                    # 时判定为 audio_exists=False 直接新建一本书，书库里同一本书出现两条。
                    if not audio_exists and _link_to_existing_enabled():
                        book_id = self._pick_linkable_book(ids)
                        if book_id is not None:
                            linked_to_existing = True
                            status = ScanFile.IMPORTED
                            logging.info(
                                "[AUDIO_IMPORT] 同名书籍已存在(book_id=%s)，音频将挂到该书而非新建：%s",
                                book_id, title)
                    logging.debug("[AUDIO_IMPORT] found existing books with same title '%s': %s, has_audio=%s, selected_book_id=%s",
                                  title, ids, audio_exists, book_id)
                if book_id is None:
                    # 确实没有可挂靠的书，才创建新书籍记录
                    book_id = self._add_new_book(user_id, mi, cover_path)
                    if book_id is None:
                        logging.error("[AUDIO_IMPORT] failed to create book entry for %s", title)
                        row.status = ScanFile.INVALID
                        self.save_or_rollback(row)
                        self._update_progress(task_id, idx + 1, total)
                        continue

                if status == ScanFile.IMPORTED:
                    dest_dir = os.path.join(output_dir, str(book_id))
                    if not os.path.exists(dest_dir):
                        os.makedirs(dest_dir)
                    for fname in os.listdir(dir_path):
                        src = os.path.join(dir_path, fname)
                        if os.path.isfile(src):
                            _copy_or_convert_file(src, dest_dir)
                    if linked_to_existing:
                        AudioBookImporter.static_status["linked"] += 1
                        logging.info("[AUDIO_IMPORT] 音频已挂到已有书籍 book_id=%s 的目录 %s",
                                     book_id, dest_dir)
                    else:
                        imported_ids.append(book_id)
                        AudioBookImporter.static_status["imported"] += 1
                    if not has_cover:
                        imported_without_cover.append(book_id)
                else:
                    AudioBookImporter.static_status["exist"] += 1

                row.book_id = book_id
                row.status = status
            except Exception as err:
                logging.error("[AUDIO_IMPORT] error processing %s: %s", dir_path, err)
                logging.error(traceback.format_exc())
                row.status = ScanFile.INVALID

            self.save_or_rollback(row)
            self._update_progress(task_id, idx + 1, total)
            time.sleep(0.1)

        if imported_without_cover:
            logging.info("[AUDIO_IMPORT] triggering autofill for %d books without cover", len(imported_without_cover))
            from webserver.services.autofill import AutoFillService
            AutoFillService().auto_fill_all(imported_without_cover)

    def _update_progress(self, task_id, done, total):
        if not task_id:
            return
        try:
            status = AudioBookImporter.static_status
            progress = int(done * 100 / total) if total else 100
            BackgroundService().update_progress(
                task_id=task_id,
                progress=progress,
                progress_data={
                    "total": status["total"],
                    "imported": status["imported"],
                    "exist": status["exist"],
                    "linked": status["linked"],
                },
            )
        except Exception as e:
            logging.error("[AUDIO_IMPORT] failed to update progress: %s", e)
