#!/usr/bin/env python3
"""EpubToAudioWorker 进度快照的并发回归测试（4.6.0-19）。

覆盖的缺陷：
  get_progress() 只做浅拷贝，chapters 仍与 2 个输出读取线程共享；
  轮询 handler 拿到后直接 JSON 序列化，读线程并发往 chapters 插键时
  会抛 "RuntimeError: dictionary changed size during iteration"，
  转换进度接口随机 500。修法：解析与快照共用一把锁，快照改深拷贝。
"""
import json
import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from webserver.worker.epub2audio_worker import EpubToAudioWorker


class TestProgressSnapshot(unittest.TestCase):
    def test_snapshot_is_isolated_copy(self):
        """改快照不得影响 worker 内部状态（浅拷贝时代这条必挂）。"""
        w = EpubToAudioWorker()
        with w._plock:
            w._parse_bookbarn_log("[BOOKBARN]Processing:1,第一章")
        snap = w.get_progress()
        snap["chapters"][1]["status"] = "corrupted"
        snap["chapters"][999] = {"title": "x", "status": "y", "error": None}
        snap["status"] = "corrupted"
        self.assertEqual(w.progress_data["chapters"][1]["status"], w.STATUS_PROCESSING)
        self.assertNotIn(999, w.progress_data["chapters"])
        self.assertEqual(w.progress_data["status"], w.STATUS_PROCESSING)

    def test_initial_end_time_is_none(self):
        """end_time 初值必须是 None：`is None` 判断在 0 上恒假，execution_time 会算错。"""
        w = EpubToAudioWorker()
        self.assertIsNone(w.progress_data["end_time"])
        self.assertIsNone(EpubToAudioWorker().progress_data["end_time"])

    def test_snapshot_consistent_while_parsing(self):
        """读线程持续插键的同时反复序列化快照，不允许抛 RuntimeError。

        旧实现（无锁 + 浅拷贝）在高频插入时会在 json.dumps 的迭代里炸掉。
        """
        w = EpubToAudioWorker()
        stop = threading.Event()

        def feed():
            i = 0
            while not stop.is_set():
                with w._plock:  # 与 _read_stream_with_progress 相同的持锁方式
                    w._parse_bookbarn_log("[BOOKBARN]Processing:%d,第%d章" % (i, i))
                i += 1

        th = threading.Thread(target=feed, daemon=True)
        th.start()
        try:
            for _ in range(300):
                data = json.loads(w.get_progress_json())
                self.assertGreaterEqual(data["processed_chapters"], 0)
        finally:
            stop.set()
            th.join(timeout=5)

    def test_parse_updates_counters(self):
        w = EpubToAudioWorker()
        with w._plock:
            w._parse_bookbarn_log("[BOOKBARN]Chapters:10")
            w._parse_bookbarn_log("[BOOKBARN]Processing:0,第一章")
            w._parse_bookbarn_log("[BOOKBARN]Converted:0,第一章")
            w._parse_bookbarn_log("[BOOKBARN]Processing:1,第二章")
            w._parse_bookbarn_log("[BOOKBARN]Error:1,超时")
        self.assertEqual(w.progress_data["total_chapters"], 10)
        self.assertEqual(w.progress_data["converted_chapters"], 1)
        self.assertEqual(w.progress_data["failed_chapters"], 1)
        self.assertEqual(w.progress_data["processed_chapters"], 2)
        self.assertEqual(w.progress_data["chapters"][1]["status"], w.STATUS_FAILED)


if __name__ == "__main__":
    unittest.main()
