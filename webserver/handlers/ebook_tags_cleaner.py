# -*- coding: UTF-8 -*-
"""电子书标签清理 API（管理员专用）。

内置化自外部工具 PoxenStudio/tool_tags_cleaner v0.2.0，业务逻辑在
services/ebook_tags_cleaner.py（EbookTagsCleaner）。规则/上限/状态只读，
start 才会写书库元数据；权限与宿主其它管理类工具一致（@is_admin）。
"""

import json

from webserver.i18n import _
from webserver.handlers.base import BaseHandler, is_admin, js
from webserver.services.ebook_tags_cleaner import EbookTagsCleaner


class EbookTagsCleanerRules(BaseHandler):
    """清理规则清单（与 meta.RULES 一致，前端规则面板直接渲染）。"""

    @js
    @is_admin
    def get(self):
        return {"err": "ok", "data": EbookTagsCleaner().get_rules()}


class EbookTagsCleanerLimits(BaseHandler):
    """书库规模与稀少标签上限（小书库保护：不足 100 本时上限强制为 1）。"""

    @js
    @is_admin
    def get(self):
        return {"err": "ok", "data": EbookTagsCleaner().get_limits()}


class EbookTagsCleanerStatus(BaseHandler):
    """当前/最近一次清理任务状态（status.json 权威状态）。"""

    @js
    @is_admin
    def get(self):
        return {"err": "ok", "data": EbookTagsCleaner().get_status()}


class EbookTagsCleanerStart(BaseHandler):
    """启动清理任务；已有任务在跑时直接返回其状态，不重复启动。"""

    @js
    @is_admin
    def post(self):
        try:
            body = json.loads(self.request.body or b"{}")
            if not isinstance(body, dict):
                raise ValueError("request body must be an object")
        except (TypeError, ValueError):
            return {"err": "params.invalid", "msg": _("请求体不是合法 JSON")}
        return {
            "err": "ok",
            "data": EbookTagsCleaner().start(body.get("rare_tag_count", 0)),
        }


class EbookTagsCleanerCancel(BaseHandler):
    """请求取消当前运行中的清理任务（协作式：下一个检查点生效）。"""

    @js
    @is_admin
    def post(self):
        try:
            data = EbookTagsCleaner().cancel()
        except RuntimeError as err:
            return {"err": "cancel.invalid", "msg": str(err)}
        return {"err": "ok", "data": data}


def routes():
    return [
        (r"/api/toolbox/ebook_tags_cleaner/rules", EbookTagsCleanerRules),
        (r"/api/toolbox/ebook_tags_cleaner/limits", EbookTagsCleanerLimits),
        (r"/api/toolbox/ebook_tags_cleaner/status", EbookTagsCleanerStatus),
        (r"/api/toolbox/ebook_tags_cleaner/start", EbookTagsCleanerStart),
        (r"/api/toolbox/ebook_tags_cleaner/cancel", EbookTagsCleanerCancel),
    ]
