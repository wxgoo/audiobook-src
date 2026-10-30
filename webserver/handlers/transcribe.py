#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""音频转写文稿 API（管理员）。

POST /api/admin/transcribe/run     {paths: [...], model: "small", lang: "auto"}
GET  /api/admin/transcribe/status
POST /api/admin/transcribe/cancel
GET  /api/admin/transcribe/available

Whisper 未安装时 available 为 false，前端据此隐藏入口。
"""

import json
import logging
import os
import threading

from webserver import loader
from webserver.handlers.base import BaseHandler, is_admin, js
from webserver.services.background_service import BackgroundService, BackgroundTask
from webserver.services import transcribe

CONF = loader.get_settings()

# 后台任务类型
SERVICE_TYPE = "transcribe"


class _Job:
    """一次批量转写会话（同进程单例，跑完可再次发起）。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.task_id = None
        self.stop_event = threading.Event()
        self.state = {"running": False, "done": 0, "failed": 0,
                      "total": 0, "progress": 0, "note": "", "error": ""}


_job = _Job()


def _run_job(paths, model, lang, keep_txt=True):
    from webserver.services.transcribe import transcribe_many

    def cb(frac, note=""):
        with _job.lock:
            _job.state["progress"] = int(frac * 100)
            if note:
                _job.state["note"] = note
        BackgroundService().update_progress(
            task_id=_job.task_id, progress=int(frac * 100),
            progress_data={"done": _job.state["done"],
                           "failed": _job.state["failed"],
                           "total": _job.state["total"]})

    try:
        done, failed, results = transcribe_many(
            paths, model_size=model, lang=lang,
            progress_cb=cb, stop_event=_job.stop_event,
            keep_txt=keep_txt)
        cancelled = _job.stop_event.is_set()
        with _job.lock:
            _job.state["done"] = done
            _job.state["failed"] = failed
            _job.state["running"] = False
            _job.state["note"] = "已取消" if cancelled else "完成"
        BackgroundService().complete_task(
            task_id=_job.task_id,
            error_message=None if not cancelled else "已取消")
        logging.info("[transcribe] job finished: done=%d failed=%d", done, failed)
    except Exception as e:
        logging.exception("[transcribe] job crashed")
        with _job.lock:
            _job.state["running"] = False
            _job.state["error"] = str(e)
        BackgroundService().complete_task(task_id=_job.task_id,
                                          error_message=str(e))


class TranscribeAvailable(BaseHandler):
    @js
    def get(self):
        # 顺带把当前配置回传给前端，让面板上的模型/语言/输出格式开关
        # 打开时显示的是「上次保存的值」而不是硬编码默认值。
        return {
            "err": "ok",
            "available": transcribe.whisper_available(),
            "backend": transcribe.detect_backend(),
            "model": CONF.get("TRANSCRIBE_MODEL", "small"),
            "lang": CONF.get("TRANSCRIBE_LANG", "auto"),
            "keep_txt": bool(CONF.get("TRANSCRIBE_KEEP_TXT", True)),
        }


class TranscribeRun(BaseHandler):
    @js
    @is_admin
    def post(self):
        try:
            data = json.loads(self.request.body.decode("utf-8"))
        except ValueError:
            return {"err": "params", "msg": "请求体不是合法 JSON"}
        if not transcribe.whisper_available():
            return {"err": "params", "msg": "服务器未安装 whisper，功能不可用"}
        raw = data.get("paths") or []
        raw = [str(p) for p in raw if p]
        if not raw:
            return {"err": "params", "msg": "paths 不能为空"}
        # 目录浏览器传来的是相对 /data 的路径 —— 统一解析成真实路径；
        # 绝对路径原样保留（允许 /data 之外的路径，交给 collect 按不存在处理）。
        from webserver.handlers.scan import resolve_server_path
        resolved = []
        for p in raw:
            if os.path.isabs(p) and os.path.exists(p):
                resolved.append(p)
                continue
            target = resolve_server_path(p)
            resolved.append(target if target is not None else p)
        # 支持目录：递归展开成音频文件
        paths, skipped = transcribe.collect_audio_files(resolved)
        if not paths:
            return {"err": "params",
                    "msg": "没有可转写的音频文件（支持 mp3/m4a/m4b/wav/flac/ogg/aac/wma）",
                    "skipped": skipped}
        with _job.lock:
            if _job.state.get("running"):
                return {"err": "busy", "msg": "已有转写任务在跑"}
            _job.state = {"running": True, "done": 0, "failed": 0,
                          "total": len(paths), "progress": 0,
                          "note": "提交", "error": ""}
            _job.stop_event = threading.Event()
            task = BackgroundService().add_task(
                service_type=SERVICE_TYPE, service_item="音频转写文稿")
            _job.task_id = task.id if hasattr(task, "id") else task
        # keep_txt 优先用请求里的值（前端面板上的开关），没传则回落到保存的设置
        keep_txt = data.get("keep_txt")
        if not isinstance(keep_txt, bool):
            keep_txt = bool(CONF.get("TRANSCRIBE_KEEP_TXT", True))
        t = threading.Thread(target=_run_job,
                             args=(paths,
                                   data.get("model") or CONF.get("TRANSCRIBE_MODEL", "small"),
                                   data.get("lang") or CONF.get("TRANSCRIBE_LANG", "auto"),
                                   keep_txt),
                             name="transcribe-job", daemon=True)
        t.start()
        return {"err": "ok", "task_id": _job.task_id,
                "files": len(paths), "skipped": skipped}


class TranscribeStatus(BaseHandler):
    @js
    @is_admin
    def get(self):
        with _job.lock:
            return {"err": "ok", "state": dict(_job.state)}


class TranscribeCancel(BaseHandler):
    @js
    @is_admin
    def post(self):
        _job.stop_event.set()
        return {"err": "ok", "msg": "已请求取消：当前音频转完就停"}


def routes():
    return [
        (r"/api/admin/transcribe/available", TranscribeAvailable),
        (r"/api/admin/transcribe/run", TranscribeRun),
        (r"/api/admin/transcribe/status", TranscribeStatus),
        (r"/api/admin/transcribe/cancel", TranscribeCancel),
    ]
