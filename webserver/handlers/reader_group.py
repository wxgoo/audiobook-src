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

    每条带 group 字段（家庭与账号 / 兴趣主题），前端按它分栏渲染，
    顺序取后端返回的先后。模板以 tags 为载体、categories 一律留空：
    #category 自定义列在多数书库是空的，拿它做模板会静默失效。
    标签名照通用书库写，换库后很可能大半对不上 —— 前端会比对
    /reader_groups/options 的真实标签做提示，并支持一键剔除未命中项。
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
        #
        # §只列「真的有书在用」的值§
        # custom_column_<colnum> 是 calibre 的**值字典**，不是「当前分类集合」。
        # 一本书从某分类下移走之后，字典里的那条记录仍然留着（calibre 不清理），
        # 于是 SELECT DISTINCT value 会把孤儿值一起吐出来——用户实测看到
        # 「哈利波特中文版」「台版」这种明显不是分类的条目混在分类下拉里。
        #
        # 危害不只是碍眼：书籍侧的判定是 `book_category in limit_categories`，
        # 而 book_category 来自 books_custom_column_<n>_link 关联的实际值。
        # 管理员若把孤儿值当分类选进白名单，那本书根本不存在 → 该组看不到任何书，
        # 而且界面上完全看不出原因（选项明明是从「系统里真实存在的分类」来的）。
        #
        # 所以必须 JOIN link 表，只保留至少被一本书引用的值，与书籍侧口径一致。
        try:
            from webserver.constants import CALIBRE_COLUMN_CATEGORY

            if CALIBRE_COLUMN_CATEGORY in self.calibre_db.field_metadata:
                colnum = int(self.calibre_db.field_metadata[CALIBRE_COLUMN_CATEGORY]["colnum"])
                sql = (
                    "SELECT DISTINCT d.value FROM custom_column_%d d "
                    "JOIN books_custom_column_%d_link l ON l.value = d.id "
                    "WHERE d.value IS NOT NULL AND d.value != '' "
                    "ORDER BY d.value" % (colnum, colnum)
                )

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


def collect_groups(handler) -> tuple:
    """组定义 + 成员名单 + 悬空引用，一次查完。返回 (groups, orphans)。

    GET / POST / 重建三个接口共用，保证响应结构完全一致（前端拿整份 groups
    覆盖本地状态，少一个字段就会把成员列清空）。

    必须是函数而不是实例方法里的逻辑：ScopedSession 在 handler.settings 里，
    全局 loader.get_settings() 拿不到它（会 KeyError）。

    悬空引用（成员挂着已不存在的组名）**只统计、不清除**：
    旧实现在这里顺手 clear_members_of 把 Reader.extra["reader_group"] 抹了，
    等于在管理员看到提示之前就把唯一能恢复的线索删掉，重建同名组也找不回人。
    留着它不是风险 —— effective_limits 对 group-missing 一律按「读不到书」
    兜底，不会静默放行。
    """
    ScopedSession = handler.settings["ScopedSession"]
    session = ScopedSession()
    try:
        members = ReaderGroupService.members_of(session)
        orphan = ReaderGroupService.orphan_groups(session)
    finally:
        session.close()
    groups = ReaderGroupService.list_groups()
    for name, cfg in groups.items():
        cfg["members"] = members.get(name, [])
    if orphan:
        logging.warning("[reader-group] orphan group refs: %s",
                        {k: len(v) for k, v in orphan.items()})
    return groups, orphan


class ReaderGroupList(BaseHandler):
    @js
    @is_admin
    def get(self):
        groups, orphan = collect_groups(self)
        return {"err": "ok", "groups": groups, "orphans": orphan}

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
        groups, orphan = collect_groups(self)
        return {"err": "ok", "groups": groups, "orphans": orphan}


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


class ReaderGroupRevive(BaseHandler):
    """按悬空组名一键重建空分组。

    场景：组定义丢了（设置被误抹、导入旧配置、手工改了 auto.py），但成员的
    Reader.extra["reader_group"] 还写着组名。以前只能靠管理员手抄组名一个个
    新建，抄错一个字组员就回不来。

    重建出来的组是「白名单 + 空条件」：严格模式下组员仍然读不到书，等管理员
    补规则；这一点必须在界面上说清，否则「点了重建还是看不到书」会被当成 bug。
    """

    @js
    @is_admin
    def post(self):
        try:
            data = json.loads(self.request.body.decode("utf-8") or "{}")
        except ValueError:
            return {"err": "params", "msg": "请求体不是合法 JSON"}
        names = data.get("names")
        if names is not None and not isinstance(names, list):
            return {"err": "params", "msg": "names 必须是数组"}
        ScopedSession = self.settings["ScopedSession"]
        session = ScopedSession()
        try:
            n, revived = ReaderGroupService.revive_groups(names, session)
        finally:
            session.close()
        if not n:
            groups, orphan = collect_groups(self)
            return {"err": "nothing", "msg": "没有需要重建的分组",
                    "revived": [], "groups": groups, "orphans": orphan}
        groups, orphan = collect_groups(self)
        return {"err": "ok", "revived": revived,
                "groups": groups, "orphans": orphan}


def routes():
    return [
        (r"/api/admin/reader_groups", ReaderGroupList),
        (r"/api/admin/reader_groups/options", ReaderGroupOptions),
        (r"/api/admin/reader_groups/presets", ReaderGroupPresets),
        (r"/api/admin/reader_groups/delete", ReaderGroupDelete),
        (r"/api/admin/reader_groups/assign", ReaderGroupAssign),
        (r"/api/admin/reader_groups/revive", ReaderGroupRevive),
        (r"/api/admin/reader_groups/debug", ReaderGroupDebug),
    ]
