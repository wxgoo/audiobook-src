#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""读者组管理 API（管理员专用）。

移植自 audiobook 的「按年级分组限读」：管理员定义若干读者组
（白名单/黑名单 + 分类/标签），把用户划入组即可批量限制可读书目，
不用逐个用户设置。生效逻辑见 services/reader_group.py。
"""

import asyncio
import json
import logging

from webserver import loader
from webserver.handlers.base import BaseHandler, is_admin, js
from webserver.services.reader_group import ReaderGroupService, get_presets

CONF = loader.get_settings()

# 这两个接口是「打开页面就要出数据」的入口，任何一步卡住都会让整页空白。
# 给每步一个上限：超过就返回已有部分 + 明确错误，绝不让浏览器无限转圈。
# 注意超时只是止损，真正的根因是同步 IO 不许待在 ioloop 线程上（见下）。
_LIST_TIMEOUT = 8.0
_OPTIONS_TIMEOUT = 8.0


def _usernames(session):
    """候选用户名（跑在工作线程里，用调用方给的 session）。"""
    from webserver.models import Reader
    return [r.username for r in session.query(
        Reader.username).order_by(Reader.username).all()]


async def _with_deadline(coro, timeout):
    """最多等 timeout 秒，返回 (是否完成, 结果)。

    超时时**不取消**底层任务：run_sqlite_async 的收尾（关 session / remove()
    线程本地 session）必须留在工作线程里，取消它会让工作线程继续使用已被
    主线程关掉的 session。让它自然跑完，结果丢弃即可。
    """
    task = asyncio.ensure_future(coro)
    done, _pending = await asyncio.wait({task}, timeout=timeout)
    if task in done:
        return True, task.result()
    # 取一下异常，避免 "Task exception was never retrieved"
    task.add_done_callback(lambda t: None if t.cancelled() else t.exception())
    return False, None


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
        return await self._load_options()

    async def _load_options(self):
        # §为什么全部丢线程池§
        # 这三份候选值原来都在 ioloop 线程上取：user 查询是同步 SQLite 读，
        # #category 还要先碰 calibre 的 field_metadata（冷启动要建缓存）。
        # 只要其中一步卡住（数据库写锁、calibre 预热持锁），唯一的 ioloop 线程
        # 就被占住，同页面上后发的 /reader_groups、/presets 也一起排队 ——
        # 表现就是「下拉全空 + 列表一直转圈」。现在每一步都在工作线程里跑，
        # 并各自限时，失败只降低对应那一项，不再拖垮整页。
        categories, tags, usernames = [], [], []
        degraded = []

        try:
            ok, value = await _with_deadline(
                self.run_sqlite_async(_usernames), _OPTIONS_TIMEOUT)
            if not ok:
                raise RuntimeError("timeout")
            usernames = value
        except Exception as e:
            degraded.append("usernames")
            logging.warning("[reader-group] load usernames failed: %s", e)
        try:
            ok, value = await _with_deadline(
                self.run_calibre_async(self._category_options), _OPTIONS_TIMEOUT)
            if not ok:
                raise RuntimeError("timeout")
            categories = value
        except Exception as e:
            degraded.append("categories")
            logging.warning("[reader-group] load categories failed: %s", e)
        try:
            ok, items = await _with_deadline(
                self.get_category_with_count_async("tag"), _OPTIONS_TIMEOUT)
            if not ok:
                raise RuntimeError("timeout")
            tags = sorted({it["name"] for it in (items or []) if it.get("name")})
        except Exception as e:
            degraded.append("tags")
            logging.warning("[reader-group] load tags failed: %s", e)
        return {"err": "ok", "categories": categories, "tags": tags,
                "usernames": usernames, "degraded": degraded}

    def _category_options(self):
        """#category 的真实取值（工作在 calibre 线程池里）。

        复用 base.py 里已有的非阻塞封装约定：run_calibre_async(locked=True)
        已经持有 db_lock，这里不能再 with self.db_lock（RLock 同线程可重入，
        但显式再取一次只会误导后来人）。

        §只列「真的有书在用」的值§
        custom_column_<colnum> 是 calibre 的**值字典**，不是「当前分类集合」。
        一本书从某分类下移走之后，字典里的那条记录仍然留着（calibre 不清理），
        于是 SELECT DISTINCT value 会把孤儿值一起吐出来 —— 用户实测看到
        「哈利波特中文版」「台版」这种明显不是分类的条目混在分类下拉里。
        危害不只是碍眼：书籍侧的判定是 `book_category in limit_categories`，
        而 book_category 来自 books_custom_column_<n>_link 关联的实际值。
        管理员若把孤儿值当分类选进白名单，那本书根本不存在 → 该组看不到任何书，
        界面上还完全看不出原因。所以必须 JOIN link 表，与书籍侧口径保持一致。
        """
        from webserver.constants import CALIBRE_COLUMN_CATEGORY

        meta = self.calibre_db.field_metadata
        if CALIBRE_COLUMN_CATEGORY not in meta:
            return []
        colnum = int(meta[CALIBRE_COLUMN_CATEGORY]["colnum"])
        sql = (
            "SELECT DISTINCT d.value FROM custom_column_%d d "
            "JOIN books_custom_column_%d_link l ON l.value = d.id "
            "WHERE d.value IS NOT NULL AND d.value != '' "
            "ORDER BY d.value" % (colnum, colnum)
        )
        rows = self.calibre_db_cache.backend.conn.get(sql) or []
        return [r[0] for r in rows]


def _collect_groups(session) -> tuple:
    """组定义 + 成员名单 + 悬空引用，一次查完。返回 (groups, orphans)。

    session 由调用方提供：写路径（POST）在请求线程用 handler 的 session，
    读路径（GET）由 run_sqlite_async 在工作线程里新建，避免全表扫描占住 ioloop。
    """
    members = ReaderGroupService.members_of(session)
    # 复用同一份 members：orphan_groups 内部再查一次等于把 Reader 全表扫两遍。
    orphan = ReaderGroupService.orphan_groups(session, members=members)
    groups = ReaderGroupService.list_groups()
    for name, cfg in groups.items():
        cfg["members"] = members.get(name, [])
    if orphan:
        logging.warning("[reader-group] orphan group refs: %s",
                        {k: len(v) for k, v in orphan.items()})
    return groups, orphan


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
        return _collect_groups(session)
    finally:
        session.close()


class ReaderGroupList(BaseHandler):
    @js
    @is_admin
    async def get(self):
        return await self._load_groups()

    async def _load_groups(self):
        # 原来是同步 def get：Tornado 把它放在 ioloop 线程上跑，Reader 全表
        # 扫描一旦遇上数据库写锁（busy_timeout=60s）就把整个进程冻住 ——
        # 同一页面里后发的 /options、/presets 全排队，界面表现为「下拉全空、
        # 列表一直转圈」。现在扫描进工作线程，并加一道上限。
        try:
            ok, value = await _with_deadline(
                self.run_sqlite_async(_collect_groups), _LIST_TIMEOUT)
            if not ok:
                logging.warning("[reader-group] list groups timeout (%.1fs)", _LIST_TIMEOUT)
                return {"err": "timeout",
                        "msg": "读取读者组超时（数据库繁忙），请稍后重试"}
            groups, orphan = value
        except Exception as e:
            logging.exception("[reader-group] list groups failed: %s", e)
            return {"err": "exception", "msg": str(e)}
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
