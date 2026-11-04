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
import shutil
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
    "kept": 0,               # delete_source=False 时保留原 mp3 的个数
    "current": "",          # 正在处理的文件名
    "errors": [],           # [(filename, errmsg)]
    "status": "idle",       # idle / running / done / error / cancelling / cancelled
    "message": "",
    "started_at": 0,
    "finished_at": 0,
    "queue": [],
    "queue_index": 0,
    "skipped": [],
    "cancel_requested": False,
}


def task_snapshot():
    """任务状态快照。

    必须拷贝嵌套结构：轮询接口把这个 dict 直接 JSON 序列化，浅拷贝会让
    errors/queue/skipped 仍与后台线程共享，序列化迭代时后台线程并发修改
    可能抛 RuntimeError（dict changed size during iteration）。
    """
    with _task_lock:
        snap = dict(_task)
    snap["errors"] = list(snap.get("errors") or [])
    snap["skipped"] = [dict(x) for x in (snap.get("skipped") or [])]
    snap["queue"] = [dict(x) for x in (snap.get("queue") or [])]
    return snap


def is_running():
    """handler 侧的「忙」判定：running 或正在收尾取消（旧线程还没退干净）。

    cancel() 会立刻把 running 置 False，但工作线程要等当前 ffmpeg 结束才真正
    退出；这个窗口里允许 start() 会覆盖掉取消中的任务状态，所以也算忙。
    """
    return _task["running"] or _task.get("status") == "cancelling"


def book_audio_dir(db, book_id):
    """解析书的 .audio/ 目录（calibre 只读操作）。

    纯 field_for 读取，不碰文件系统之外的任何东西，设计为可放进
    run_calibre_read_async 在 calibre 池里调用。书不存在/无路径返回 None。
    """
    try:
        audio_dir, _legacy = audio_dir_for_read(db, int(book_id))
    except Exception as e:
        LOG.warning("[audio_transcode] 解析音频目录失败 book=%s: %s", book_id, e)
        return None
    return audio_dir or None


def list_mp3_in_dir(audio_dir):
    """列出目录下的 mp3（纯文件系统操作，不碰 db，可放线程池）。"""
    if not audio_dir or not os.path.isdir(audio_dir):
        return []
    return sorted(
        f for f in os.listdir(audio_dir)
        if f.lower().endswith(".mp3") and os.path.isfile(os.path.join(audio_dir, f))
    )


def list_mp3_files(db, book_id):
    """返回该书 .audio/ 下 mp3 文件名列表（按文件名排序）。

    db 由调用方（handler）传入。书不存在返回 None，没有音频返回空表。
    注意：内含 calibre 读调用 + 目录遍历，事件循环上调用会阻塞 ioloop——
    handler 里请先 run_calibre_read_async(book_audio_dir) 再在线程池里
    list_mp3_in_dir，本函数留给兼容旧调用方和非 ioloop 场景。
    """
    audio_dir = book_audio_dir(db, book_id)
    if audio_dir is None:
        return None  # 书不存在
    return list_mp3_in_dir(audio_dir)


def _audio_dir_of(db, book_id):
    """取书的音频目录（只读）；取不到返回 None。"""
    audio_dir = book_audio_dir(db, book_id)
    if audio_dir and os.path.isdir(audio_dir):
        return audio_dir
    return None


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


def probe_files_in_dir(audio_dir, files=None, limit=200):
    """探测目录下 mp3 的概况（纯文件系统 + ffprobe 子进程，不碰 db）。

    一个文件一次 ffprobe 子进程，单本书最多 limit 次——**必须**在
    utils.run_in_threadpool 之类的线程池里调用；放 Tornado handler（ioloop
    线程）同步跑会把全站请求冻住几十秒。

    返回 dict：files 明细、总大小、总时长、平均码率、最低/最高码率。
    files 超过 limit 时只探测前 limit 个，此时 sampled=True，
    前端应说明「基于抽样」。
    """
    if files is None:
        files = list_mp3_in_dir(audio_dir)
    picked = files[:limit] if limit and len(files) > limit else files
    details = []
    for name in picked:
        details.append(probe_mp3(os.path.join(audio_dir or "", name)))

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


def probe_book_audio(db, book_id, files=None, limit=200):
    """探测一本书的音频概况，给前端展示「现在是什么样」。

    兼容封装：先解析音频目录（calibre 读），再对目录做纯文件系统探测。
    同样**不能**在 ioloop 上直接调用（内含多次 ffprobe）——handler 里请
    分两步：run_calibre_read_async(book_audio_dir) + run_in_threadpool(
    probe_files_in_dir)。
    """
    audio_dir = _audio_dir_of(db, book_id)
    if not audio_dir:
        return None
    if not files:
        files = list_mp3_in_dir(audio_dir)
    return probe_files_in_dir(audio_dir, files, limit=limit)


def start(books, bitrate="64k", titles=None, delete_source=True):
    """启动转码队列。books 为 [{"book_id": int, "audio_dir": str}]。

    4.6.0-19 起不再接收 db：音频目录由 handler 先在 calibre 池里解析好
    （book_audio_dir），后台线程只做纯文件系统/子进程操作，不再持有任何
    calibre 对象。

    delete_source: 转码成功后是否删除原 mp3。默认 True（沿用原行为），
    但用户可以在页面上取消勾选，保留原文件自己核对后再删。
    失败的 mp3 无论如何都保留。

    多本时按顺序逐书处理；某书没有 mp3 直接跳过（计入 skipped）。
    返回 (ok, msg)。内部做文件系统遍历，handler 里建议经线程池调用。
    """
    if shutil.which("ffmpeg") is None:
        # ffmpeg 预检：环境里没有 ffmpeg 时每个文件都会失败，与其启动后
        # 逐个报 "No such file or directory"，不如直接拒绝并说明原因。
        return False, _("未找到 ffmpeg，无法转码（请确认运行环境已安装）")

    if isinstance(books, dict):
        books = [books]
    normalized = []
    for b in books or []:
        try:
            bid = int(b.get("book_id") or 0)
        except (TypeError, ValueError):
            continue
        if bid <= 0:
            continue
        normalized.append({"book_id": bid, "audio_dir": b.get("audio_dir")})
    if not normalized:
        return False, _("未指定书籍")

    titles = titles or {}
    with _task_lock:
        if _task["running"] or _task.get("status") == "cancelling":
            # cancel() 后旧线程可能还没退（当前文件转完才停），这个窗口里
            # 启动新任务会覆盖取消中的状态，一并拒绝。
            # % 优先级高于 or：必须先拼好兜底字符串再格式化，
            # 否则 book_title 为空时 or 兜底永远不会生效。
            label = _task.get("book_title") or ("#%s" % _task.get("book_id"))
            return False, _("已有转码任务在进行中（%s）") % label

        # 预检：过滤掉没有 mp3 的书（纯文件系统操作）
        queue = []
        skipped = []
        for item in normalized:
            files = list_mp3_in_dir(item["audio_dir"])
            if item["audio_dir"] is None:
                skipped.append({"book_id": item["book_id"], "reason": "not_found"})
            elif not files:
                skipped.append({"book_id": item["book_id"], "reason": "no_mp3"})
            else:
                queue.append({"book_id": item["book_id"],
                              "audio_dir": item["audio_dir"], "files": files})

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
            "kept": 0,
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
            "cancel_requested": False,
        })
        total = _task["total"]

    t = threading.Thread(target=_run_queue, args=(queue,), daemon=True)
    global _thread
    _thread = t
    t.start()
    if len(queue) == 1:
        return True, _("转码已启动，共 %d 个文件") % total
    return True, _("批量转码已启动：%d 本书，共 %d 个文件") % (len(queue), total)


def cancel():
    """请求取消进行中的转码任务。

    粒度是「当前文件」：正在跑的 ffmpeg 等它转完（或超时）后停止，
    后续文件不再处理；已转成功的 m4a 保留，失败/未处理的 mp3 原样保留。
    """
    with _task_lock:
        if not _task["running"]:
            return False, _("当前没有进行中的转码任务")
        _task["cancel_requested"] = True
        _task["running"] = False
        _task["status"] = "cancelling"
        _task["message"] = _("正在取消：当前文件转完即停，后续文件不再处理")
    return True, _("已请求取消，正在停止")


# 当前工作线程引用（仅供测试等待任务收尾用，不参与业务逻辑）
_thread = None


def _join_for_tests(timeout=30):
    """测试钩子：等后台转码线程跑完。生产代码不要调用。"""
    t = _thread
    if t and t.is_alive():
        t.join(timeout=timeout)


def _run_queue(queue):
    """按队列逐书转码。queue 元素: {book_id, audio_dir, files}。"""
    try:
        for qi, item in enumerate(queue):
            if not _task["running"]:  # cancel() 置 False 后逐书停
                break
            _task["queue_index"] = qi
            _task["book_id"] = item["book_id"]
            _task["book_title"] = _task["queue"][qi]["title"]
            _transcode_one_book(item, qi)
        with _task_lock:
            if _task.get("cancel_requested"):
                _task["status"] = "cancelled"
                _task["message"] = _("已取消：%d 成功 %d 失败（其余 mp3 原样保留）") % (
                    _task["done"], _task["failed"])
            else:
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
        with _task_lock:
            # 兜底：cancel() 恰好落在「循环已结束、状态已写完」之后的窗口时，
            # 会把 status 改成 cancelling 但再没有人收尾，is_busy 就永远为真。
            if _task["status"] == "cancelling":
                _task["status"] = "cancelled"
                _task["message"] = _("已取消：%d 成功 %d 失败（其余 mp3 原样保留）") % (
                    _task["done"], _task["failed"])


def _transcode_one_book(item, queue_index):
    book_id = item["book_id"]
    try:
        audio_dir = item["audio_dir"]
        if not audio_dir or not os.path.isdir(audio_dir):
            raise RuntimeError("audio dir missing")
        bitrate = _task["bitrate"]
        for name in item["files"]:
            if not _task["running"]:  # cancel() 请求后逐文件停
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
        # 单书级异常（如目录消失）：把剩余未处理的文件记为失败，队列继续下一本
        qi = _task["queue"][queue_index]
        remaining = len(item["files"]) - (qi["done"] + qi["failed"])
        _task["failed"] += remaining
        _task["errors"].append({
            "file": _("书 #%s 整体失败" % book_id), "error": str(e)[:300]})
        logging.warning("[audio_transcode] 书 %s 整体失败: %s", book_id, e)
