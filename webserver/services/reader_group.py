#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""读者组分级权限（移植自 audiobook 的按年级分组思路）。

设计：
  * 组定义存 CONF["READER_GROUPS"]（持久化在管理员设置里，格式见 save_group），
    不需要数据库迁移；
  * 用户归属存 Reader.extra["reader_group"]（JSON 字段，同样零迁移）；
  * 生效规则：用户自己显式设置了 read_limit/limit_categories/limit_tags 就用
    自己的；否则回退到所属组的配置。判定复用 BaseHandler.is_book_in_reading_range
    的白名单/黑名单语义。
"""

import logging

from webserver import loader

CONF = loader.get_settings()

GROUPS_KEY = "READER_GROUPS"
MEMBER_KEY = "reader_group"

# 预置模板：管理员在「读者组」页一键载入，避免空白表格无从下手。
#
# 注意两类字段的语义完全不同，别混：
#   tags       —— 匹配 `tags` 表里的标签名，也是这里的主战场；
#   categories —— 匹配 #category 自定义列的值（书入库时的分类路径），
#                 与 settings.BOOK_NAV 的分类导航是两套东西，BOOK_NAV 只负责
#                 前端把标签分组显示，并不参与权限判断。
#
# 所以模板一律以 tags 为载体：BOOK_NAV 里那些标签名是真实会出现在书上的，
# 而 #category 列在多数书库里是空的，拿它做模板会静默失效。
PRESET_GROUPS = [
    {
        "name": "儿童",
        "mode": "whitelist",
        "categories": "",
        "tags": ("绘本,少儿,童书,儿童,儿童文学,童话,小学书单,初中书单,"
                 "高中书单,小学语文阅读推荐,国学,唐诗,宋词,科幻小说,中国科幻,硬科幻"),
        "desc": "白名单：绘本童书、少儿科幻、国学诗词。刻意不含「文学」「小说」大类，避免恐怖悬疑混入。",
    },
    {
        "name": "访客",
        "mode": "whitelist",
        "categories": "",
        "tags": ("小说,文学,外国文学,中国文学,散文,诗歌,随笔,经典,名著,世界名著,"
                 "历史,中国历史,世界史,历史学,历史人物,历史文化,"
                 "哲学,社会学,文化,艺术,传记,回忆录,人物传记,纪实,非虚构,"
                 "科普,科学,自然科学,人工智能,计算机,数学,物理,天文"),
        "desc": "白名单：人文与科普为主，屏蔽经济金融、心理励志、医学养生等私密向内容。",
    },
    {
        "name": "成人家属",
        "mode": "whitelist",
        "categories": "",
        "tags": "",
        "desc": "不限：留空即不限权，等于全库可读。用于家庭成员账号。",
    },
    {
        "name": "会员",
        "mode": "blacklist",
        "categories": "",
        "tags": ("心理学,心理,励志,女性,自我管理,治愈,成长,个人成长,职场,沟通,成功,"
                 "人生,个人修养与自我完善,治愈系,社会以与交往,生活,个人管理,旅行,健康,"
                 "自我成长,自我提升,成功心理学,时间管理,职业规划,女性主义,情感,心灵,"
                 "灵修,社会心理学,个人提升,心理學,认知心理学,进化心理学,心灵成长,"
                 "思维方式,鸡汤,认识精进,疗愈,人生哲学,心理自助,人际关系,自我发现,职业,"
                 "身心灵,医学,中医,饮食,健身,养生,神经科学,医疗史,营养学,减肥,食物,"
                 "癌症,生命"),
        "desc": "黑名单：全库可读，仅屏蔽心理励志与医学养生相关标签。适合对外订阅用户。",
    },
]


def get_presets() -> list:
    """返回预置模板列表（深拷贝，调用方随便改都不会污染常量）"""
    return [
        {
            "name": p["name"],
            "mode": p["mode"],
            "categories": p["categories"],
            "tags": p["tags"],
            "desc": p["desc"],
        }
        for p in PRESET_GROUPS
    ]


def _normalize_tags(value) -> str:
    """把列表/字符串统一成逗号分隔、去空白去重复的标签串"""
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, (list, tuple)):
        parts = [str(v) for v in value]
    else:
        parts = []
    seen, out = set(), []
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return ",".join(out)


def _groups() -> dict:
    raw = CONF.get(GROUPS_KEY) or {}
    return raw if isinstance(raw, dict) else {}


def _persist(groups: dict):
    """把组定义落盘（写进 auto.py 的设置持久化机制）。失败只告警：
    内存里的 CONF 仍然生效，重启后丢的只是这次修改。"""
    try:
        from webserver.base.setting_saver import SettingsSaver
        SettingsSaver().save_partial({GROUPS_KEY: groups})
    except Exception as e:  # pragma: no cover
        logging.warning("[reader-group] persist failed: %s", e)


class ReaderGroupService:
    """读者组的增删查与成员分配。所有方法都是静态的，与 mybooks 其他 service 一致。"""

    # ---------- 组定义 ----------

    @staticmethod
    def list_groups() -> dict:
        """返回 {组名: {mode, categories, tags, members}}"""
        groups = {}
        for name, cfg in _groups().items():
            if not isinstance(cfg, dict):
                continue
            groups[name] = {
                "mode": cfg.get("mode", "whitelist"),
                "categories": cfg.get("categories", ""),
                "tags": cfg.get("tags", ""),
            }
        return groups

    @staticmethod
    def save_group(name: str, mode: str = "whitelist",
                   categories="", tags="", old_name: str = "",
                   session=None) -> tuple:
        """创建/更新组。mode: whitelist（只可读匹配项）/ blacklist（禁读匹配项）。

        old_name 非空且与 name 不同时视为「改名」：删除旧组定义，并把原组成员
        的归属引用迁移到新组名（否则成员还挂在旧名上，看起来像被清空了）。
        """
        name = (name or "").strip()
        if not name:
            return False, "组名不能为空"
        if mode not in ("whitelist", "blacklist"):
            return False, "mode 必须是 whitelist 或 blacklist"
        groups = dict(_groups())
        groups[name] = {
            "mode": mode,
            "categories": _normalize_tags(categories),
            "tags": _normalize_tags(tags),
        }
        old_name = (old_name or "").strip()
        renamed = bool(old_name) and old_name != name and old_name in groups
        if renamed:
            groups.pop(old_name)
        CONF[GROUPS_KEY] = groups
        _persist(groups)
        if renamed:
            moved = ReaderGroupService._rename_members(old_name, name, session)
            logging.info("[reader-group] renamed group %r -> %r, moved %d members",
                         old_name, name, moved)
        else:
            logging.info("[reader-group] saved group %r (%s)", name, mode)
        return True, "ok"

    @staticmethod
    def _rename_members(old_name: str, new_name: str, session=None) -> int:
        """改名时同步迁移成员归属。session 由调用方提供；没有 session 就跳过。"""
        if session is None:
            return 0
        try:
            from webserver.models import Reader
            n = 0
            for r in session.query(Reader).all():
                if (r.extra or {}).get(MEMBER_KEY) == old_name:
                    extra = dict(r.extra or {})
                    extra[MEMBER_KEY] = new_name
                    r.extra = extra
                    n += 1
            session.commit()
            return n
        except Exception as e:  # pragma: no cover
            logging.warning("[reader-group] rename members failed: %s", e)
            return 0

    @staticmethod
    def delete_group(name: str, session=None) -> tuple:
        name = (name or "").strip()
        groups = dict(_groups())
        if name not in groups:
            return False, "没有这个组"
        groups.pop(name)
        CONF[GROUPS_KEY] = groups
        _persist(groups)
        # 组删掉了，把成员的归属引用一并清掉，避免悬挂
        removed = ReaderGroupService._clear_members(name, session)
        logging.info("[reader-group] deleted group %r, cleared %d members",
                     name, removed)
        return True, "ok"

    # ---------- 成员 ----------

    @staticmethod
    def members_of(session) -> list:
        """列出所有组员。需要调用方提供 SQLAlchemy session
        （handler 里有 settings["ScopedSession"]），service 不直接碰 DB。"""
        from webserver.models import Reader
        try:
            rows = session.query(Reader).all()
        except Exception as e:  # pragma: no cover - DB 不可用
            logging.warning("[reader-group] members_of failed: %s", e)
            return []
        out = {}
        for r in rows:
            g = (r.extra or {}).get(MEMBER_KEY, "")
            if g:
                out.setdefault(g, []).append(r.username)
        return out

    @staticmethod
    def assign(reader, group_name: str) -> bool:
        """把 Reader 实体划入组（group_name 为空串表示退出组）"""
        group_name = (group_name or "").strip()
        if group_name and group_name not in _groups():
            return False
        extra = dict(reader.extra or {})
        if group_name:
            extra[MEMBER_KEY] = group_name
        else:
            extra.pop(MEMBER_KEY, None)
        reader.extra = extra
        return True

    @staticmethod
    def group_of(reader) -> str:
        return str((reader.extra or {}).get(MEMBER_KEY, "") or "")

    # ---------- 生效规则 ----------

    @staticmethod
    def effective_limits(reader) -> dict:
        """用户的生效限制：自身显式设置优先，否则用组的配置。

        返回 {"read_limit": 0/1/2, "limit_categories": str, "limit_tags": str}
        """
        own_limit = int(getattr(reader, "read_limit", 0) or 0)
        own_cats = (reader.limit_categories or "").strip()
        own_tags = (reader.limit_tags or "").strip()
        if own_limit > 0 or own_cats or own_tags:
            return {"read_limit": own_limit,
                    "limit_categories": own_cats,
                    "limit_tags": own_tags}
        name = ReaderGroupService.group_of(reader)
        cfg = _groups().get(name)
        if not cfg:
            return {"read_limit": 0, "limit_categories": "", "limit_tags": ""}
        mode = cfg.get("mode", "whitelist")
        cats = (cfg.get("categories", "") or "").strip()
        tags = (cfg.get("tags", "") or "").strip()
        # 空规则不等于「什么都不让读」：白名单里一个条件都没填时，
        # 说明这个组就是用来「不限权」的（例如「成人家属」模板），
        # 必须当作 read_limit=0 放行。否则空条件会被展开成空集合，
        # 结果是屏蔽全库 —— 这正是最容易被误认为「系统坏了」的形态。
        if mode == "whitelist" and not cats and not tags:
            return {"read_limit": 0, "limit_categories": "", "limit_tags": ""}
        return {
            "read_limit": 1 if mode == "whitelist" else 2,
            "limit_categories": cats,
            "limit_tags": tags,
        }

    @staticmethod
    def _clear_members(name: str, session=None) -> int:
        """删组时清掉成员引用。session 由调用方提供；没有 session 就跳过。"""
        if session is None:
            return 0
        try:
            from webserver.models import Reader
            n = 0
            for r in session.query(Reader).all():
                if (r.extra or {}).get(MEMBER_KEY) == name:
                    extra = dict(r.extra or {})
                    extra.pop(MEMBER_KEY, None)
                    r.extra = extra
                    n += 1
            session.commit()
            return n
        except Exception as e:  # pragma: no cover
            logging.warning("[reader-group] clear members failed: %s", e)
            return 0
