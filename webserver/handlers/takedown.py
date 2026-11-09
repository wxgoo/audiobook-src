#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""「版权下架」管理接口（仅管理员）。

路由：
  GET  /api/admin/takedown/list      下架清单 + 当前声明文案
  POST /api/admin/takedown/set       下架（支持 book_id 单本 / book_ids 批量）
  POST /api/admin/takedown/remove    恢复（支持 book_id 单本 / book_ids 批量）

下架只改本站 book_takedowns 表，不动 Calibre 书库、不删文件：
书还在，只是后端不再提供正文，详情页显示版权声明。
"""
import logging

import tornado

from webserver.handlers.base import BaseHandler, js, is_admin
from webserver.i18n import _
from webserver.services import book_takedown as bt

MAX_BATCH = 200


def _parse_ids(data):
    raw = []
    if data.get("book_id") not in (None, ""):
        raw.append(data["book_id"])
    ids = data.get("book_ids")
    if isinstance(ids, (list, tuple)):
        raw.extend(ids)
    out = []
    for x in raw:
        try:
            n = int(x)
        except (TypeError, ValueError):
            continue
        if n > 0 and n not in out:
            out.append(n)
    return out[:MAX_BATCH]


class _JsonMixin:
    def _body(self):
        try:
            data = tornado.escape.json_decode(self.request.body or b"{}")
        except ValueError:
            return None
        return data if isinstance(data, dict) else None


class AdminTakedownList(BaseHandler):
    @js
    @is_admin
    def get(self):
        items = bt.list_takedowns()
        return {"err": "ok", "total": len(items), "items": items,
                "notice": bt.notice(), "default_notice": bt.DEFAULT_NOTICE}


class AdminTakedownSet(BaseHandler, _JsonMixin):
    @js
    @is_admin
    def post(self):
        data = self._body()
        if data is None:
            return {"err": "params.invalid", "msg": _("请求体不是合法的 JSON")}
        ids = _parse_ids(data)
        if not ids:
            return {"err": "params.missing", "msg": _("缺少 book_id")}
        reason = str(data.get("reason") or "").strip()[:2000]
        operator = ""
        try:
            if self.current_user:
                operator = self.current_user.username or self.current_user.name or ""
        except Exception:
            pass
        saved, skipped = [], []
        for bid in ids:
            book = self.get_book(bid, raise_exception=False)
            if not book:
                skipped.append(bid)
                continue
            title = str(book.get("title") or "")[:1000]
            bt.set_takedown(bid, title=title, reason=reason,
                            operator=str(operator or "")[:200],
                            operator_id=self.user_id() or 0)
            saved.append(bid)
        logging.warning("[COPYRIGHT] admin %s 下架书目 %s，原因=%s",
                        self.user_id(), saved, reason or "(未填写)")
        if not saved:
            return {"err": "params.book.invalid", "msg": _("书籍不存在，未执行下架")}
        return {"err": "ok", "book_ids": saved, "skipped": skipped,
                "items": bt.list_takedowns(), "notice": bt.notice(),
                "msg": _("已下架 %d 本，阅读与下载已停止提供") % len(saved)}


class AdminTakedownRemove(BaseHandler, _JsonMixin):
    @js
    @is_admin
    def post(self):
        data = self._body()
        if data is None:
            return {"err": "params.invalid", "msg": _("请求体不是合法的 JSON")}
        ids = _parse_ids(data)
        if not ids:
            return {"err": "params.missing", "msg": _("缺少 book_id")}
        for bid in ids:
            bt.clear_takedown(bid)
        logging.warning("[COPYRIGHT] admin %s 恢复书目 %s", self.user_id(), ids)
        return {"err": "ok", "book_ids": ids, "items": bt.list_takedowns(),
                "msg": _("已恢复 %d 本，阅读与下载重新开放") % len(ids)}


def routes():
    return [
        (r"/api/admin/takedown/list", AdminTakedownList),
        (r"/api/admin/takedown/set", AdminTakedownSet),
        (r"/api/admin/takedown/remove", AdminTakedownRemove),
    ]
