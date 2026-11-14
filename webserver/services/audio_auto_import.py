#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""有声书导入目录（imports/audiobooks/）自动导入。

为什么不用 inotify：``monitor_service`` 明确跳过 ``AUDIO_BOOK_IMPORTS`` 目录
（它只负责电子书，且只认 CLOSE_WRITE / MOVED_TO，CREATE 一律丢弃）。而用户
多是经 SMB 从另一台机器拷入整本有声书（几十个分片、持续几分钟），3 秒防抖
会在文件没拷完时触发，截断的音频会被当成完整文件入库。

这里改用「目录指纹 + 连续两轮稳定」的轮询：
  * 指纹覆盖一级子目录内所有音频文件的 (相对路径, size, mtime_ns)；
    封面、字幕、``@eaDir`` 缩略图、临时文件的变化不算「有新书」。
  * 拷贝/删除期间指纹持续变化，稳定计数归零；连续 N 轮一致才触发。
  * 触发的是 ``AudioBookImporter.do_import``，它自身用 ``audiodir:`` + 路径
    MD5 存 ScanFile 判重，已导入目录只会补同步新增音频，不会重复建书。
    因此某次触发因互斥被跳过也无害：下一次任意目录变化会再跑一轮全量，
    把之前漏掉的目录一并补上（最终一致）。

跟随 ``IMPORT_BY_INOTIFY`` 开关启停；``AUDIO_AUTO_IMPORT_ENABLED=False`` 可
单独关掉有声书部分。纯后台线程，不持有 DB 连接。
"""

import hashlib
import logging
import os
import threading
import time

from webserver import constants, loader

CONF = loader.get_settings()

DEFAULT_INTERVAL = 60
MIN_INTERVAL = 20
STABLE_ROUNDS = 2

_AUDIO_EXTS = tuple(e.lower() for e in constants.SUPPORTED_AUDIO_FORMATS)


def audio_import_dir():
    """当前配置下的有声书导入目录（未 realpath，便于测试指向临时目录）。"""
    return os.path.join(
        CONF.get("scan_upload_path", "/data/books/imports/"),
        constants.AUDIO_BOOK_IMPORTS,
    )


def _is_noise(name):
    """群晖 @eaDir、隐藏/临时目录、编辑器残留不参与指纹。"""
    return name.startswith((".", "~")) or name == "@eaDir"


def fingerprint(root):
    """返回 ``(hexdigest, 一级子目录数)``；目录不存在/不可读返回 ``(None, 0)``。

    指纹只由音频文件的路径与大小/mtime 决定，且排序后摘要，
    保证遍历顺序、mtime 精度差异不产生抖动。
    """
    if not os.path.isdir(root):
        return None, 0
    try:
        with os.scandir(root) as it:
            names = sorted(e.name for e in it)
    except OSError as e:
        logging.debug("[AUDIO_AUTO] scandir %s failed: %s", root, e)
        return None, 0

    entries = []
    n_dirs = 0
    for name in names:
        if _is_noise(name):
            continue
        path = os.path.join(root, name)
        if os.path.isdir(path):
            n_dirs += 1
            bases = [path]
        elif os.path.isfile(path) and name.lower().endswith(_AUDIO_EXTS):
            # AudioBookImporter 有兜底：音频直接扔在 audiobooks/ 根目录也算一本书
            bases = [path]
        else:
            continue

        for base in bases:
            if os.path.isdir(base):
                for dirpath, dirnames, filenames in os.walk(base):
                    dirnames[:] = [d for d in dirnames if not _is_noise(d)]
                    for fn in sorted(filenames):
                        if not fn.lower().endswith(_AUDIO_EXTS):
                            continue
                        fp = os.path.join(dirpath, fn)
                        try:
                            st = os.stat(fp)
                        except OSError:
                            continue
                        entries.append((os.path.relpath(fp, root), st.st_size, st.st_mtime_ns))
            else:
                try:
                    st = os.stat(base)
                    entries.append((os.path.relpath(base, root), st.st_size, st.st_mtime_ns))
                except OSError:
                    pass

    h = hashlib.sha256()
    for rel, size, mtime in sorted(entries):
        h.update(("%s|%d|%d\n" % (rel, size, mtime)).encode("utf-8"))
    return h.hexdigest(), n_dirs


class AudioAutoImportService:
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._initialized = False
                    cls._instance = inst
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._running = False
        self._thread = None
        self._stop_event = threading.Event()
        # 上一轮看到的指纹 / 连续稳定轮数 / 上次成功触发时的指纹
        self._prev_fp = None
        self._stable = 0
        self._triggered_fp = None
        self._last_trigger_at = 0.0

    @staticmethod
    def interval():
        try:
            return max(MIN_INTERVAL, int(CONF.get("AUDIO_AUTO_IMPORT_INTERVAL", DEFAULT_INTERVAL)))
        except (TypeError, ValueError):
            return DEFAULT_INTERVAL

    @staticmethod
    def enabled():
        return bool(CONF.get("IMPORT_BY_INOTIFY", False)) and bool(
            CONF.get("AUDIO_AUTO_IMPORT_ENABLED", True)
        )

    def start(self):
        """启动轮询（幂等）。已运行则忽略。"""
        if self._running:
            return
        self._stop_event.clear()
        self._running = True
        self._prev_fp = None
        self._stable = 0
        self._triggered_fp = None
        self._thread = threading.Thread(
            target=self._loop, name="AudioAutoImport.poller", daemon=True
        )
        self._thread.start()
        logging.info(
            "[AUDIO_AUTO] started, dir=%s interval=%ds stable_rounds=%d",
            audio_import_dir(), self.interval(), STABLE_ROUNDS,
        )

    def stop(self):
        """停止轮询（幂等），唤醒等待中的线程。"""
        self._running = False
        self._stop_event.set()
        t = self._thread
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=3)
        self._thread = None
        logging.info("[AUDIO_AUTO] stopped")

    def _loop(self):
        while self._running:
            # Event.wait 让 stop() 能立刻唤醒，不必等满一个 interval
            if self._stop_event.wait(self.interval()):
                break
            try:
                self.tick()
            except Exception:
                logging.exception("[AUDIO_AUTO] tick failed, will retry next round")
        logging.info("[AUDIO_AUTO] poller thread exiting")

    @staticmethod
    def _can_import():
        # 延迟导入：轮询线程启动时不必拉起 models / calibre 等重模块
        from webserver.services.audios_import import AudioBookImporter
        from webserver.services.scan_service import ScanService

        return not (
            AudioBookImporter.is_running()
            or ScanService.is_importing()
            or ScanService.is_bulk_deleting()
        )

    @staticmethod
    def _trigger_import():
        from webserver.services.audios_import import AudioBookImporter

        user_id = CONF.get("ADMIN_ID", 1)
        AudioBookImporter().do_import(user_id)

    def tick(self):
        """一轮检查。抽成公开方法便于契约测试直接驱动，不必真起线程。"""
        if not self.enabled():
            return False

        fp, n_dirs = fingerprint(audio_import_dir())
        if fp is None:
            # 目录不存在/刚被移走：不刷错误日志（用户可能还没建），重置稳定计数
            self._prev_fp = None
            self._stable = 0
            return False

        if fp == self._prev_fp:
            self._stable += 1
        else:
            self._prev_fp = fp
            self._stable = 1
            logging.info("[AUDIO_AUTO] fingerprint changed -> %s (%d dirs), waiting for stability", fp[:12], n_dirs)

        if self._stable < STABLE_ROUNDS:
            return False
        if fp == self._triggered_fp:
            return False
        if not self._can_import():
            # 忙时不「消费」这次变化，下一轮空闲后仍会触发
            logging.info("[AUDIO_AUTO] importer busy, retry next round")
            return False

        logging.info(
            "[AUDIO_AUTO] fingerprint stable for %d rounds (%d dirs), triggering AudioBookImporter",
            self._stable, n_dirs,
        )
        self._trigger_import()
        self._triggered_fp = fp
        self._last_trigger_at = time.time()
        return True


def get_audio_auto_import_service():
    return AudioAutoImportService()
