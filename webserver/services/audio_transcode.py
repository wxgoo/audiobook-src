#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""音频批量转码工具（工具箱）：把指定书 .audio/ 里的 mp3 批量转成 m4a。

动机
----
导入的老 audiobook mp3 普遍带着杂乱的 ID3 标签（artist 常是播音员而不是作者，
专辑名五花八门），之前已导致 AudioBookImporter 按播音员建错书。转码时加
``-map_metadata -1`` 一次洗掉；顺带转 AAC 并加 ``+faststart``（moov 前置），
浏览器边下边播、seek 都更快。AAC 同等听感码率更低，网络盘播放更顺。

安全设计
--------
* 单文件失败不中断整批：记下错误继续下一个；
* mp3 只在对应 m4a 成功生成（存在且 >0）之后才删除，失败原样保留；
* 同一时刻只允许一个转码任务（模块级锁），避免两个任务同时改同一个目录；
* 进度是模块级字典，Tornado 多个请求共享。
"""

import logging
import os
import subprocess
import threading
import time

from webserver.base.audio_dir import audio_dir_for_read
from webserver.i18n import _

LOG = logging.getLogger(__name__)

# 转码参数：AAC + 洗元数据 + faststart。码率由用户选择。
FFMPEG_BASE = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]

# 模块级任务状态。进程内只有一个转码任务在跑。
_task_lock = threading.Lock()
_task = {
    "running": False,
    "book_id": None,
    "book_title": "",
    "bitrate": "64k",
    "total": 0,
    "done": 0,
    "failed": 0,
    "current": "",          # 正在处理的文件名
    "errors": [],           # [(filename, errmsg)]
    "status": "idle",       # idle / running / done / error
    "message": "",
    "started_at": 0,
    "finished_at": 0,
}


def task_snapshot():
    return dict(_task)


def is_running():
    return _task["running"]


def list_mp3_files(db, book_id):
    """返回该书 .audio/ 下 mp3 文件名列表（按文件名排序）。

    db 由调用方（handler）传入。书不存在返回 None，没有音频返回空表。
    """
    try:
        audio_dir, _legacy = audio_dir_for_read(db, int(book_id))
    except Exception as e:
        LOG.warning("[audio_transcode] 解析音频目录失败 book=%s: %s", book_id, e)
        return None  # 书不存在
    if not audio_dir or not os.path.isdir(audio_dir):
        return []
    return sorted(
        f for f in os.listdir(audio_dir)
        if f.lower().endswith(".mp3") and os.path.isfile(os.path.join(audio_dir, f))
    )


def start(db, book_id, bitrate="64k", title=""):
    """启动转码线程。返回 (ok, msg)。db 与书名由 handler 传入。"""
    with _task_lock:
        if _task["running"]:
            return False, _("已有转码任务在进行中（书 %s）") % _task.get("book_id")

        files = list_mp3_files(db, book_id)
        if files is None:
            return False, _("书籍不存在")
        if not files:
            return False, _("该书的 .audio/ 目录里没有 mp3 文件")

        _task.update({
            "running": True,
            "book_id": int(book_id),
            "book_title": title or "",
            "bitrate": bitrate if bitrate in ("64k", "96k", "128k") else "64k",
            "total": len(files),
            "done": 0,
            "failed": 0,
            "current": "",
            "errors": [],
            "status": "running",
            "message": "",
            "started_at": time.time(),
            "finished_at": 0,
        })

    t = threading.Thread(target=_run, args=(db, int(book_id)), daemon=True)
    t.start()
    return True, _("转码已启动，共 %d 个文件") % len(files)


def _run(db, book_id):
    try:
        audio_dir, _legacy = audio_dir_for_read(db, book_id)
        files = sorted(
            f for f in os.listdir(audio_dir)
            if f.lower().endswith(".mp3") and os.path.isfile(os.path.join(audio_dir, f))
        )
        bitrate = _task["bitrate"]
        for name in files:
            if not _task["running"]:  # 预留：将来支持取消
                break
            _task["current"] = name
            src = os.path.join(audio_dir, name)
            stem = os.path.splitext(name)[0]
            dst = os.path.join(audio_dir, stem + ".m4a")

            if os.path.exists(dst):
                # 已有同名 m4a：转出的会覆盖它，这是预期（以最新转码为准）
                logging.info("[audio_transcode] 覆盖已有 m4a: %s", dst)

            tmp = dst + ".tmp"
            cmd = FFMPEG_BASE + [
                "-i", src,
                "-map_metadata", "-1",       # 洗掉 ID3：作者/专辑等不再依赖 mp3 标签
                "-map", "0:a",               # 只要音频流
                "-c:a", "aac",
                "-b:a", bitrate,
                "-movflags", "+faststart",   # moov 前置，浏览器秒开可拖
                tmp,
            ]
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=3600,
                )
                if proc.returncode != 0 or not os.path.exists(tmp) \
                        or os.path.getsize(tmp) == 0:
                    err = (proc.stderr or "").strip().splitlines()
                    raise RuntimeError(
                        "ffmpeg rc=%s %s" % (proc.returncode,
                                             err[-1] if err else "no output")
                    )
                os.replace(tmp, dst)          # 转码成功：m4a 就位
                os.remove(src)                # mp3 只有在 m4a 成功后才删
                _task["done"] += 1
                logging.info("[audio_transcode] %s -> %s OK", name, stem + ".m4a")
            except Exception as e:
                # 失败：清掉半成品，保留 mp3，继续下一个
                _task["failed"] += 1
                _task["errors"].append({"file": name, "error": str(e)[:300]})
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except OSError:
                    pass
                logging.warning("[audio_transcode] %s 失败: %s", name, e)
        _task["status"] = "done"
        _task["message"] = _("完成：%d 成功，%d 失败（失败的 mp3 已保留）") % (
            _task["done"], _task["failed"])
    except Exception as e:
        _task["status"] = "error"
        _task["message"] = _("任务异常：%s") % e
        logging.exception("[audio_transcode] 任务异常")
    finally:
        _task["running"] = False
        _task["current"] = ""
        _task["finished_at"] = time.time()
