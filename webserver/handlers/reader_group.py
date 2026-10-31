#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""读者组管理 API（管理员专用）。

移植自 audiobook 的「按年级分组限读」：管理员定义若干读者组
（白名单/黑名单 + 分类/标签），把用户划入组即可批量限制可读书目，
不用逐个用户设置。生效逻辑见 services/reader_group.py。
"""

import json
import logging

from webserver import loader
from webserver.handlers.base import BaseHandler, is_admin, js
from webserver.services.reader_group import ReaderGroupService, get_presets

CONF = loader.get_settings()


class ReaderGroupPresets(BaseHandler):
    """预置模板列表。管理员点「从模板创建」时前端拿这份数据填表。

    模板里的 categories 用的是 BOOK_NAV 的分类名（如「教育」「文学」），
    不是标签名 —— 后端会按分类名展开成标签集合。所以即便书库还没入库、
    tags 表是空的，模板依然可用，不会出现「填了等于没填」的空转。
    """

    @js
    @is_admin
    async def get(self):
        return {"err": "ok", "presets": get_presets()}


class ReaderGroupOptions(BaseHandler):
    """读者组编辑器的候选值：系统里实际存在的分类与标签。

    以前前端是纯文本框，管理员得凭记忆手打分类/标签名，打错一个字符就静默失效
    （白名单变成看不到任何书、黑名单变成什么都没屏蔽）。这里把库里真实存在的值
    吐出来给 v-combobox 用，同时仍允许自由输入（兼容还没入库的未来值）。
    """

    @js
    @is_admin
    async def get(self):
        categories, tags = [], []
        # 用户名候选：给「批量分配用户到组」的下拉多选框用，
        # 管理员不用再凭记忆手打用户名（打错只会静默 missing）。
        usernames = []
        try:
            from webserver.models import Reader
            ScopedSession = self.settings["ScopedSession"]
            session = ScopedSession()
            try:
                usernames = [r.username for r in session.query(
                    Reader.username).order_by(Reader.username).all()]
            finally:
                session.close()
        except Exception as e:
            logging.warning("[reader-group] load usernames failed: %s", e)
        # 分类：calibre 自定义列 #category，值在 custom_column_<colnum> 表里。
        # 复用 base.py 里已有的非阻塞查询封装，避免自己拼 SQL 踩连接池的坑。
        try:
            from webserver.constants import CALIBRE_COLUMN_CATEGORY

            if CALIBRE_COLUMN_CATEGORY in self.calibre_db.field_metadata:
                colnum = self.calibre_db.field_metadata[CALIBRE_COLUMN_CATEGORY]["colnum"]
                sql = ("SELECT DISTINCT value FROM custom_column_%d "
                       "WHERE value IS NOT NULL AND value != '' ORDER BY value"
                       % int(colnum))

                def _query():
                    # 注意：run_calibre_async(locked=True) 内部已经持有 db_lock，
                    # 这里再 with self.db_lock 会自死锁，直接查即可。
                    rows = self.calibre_db_cache.backend.conn.get(sql) or []
                    return [r[0] for r in rows]

                categories = await self.run_calibre_async(_query)
        except Exception as e:
            logging.warning("[reader-group] load categories failed: %s", e)
        # 标签：直接复用已有的分类统计方法（返回 [{id,name,count}]）
        try:
            items = await self.get_category_with_count_async("tag")
            tags = sorted({it["name"] for it in (items or []) if it.get("name")})
        except Exception as e:
            logging.warning("[reader-group] load tags failed: %s", e)
        return {"err": "ok", "categories": categories, "tags": tags,
                "usernames": usernames}


class ReaderGroupList(BaseHandler):
    @js
    @is_admin
    def get(self):
        groups = self._groups_with_members()
        return {"err": "ok", "groups": groups,
                "orphans": getattr(self, "_orphan_groups", {})}

    @js
    @is_admin
    def post(self):
        """创建/更新组：{name, mode, categories, tags, old_name?}

        old_name 非空且 != name 表示改名，后端会迁移原组成员。
        响应必须带 members —— 前端保存后用整个 groups 覆盖本地状态，
        少了 members 表格里的成员列就会全部被置空。"""
        try:
            data = json.loads(self.request.body.decode("utf-8"))
        except ValueError:
            return {"err": "params", "msg": "请求体不是合法 JSON"}
        ScopedSession = self.settings["ScopedSession"]
        session = ScopedSession()
        try:
            ok, msg = ReaderGroupService.save_group(
                data.get("name", ""), data.get("mode", "whitelist"),
                data.get("categories", ""), data.get("tags", ""),
                old_name=data.get("old_name", ""), session=session)
        finally:
            session.close()
        if not ok:
            return {"err": "params", "msg": msg}
        return {"err": "ok", "groups": self._groups_with_members()}

    def _groups_with_members(self) -> dict:
        """组定义 + 成员名单合并返回（GET/POST 共用，保证结构一致）。

        必须是实例方法：ScopedSession 在 self.settings 里，
        全局 loader.get_settings() 拿不到它（会 KeyError）。
        """
        ScopedSession = self.settings["ScopedSession"]
        session = ScopedSession()
        try:
            members = ReaderGroupService.members_of(session)
            # 组已不存在但成员还挂着 → 修好数据，别留悬空引用。
            # 不修的话：组被删了成员却仍被判定为「受限且读不到书」，
            # 管理员在界面上看不到这些人，只能靠猜。
            stale = [g for g in members if g not in ReaderGroupService.list_groups()]
            if stale:
                fixed = ReaderGroupService.clear_members_of(stale, session)
                if fixed:
                    logging.warning("[reader-group] dropped %d stale member refs: %s",
                                    fixed, stale)
                for g in stale:
                    members.pop(g, None)
        finally:
            session.close()
        groups = ReaderGroupService.list_groups()
        for name, cfg in groups.items():
            cfg["members"] = members.get(name, [])
        # 悬空引用：成员的 extra 里写着某组名，但该组已不存在（删组/改名/导入
        # 数据没带上设置）。这类用户在权限判定里是「读不到任何书」，
        # 必须显式暴露出来，否则管理员只看到"这个人不在任何组里"，无从发现。
        orphan = {}
        for gname, users in members.items():
            if gname not in groups:
                orphan[gname] = users
        if orphan:
            logging.warning("[reader-group] orphan group refs: %s", orphan)
        self._orphan_groups = orphan
        return groups


class ReaderGroupDelete(BaseHandler):
    @js
    @is_admin
    def post(self):
        try:
            data = json.loads(self.request.body.decode("utf-8"))
        except ValueError:
            return {"err": "params", "msg": "请求体不是合法 JSON"}
        ScopedSession = self.settings["ScopedSession"]
        session = ScopedSession()
        try:
            ok, msg = ReaderGroupService.delete_group(data.get("name", ""), session)
        finally:
            session.close()
        if not ok:
            return {"err": "params", "msg": msg}
        return {"err": "ok"}


class ReaderGroupAssign(BaseHandler):
    @js
    @is_admin
    def post(self):
        """把一批用户划入组：{usernames: [...], group: "" 表示退出组}"""
        try:
            data = json.loads(self.request.body.decode("utf-8"))
        except ValueError:
            return {"err": "params", "msg": "请求体不是合法 JSON"}
        usernames = data.get("usernames") or []
        group = data.get("group", "")
        if not isinstance(usernames, list) or not usernames:
            return {"err": "params", "msg": "usernames 不能为空"}
        from webserver.models import Reader
        ScopedSession = self.settings["ScopedSession"]
        session = ScopedSession()
        n = 0
        try:
            readers = session.query(Reader).filter(
                Reader.username.in_(usernames)).all()
            found = {r.username for r in readers}
            for r in readers:
                if ReaderGroupService.assign(r, group):
                    n += 1
            session.commit()
        finally:
            session.close()
        missing = [u for u in usernames if u not in found]
        return {"err": "ok", "assigned": n, "missing": missing}


class ReaderGroupDebug(BaseHandler):
    """排障用：看某个用户当前真正生效的阅读限制是什么、从哪来的。

    GET /api/admin/reader_groups/debug?username=anni
    返回 effective（生效规则）、own（用户自身设置）、group（所属组定义）、
    global_switch（总开关 ALLOW_READ_RANGE_SETTING）。

    权限失效类问题 90% 是这四种：
      1. 总开关没开         → global_switch=false
      2. 用户根本不在组里    → group="" / source="none"
      3. 白名单一个条件没填  → source="group-strict"（严格模式下应为读不到书）
      4. 用户自身又设了限制  → source="self"（组配置被自身设置覆盖）
    """

    @js
    @is_admin
    def get(self):
        from webserver.constants import ALLOW_READ_RANGE_SETTING
        from webserver.models import Reader
        from webserver import loader
        CONF = loader.get_settings()
        from webserver.services.reader_group import (
            ReaderGroupService, _groups, strict_mode)

        username = (self.get_argument("username", "") or "").strip()
        ScopedSession = self.settings["ScopedSession"]
        session = ScopedSession()
        try:
            q = session.query(Reader)
            if username:
                q = q.filter(Reader.username == username)
            readers = q.all()
            out = []
            for r in readers:
                group = ReaderGroupService.group_of(r)
                out.append({
                    "username": r.username,
                    "own": {
                        "read_limit": int(r.read_limit or 0),
                        "limit_categories": r.limit_categories or "",
                        "limit_tags": r.limit_tags or "",
                    },
                    "group": group,
                    "group_def": _groups().get(group),
                    "effective": ReaderGroupService.effective_limits(r),
                    "global_switch": bool(CONF.get(ALLOW_READ_RANGE_SETTING, False)),
                    "strict": strict_mode(),
                })
        finally:
            session.close()
        return {"err": "ok", "readers": out}


def routes():
    return [
        (r"/api/admin/reader_groups", ReaderGroupList),
        (r"/api/admin/reader_groups/options", ReaderGroupOptions),
        (r"/api/admin/reader_groups/presets", ReaderGroupPresets),
        (r"/api/admin/reader_groups/delete", ReaderGroupDelete),
        (r"/api/admin/reader_groups/assign", ReaderGroupAssign),
        (r"/api/admin/reader_groups/debug", ReaderGroupDebug),
    ]
