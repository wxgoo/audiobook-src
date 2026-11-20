# -*- coding: UTF-8 -*-
"""合集自动分册 —— 后端 HTTP 接口（已整合进原「EPUB拆分」工具页）。

历史：曾作为独立工具 epub_auto_split + 自包含 HTML 页发布，因工具卡跳转与
前端静态页不匹配导致 404、且与「EPUB拆分」重复。现改为内部接口模块：
前端 epub_split.vue 的模式切换直接调用下面两个接口，不再有独立工具/独立页。

路由（由 patch_internal.py 在 toolbox.routes() 里展开注册）：
  POST /api/toolbox/epub_split/detect  解析目录 + 自动检测分册
  POST /api/toolbox/epub_split/batch   按确认的分组批量拆分
"""
import logging

import tornado

from webserver.i18n import _
from webserver.handlers.base import BaseHandler, js, is_admin
from webserver.toolbox.epub_auto_split import EpubAutoSplitTool

logger = logging.getLogger(__name__)


class AdminEpubAutoSplitDetect(BaseHandler):
    @js
    @is_admin
    def post(self):
        data = tornado.escape.json_decode(self.request.body)
        book_id = data.get("book_id")
        if not book_id:
            return {"err": "params.missing", "msg": _("请提供书籍ID")}
        try:
            result = EpubAutoSplitTool().detect(int(book_id))
        except RuntimeError as err:
            return {"err": "epub_auto_split.failed", "msg": str(err)}
        except Exception as err:
            logger.exception("[EpubAutoSplit] detect failed")
            return {"err": "epub_auto_split.failed", "msg": "解析失败：%s" % err}
        return {"err": "ok", "data": result}


class AdminEpubAutoSplitBatch(BaseHandler):
    @js
    @is_admin
    def post(self):
        data = tornado.escape.json_decode(self.request.body)
        book_id = data.get("book_id")
        volumes = data.get("volumes")
        use_chapter_cover = bool(data.get("use_chapter_cover", True))
        if not book_id:
            return {"err": "params.missing", "msg": _("请提供书籍ID")}
        if not isinstance(volumes, list) or not volumes:
            return {"err": "params.missing", "msg": _("请至少保留一个分册")}
        # 清洗参数，避免脏数据进入后端
        clean = []
        for v in volumes:
            try:
                clean.append({
                    "name": str(v.get("name") or "未命名分册"),
                    "start": int(v["start"]),
                    "end": int(v["end"]),
                })
            except Exception:
                return {"err": "params.invalid", "msg": _("分册参数无效")}
        try:
            result = EpubAutoSplitTool().batch_split(
                int(book_id), clean, self.user_id(),
                use_chapter_cover=use_chapter_cover,
            )
        except RuntimeError as err:
            return {"err": "epub_auto_split.failed", "msg": str(err)}
        except Exception as err:
            logger.exception("[EpubAutoSplit] batch failed")
            return {"err": "epub_auto_split.failed", "msg": "拆分失败：%s" % err}
        return {"err": "ok", "msg": _("拆分完成"), "data": result}


def routes():
    # 整合进 epub_split 工具页：路径前缀改为 epub_split，不再有独立页路由。
    return [
        (r"/api/toolbox/epub_split/detect", AdminEpubAutoSplitDetect),
        (r"/api/toolbox/epub_split/batch", AdminEpubAutoSplitBatch),
    ]
