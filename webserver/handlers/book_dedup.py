#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""同名重复书清理 API（管理员专用）。

配合 services/book_dedup.py：先 scan 出方案给页面预览，确认后 apply 执行。
设计上强制「先看后做」——scan 只读，apply 才写，且 apply 前自动备份用户库。

为什么要这个工具：有声书 `audios/<book_id>/` 与电子书 `library/` 分目录存放，
上游导入音频时只判断"有没有音频目录"，没有就新建一本书，于是"先导 epub、
后加同名音频"必然在书库里留下两条记录。v4.8.0 修了导入逻辑，但**已产生的
重复记录不会自愈**（ScanFile 已是 IMPORTED，重扫被跳过），只能一次性迁移。
"""

import json
import logging
import os

from webserver import loader
from webserver.handlers.base import BaseHandler, is_admin, js
from webserver.services.book_dedup import DuplicateBookMerger

CONF = loader.get_settings()


def _build_merger(handler):
    """为当前请求构造 merger。

    DuplicateBookMerger 的方法是同步的（要遍历磁盘、逐行改库），而 calibre 元数据
    读取必须走工作线程 + db_lock。这里用「带缓存的同步 fetcher」桥接：每个不同的
    id 集合只在首次调用时进 db_lock 取一次，同一请求内后续复用缓存。
    """
    from webserver.services.audios_import import AUDIO_OUTPUT_DIR

    db = handler.calibre_db
    cache = {}

    def sync_fetcher(ids):
        key = tuple(sorted(int(i) for i in ids))
        if key not in cache:
            with handler.db_lock:
                cache[key] = db.get_data_as_dict(book_ids=list(key)) or []
        return cache[key]

    backup_dir = str(CONF.get("BOOK_DEDUP_BACKUP_DIR") or "")
    if not backup_dir:
        data_dir = CONF.get("data_path") or "/data/books"
        backup_dir = os.path.join(data_dir, "backup")

    return DuplicateBookMerger(
        db, handler.sqlite_session, AUDIO_OUTPUT_DIR,
        backup_dir=backup_dir, meta_fetcher=sync_fetcher)


class DuplicateBookScan(BaseHandler):
    """扫描同名重复书，返回处置方案（只读，不改数据）。"""

    @js
    @is_admin
    async def get(self):
        merger = _build_merger(self)
        try:
            # calibre 元数据读取在 sync_fetcher 里进 db_lock（calibre_pool 以外
            # 的同步调用），本方法是 async，跑在 ioloop 线程上——扫描只在管理员
            # 手动点按钮时触发，几百到几千本书的元数据读取在百毫秒级，可接受。
            plan = merger.scan()
        except Exception as err:
            logging.error("[DEDUP] 扫描失败: %s", err)
            return {"err": "server.error", "msg": str(err)}
        return {"err": "ok", "plan": plan}


class DuplicateBookApply(BaseHandler):
    """执行合并。请求体：{groups: [{keep_book_id, drop_book_ids}], backup: true}"""

    @js
    @is_admin
    async def post(self):
        try:
            data = json.loads(self.request.body.decode("utf-8"))
        except ValueError:
            return {"err": "params", "msg": "请求体不是合法 JSON"}

        selected = data.get("groups") or []
        if not isinstance(selected, list) or not selected:
            return {"err": "params", "msg": "没有选中任何要合并的重复书"}

        merger = _build_merger(self)
        full_plan = merger.scan()
        if full_plan.get("error"):
            return {"err": "server.error", "msg": full_plan["error"]}

        # 只执行用户勾选的组，且必须以本次扫描的结果为准重建方案
        # （前端回传的只会是 keep/drop id，具体动作由后端重新计算，避免被篡改）
        wanted = set()
        for item in selected:
            keep = item.get("keep_book_id")
            drops = tuple(sorted(int(x) for x in (item.get("drop_book_ids") or [])))
            if keep is not None:
                wanted.add((int(keep), drops))

        groups = []
        for g in full_plan.get("groups") or []:
            if g.get("action") != "merge":
                continue
            sig = (int(g["keep_book_id"]), tuple(sorted(int(x) for x in g["drop_book_ids"])))
            if sig in wanted:
                groups.append(g)

        if not groups:
            return {"err": "not_found", "msg": "选中的重复书已不存在，请重新扫描"}

        do_backup = data.get("backup", True)
        try:
            result = merger.apply({"groups": groups}, do_backup=bool(do_backup))
        except Exception as err:
            logging.error("[DEDUP] 执行合并失败: %s", err)
            return {"err": "server.error", "msg": str(err)}

        merged = len(result.get("merged") or [])
        failed = len(result.get("failed") or [])
        msg = "已合并 %d 组" % merged
        if failed:
            msg += "，%d 组失败（详见日志）" % failed
        return {
            "err": "ok",
            "msg": msg,
            "merged": merged,
            "failed": failed,
            "backup": result.get("backup"),
            "detail": result,
        }


class DuplicateBookPreview(BaseHandler):
    """预览某组合并会动多少条关联数据（只读）。"""

    @js
    @is_admin
    async def get(self):
        try:
            keep = int(self.get_argument("keep_book_id", "0"))
            drops = [int(x) for x in (self.get_argument("drop_book_ids", "") or "").split(",") if x.strip()]
        except ValueError:
            return {"err": "params", "msg": "参数不合法"}
        if not keep or not drops:
            return {"err": "params", "msg": "keep_book_id 与 drop_book_ids 都必须提供"}

        merger = _build_merger(self)
        try:
            detail = merger.preview(keep, drops)
        except Exception as err:
            logging.error("[DEDUP] 预览失败: %s", err)
            return {"err": "server.error", "msg": str(err)}
        return {"err": "ok", "keep_book_id": keep, "detail": detail}


def routes():
    return [
        (r"/api/admin/book_dedup/scan", DuplicateBookScan),
        (r"/api/admin/book_dedup/preview", DuplicateBookPreview),
        (r"/api/admin/book_dedup/apply", DuplicateBookApply),
    ]
