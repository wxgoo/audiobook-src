#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""中文检索索引的管理接口（管理员专用）。

- GET  /api/admin/search_index/status   查看索引状态（文档数、是否过期、上次构建）
- POST /api/admin/search_index/rebuild  触发后台重建（立即返回，不阻塞请求）

搜索本身仍走原来的 /api 接口（`search=` 参数不变），本模块只负责索引的
可观测性与重建入口。
"""

import logging

from webserver.i18n import _
from webserver.handlers.base import BaseHandler, is_admin, js
from webserver.services.search_index import get_search_index


class SearchIndexStatus(BaseHandler):
    @js
    @is_admin
    def get(self):
        if not self.is_admin():
            return {"err": "permission.not_admin",
                    "msg": _("只有管理员可以查看检索索引状态")}
        return {"err": "ok", "data": get_search_index().status()}


class SearchIndexRebuild(BaseHandler):
    @js
    @is_admin
    def post(self):
        if not self.is_admin():
            return {"err": "permission.not_admin",
                    "msg": _("只有管理员可以重建检索索引")}
        service = get_search_index()
        started = service.request_rebuild(force=True)
        if not started:
            logging.info("[SEARCH_INDEX] rebuild request ignored (disabled or running)")
            return {"err": "ok",
                    "msg": _("索引已禁用或正在重建"),
                    "data": service.status()}
        return {"err": "ok", "msg": _("索引重建已在后台开始"),
                "data": service.status()}


def routes():
    return [
        (r"/api/admin/search_index/status", SearchIndexStatus),
        (r"/api/admin/search_index/rebuild", SearchIndexRebuild),
    ]
