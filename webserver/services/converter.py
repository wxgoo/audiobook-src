#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import os
import logging
import shlex
import traceback

from webserver.i18n import _
import subprocess
import time
import psutil

from webserver import loader
from webserver import utils
from webserver.plugins.parser.txt import get_content_encoding
from webserver.services import AsyncService
from webserver.services.mail import MailService
from webserver.services.background_service import BackgroundService, BackgroundTask

EBOOK_CONVERT_CMD = "ebook-convert"
DEFAULT_CONVERT_TIMEOUT = 3 * 60 * 1000  # 3 minutes, in milliseconds

CONF = loader.get_settings()


def shell_quote_for_log(value):
    quoted = shlex.quote(value)
    if quoted != value and "'" in value and not any(c in value for c in "\"\\$`"):
        return '"%s"' % value
    return quoted


class ConverterService(AsyncService):
    def _check_txt_encoding(self, file_path):
        with open(file_path, mode='rb') as file:
            content = file.read(4096)
        if not content:
            return 'utf-8'
        return get_content_encoding(content)

    def get_fmt(self, path):
        fmt = os.path.splitext(path)[1]
        return fmt[1:].lower() if fmt else ""

    def get_path_of_fmt(self, book, fmt):
        """for mock test"""
        from calibre.utils.filenames import ascii_filename
        return os.path.join(CONF["convert_path"], "%s.%s" % (ascii_filename(book["title"]), fmt))

    def get_path_progress(self, book_id):
        return os.path.join(CONF["progress_path"], "progress-%s.log" % book_id)

    def is_book_converting(self, book):
        converted_book_path_prefix = os.path.join(
            CONF["convert_path"],
            "book-%s-" % book["id"],
        )
        found = False
        for process in psutil.process_iter(['cmdline']):
            try:
                cmdline = process.info['cmdline']
                if cmdline and any(converted_book_path_prefix in arg for arg in cmdline):
                    logging.info("Found process with string '%s': PID %s", converted_book_path_prefix, process.pid)
                    found = True
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return found

    def do_ebook_convert(self, old_path, new_path, log_path):
        """convert book, and block, and wait"""
        new_fmt = self.get_fmt(new_path)

        args = [EBOOK_CONVERT_CMD, old_path, new_path]
        args += ["--book-producer", "PoxenStudio/MyBooks(https://mybooks.top)"]
        if new_fmt == "epub":
            args += ["--epub-version", "2"]
            if old_path.lower().endswith(".txt"):
                encode = self._check_txt_encoding(old_path)
                args += ["--chapter-mark", "pagebreak",
                         "--output-profile", "kindle",
                         "--input-encoding", encode,
                         "--language", "zh",
                         "--chapter", "//*[local-name()='p' and re:test(., '(^第?[0-9一二三四五六七八九十百千]+[章节卷回集].*|^章[0-9]+.*|^引子|^楔子|^尾声)', 'i')]",
                         "--flow-size", "260"]
            else:
                args += ["--flow-size", "0"]
        elif new_fmt == "azw3":
            args += ["--embed-font-family", "Lato"]
            args += ["--enable-heuristics", "--output-profile", "kindle"]
        elif new_fmt == "pdf":
            cn_font_name = "\"WenQuanYi Micro Hei,文泉驛微米黑,文泉驿微米黑\""
            args += ["--paper-size=a5"]
            args += ["--pdf-page-margin-left=15"]
            args += ["--pdf-page-margin-top=15"]
            args += ["--pdf-page-margin-right=15"]
            args += ["--pdf-page-margin-bottom=15"]
            args += ["--no-chapters-in-toc"]
            args += ["--base-font-size=12"]
            args += ["--filter-css=font-family"]
            args += [f"--pdf-sans-family=\"{cn_font_name}\""]
            args += [f"--pdf-serif-family=\"{cn_font_name}\""]

        timeout = DEFAULT_CONVERT_TIMEOUT
        try:
            timeout = int(CONF.get("convert_timeout", DEFAULT_CONVERT_TIMEOUT))
            timeout = max(timeout, DEFAULT_CONVERT_TIMEOUT)
        except Exception as e:
            logging.warning("Failed to get convert timeout from config: %s", e)
            timeout = DEFAULT_CONVERT_TIMEOUT

        with open(log_path, "w") as log:
            cmd = " ".join(shell_quote_for_log(v) for v in args)
            logging.info("CMD: %s" % cmd)
            env = os.environ.copy()
            env["QTWEBENGINE_DISABLE_SANDBOX"] = "1"
            # 容器以 root 运行，Chromium（QtWebEngine 的 PDF 渲染引擎）拒绝在
            # root 下启用自身沙箱，直接报错退出：
            #   Running as root without --no-sandbox is not supported
            # 单设 QTWEBENGINE_DISABLE_SANDBOX=1 不够，必须显式 --no-sandbox。
            # 容器内无外泄面，root 下关沙箱可接受（docx→epub、epub 封面渲染都靠它）。
            env["QTWEBENGINE_CHROMIUM_FLAGS"] = "--no-sandbox --disable-dev-shm-usage"
            env["XDG_RUNTIME_DIR"] = "/tmp/runtime-ubuntu"
            p = subprocess.Popen(args, stdout=log, stderr=subprocess.PIPE, env=env)
            try:
                _, stde = p.communicate(timeout=timeout)
                logging.info("ebook-convert finish: %s, err: %s" % (new_path, bytes.decode(stde)))
            except subprocess.TimeoutExpired:
                logging.info("ebook-convert timeout: %s" % new_path)
                p.kill()
                try:
                    # kill 后必须收尸：不 wait 会留僵尸进程，stderr 管道也不再被读
                    p.wait(timeout=30)
                except Exception:
                    pass
                return False
            # 崩溃 ≠ 正常结束：glibc 熵源失败、Chromium 沙箱拒绝等都会让
            # ebook-convert 非零退出且不产出文件。只判超时会让上游拿到
            # FileNotFoundError（线上真实案例：docx→pdf 全军覆没却只报
            # "No such file or directory"）。这里补两层判定。
            if p.returncode != 0 or not os.path.exists(new_path):
                logging.error(
                    "ebook-convert failed (rc=%s, output exists=%s): %s",
                    p.returncode, os.path.exists(new_path), new_path,
                )
                return False
            return True

    def convert_to_mobi_format(self, book, new_fmt):
        new_path = self.get_path_of_fmt(book, new_fmt)
        progress_file = self.get_path_progress(book["id"])

        old_path = None
        for f in ["txt", "azw3"]:
            old_path = book.get("fmt_%s" % f, old_path)

        ok = self.do_ebook_convert(old_path, new_path, progress_file)
        if not ok:
            return None
        with open(new_path, "rb") as f:
            self.db.add_format(book["id"], new_fmt, f, index_is_id=True)
        return new_path

    @AsyncService.register_service
    def convert_and_send(self, user_id: int, site_url: str, book: dict, mail_to: str):
        # https://www.amazon.cn/gp/help/customer/display.html?ref_=hp_left_v4_sib&nodeId=G5WYD9SAF7PGXRNA
        fmt = "epub"  # best format for kindle
        fpath = self.convert_to_mobi_format(book, fmt)
        if fpath:
            MailService().send_book(user_id, site_url, book, mail_to, fmt, fpath)
        else:
            self.add_msg(user_id, "danger", _(u"文件格式转换失败，请到公众号上私信联系"))

    @AsyncService.register_service
    def convert_and_save(self, user_id, book, fpath, new_fmt):
        if new_fmt == "":
            new_fmt = "epub"
        new_path = os.path.join(
            CONF["convert_path"], "book-%s-%s.%s" % (book["id"], int(time.time()), new_fmt),
        )

        # double confirm the new format not existed
        new_fmt_file_path = self.db.format_abspath(book['id'], new_fmt, index_is_id=True)
        if new_fmt_file_path:
            logging.info(f"[CONVERT] the format file of {new_fmt} is existed. Skip!")
            return

        progress_file = ConverterService().get_path_progress(book["id"])
        logging.info("convert book: %s => %s, progress file: %s" % (fpath, new_path, progress_file))

        title = book.get("title", "Unknown Title")
        if len(title) > 20:
            title = title[0:19] + "..."
        service_item = f"[{book['id']}]{title}"
        task = BackgroundService().add_task(BackgroundTask.SERVICE_TYPE_CONVERT, service_item, book_id=book["id"])
        ok = ConverterService().do_ebook_convert(fpath, new_path, progress_file)
        if task:
            logging.info(f"[CONVERT] complete the task {task.id}, book:{title}")
            BackgroundService().complete_task(task.id)
        if not ok:
            self.add_msg(user_id, "danger", "[%s]文件格式转换失败！请在设置中调整转换超时时间后重试" % service_item)
            return

        # 4.6.0-9 坏字体清理（新书侧）：
        # calibre 从 PDF/DJVU 转 epub 时，若源字体带子集加密保护，会产出一批以
        # ASCII `FONT` 开头的伪字体（不是合法 sfnt）。浏览器 OTS 直接拒绝并报
        # `invalid sfntVersion: 1179602516`，正文回退系统字体；而这些死数据
        # 往往占全书一半以上体积（实测一本 3.11MB 的书里 1.66MB 是它），
        # 弱网下白白拖慢整本下载。转换刚结束就地清掉，后续下载即精简版。
        # 详见 webserver/services/epub_font_fix.py。
        if new_fmt == "epub":
            try:
                from webserver.services.epub_font_fix import strip_from_epub_file

                fix = strip_from_epub_file(new_path, backup_suffix=None)
                if fix.get("changed"):
                    logging.info(
                        "[CONVERT] 已清理 %d 个坏字体: %s -> %s 字节",
                        len(fix.get("fonts") or []), fix.get("before"), fix.get("after"),
                    )
            except Exception:
                # 清理失败不能影响转换结果本身，照常入库
                logging.warning("[CONVERT] 坏字体清理失败，跳过 book=%s", book["id"])
                logging.warning(traceback.format_exc())

        with open(new_path, "rb") as f:
            self.db.add_format(book["id"], new_fmt, f, index_is_id=True)
            logging.info("added new book: %s", new_path)

        # Write metadata to the new file (including cover)
        try:
            from calibre.ebooks.metadata.meta import set_metadata

            book_id = book["id"]
            mi = self.db.get_metadata(book_id, index_is_id=True)
            if mi:
                if mi.title:
                    mi.title_sort = utils.super_strip(mi.title)
                if mi.authors:
                    mi.author_sort = utils.super_strip(mi.authors[0])

                cover_data = self.db.cover(book_id, index_is_id=True)
                if cover_data:
                    mi.cover_data = ("jpeg", cover_data)

                fmt_path = self.db.format_abspath(book_id, new_fmt, index_is_id=True)
                if fmt_path and os.path.exists(fmt_path):
                    with open(fmt_path, "rb+") as stream:
                        set_metadata(stream, mi, stream_type=new_fmt)
                    logging.info(f"[CONVERT] Metadata written to {new_fmt.upper()} for book {book_id}")
                else:
                    logging.warning(f"[CONVERT] Cannot find converted file path for book {book_id} fmt {new_fmt}")
        except Exception:
            logging.error(f"[CONVERT] Failed to write metadata after conversion for book {book['id']}")
            logging.error(traceback.format_exc())

        self.add_msg(user_id, "success", _(u"[%s]文件格式转换成功" % service_item))
        # 清理临时文件
        os.remove(new_path)
