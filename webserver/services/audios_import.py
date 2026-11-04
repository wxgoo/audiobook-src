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
from webserver.base.audio_dir import audio_dir_for_read, audio_dir_for_write

CONF = loader.get_settings()

AUDIO_IMPORT_DIR = os.path.join(CONF.get("scan_upload_path", "/data/books/imports/"), constants.AUDIO_BOOK_IMPORTS)

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


def _warn_audio_outside_import_dir(import_dir):
    """真导不进东西时，检查音频是不是放错了位置，并写进日志。

    最常见的放错法：音频扔在 imports/ 根目录（跟电子书混一起），而不是
    imports/audiobooks/ 下。这时导入结果就是「0 本」，日志里什么都不说，
    用户只能盯着界面猜。这里主动数一下上层目录，命中就明确指出来。
    """
    try:
        parent = os.path.dirname(os.path.normpath(import_dir))
        if not parent or not os.path.isdir(parent):
            return
        ext = tuple(constants.SUPPORTED_AUDIO_FORMATS)
        stray = [f for f in os.listdir(parent)
                 if os.path.isfile(os.path.join(parent, f)) and f.lower().endswith(ext)]
        if stray:
            logging.warning(
                "[AUDIO_IMPORT] 在 %s 里发现 %d 个音频文件，但它们必须放在 %s 下才会被导入"
                "（例如 %s，或直接放到该目录）。示例：%s",
                parent, len(stray), import_dir, import_dir, ", ".join(stray[:3]))
    except OSError as err:
        logging.debug("[AUDIO_IMPORT] scan parent dir failed: %s", err)


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


def _copy_or_convert_file(src_path, dst_dir, dest_name=None):
    """Copy a file to dst_dir. If it's a WMA file, convert to MP3 instead.

    dest_name: 目标文件名（可带子目录前缀）。sidecar 扩展（4.6.0-19）跨子目录
    同名冲突时由调用方生成「子目录名-文件名」；缺省沿用源文件名。
    """
    filename = os.path.basename(src_path)
    dest_filename = _get_dest_filename(dest_name) if dest_name else _get_dest_filename(filename)
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


def _fix_mojibake(text):
    """修复被按 latin-1 误读的中文标签。

    很多老 mp3 的 ID3v1 / 未声明编码的 ID3v2 里存的是 GBK 字节，mutagen 按
    latin-1 解出来就是「lĐÆú'ìðŌËÆÚ」这种乱码。特征很明显：每个字符都在
    U+0080~U+00FF 区间（latin-1 高半区）。把它按 latin-1 编回字节再用 GBK
    解一次就能还原；还原出来还有替换字符（\ufffd）说明原本就不是 GBK，
    保持原样别越修越坏。
    """
    if not text:
        return text
    try:
        raw = text.encode("latin-1")
    except UnicodeEncodeError:
        # 有 latin-1 之外的字符，说明不是这个模式的乱码
        return text
    if not any(b >= 0x80 for b in raw):
        return text  # 纯 ASCII，没有乱码空间

    # GBK 优先，BIG5 兜底：台湾版繁体 mp3 的 ID3 标签是 BIG5 编码，
    # 被 latin-1 误读后的形态和 GBK 一样（字符全落在 U+0080~U+00FF），
    # 但按 GBK 解会出替换符或明显不通的怪字（如 «sÒÁ¶°T»…）。
    for enc in ("gbk", "big5"):
        fixed = raw.decode(enc, errors="replace")
        if "\ufffd" in fixed:
            continue
        # 有替换符说明该编码对不上，试下一个；都失败就放弃
        logging.info("[AUDIO_IMPORT] fixed mojibake (%s): %r -> %r", enc, text, fixed)
        return fixed
    return text


def _extract_audio_metadata(audio_path, fallback_title):
    """从音频标签读 (书名, 演播者)。

    ⚠️ 返回的第二个值**不是作者**，是演播者（朗读者）。
    中文有声资源的 ID3 里 TPE1(artist) 几乎一律填播音员——用户库里那本
    「哈利波特与魔法石」的每首音轨都是 TPE1=李慧敏（央广播音员），
    真作者 J·K·罗琳 一个字都没出现。把 artist 当作者会让书库里凭空多出一个
    「李慧敏」作者，而这位其实是演播者，据此做的作者归类、去重、刮削全是错的。

    所以调用方必须：作者另想办法（优先同名电子书，否则佚名），
    演播者写进书的演播者字段/标签/简介——信息不丢，但不占作者位。
    """
    try:
        import mutagen
        audio = mutagen.File(audio_path, easy=True)
        if audio is None:
            return fallback_title, None
        title = None
        narrator = None
        if hasattr(audio, "tags") and audio.tags:
            title_tag = audio.tags.get("album") or audio.tags.get("title")
            # artist/albumartist 在中文有声书里是演播者，不是作者
            narrator_tag = audio.tags.get("artist") or audio.tags.get("albumartist")
            if title_tag:
                title = str(title_tag[0]).strip() if isinstance(title_tag, list) else str(title_tag).strip()
            if narrator_tag:
                narrator = str(narrator_tag[0]).strip() if isinstance(narrator_tag, list) else str(narrator_tag).strip()

        # Fallback for some m4b files (e.g. lavf) where easy=True doesn't map the tags
        if not title or not narrator:
            raw_audio = mutagen.File(audio_path, easy=False)
            if hasattr(raw_audio, "tags") and raw_audio.tags:
                if not title:
                    title_tag = raw_audio.tags.get("\x00\x00\x00\x01")
                    if title_tag:
                        title = str(title_tag[0]).strip() if isinstance(title_tag, list) else str(title_tag).strip()
                if not narrator:
                    narrator_tag = raw_audio.tags.get("\x00\x00\x00\x02")
                    if narrator_tag:
                        narrator = str(narrator_tag[0]).strip() if isinstance(narrator_tag, list) else str(narrator_tag).strip()

        title = _fix_mojibake(title)
        narrator = _fix_mojibake(narrator)

        logging.debug("[AUDIO_IMPORT] Extracted metadata from %s: title=%s, narrator=%s", audio_path, title, narrator)
        return title or fallback_title, narrator
    except Exception as e:
        logging.warning("[AUDIO_IMPORT] Failed to read audio metadata from %s: %s", audio_path, e)
        return fallback_title, None


def attach_narrator(db, book_id, narrator):
    """把演播者写进书里，三个地方都写：结构化列、标签、简介。

    4.6.0-18。模块级函数而非实例方法，因为有两个调用方：
      - AudioBookImporter.do_import（「导入有声书」入口）
      - ScanService._sync_sidecar_audio（扫书时同目录音频随书带入）

    为什么不全塞作者：中文有声资源的 ID3/ID 里 TPE1 填的是播音员，
    把「李慧敏」当作者会让书库凭空长出一个伪作者，作者页、去重、
    自动刮削全部跟着错。作者位要么是电子书带来的真作者，要么老实标佚名。

    为什么三处都写：
      - #narrator 列：结构化，以后能按演播者筛选/展示
      - tags：书列表页就能看见，不用点进去
      - comments：书详情页显眼位置，用户最可能看到

    全部 best-effort：写失败只记日志，绝不能让导入失败。
    """
    if not narrator:
        return
    book_id = int(book_id)

    # 1) 结构化列
    try:
        db.new_api.set_field(constants.CALIBRE_COLUMN_NARRATOR, {book_id: narrator})
    except Exception as err:
        logging.warning("[AUDIO_IMPORT] 写 #narrator 失败(book %s): %s", book_id, err)

    # 2) 标签 + 3) 简介
    try:
        mi = db.get_metadata(book_id, index_is_id=True, get_user_categories=False)
    except Exception as err:
        logging.warning("[AUDIO_IMPORT] 读元数据失败(book %s): %s", book_id, err)
        return
    if mi is None:
        return

    try:
        tags = list(mi.tags or [])
        tag = _("演播:%s") % narrator
        if tag not in tags:
            tags.append(tag)
            db.new_api.set_field("tags", {book_id: tags})
    except Exception as err:
        logging.warning("[AUDIO_IMPORT] 写 tags 失败(book %s): %s", book_id, err)

    try:
        comments = (mi.comments or "").strip()
        line = _("演播：%s") % narrator
        if line not in comments:
            merged = (comments + "<br/>" + line) if comments else line
            db.new_api.set_field("comments", {book_id: merged})
    except Exception as err:
        logging.warning("[AUDIO_IMPORT] 写 comments 失败(book %s): %s", book_id, err)


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
        # 新布局（书目录内 .audio/）和旧布局（audios/<id>/）都算「有音频」，
        # 迁移期间两种都可能出现，只认新布局会让旧数据被判成"没有音频"而重复导入。
        path, _legacy = audio_dir_for_read(self.db, book_id)
        if not os.path.isdir(path):
            return False
        audio_files = [f for f in os.listdir(path) if f.lower().endswith(tuple(constants.SUPPORTED_AUDIO_FORMATS))]
        return bool(audio_files)

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
            if not os.path.isfile(src):
                continue
            # 增量同步同样跳过电子书：它们走 add_format 挂到书本身，不进 .audio/
            _ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
            if _ext in constants.SUPPORTED_EBOOK_FORMATS and _ext != "txt":
                continue
            _copy_or_convert_file(src, dest_dir)

    @AsyncService.register_service
    def do_import(self, user_id):
        with ScanService.task_claim_lock:
            if AudioBookImporter.static_is_running:
                logging.error("[AUDIO_IMPORT] already running, skip")
                return
            if ScanService.is_importing():
                # 与扫描导入互斥（4.6.0-19）：原来只有批量删除一侧设防，
                # 两边同时搬音频/写 ScanFile 会互相踩
                logging.error("[AUDIO_IMPORT] scan importing is running, skip")
                self.add_msg(user_id=user_id, status="error", msg=_("已有扫描导入任务正在运行，请稍后再试"))
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

        if not os.path.isdir(import_dir):
            logging.warning("[AUDIO_IMPORT] import dir does not exist: %s", import_dir)
            _warn_audio_outside_import_dir(import_dir)
            return

        subdirs = sorted([
            d for d in os.listdir(import_dir)
            if os.path.isdir(os.path.join(import_dir, d))
            and not d.startswith(".") and not d.startswith("~")
        ])

        # 兜底：imports/audiobooks/ 根目录下直接扔了音频文件（没建子目录）时，
        # 把根目录本身当成「一本书」。说明文案写的是「有声书放到 audiobooks/」，
        # 用户这么放完全合理，原先只遍历一级子目录会得到一个空列表、静默导入 0 本。
        root_audios = sorted([
            f for f in os.listdir(import_dir)
            if os.path.isfile(os.path.join(import_dir, f))
            and f.lower().endswith(tuple(constants.SUPPORTED_AUDIO_FORMATS))
        ])
        if root_audios:
            logging.info("[AUDIO_IMPORT] found %d audio file(s) directly in %s, "
                         "treating the folder itself as one book", len(root_audios), import_dir)
            subdirs.insert(0, ".")

        if not subdirs:
            # 目录在、但确实没东西可导：把常见放错位置的情况写进日志，
            # 免得用户只看到「已导入 0 本」不知道下一步该查哪里。
            logging.warning("[AUDIO_IMPORT] nothing to import under %s", import_dir)
            _warn_audio_outside_import_dir(import_dir)

        total = len(subdirs)
        AudioBookImporter.static_status["total"] = total
        imported_ids = []
        imported_without_cover = []

        for idx, dir_name in enumerate(subdirs):
            dir_path = os.path.normpath(os.path.join(import_dir, dir_name))
            dir_hash = "audiodir:" + hashlib.md5(dir_path.encode("utf-8")).hexdigest()
            logging.info("[AUDIO_IMPORT] Processing directory %d/%d: %s", idx + 1, total, dir_path)

            # 目录列表是开跑前一次性取的，中途被移走/改名很正常（用户正在整理文件）。
            # 以前这种情况会抛 FileNotFoundError 把整个任务 abort，前面已导入的
            # 记录虽然留着，但本轮剩余的书一本都处理不到，日志只有一句 Errno 2。
            # 单条目录消失只跳过这一条，其它书照常处理。
            if not os.path.isdir(dir_path):
                logging.warning("[AUDIO_IMPORT] 目录已不存在，跳过（可能刚被移走/改名）：%s", dir_path)
                AudioBookImporter.static_status["skipped"] += 1
                self._update_progress(task_id, idx + 1, total)
                continue

            existing = self.session.query(ScanFile).filter(ScanFile.hash == dir_hash).first()
            if existing and existing.status in (ScanFile.IMPORTED, ScanFile.EXIST):
                # 已导入过的书：把导入目录里新增的音频同步到该书目录下的 .audio/
                if existing.status == ScanFile.IMPORTED:
                    book_id = existing.book_id
                    if book_id and self._check_audio_exists(book_id):
                        dest = audio_dir_for_write(self.db, book_id)
                        if dest:
                            self._synch_audio_files(dir_path, dest)
                        else:
                            logging.warning("[AUDIO_IMPORT] 找不到 book %s 的书目录，跳过同步", book_id)

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
            # dir_name 为 "." 表示音频直接放在 audiobooks/ 根目录（见上面的兜底）。
            # 这时目录名不能当书名，依次退回：ID3 标签 → 第一个音频文件名。
            fallback_title = "" if dir_name == "." else dir_name
            # §电子书优先§（4.6.0-15）目录里同时有 epub/mobi 等电子书和音频时
            # （典型：有声书资源包，epub+mp3 混在一个目录），以电子书的元数据
            # 建书，而不是 mp3 的 ID3 标签——ID3 的 artist 常是播音员（如
            # 「李慧敏」），title 也常是乱七八糟的源名，会把书建错。电子书随后
            # add_format 挂到该书，音频复制到 .audio/：一本书、书音频齐全。
            ebook_file = None
            ebook_fmt = None
            ebook_mi = None
            for _f in sorted(os.listdir(dir_path)):
                _ext = _f.rsplit(".", 1)[-1].lower() if "." in _f else ""
                if _ext in constants.SUPPORTED_EBOOK_FORMATS and _ext != "txt":
                    ebook_file = os.path.join(dir_path, _f)
                    ebook_fmt = _ext
                    break
            if ebook_file:
                try:
                    from webserver.base.book_files import read_book_metadata
                    ebook_mi = read_book_metadata(
                        ebook_file, ebook_fmt, os.path.basename(ebook_file))
                    logging.info("[AUDIO_IMPORT] 目录内发现电子书 %s，元数据以电子书为准",
                                 os.path.basename(ebook_file))
                except Exception as err:
                    logging.warning("[AUDIO_IMPORT] 读取电子书元数据失败(%s): %s",
                                    ebook_file, err)
                    ebook_mi = None
            ebook_title = ebook_author = None
            if ebook_mi is not None:
                ebook_title = utils.super_strip(ebook_mi.title or "") or None
                if ebook_mi.authors and ebook_mi.authors[0]:
                    ebook_author = utils.super_strip(str(ebook_mi.authors[0])) or None
            if ebook_title:
                title = ebook_title
                author = ebook_author or _("佚名")
                narrator = None
            else:
                # §artist 是演播者不是作者§ 4.6.0-18
                # 中文有声资源的 ID3 里 TPE1(artist) 几乎一律填播音员，真作者缺失。
                # 用户库里「哈利波特与魔法石」每首音轨都是 TPE1=李慧敏（央广播音员），
                # J·K·罗琳 一个字都没有。此时：
                #   1. 先找同名的电子书，用它的作者（下面的查重归并会把音频挂过去）
                #   2. 找不到就老实标佚名——宁可没作者，也不能让演播者冒充作者
                # 演播者不丢：写进 #narrator 列 + 标签 + 简介，见 attach_narrator。
                title, narrator = _extract_audio_metadata(first_audio, fallback_title)
                title = utils.super_strip(title) if title else ""
                if not title:
                    title = fallback_title or os.path.splitext(audio_files[0])[0]
                narrator = utils.super_strip(narrator) if narrator else None
                author = _("佚名")

            # 4.6.0-9：作者名最脏的来源是有声书的 ID3，但 4.6.0-18 起 artist 已不再
            # 当作者用，这里只对「来自电子书」的作者做清洗（ID3 的演播者不需要
            # 走作者归一化：别名表里没有播音员，硬套反而会误伤）。
            # ⚠️ 不能用 "_" 接收译者列表：本模块的 "_" 是 i18n 函数，
            # 覆盖后后面所有 _("...") 都会崩。
            if author and author != _("佚名"):
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
                _stage = "查重"
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
                    _stage = "创建书籍记录"
                    book_id = self._add_new_book(user_id, mi, cover_path)
                    if book_id is None:
                        logging.error("[AUDIO_IMPORT] failed to create book entry for %s", title)
                        row.status = ScanFile.INVALID
                        self.save_or_rollback(row)
                        self._update_progress(task_id, idx + 1, total)
                        continue

                if status == ScanFile.IMPORTED:
                    # 音频写进书自己的目录（library/<作者>/<书名> (id)/.audio/），
                    # 不再往 audios/<id>/ 放。书目录不存在说明这本书还没真正进库，
                    # 此时不硬造目录，避免在 library 里留下一堆空壳。
                    _stage = "解析书目录"
                    dest_dir = audio_dir_for_write(self.db, book_id)
                    if not dest_dir:
                        logging.error("[AUDIO_IMPORT] book %s 没有可用的书目录，跳过音频复制（%s）",
                                      book_id, dir_path)
                        row.status = ScanFile.INVALID
                        self.save_or_rollback(row)
                        self._update_progress(task_id, idx + 1, total)
                        continue
                    _stage = "复制音频"
                    for fname in os.listdir(dir_path):
                        src = os.path.join(dir_path, fname)
                        if not os.path.isfile(src):
                            continue
                        # 电子书已 add_format 挂到书本身，不复制进 .audio/
                        if ebook_file and os.path.normcase(os.path.abspath(src)) == os.path.normcase(os.path.abspath(ebook_file)):
                            continue
                        _copy_or_convert_file(src, dest_dir)
                    # §电子书优先§ 把目录里的电子书挂为书的格式文件
                    if ebook_file:
                        try:
                            _bmi = self.db.get_metadata(book_id, index_is_id=True, get_user_categories=False)
                            if _bmi.formats and ebook_fmt.upper() in _bmi.formats:
                                logging.info("[AUDIO_IMPORT] 书 %s 已有 %s 格式，跳过 add_format",
                                             book_id, ebook_fmt.upper())
                            else:
                                self.db.add_format(book_id, ebook_fmt.upper(), ebook_file, index_is_id=True)
                                logging.info("[AUDIO_IMPORT] 电子书已挂到书 %s：%s",
                                             book_id, os.path.basename(ebook_file))
                        except Exception as err:
                            logging.warning("[AUDIO_IMPORT] add_format 失败(%s): %s",
                                            ebook_file, err)
                    if linked_to_existing:
                        AudioBookImporter.static_status["linked"] += 1
                        logging.info("[AUDIO_IMPORT] 音频已挂到已有书籍 book_id=%s 的目录 %s",
                                     book_id, dest_dir)
                    else:
                        imported_ids.append(book_id)
                        AudioBookImporter.static_status["imported"] += 1
                    if not has_cover:
                        imported_without_cover.append(book_id)
                    # §把演播者落到书里，别丢§ 4.6.0-18
                    # 作者位让给真作者（或佚名），演播者信息单独存：
                    # #narrator 列（结构化，可按演播者筛选/展示）+ 简介 + 标签（人能看见）。
                    # 只在没被电子书接管时写——有电子书的书，演播者信息以电子书元数据为准。
                    if narrator:
                        attach_narrator(self.db, book_id, narrator)
                        # 挂靠到已有电子书的场景下，原书作者是对的，不改
                        logging.info("[AUDIO_IMPORT] book %s 演播者：%s", book_id, narrator)
                else:
                    AudioBookImporter.static_status["exist"] += 1

                row.book_id = book_id
                row.status = status
            except Exception as err:
                # 带上阶段名，否则日志里只有一句异常，看不出是「查重」「建书」
                # 还是「搬音频」挂的（4.6.0-13 的 db.cache 事故就是这样被埋住的）
                logging.error("[AUDIO_IMPORT] error processing %s [阶段=%s book_id=%s]: %s (%s)",
                              dir_path, _stage, book_id, err, type(err).__name__)
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
