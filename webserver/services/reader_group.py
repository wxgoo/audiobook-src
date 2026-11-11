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

import json
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
# 模板分两类，界面上分栏展示（PRESET_GROUP_* 是栏目标题，改文案只改这三行）：
#   家庭与账号 —— 「这个账号给谁用」，按人的身份挑；
#   兴趣主题   —— 「这个账号读什么」，按内容方向挑。
PRESET_GROUP_FAMILY = "家庭与账号"
PRESET_GROUP_TOPIC = "兴趣主题"

PRESET_GROUPS = [
    # ---------- 家庭与账号 ----------
    {
        "group": PRESET_GROUP_FAMILY,
        "name": "婴幼儿亲子",
        "mode": "whitelist",
        "categories": "",
        "tags": ("绘本,图画书,低幼,亲子,亲子共读,睡前故事,儿歌,童谣,童话,"
                 "认知,启蒙,益智,幼儿,宝宝,儿童文学"),
        "desc": "白名单：绘本、睡前故事、儿歌童谣。给学龄前孩子，或家长陪读时用。",
    },
    {
        "group": PRESET_GROUP_FAMILY,
        "name": "儿童",
        "mode": "whitelist",
        "categories": "",
        "tags": ("绘本,少儿,童书,儿童,儿童文学,童话,小学书单,初中书单,"
                 "高中书单,小学语文阅读推荐,国学,唐诗,宋词,科幻小说,中国科幻,硬科幻"),
        "desc": "白名单：绘本童书、少儿科幻、国学诗词。刻意不含「文学」「小说」大类，避免恐怖悬疑混入。",
    },
    {
        "group": PRESET_GROUP_FAMILY,
        "name": "青少年",
        "mode": "whitelist",
        "categories": "",
        "tags": ("小学书单,初中书单,高中书单,小学语文阅读推荐,国学,唐诗,宋词,"
                 "名著,世界名著,经典,科幻小说,中国科幻,硬科幻,科普,科学,"
                 "自然科学,历史,中国历史,世界史,传记,人物传记"),
        "desc": "白名单：中小学必读、科普、历史与名著。比「儿童」宽、比「访客」窄，适合中学生自己用。",
    },
    {
        "group": PRESET_GROUP_FAMILY,
        "name": "长辈听书",
        "mode": "whitelist",
        "categories": "",
        "tags": ("戏曲,评书,相声,养生,中医,饮食,健康,历史,中国历史,历史文化,"
                 "传记,回忆录,散文,诗词,唐诗,宋词,国学"),
        "desc": "白名单：戏曲评书、养生健康、历史散文。适合只听书/看戏的长辈账号。",
    },
    {
        "group": PRESET_GROUP_FAMILY,
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
        "group": PRESET_GROUP_FAMILY,
        "name": "家庭共用",
        "mode": "blacklist",
        "categories": "",
        # 这里**故意**只写中性词。Gitee raw 有内容审核，代码里出现某些露骨/暴力词组
        # 会被整份文件判 451，在线更新的下载直接失败（r18 就这么废了一版）。
        # 书库里若有更直白的标签，让管理员在「标签」下拉里自己补两条即可。
        "tags": ("成人向,两性,重口,暗黑,猎奇,恐怖,惊悚,灵异,悬疑惊悚"),
        "desc": "黑名单：全库可读，只挡成人向与惊悚恐怖。多人共用一个账号、又懒得逐个配白名单时的折中；库里若有更直白的标签，请从下方标签下拉里补上。",
    },
    {
        "group": PRESET_GROUP_FAMILY,
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
    {
        "group": PRESET_GROUP_FAMILY,
        "name": "成人家属",
        "mode": "open",
        "categories": "",
        "tags": "",
        "desc": "不限：全库可读。给不想被限制的家庭成员账号。必须选「不限」模式——白名单留空在严格模式下等于一本书都看不到。",
    },
    # ---------- 兴趣主题 ----------
    {
        "group": PRESET_GROUP_TOPIC,
        "name": "公版经典",
        "mode": "whitelist",
        "categories": "",
        "tags": ("名著,世界名著,经典,中国文学,外国文学,散文,诗歌,诗词,唐诗,宋词,"
                 "国学,历史,哲学"),
        "desc": "白名单：公版名著与人文经典。适合对外展示的「公开书架」，也是版权风险最低的一套。",
    },
    {
        "group": PRESET_GROUP_TOPIC,
        "name": "人文社科",
        "mode": "whitelist",
        "categories": "",
        "tags": ("哲学,社会学,政治学,法律,法学,人类学,文化,文化研究,宗教,伦理学,"
                 "美学,思想史,学术,历史,历史学,社会,经济学,心理学"),
        "desc": "白名单：哲学、社会学、法律、思想史。给读社科理论的人；也含心理学（要排除请用「会员」那套黑名单）。",
    },
    {
        "group": PRESET_GROUP_TOPIC,
        "name": "经管职场",
        "mode": "whitelist",
        "categories": "",
        "tags": ("经济,经济学,金融,投资,理财,股票,基金,管理,企业管理,商业,"
                 "市场营销,创业,职场,领导力,会计,财务,商业模式,运营,组织管理,"
                 "宏观经济,货币,贸易,产业"),
        "desc": "白名单：经济金融、管理投资、职场成长。适合只看经管的账号。",
    },
    {
        "group": PRESET_GROUP_TOPIC,
        "name": "理工科普",
        "mode": "whitelist",
        "categories": "",
        "tags": ("科普,科学,自然科学,数学,物理,化学,生物,天文,地理,地质,"
                 "宇宙,量子,进化,生命科学,医学,工程,技术,科技,博物"),
        "desc": "白名单：数理化生、天文地理与科普。给爱看科学读物的账号。",
    },
    {
        "group": PRESET_GROUP_TOPIC,
        "name": "技术编程",
        "mode": "whitelist",
        "categories": "",
        "tags": ("计算机,编程,程序设计,算法,数据结构,人工智能,机器学习,深度学习,"
                 "软件工程,数据库,操作系统,计算机网络,网络,Linux,Python,Java,"
                 "前端,后端,架构,运维,安全,云计算,数学"),
        "desc": "白名单：编程语言、算法、AI 与系统工程。给程序员账号，比「理工科普」更偏实践。",
    },
    {
        "group": PRESET_GROUP_TOPIC,
        "name": "历史爱好者",
        "mode": "whitelist",
        "categories": "",
        "tags": ("历史,中国历史,世界史,历史学,历史人物,历史文化,古代史,近代史,"
                 "现代史,断代史,史学理论,考古,军事,军事史,战争,传记,回忆录"),
        "desc": "白名单：中外通史、断代史、人物传记与军事史。",
    },
    {
        "group": PRESET_GROUP_TOPIC,
        "name": "科幻迷",
        "mode": "whitelist",
        "categories": "",
        "tags": ("科幻,科幻小说,中国科幻,外国科幻,硬科幻,软科幻,太空歌剧,"
                 "赛博朋克,时间旅行,末日,星际,科幻奇幻"),
        "desc": "白名单：科幻各子类型。注意「硬科幻」同时出现在「儿童」模板里，两组可以共存。",
    },
    {
        "group": PRESET_GROUP_TOPIC,
        "name": "悬疑推理",
        "mode": "whitelist",
        "categories": "",
        "tags": ("推理,推理小说,悬疑,悬疑小说,侦探,侦探小说,犯罪小说,本格推理,"
                 "社会派,日本推理,欧美推理,间谍,谍战"),
        "desc": "白名单：推理悬疑各流派。刻意不含「惊悚」「恐怖」，要连恐怖一起看就把这两个标签加上。",
    },
    {
        "group": PRESET_GROUP_TOPIC,
        "name": "武侠奇幻",
        "mode": "whitelist",
        "categories": "",
        "tags": ("武侠,武侠小说,仙侠,玄幻,奇幻,修真,网络小说,东方玄幻,"
                 "仙侠修真,江湖,武侠仙侠,轻小说"),
        "desc": "白名单：武侠、仙侠、玄幻与网络文学。",
    },
]


def get_presets() -> list:
    """返回预置模板列表（深拷贝，调用方随便改都不会污染常量）"""
    return [
        {
            "group": p.get("group") or PRESET_GROUP_FAMILY,
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
    # §历史数据兼容§ 这份配置曾通过通用设置表单原样落盘，被写成 JSON 字符串
    # （auto.py 里是带引号的文本）。重启后 isinstance(raw, dict) 为假，所有组
    # 会静默消失——列表显示「暂无分组」、批量分配下拉没有任何组名，而成员
    # 归属其实还在 Reader.extra 里。这里先把字符串解回 dict，再判类型。
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = {}
    return raw if isinstance(raw, dict) else {}


def _persist(groups: dict):
    """把组定义落盘（写进 auto.py 的设置持久化机制）。失败只告警：
    内存里的 CONF 仍然生效，重启后丢的只是这次修改。"""
    try:
        from webserver.base.setting_saver import SettingsSaver
        SettingsSaver().save_partial({GROUPS_KEY: groups})
    except Exception as e:  # pragma: no cover
        logging.warning("[reader-group] persist failed: %s", e)


def strict_mode() -> bool:
    """白名单组「一个条件都没填」时，是否当作「什么都读不到」。

    mybooks 原生的阅读范围语义是：白名单空条件 = 不限权（放行全库）。
    但读者组是管理员手工建的规则，一个只写了组名、没填任何分类/标签的
    「白名单」组，管理员的本意几乎总是「先限制住、再慢慢配」，
    放行全库会让整套权限看起来完全失效（实测踩过）。

    所以读者组自己再加一个开关 READER_GROUP_STRICT（默认 true）：
        严格开：白名单空条件 = 读不到任何书
        严格关：退回原生语义 = 不限权
    只影响「白名单 + 空条件」这一种组合，黑名单不受影响。
    """
    return bool(CONF.get("READER_GROUP_STRICT", True))


def groups_enabled() -> bool:
    """读者组总开关（4.6.0-19 新增）。

    关闭时组规则全链路失效——所有权限判定点都经由 effective_limits() 取组
    配置，在这里单点收口即可，不用逐个改判定点。用户自身的
    read_limit/limit_categories/limit_tags 不受影响（那层由
    ALLOW_READ_RANGE_SETTING 总闸管）。成员归属照常保存，重新打开即恢复。
    """
    return bool(CONF.get("READER_GROUPS_ENABLED", True))


def book_matches_limits(book, eff) -> bool:
    """判定一本书在当前「生效限制」下是否可读——唯一的口径来源。

    书列表（BaseHandler.is_book_in_reading_range）与各类统计
    （左侧树 / 分类页 / 标签云 / 元数据列表的 count）必须调用同一份逻辑，
    否则会出现「树里写着 328 本，点进去只有 12 本」这种口径分裂。
    以前统计侧各写各的 SQL（全库 count(distinct book)），数字天然对不上。

    eff 为 effective_limits() 的返回值，或含同样三个键的 dict。
    """
    read_limit = int(eff.get("read_limit") or 0)
    if read_limit == 0:
        return True
    limit_categories = set(filter(None, (eff.get("limit_categories") or "").split(",")))
    limit_tags = set(filter(None, (eff.get("limit_tags") or "").split(",")))
    # 一个条件都没填：两种名单的语义正好相反，不能一起返回 False。
    #   白名单空 → 什么都匹配不上（严格模式的哨兵条件也走这里）；
    #   黑名单空 → 什么都不屏蔽，等于全库可读。
    if not limit_categories and not limit_tags:
        return read_limit != 1

    from webserver.constants import CALIBRE_COLUMN_CATEGORY

    book_category = book.get(CALIBRE_COLUMN_CATEGORY) or ""
    book_tags = set(book.get("tags") or [])
    # 分类与标签是「或」的关系：只填了一边时，绝不要求另一边也匹配。
    matched = (limit_categories and book_category in limit_categories) or bool(
        limit_tags and book_tags & limit_tags
    )
    return matched if read_limit == 1 else not matched


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
        """创建/更新组。mode: whitelist（只可读匹配项）/ blacklist（禁读匹配项）/
        open（不限，全库可读）。

        old_name 非空且与 name 不同时视为「改名」：删除旧组定义，并把原组成员
        的归属引用迁移到新组名（否则成员还挂在旧名上，看起来像被清空了）。
        """
        name = (name or "").strip()
        if not name:
            return False, "组名不能为空"
        if mode not in ("whitelist", "blacklist", "open"):
            return False, "mode 必须是 whitelist、blacklist 或 open"
        groups = dict(_groups())
        old_name = (old_name or "").strip()
        # 改名撞上已存在的组名：一旦继续，目标组的定义会被覆盖，两组组员还会
        # 混在同一个名字下（成员存的是组名字符串，无法区分来源），必须拒绝。
        if (old_name and old_name != name and old_name in groups
                and name in groups):
            return False, "已存在同名组，请换一个组名，或先删除该组"
        groups[name] = {
            "mode": mode,
            # 「不限」组没有匹配条件可言：存进来只会让语义含糊（写了标签却不生效），
            # 一律清空。想改成限制型，先切模式再填条件。
            "categories": "" if mode == "open" else _normalize_tags(categories),
            "tags": "" if mode == "open" else _normalize_tags(tags),
        }
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

    # ---------- 悬空引用 ----------

    @staticmethod
    def orphan_groups(session, members=None) -> dict:
        """{组名: [用户名]}：成员 extra 里写着某组名，但该组定义已不存在。

        这些人在权限判定里走 effective_limits 的 "group-missing" 分支
        （读不到任何书），组列表里又找不到他们 —— 不显式报出来，管理员只会
        觉得「这人怎么啥都看不见」。

        注意：**只能报告，不能顺手清**。清掉 Reader.extra["reader_group"] 是
        不可逆的；留着它，管理员重建同名组后成员归属立刻回位。
        （旧实现在 GET 列表时直接 clear_members_of，等于把唯一能恢复的线索
        当场删了，重建组也找不回人。）
        """
        if members is None:
            members = ReaderGroupService.members_of(session)
        known = ReaderGroupService.list_groups()
        return {name: users for name, users in members.items() if name not in known}

    @staticmethod
    def revive_groups(names=None, session=None) -> tuple:
        """按悬空组名重建空分组（白名单、无条件），返回 (重建数, 组名列表)。

        成员归属存的是组名字符串，从来没丢过；组定义一回来，这些人自动归位，
        管理员只需要补填白名单条件。新建的组是「白名单 + 没有条件」，严格模式
        下等于读不到书 —— 这是有意的：宁可先挡住，也不能在管理员还没来得及
        配规则时静默放行全库。

        names 为空表示「重建全部悬空组」；传了名字但已不是悬空状态的会忽略。
        """
        if session is None:
            return 0, []
        orphan = ReaderGroupService.orphan_groups(session)
        wanted = [str(n or "").strip() for n in (names or [])]
        wanted = [n for n in wanted if n]
        targets = [n for n in wanted if n in orphan] if wanted else list(orphan)
        seen, ordered = set(), []
        for n in targets:
            if n not in seen:
                seen.add(n)
                ordered.append(n)
        if not ordered:
            return 0, []
        groups = dict(_groups())
        for n in ordered:
            groups[n] = {"mode": "whitelist", "categories": "", "tags": ""}
        CONF[GROUPS_KEY] = groups
        _persist(groups)
        logging.info("[reader-group] revived %d orphan groups: %s",
                     len(ordered), ordered)
        return len(ordered), ordered

    # ---------- 成员 ----------

    @staticmethod
    def members_of(session) -> dict:
        """列出所有组员 {组名: [用户名]}。需要调用方提供 SQLAlchemy session
        （handler 里有 settings["ScopedSession"]），service 不直接碰 DB。"""
        from webserver.models import Reader
        try:
            rows = session.query(Reader).all()
        except Exception as e:  # pragma: no cover - DB 不可用
            logging.warning("[reader-group] members_of failed: %s", e)
            # 必须返回 dict：调用方紧接着 .get(name) / .items()，返回 [] 会把
            # 「数据库读失败」变成 AttributeError，列表接口直接 500。
            return {}
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
    def clear_members_of(group_names, session=None) -> int:
        """清掉指向「已不存在的组」的成员引用，返回修复人数。

        **当前没有调用方，也不要在列表接口里调用它。**
        清掉 Reader.extra["reader_group"] 是不可逆的（DB 里没有 extra 的历史），
        悬空引用一旦被抹，管理员重建同名组也找不回人。r17 起列表接口只报告
        （orphan_groups），恢复走 revive_groups()。

        保留本方法仅为「管理员明确要求丢弃这些归属」的场景，
        且必须先让管理员看到组名与人数。
        """
        if session is None or not group_names:
            return 0
        names = set(group_names)
        try:
            from webserver.models import Reader
            n = 0
            for r in session.query(Reader).all():
                g = (r.extra or {}).get(MEMBER_KEY)
                if g in names:
                    extra = dict(r.extra or {})
                    extra.pop(MEMBER_KEY, None)
                    r.extra = extra
                    n += 1
            if n:
                session.commit()
            return n
        except Exception as e:  # pragma: no cover
            logging.warning("[reader-group] clear stale members failed: %s", e)
            session.rollback()
            return 0

    @staticmethod
    def group_of(reader) -> str:
        return str((reader.extra or {}).get(MEMBER_KEY, "") or "")

    # ---------- 生效规则 ----------

    @staticmethod
    def effective_limits(reader) -> dict:
        """用户的生效限制：自身显式设置优先，否则用组的配置。

        返回 {"read_limit": 0/1/2, "limit_categories": str, "limit_tags": str}

        4.6.0-19 起受总开关 READER_GROUPS_ENABLED 控制：关闭时组规则全链路
        失效（所有判定点都经由本函数取组配置，单点收口即可），用户自身的
        read_limit/limit_categories/limit_tags 仍然生效——总开关关的是
        「读者组」这一层，不是整个阅读范围体系（那是 ALLOW_READ_RANGE_SETTING）。
        """
        own_limit = int(getattr(reader, "read_limit", 0) or 0)
        own_cats = (reader.limit_categories or "").strip()
        own_tags = (reader.limit_tags or "").strip()
        if not groups_enabled():
            if own_limit > 0 or own_cats or own_tags:
                return {"read_limit": own_limit,
                        "limit_categories": own_cats,
                        "limit_tags": own_tags,
                        "source": "self", "group": ""}
            return {"read_limit": 0, "limit_categories": "", "limit_tags": "",
                    "source": "group-disabled", "group": ""}
        if own_limit > 0 or own_cats or own_tags:
            return {"read_limit": own_limit,
                    "limit_categories": own_cats,
                    "limit_tags": own_tags,
                    "source": "self", "group": ""}
        name = ReaderGroupService.group_of(reader)
        cfg = _groups().get(name)
        if not cfg:
            if not name:
                # 真的没进组：不受限，这是正常状态。
                return {"read_limit": 0, "limit_categories": "", "limit_tags": "",
                        "source": "none", "group": ""}
            # 成员记录里写着某个组，但这个组已经不存在了（删组、改名、
            # 导入 db 时设置没跟过来）。这时绝对不能当作「不受限」——
            # 数据一脏权限就静默全开，是最危险的兜底方向。
            # 一律按「受限且无一本书可读」处理，管理界面会标红提示重新分配。
            logging.warning("[reader-group] reader points to missing group %r, "
                            "treating as no-access", name)
            return {"read_limit": 1,
                    "limit_categories": "__none__",
                    "limit_tags": "__none__",
                    "source": "group-missing", "group": name}
        mode = cfg.get("mode", "whitelist")
        cats = (cfg.get("categories", "") or "").strip()
        tags = (cfg.get("tags", "") or "").strip()
        # 「不限」组：显式标记「全库可读」。
        # 必须单独有这个模式，因为「白名单 + 空条件」不能兼任此职——严格模式下
        # 那等于「一本书都看不到」（见下面分支）。想让某个组不受限，只能明说。
        if mode == "open":
            return {"read_limit": 0, "limit_categories": "", "limit_tags": "",
                    "source": "group-open", "group": name}
        # 白名单里一个条件都没填：按「严格模式」处理（默认开启）。
        # 注意这里和 mybooks 原生意图相反——原版认为空条件=不限权，
        # 但读者组是管理员手工建的规则，只写了组名没填条件时，
        # 本意几乎总是「先限制住、再慢慢配」，放行全库会让权限看起来完全失效。
        # 想回到原版语义：设置 READER_GROUP_STRICT=false。
        if mode == "whitelist" and not cats and not tags:
            if strict_mode():
                # 严格模式：返回一个不可能的哨兵条件，保证 read_limit>0 且
                # 匹配不到任何书（is_book_in_reading_range 里会判定为不可见）
                return {"read_limit": 1,
                        "limit_categories": "__none__",
                        "limit_tags": "__none__",
                        "source": "group-strict", "group": name}
            return {"read_limit": 0, "limit_categories": "", "limit_tags": "",
                    "source": "group-empty", "group": name}
        return {
            "read_limit": 1 if mode == "whitelist" else 2,
            "limit_categories": cats,
            "limit_tags": tags,
            "source": "group", "group": name,
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
