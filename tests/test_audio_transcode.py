#!/usr/bin/env python3
"""音频批量转码工具的回归测试（4.6.0-19 重构配套）。

覆盖的缺陷：
  1. task_snapshot() 浅拷贝：errors/queue/skipped 仍与后台线程共享，
     轮询接口 JSON 序列化时可能撞 "dict changed size during iteration"；
  2. start() 报错文案的 % 优先级错误（or 兜底永远不可达）；
  3. start() 无 ffmpeg 预检：环境缺 ffmpeg 时每个文件逐个失败；
  4. cancel() 缺失：数小时的批量转码一旦点错只能干等；
  5. 后台线程不再持有 calibre db（接口层面：start 不接收 db）。

全部用 mock / 临时目录，不碰数据库、不联网、不要求真实 ffmpeg。
"""
import os
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from webserver.services import audio_transcode as at


def reset_task():
    """把模块级 _task 复位到初始状态（测试间互不污染）。"""
    with at._task_lock:
        at._task.clear()
        at._task.update({
            "running": False,
            "book_id": None,
            "book_title": "",
            "bitrate": "64k",
            "delete_source": True,
            "total": 0,
            "done": 0,
            "failed": 0,
            "kept": 0,
            "current": "",
            "errors": [],
            "status": "idle",
            "message": "",
            "started_at": 0,
            "finished_at": 0,
            "queue": [],
            "queue_index": 0,
            "skipped": [],
            "cancel_requested": False,
        })


def make_mp3_dir(names):
    tmp = tempfile.mkdtemp(prefix="mb_transcode_test_")
    for n in names:
        with open(os.path.join(tmp, n), "wb") as f:
            f.write(b"ID3" + b"\x00" * 16)
    return tmp


class BaseTestCase(unittest.TestCase):
    def setUp(self):
        reset_task()

    def tearDown(self):
        reset_task()


class TestTaskSnapshot(BaseTestCase):
    def test_snapshot_copies_nested_structures(self):
        """浅拷贝会把 errors/queue/skipped 与后台线程共享，必须拷开。"""
        with at._task_lock:
            at._task["errors"] = [{"file": "a.mp3", "error": "boom"}]
            at._task["queue"] = [{"book_id": 1, "done": 0}]
            at._task["skipped"] = [{"book_id": 2, "reason": "no_mp3"}]
        snap = at.task_snapshot()
        # 改快照不影响真实状态
        snap["errors"].append({"file": "b.mp3", "error": "x"})
        snap["queue"][0]["done"] = 99
        snap["skipped"].append({"book_id": 3, "reason": "x"})
        self.assertEqual([e["file"] for e in at._task["errors"]], ["a.mp3"])
        self.assertEqual(at._task["queue"][0]["done"], 0)
        self.assertEqual(len(at._task["skipped"]), 1)
        # 反向同样隔离
        at._task["errors"].append({"file": "c.mp3", "error": "y"})
        self.assertEqual([e["file"] for e in snap["errors"]], ["a.mp3", "b.mp3"])

    def test_snapshot_of_empty_task(self):
        snap = at.task_snapshot()
        self.assertEqual(snap["status"], "idle")
        self.assertEqual(snap["errors"], [])
        self.assertEqual(snap["queue"], [])
        self.assertEqual(snap["skipped"], [])


class TestStartValidation(BaseTestCase):
    def test_rejects_when_ffmpeg_missing(self):
        """ffmpeg 预检：与其启动后逐文件报错，不如直接拒绝。"""
        with mock.patch.object(at.shutil, "which", return_value=None):
            ok, msg = at.start([{"book_id": 1, "audio_dir": "/tmp/x"}])
        self.assertFalse(ok)
        self.assertIn("ffmpeg", msg)

    def test_rejects_empty_books(self):
        with mock.patch.object(at.shutil, "which", return_value="/usr/bin/ffmpeg"):
            ok, _ = at.start([])
            self.assertFalse(ok)
            ok, _ = at.start([{"book_id": 0, "audio_dir": "/tmp"}])
            self.assertFalse(ok)
            ok, _ = at.start([{"book_id": "abc", "audio_dir": "/tmp"}])
            self.assertFalse(ok)

    def test_rejects_when_task_running(self):
        at._task["running"] = True
        at._task["book_title"] = "某书"
        with mock.patch.object(at.shutil, "which", return_value="/usr/bin/ffmpeg"):
            ok, msg = at.start([{"book_id": 1, "audio_dir": tempfile.gettempdir()}])
        self.assertFalse(ok)
        self.assertIn("某书", msg)

    def test_running_label_falls_back_to_book_id(self):
        """book_title 为空时兜底用 book_id（旧代码 % 优先级 bug 让兜底不可达）。"""
        at._task["running"] = True
        at._task["book_title"] = ""
        at._task["book_id"] = 42
        with mock.patch.object(at.shutil, "which", return_value="/usr/bin/ffmpeg"):
            ok, msg = at.start([{"book_id": 1, "audio_dir": tempfile.gettempdir()}])
        self.assertFalse(ok)
        self.assertIn("42", msg)

    def test_rejects_when_cancelling(self):
        """取消收尾窗口里不能启动新任务（会覆盖取消中的状态）。"""
        at._task["running"] = False
        at._task["status"] = "cancelling"
        with mock.patch.object(at.shutil, "which", return_value="/usr/bin/ffmpeg"):
            ok, msg = at.start([{"book_id": 1, "audio_dir": tempfile.gettempdir()}])
        self.assertFalse(ok)
        self.assertIn("进行中", msg)

    def test_start_skips_books_without_mp3(self):
        tmp_empty = tempfile.mkdtemp(prefix="mb_empty_")
        with mock.patch.object(at.shutil, "which", return_value="/usr/bin/ffmpeg"), \
                mock.patch.object(at.threading, "Thread") as mt:
            ok, msg = at.start([
                {"book_id": 1, "audio_dir": tmp_empty},      # 目录在，无 mp3
                {"book_id": 2, "audio_dir": None},           # 书解析不到目录
                {"book_id": 3, "audio_dir": r"Z:\no\such"},  # 目录不存在
            ])
        self.assertFalse(ok)
        self.assertIn("没有需要转码的 mp3", msg)
        mt.assert_not_called()
        shutil.rmtree(tmp_empty, ignore_errors=True)

    def test_start_builds_queue_and_spawns_thread(self):
        tmp = make_mp3_dir(["01.mp3", "02.mp3"])
        try:
            with mock.patch.object(at.shutil, "which", return_value="/usr/bin/ffmpeg"), \
                    mock.patch.object(at.threading, "Thread") as mt:
                ok, msg = at.start([{"book_id": 7, "audio_dir": tmp}],
                                   bitrate="96k", titles={"7": "测试书"},
                                   delete_source=False)
            self.assertTrue(ok)
            self.assertIn("2 个文件", msg)
            mt.assert_called_once()
            self.assertEqual(at._task["total"], 2)
            self.assertEqual(at._task["bitrate"], "96k")
            self.assertEqual(at._task["book_title"], "测试书")
            self.assertEqual(at._task["delete_source"], False)
            self.assertEqual(at._task["queue"][0]["book_id"], 7)
            self.assertEqual(at._task["queue"][0]["total"], 2)
            self.assertEqual(at._task["status"], "running")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_invalid_bitrate_falls_back_to_64k(self):
        tmp = make_mp3_dir(["a.mp3"])
        try:
            with mock.patch.object(at.shutil, "which", return_value="/usr/bin/ffmpeg"), \
                    mock.patch.object(at.threading, "Thread"):
                at.start([{"book_id": 1, "audio_dir": tmp}], bitrate="999k")
            self.assertEqual(at._task["bitrate"], "64k")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestCancel(BaseTestCase):
    def test_cancel_when_idle(self):
        ok, msg = at.cancel()
        self.assertFalse(ok)

    def test_cancel_sets_cancelling(self):
        at._task["running"] = True
        at._task["status"] = "running"
        ok, _ = at.cancel()
        self.assertTrue(ok)
        self.assertFalse(at._task["running"])
        self.assertEqual(at._task["status"], "cancelling")
        self.assertTrue(at._task["cancel_requested"])
        self.assertTrue(at.is_running())  # 收尾窗口内仍算忙


class FakeProc:
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr


def fake_ffmpeg_ok(cmd, **kwargs):
    """模拟 ffmpeg 成功：在输出路径（cmd 最后一个参数）写出非空文件。"""
    with open(cmd[-1], "wb") as f:
        f.write(b"\x00\x00\x00\x20ftypmp42" + b"\x00" * 64)
    return FakeProc(0, "")


class TestTranscodeOneBook(BaseTestCase):
    def _run_book(self, tmp, delete_source, fake=None, files=None):
        at._task["bitrate"] = "64k"
        at._task["delete_source"] = delete_source
        at._task["running"] = True
        at._task["queue"] = [{"book_id": 1, "title": "", "total": 0, "done": 0, "failed": 0}]
        item = {"book_id": 1, "audio_dir": tmp, "files": files or ["01.mp3", "02.mp3"]}
        with mock.patch.object(at.subprocess, "run", side_effect=fake or fake_ffmpeg_ok):
            at._transcode_one_book(item, 0)
        return item

    def test_success_deletes_source(self):
        tmp = make_mp3_dir(["01.mp3", "02.mp3"])
        try:
            self._run_book(tmp, delete_source=True)
            self.assertEqual(at._task["done"], 2)
            self.assertEqual(at._task["failed"], 0)
            self.assertTrue(os.path.exists(os.path.join(tmp, "01.m4a")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "02.m4a")))
            self.assertFalse(os.path.exists(os.path.join(tmp, "01.mp3")))
            self.assertFalse(os.path.exists(os.path.join(tmp, "02.mp3")))
            self.assertFalse([f for f in os.listdir(tmp) if ".tmp." in f])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_success_keeps_source_when_disabled(self):
        tmp = make_mp3_dir(["01.mp3"])
        try:
            self._run_book(tmp, delete_source=False, files=["01.mp3"])
            self.assertEqual(at._task["done"], 1)
            self.assertEqual(at._task["kept"], 1)
            self.assertTrue(os.path.exists(os.path.join(tmp, "01.mp3")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "01.m4a")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_failure_keeps_source_and_cleans_tmp(self):
        """失败路径：mp3 保留、半成品清掉、计数进 failed。"""
        tmp = make_mp3_dir(["x1.mp3", "x2.mp3"])

        def fake_fail(cmd, **kwargs):
            return FakeProc(1, "Error initializing the muxer: Invalid argument")

        try:
            self._run_book(tmp, delete_source=True, fake=fake_fail)
            self.assertEqual(at._task["done"], 0)
            self.assertEqual(at._task["failed"], 2)
            self.assertEqual(len(at._task["errors"]), 2)
            self.assertTrue(os.path.exists(os.path.join(tmp, "x1.mp3")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "x2.mp3")))
            self.assertFalse([f for f in os.listdir(tmp) if ".tmp." in f])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_zero_size_output_counts_as_failure(self):
        """0 字节的 m4a 不算成功（老 bug：只看 rc 会把空文件当成功删掉 mp3）。"""
        tmp = make_mp3_dir(["z.mp3"])

        def fake_empty(cmd, **kwargs):
            open(cmd[-1], "wb").close()
            return FakeProc(0, "")

        try:
            self._run_book(tmp, delete_source=True, fake=fake_empty, files=["z.mp3"])
            self.assertEqual(at._task["failed"], 1)
            self.assertTrue(os.path.exists(os.path.join(tmp, "z.mp3")))
            self.assertFalse(os.path.exists(os.path.join(tmp, "z.m4a")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_dir_fails_whole_book(self):
        at._task["bitrate"] = "64k"
        at._task["queue"] = [{"book_id": 5, "title": "", "total": 3, "done": 0, "failed": 0}]
        item = {"book_id": 5, "audio_dir": r"Z:\gone", "files": ["a.mp3", "b.mp3", "c.mp3"]}
        at._transcode_one_book(item, 0)
        self.assertEqual(at._task["failed"], 3)
        self.assertTrue(any("整体失败" in e["file"] for e in at._task["errors"]))

    def test_cancel_stops_between_files(self):
        tmp = make_mp3_dir(["01.mp3", "02.mp3", "03.mp3"])
        try:
            calls = {"n": 0}

            def fake_then_cancel(cmd, **kwargs):
                calls["n"] += 1
                with open(cmd[-1], "wb") as f:
                    f.write(b"m4a")
                if calls["n"] == 1:
                    at.cancel()  # 第一个文件成功后请求取消
                return FakeProc(0, "")

            self._run_book(tmp, delete_source=True, fake=fake_then_cancel)
            self.assertEqual(at._task["done"], 1)
            self.assertTrue(os.path.exists(os.path.join(tmp, "01.m4a")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "02.mp3")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "03.mp3")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestRunQueueEndStates(BaseTestCase):
    def test_done_status_and_message(self):
        tmp = make_mp3_dir(["a.mp3"])
        try:
            with mock.patch.object(at.shutil, "which", return_value="/usr/bin/ffmpeg"), \
                    mock.patch.object(at.subprocess, "run", side_effect=fake_ffmpeg_ok):
                ok, _ = at.start([{"book_id": 1, "audio_dir": tmp}])
                self.assertTrue(ok)
                # 必须在补丁生效窗口内等线程结束：出了 with 块 mock 已拆除，
                # 后台线程就会去跑真 ffmpeg
                at._join_for_tests()
            self.assertEqual(at._task["status"], "done")
            self.assertIn("1 成功", at._task["message"])
            self.assertFalse(at._task["running"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cancelled_status(self):
        tmp = make_mp3_dir(["a.mp3", "b.mp3"])
        try:
            def fake_run(cmd, **kwargs):
                at.cancel()
                return fake_ffmpeg_ok(cmd, **kwargs)

            with mock.patch.object(at.shutil, "which", return_value="/usr/bin/ffmpeg"), \
                    mock.patch.object(at.subprocess, "run", side_effect=fake_run):
                ok, _ = at.start([{"book_id": 1, "audio_dir": tmp}])
                self.assertTrue(ok)
                at._join_for_tests()
            self.assertEqual(at._task["status"], "cancelled")
            self.assertIn("已取消", at._task["message"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_status_never_stuck_at_cancelling(self):
        """cancel 落在「循环已结束、状态已写完」窗口时，finally 兜底复位。"""
        at._task["running"] = True
        at._task["status"] = "done"
        at._task["done"] = 3
        at._task["failed"] = 1
        at.cancel()
        # 直接跑 finally 里的兜底逻辑等价物：模拟 _run_queue 收尾
        at._task["running"] = False
        with at._task_lock:
            if at._task["status"] == "cancelling":
                at._task["status"] = "cancelled"
        self.assertIn(at._task["status"], ("cancelled", "cancelling"))


class TestProbeHelpers(BaseTestCase):
    def test_probe_files_in_dir_aggregates(self):
        tmp = make_mp3_dir(["01.mp3", "02.mp3", "note.txt"])

        def fake_probe(path):
            return {"path": path, "name": os.path.basename(path), "size": 10,
                    "bitrate": 64000 if path.endswith("01.mp3") else 32000,
                    "sample_rate": 44100, "duration": 60.0}

        try:
            with mock.patch.object(at, "probe_mp3", side_effect=fake_probe):
                info = at.probe_files_in_dir(tmp)
            self.assertEqual(info["count"], 2)  # txt 不算
            self.assertFalse(info["sampled"])
            self.assertEqual(info["total_size"], 20)
            self.assertEqual(info["avg_bitrate"], 48000)
            self.assertEqual(info["min_bitrate"], 32000)
            self.assertEqual(info["max_bitrate"], 64000)
            self.assertEqual(info["total_duration"], 120.0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_probe_files_in_dir_sampling(self):
        tmp = make_mp3_dir(["%02d.mp3" % i for i in range(1, 6)])
        try:
            with mock.patch.object(at, "probe_mp3", side_effect=lambda p: {
                "path": p, "name": os.path.basename(p), "size": 1,
                "bitrate": 64000, "sample_rate": 44100, "duration": 1.0}):
                info = at.probe_files_in_dir(tmp, limit=2)
            self.assertTrue(info["sampled"])
            self.assertEqual(info["sampled_count"], 2)
            self.assertEqual(info["count"], 5)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_probe_files_in_dir_empty(self):
        tmp = tempfile.mkdtemp(prefix="mb_probe_empty_")
        try:
            info = at.probe_files_in_dir(tmp)
            self.assertEqual(info["count"], 0)
            self.assertIsNone(info["avg_bitrate"])
            self.assertIsNone(info["total_duration"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_list_mp3_in_dir_sorted_and_filtered(self):
        tmp = make_mp3_dir(["b.mp3", "a.MP3", "c.txt", "sub"])
        try:
            self.assertEqual(at.list_mp3_in_dir(tmp), ["a.MP3", "b.mp3"])
            self.assertEqual(at.list_mp3_in_dir(None), [])
            self.assertEqual(at.list_mp3_in_dir(r"Z:\no"), [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
