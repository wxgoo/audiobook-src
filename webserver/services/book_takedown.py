#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""书籍「版权下架」：被版权人要求下架的书，不再提供阅读与下载。

设计要点
--------
* 书本身不删除、不隐藏：书目信息、封面、统计都保留，详情页正常打开并展示
  版权声明，引导读者购买正版。这在合规上比"整本消失"更清晰。
* 标记存在本站自己的 SQLAlchemy 库 ``book_takedowns`` 表里（见 models.py），
  不动 Calibre 的 metadata.db，不需要 calibre 自定义列，也不用手写 ALTER TABLE；
  表由 ``ensure_new_tables()`` 幂等补建。
* 判定必须发生在 **Python 层设 X-Accel-Redirect 之前**：一旦交给 nginx
  ``/_lib/`` 直出，Python 就没有第二次机会拦截了。因此统一门禁挂在
  ``BaseHandler.prepare()``，覆盖所有内容出口（含下载直链、epub 分片、
  TXT 正文、MyReader 文件路径、邮件推送、OPDS 直链、音频）。
* 旁路（WebDAV WSGI、MCP download_book 的 book_id 在请求体里）单独调用
  ``guard()``；OPDS / WebDAV 目录列表另外剔除下架书。
"""

import html
import logging
import re
import threading
import time

from webserver import loader
from webserver.models import BookTakedown

CONF = loader.get_settings()

DEFAULT_NOTICE = "因版权人要求，已下架处理，请购买正版图书支持原作者！"
NOTICE_CONF_KEY = "COPYRIGHT_TAKEDOWN_NOTICE"
ERR = "book.copyright_takedown"
CACHE_TTL = 60.0

_CACHE = {"ids": set(), "details": {}, "ts": 0.0, "loaded": False}
_LOCK = threading.RLock()


def notice():
    """版权声明文案。运维可在配置里覆盖 CONF["COPYRIGHT_TAKEDOWN_NOTICE"]。"""
    text = (CONF.get(NOTICE_CONF_KEY) or "").strip()
    return text or DEFAULT_NOTICE


def _refresh(force=False):
    now = time.time()
    with _LOCK:
        if _CACHE["loaded"] and not force and now - _CACHE["ts"] < CACHE_TTL:
            return
        try:
            rows = BookTakedown._session().query(BookTakedown).all()
            ids = {int(r.book_id) for r in rows}
            details = {int(r.book_id): r.as_dict() for r in rows}
        except Exception as e:
            # 读失败时**不清空已有缓存**：否则数据库抖动会让下架短暂失效。
            logging.warning("[COPYRIGHT] 读取下架列表失败，沿用已有缓存: %s", e)
            if not _CACHE["loaded"]:
                _CACHE.update(ids=set(), details={}, loaded=True, ts=now)
            return
        _CACHE.update(ids=ids, details=details, loaded=True, ts=now)


def is_takedown(book_id):
    try:
        bid = int(book_id)
    except (TypeError, ValueError):
        return False
    _refresh()
    with _LOCK:
        return bid in _CACHE["ids"]


def takedown_info(book_id):
    try:
        bid = int(book_id)
    except (TypeError, ValueError):
        return None
    _refresh()
    with _LOCK:
        return dict(_CACHE["details"].get(bid) or {}) or None


def takedown_ids():
    _refresh()
    with _LOCK:
        return set(_CACHE["ids"])


def list_takedowns():
    _refresh(force=True)
    with _LOCK:
        rows = [dict(v) for v in _CACHE["details"].values()]
    rows.sort(key=lambda x: x.get("create_time") or "", reverse=True)
    return rows


def set_takedown(book_id, title="", reason="", operator="", operator_id=0):
    import datetime

    bid = int(book_id)
    s = BookTakedown._session()
    try:
        row = s.query(BookTakedown).filter_by(book_id=bid).one_or_none()
        if row is None:
            row = BookTakedown(bid, title=title, reason=reason,
                               operator=operator, operator_id=operator_id)
            s.add(row)
        else:
            row.title = title or ""
            row.reason = reason or ""
            row.operator = operator or ""
            row.operator_id = operator_id or 0
            row.create_time = datetime.datetime.now()
        s.commit()
        data = row.as_dict()
    except Exception:
        s.rollback()
        raise
    with _LOCK:
        _CACHE["ids"].add(bid)
        _CACHE["details"][bid] = data
        _CACHE["loaded"] = True
        _CACHE["ts"] = time.time()
    return data


def clear_takedown(book_id):
    bid = int(book_id)
    s = BookTakedown._session()
    try:
        row = s.query(BookTakedown).filter_by(book_id=bid).one_or_none()
        if row is not None:
            s.delete(row)
            s.commit()
    except Exception:
        s.rollback()
        raise
    with _LOCK:
        _CACHE["ids"].discard(bid)
        _CACHE["details"].pop(bid, None)
        _CACHE["loaded"] = True
        _CACHE["ts"] = time.time()
    return True


# ---------------------------------------------------------------------------
# 内容出口识别
#
# 只匹配"会把正文/原文件交给读者"的路径。刻意**不**匹配：
#   /api/book/<id>            详情页（要显示版权声明）
#   /api/book/<id>/edit|delete|favorite|readstate/...  书目与管理操作
#   /get/cover|thumb|opf      封面与元数据（下架书仍要能展示封面）
#   /api/admin/takedown/*     管理接口本身
#   /book/<id>                Nuxt 前端页面（catch-all，不继承 BaseHandler）
# ---------------------------------------------------------------------------
_CONTENT_PATTERNS = tuple(re.compile(p) for p in (
    r"^/api/book/(\d+)\.[A-Za-z0-9_+\-]+$",          # 下载直链（含 ?from=opds）
    r"^/read/(\d+)$",                                  # 阅读页
    r"^/api/book/(\d+)/read$",                         # 阅读 API
    r"^/get/extract/(\d+)(?:/.*)?$",                   # epub 正文分片
    r"^/api/read/txt/(\d+)$",                          # TXT 正文
    r"^/api/book/(\d+)/filepath$",                     # MyReader 本地文件路径
    r"^/api/book/(\d+)/convert$",                      # 格式转换（读原文件）
    r"^/api/book/(\d+)/topdf$",
    r"^/api/book/(\d+)/mailto$",                       # 邮件推送附件
    r"^/api/book/(\d+)/send_to_device$",               # 推送到设备
    r"^/api/book/(\d+)/addstamp$",
    r"^/api/book/(\d+)/savemeta$",                     # 写回原文件
    r"^/api/audios/(\d+)/collection/download$",
    r"^/podcast/audio/(\d+)/[^/]+/.+$",
    r"^/podcast/book/(\d+)(?:/opml)?$",
))

# AudioFile 的路由是 /api/audio/<book_id>/<filename>，同一前缀下还挂着
# /progress、/conversion、/cancel、/delete、/purchase 等管理/进度接口。
# 只认"带音频扩展名"的第二段，避免把进度上报也当成内容请求拦掉。
_AUDIO_FILE_RE = re.compile(
    r"^/api/audio/(\d+)/[^/]+\.(?:mp3|m4a|m4b|wav|ogg|flac|aac|opus|webm)$",
    re.IGNORECASE,
)

_DOWNLOAD_RE = re.compile(r"^/api/book/\d+\.[A-Za-z0-9_+\-]+$")


def content_book_id(path):
    """从请求路径里提取"内容出口"的 book_id；非内容路径返回 None。"""
    p = (path or "").split("?", 1)[0]
    if not p:
        return None
    if len(p) > 1:
        p = p.rstrip("/") or "/"
    m = _AUDIO_FILE_RE.match(p)
    if m:
        return int(m.group(1))
    for pat in _CONTENT_PATTERNS:
        m = pat.match(p)
        if m:
            return int(m.group(1))
    return None


def _html_page(msg):
    safe = html.escape(msg)
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>版权声明</title><style>'
        'body{margin:0;min-height:100vh;display:flex;align-items:center;'
        'justify-content:center;background:#f5f5f5;color:#263238;'
        'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}'
        '.box{max-width:520px;margin:24px;padding:32px 36px;background:#fff;'
        'border-radius:14px;box-shadow:0 8px 30px rgba(0,0,0,.10);text-align:center}'
        '.ico{font-size:44px;line-height:1;margin-bottom:16px}'
        'h1{font-size:20px;margin:0 0 14px;font-weight:600}'
        'p{font-size:16px;line-height:1.9;margin:0;color:#455a64}'
        '.tip{margin-top:22px;font-size:13px;color:#90a4ae}'
        '</style></head><body><div class="box">'
        '<div class="ico">&#128218;</div><h1>版权声明</h1>'
        '<p>' + safe + '</p>'
        '<div class="tip">本书已停止提供在线阅读与下载</div>'
        '</div></body></html>'
    )


def reject(handler, book_id):
    """统一拒绝响应。按消费者形态分流，避免下载器把 JSON 存成假书。

    * 下载直链 / 正文分片 / 阅读页 / OPDS / WAP → 403 + 自包含 HTML 声明页
      （200 + JSON 会被 aria2/IDM/epub.js 当成资源解析成功）；
    * 其余 /api/* JSON 接口 → 200 + err=book.copyright_takedown，前端 $backend
      能拿到文案并弹出声明。
    """
    from tornado import web

    msg = notice()
    path = getattr(getattr(handler, "request", None), "path", "") or ""
    is_binary = bool(_DOWNLOAD_RE.match(path.rstrip("/")))
    is_resource = is_binary or path.startswith(("/get/", "/read/", "/opds", "/wap", "/podcast/", "/books/"))
    if is_resource:
        handler.set_status(403)
        handler.set_header("Content-Type", "text/html; charset=UTF-8")
        handler.set_header("Cache-Control", "no-store")
        handler.write(_html_page(msg))
    else:
        # $backend 只在 200 时解析 err，见 app/src/plugins/backend.js
        handler.set_status(200)
        handler.write({
            "err": ERR,
            "msg": msg,
            "copyright_notice": msg,
            "book_id": int(book_id),
            "is_takedown": True,
        })
    raise web.Finish()


def guard(handler, book_id):
    """旁路（WebDAV / MCP / 内部调用）用的显式检查，命中即写响应并终止请求。"""
    if is_takedown(book_id):
        reject(handler, book_id)
    return False


def check_path(handler, path=None):
    """BaseHandler.prepare() 的统一门禁入口：内容路径 + 下架书 → 拒绝。"""
    p = path if path is not None else getattr(getattr(handler, "request", None), "path", "")
    bid = content_book_id(p)
    if bid is None or not is_takedown(bid):
        return False
    reject(handler, bid)
    return True
