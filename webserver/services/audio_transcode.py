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

import json
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
    "delete_source": True,   # 转码成功后是否删除原 mp3（页面可关）
    "total": 0,
    "done": 0,
    "failed": 0,
    "current": "",          # 正在处理的文件名
    "errors": [],           # [(filename, errmsg)]
    "status": "idle",       # idle / running / done / error
    "message": "",
    "started_at": 0,
    "finished_at": 0,
    "queue": [],
    "queue_index": 0,
    "skipped": [],
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


def _audio_dir_of(db, book_id):
    """取书的音频目录（只读）；取不到返回 None。"""
    try:
        audio_dir, _legacy = audio_dir_for_read(db, int(book_id))
    except Exception:
        return None
    return audio_dir if audio_dir and os.path.isdir(audio_dir) else None


def probe_mp3(path):
    """用 ffprobe 读单个 mp3 的码率/采样率/时长/大小。

    为什么要探测：转码前用户看不到源码率，只能盲选档位。若源文件本身只有
    32k，选 128k 转出来只是把低质量放大——文件更大、音质一点没提升。
    探测结果用来提示「是否白转」。

    任何异常（ffprobe 缺失、文件损坏、解析失败）都返回 None，调用方按
    「未知」处理，绝不因为探测失败影响扫描本身。
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    info = {"path": path, "name": os.path.basename(path), "size": size,
            "bitrate": None, "sample_rate": None, "duration": None}
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=bit_rate,sample_rate:format=bit_rate,duration",
             "-of", "json", path],
            capture_output=True, timeout=20,
        )
        if out.returncode != 0:
            return info
        data = json.loads(out.stdout.decode("utf-8", "replace") or "{}")
        streams = data.get("streams") or [{}]
        fmt = data.get("format") or {}
        # 优先用流级码率，退到容器级（VBR 的 mp3 常只有容器级）
        br = streams[0].get("bit_rate") or fmt.get("bit_rate")
        info["bitrate"] = int(br) if br and str(br).isdigit() else None
        sr = streams[0].get("sample_rate")
        info["sample_rate"] = int(sr) if sr and str(sr).isdigit() else None
        du = fmt.get("duration")
        try:
            info["duration"] = float(du) if du else None
        except (TypeError, ValueError):
            info["duration"] = None
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        LOG.info("[audio_transcode] ffprobe 失败 %s: %s", path, e)
    return info


def probe_book_audio(db, book_id, files=None, limit=200):
    """探测一本书的音频概况，给前端展示「现在是什么样」。

    返回 dict：files 明细、总大小、总时长、平均码率、最低/最高码率。
    files 超过 limit 时只探测前 limit 个（全库扫描时避免几百次 ffprobe 卡住），
    此时 sampled=True，前端应说明「基于抽样」。
    """
    audio_dir = _audio_dir_of(db, book_id)
    if not files:
        files = list_mp3_files(db, book_id) or []
    if not audio_dir:
        return None
    picked = files[:limit] if limit and len(files) > limit else files
    details = []
    for name in picked:
        details.append(probe_mp3(os.path.join(audio_dir, name)))

    total_size = sum(d["size"] or 0 for d in details)
    known = [d for d in details if d["bitrate"]]
    durations = [d["duration"] for d in details if d["duration"]]
    return {
        "count": len(files),
        "sampled": len(picked) < len(files),
        "sampled_count": len(picked),
        "total_size": total_size,
        "total_duration": sum(durations) if durations else None,
        "avg_bitrate": int(sum(d["bitrate"] for d in known) / len(known)) if known else None,
        "min_bitrate": min((d["bitrate"] for d in known), default=None),
        "max_bitrate": max((d["bitrate"] for d in known), default=None),
        "sample_rate": next((d["sample_rate"] for d in details if d["sample_rate"]), None),
        "files": details,
    }



def start(db, book_ids, bitrate="64k", titles=None, delete_source=True):
    """启动转码队列。book_ids 可传单本 int 或多本 list。

    delete_source: 转码成功后是否删除原 mp3。默认 True（沿用原行为），
    但用户可以在页面上取消勾选，保留原文件自己核对后再删。
    失败的 mp3 无论如何都保留。

    多本时按顺序逐书处理；某书没有 mp3 直接跳过（计入 skipped）。
    返回 (ok, msg)。
    """
    if isinstance(book_ids, int):
        book_ids = [book_ids]
    book_ids = [int(b) for b in (book_ids or []) if int(b) > 0]
    if not book_ids:
        return False, _("未指定书籍")

    titles = titles or {}
    with _task_lock:
        if _task["running"]:
            return False, _("已有转码任务在进行中（书 %s）") % _task.get("book_title")                 or _task.get("book_id")

        # 预检：过滤掉没有 mp3 的书
        queue = []
        skipped = []
        for bid in book_ids:
            files = list_mp3_files(db, bid)
            if files is None:
                skipped.append({"book_id": bid, "reason": "not_found"})
            elif not files:
                skipped.append({"book_id": bid, "reason": "no_mp3"})
            else:
                queue.append({"book_id": bid, "files": files})

        if not queue:
            return False, _("所选书籍都没有需要转码的 mp3")

        _task.update({
            "running": True,
            "book_id": queue[0]["book_id"],
            "book_title": titles.get(str(queue[0]["book_id"]), ""),
            "bitrate": bitrate if bitrate in ("64k", "96k", "128k") else "64k",
            "delete_source": bool(delete_source),
            "total": sum(len(q["files"]) for q in queue),
            "done": 0,
            "failed": 0,
            "current": "",
            "errors": [],
            "status": "running",
            "message": "",
            "started_at": time.time(),
            "finished_at": 0,
            # 多书队列信息（单书时只有一个元素）
            "queue": [
                {"book_id": q["book_id"], "title": titles.get(str(q["book_id"]), ""),
                 "total": len(q["files"]), "done": 0, "failed": 0}
                for q in queue
            ],
            "queue_index": 0,
            "skipped": skipped,
        })

    t = threading.Thread(target=_run_queue, args=(db, queue), daemon=True)
    t.start()
    if len(queue) == 1:
        return True, _("转码已启动，共 %d 个文件") % _task["total"]
    return True, _("批量转码已启动：%d 本书，共 %d 个文件") % (len(queue), _task["total"])


def _run_queue(db, queue):
    """按队列逐书转码。queue 元素: {book_id, files}。"""
    try:
        for qi, item in enumerate(queue):
            if not _task["running"]:
                break
            _task["queue_index"] = qi
            _task["book_id"] = item["book_id"]
            _task["book_title"] = _task["queue"][qi]["title"]
            _transcode_one_book(db, item["book_id"], item["files"], qi)
        _task["status"] = "done"
        if _task.get("delete_source", True):
            _task["message"] = _("完成：%d 本书 %d 成功 %d 失败（失败的 mp3 已保留）") % (
                len(queue), _task["done"], _task["failed"])
        else:
            _task["message"] = _("完成：%d 本书 %d 成功 %d 失败（原 mp3 已按要求保留）") % (
                len(queue), _task["done"], _task["failed"])
        if _task.get("skipped"):
            _task["message"] += _(", 跳过 %d 本（无 mp3 或书不存在）") % len(_task["skipped"])
    except Exception as e:
        _task["status"] = "error"
        _task["message"] = _("任务异常：%s") % e
        logging.exception("[audio_transcode] 任务异常")
    finally:
        _task["running"] = False
        _task["current"] = ""
        _task["finished_at"] = time.time()


def _transcode_one_book(db, book_id, files, queue_index):
    try:
        audio_dir, _legacy = audio_dir_for_read(db, book_id)
        if not audio_dir or not os.path.isdir(audio_dir):
            raise RuntimeError("audio dir missing")
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

            # §临时文件必须保住 .m4a 扩展名§
            # 原来写 dst + ".tmp" → "xxx.m4a.tmp"，ffmpeg 只看最后一个后缀，
            # 认不出容器格式，直接报
            #   Error initializing the muxer for xxx.m4a.tmp: Invalid argument
            # 于是每一次转码都失败（mp3 全保留，一个 m4a 也生成不出来）。
            # 改成 xxx.tmp.m4a：后缀仍是 .m4a，同时用 -f mp4 双保险。
            tmp = os.path.join(audio_dir, stem + ".tmp.m4a")
            cmd = FFMPEG_BASE + [
                "-i", src,
                "-map_metadata", "-1",       # 洗掉 ID3：作者/专辑等不再依赖 mp3 标签
                "-map", "0:a",               # 只要音频流
                "-c:a", "aac",
                "-b:a", bitrate,
                "-movflags", "+faststart",   # moov 前置，浏览器秒开可拖
                "-f", "mp4",                 # 显式指定容器，不依赖后缀推断
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
                # §原 mp3 删不删由用户说了算§ 4.6.0-18
                # 原来是无条件 os.remove(src)：用户想先试听对比、或磁盘够用想留底，
                # 都没得选，转完原文件就没了。现在页面有开关，默认仍删（沿用旧行为）。
                # 失败路径不受影响，mp3 一律保留。
                if _task.get("delete_source", True):
                    os.remove(src)
                else:
                    _task["kept"] = _task.get("kept", 0) + 1
                _task["done"] += 1
                _task["queue"][queue_index]["done"] += 1
                logging.info("[audio_transcode] %s -> %s OK", name, stem + ".m4a")
            except Exception as e:
                # 失败：清掉半成品，保留 mp3，继续下一个
                _task["failed"] += 1
                _task["queue"][queue_index]["failed"] += 1
                _task["errors"].append({"file": name, "error": str(e)[:300]})
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except OSError:
                    pass
                logging.warning("[audio_transcode] %s 失败: %s", name, e)
    except Exception as e:
        # 单书级异常（如目录消失）：记错误，队列继续下一本
        _task["failed"] += len(files) - (_task["queue"][queue_index]["done"]
                                          + _task["queue"][queue_index]["failed"])
        _task["errors"].append({
            "file": _("书 #%s 整体失败" % book_id), "error": str(e)[:300]})
        logging.warning("[audio_transcode] 书 %s 整体失败: %s", book_id, e)
