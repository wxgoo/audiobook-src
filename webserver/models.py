#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import datetime
import sys
import hashlib
import logging
import re
import time
import json
import os
import zlib
from webserver import site_time
from webserver.i18n import _

from social_sqlalchemy.storage import JSONType, SQLAlchemyMixin
from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, or_
from sqlalchemy.ext.mutable import Mutable
from sqlalchemy.orm import relationship, declarative_base, object_session
from webserver.constants import BOOK_TYPE_EBOOK


# 阅读状态常量
READ_STATE_UNREAD = 0  # 未读
READ_STATE_READING = 1  # 在读
READ_STATE_FINISHED = 2  # 已读完

Base = declarative_base()


def mksalt():
    import random
    import string

    # for python3, just use: crypt.mksalt(crypt.METHOD_SHA512)
    saltchars = string.ascii_letters + string.digits + "./"
    salt = []
    for c in range(32):
        idx = int(random.random() * 10000) % len(saltchars)
        salt.append(saltchars[idx])
    return "".join(salt)


Base = declarative_base()


# 当前绑定的 session 工厂（None = 还没绑）。
#
# 为什么存模块级变量、而不是只把闭包挂到 Base 上：
# 有些测试文件会往 sys.modules 里塞假的 `webserver` 包，用完再 pop 掉；
# 之后任何 `import webserver.models` 都会**重新执行本文件**，产出一套全新的
# `Base` / `Reader` / `ScanFile` 类。旧的那套类上还挂着 bind_session 打进去的
# `_session`，新的这套没有 —— 于是 `ScanFile._session()` 一路退到
# `SQLAlchemyMixin` 的默认实现，报 `NotImplementedError: Implement in subclass`。
#
# 把绑定放在这里，`_session` 每次调用时都读一次当前值：即便模块被重新 import，
# 只要重新执行时能从旧模块里把已有的 session 继承过来（见文件末尾的
# `_inherit_session_from_previous_module`），绑定就不会丢。
_BOUND_SESSION = None


def get_bound_session():
    """返回当前绑定的 session 工厂（未绑定时为 None）。"""
    return _BOUND_SESSION


def _session(cls):
    """所有模型类的 `_session()` 最终都落到这里。

    定义在模块级、只读 `_BOUND_SESSION`，而不是像早先那样写在 `bind_session`
    里做闭包 —— 闭包版一旦需要「把同一个函数补到子类上」（见
    `_patch_subclasses_session`）就得往外传，很容易漏一层作用域。
    """
    current = _BOUND_SESSION
    if current is None:
        # 没绑就明确报错，别返回 None 让调用方在别处莫名其妙地炸
        raise RuntimeError(
            "models._session() 未绑定：请先调用 webserver.models.bind_session()"
        )
    return current


def _save_instance(cls, instance):
    """保存实例：优先用**对象自己所属**的 session。

    移植自 talebook 上游（对应他们 issue #782）：`sqlite_session` 是请求级的
    scoped session，Tornado 在同一 ioloop 线程里并发处理多个请求。请求 A 收尾
    时 `on_finish()` 里的 `ScopedSession.remove()` 会把注册表里的 session 摘掉，
    于是请求 B 手里那个对象「所属的 session」和注册表当前给的 session 已经不是
    同一个。这时如果还按注册表拿 session 去 `add()`，就会抛

        Object '<ScanFile>' is already attached to session '718' (this is '719')

    `tests/test_scan.py` 那 5 个 `InvalidRequestError` 就是这个形状。

    所以：能查到对象所属 session 就用它（`object_session`），查不到（新对象、
    还没进任何 session）才回落到注册表。commit 失败要 rollback，否则这个
    可能是长生命周期的 session 会滞留在失败事务里，后面每次 flush 都连锁失败
    —— 这正是之前 `PendingRollbackError` 的传播路径。
    """
    db = object_session(instance) or cls._session()
    db.add(instance)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return instance


def bind_session(session):
    global _BOUND_SESSION
    _BOUND_SESSION = session

    Base._session = classmethod(_session)
    SQLAlchemyMixin._session = classmethod(_session)
    SQLAlchemyMixin._save_instance = classmethod(_save_instance)
    _patch_subclasses_session(Base)
    logging.info("Bind modles._session()")


def _patch_subclasses_session(base):
    """把 `_session` 钉到本模块里**每一个**模型类上。

    光给 `Base` / `SQLAlchemyMixin` 赋值不够。模型都是

        class Reader(Base, SQLAlchemyMixin): ...

    这种多继承，MRO 里 `Base` 在前 —— 听着没问题，但 `SQLAlchemyMixin` 才是
    定义 `_query()` 的那个类，而 `_query()` 里写的是 `cls._session()`：
    属性查找从 `cls` 开始沿 **它自己的 MRO** 走，`Reader.__mro__` 里
    `Base` 也排在 `SQLAlchemyMixin` 前面，所以只有「绑定时 `Base` 上已经有
    `_session`」才能查到。

    真正的坑是**重新 import**：某个测试把 `webserver.models` 从 sys.modules
    里摘掉再 import 一次，会产出**全新的** `Base` 与一套全新的模型类，而
    `social_sqlalchemy.storage.SQLAlchemyMixin` 是第三方模块、不会重新执行，
    上面被上一次 `bind_session` 打过补丁的 `_session` 还留着 —— 于是
    `InstalledTool.get()` 这类方法通过 MRO 查到了那个**旧模块**里的 `_session`，
    它闭包捕获的是旧模块的 `_BOUND_SESSION`，新模块这边压根没绑过，
    表现成 `AttributeError: type object 'InstalledTool' has no attribute '_query'`
    （`_session` 在新类上找不到，`_query` 于是也解析失败）。

    直接在绑定时刻把 `_session` 写到每个类自己的 `__dict__` 里，MRO 就再也不会
    跑到第三方基类上去，也就不可能拿到旧模块的绑定。
    """
    for klass in list(base.__subclasses__()):
        klass._session = classmethod(_session)
        _patch_subclasses_session(klass)


def _inherit_session_from_previous_module(previous):
    """模块被重新 import 时，继承上一个实例已经绑定的 session。

    `sys.modules.pop("webserver.models")`（或 importlib.reload）之后再 import
    时，旧的模块对象会被丢掉。如果它上面已经 bind 过 session，新模块理应接过来，
    否则整个进程就丢了数据库连接（表现见 `_BOUND_SESSION` 上面的注释）。

    调用方负责把旧模块对象传进来，因为到了这里 `sys.modules[__name__]` 已经
    是新模块了。
    """
    inherited = getattr(previous, "_BOUND_SESSION", None) if previous is not None else None
    if inherited is not None and _BOUND_SESSION is None:
        bind_session(inherited)


def to_dict(self):
    return {c.name: getattr(self, c.name, None) for c in self.__table__.columns}


Base.to_dict = to_dict


class MutableDict(Mutable, dict):
    @classmethod
    def coerce(cls, key, value):
        "Convert plain dictionaries to MutableDict."
        if isinstance(value, MutableDict):
            return value
        if isinstance(value, dict):
            return MutableDict(value)
        return Mutable.coerce(key, value)

    def __setitem__(self, key, value):
        "Detect dictionary set events and emit change events."
        dict.__setitem__(self, key, value)
        self.changed()

    def __delitem__(self, key):
        "Detect dictionary del events and emit change events."
        dict.__delitem__(self, key)
        self.changed()

    def __getitem__(self, key):
        if not dict.__contains__(self, key):
            return ""
        return dict.__getitem__(self, key)


class Reader(Base, SQLAlchemyMixin):
    DEFAULT_PERMISSION = ""
    DISABLE_MANAGE = "USED"
    DISABLE_PUSH = "P"

    OVERSIZE_SHRINK_RATE = 0.8
    SQLITE_MAX_LENGTH = 32 * 1024.0

    RE_EMAIL = r"[^@]+@[^@]+\.[^@]+"
    # §必须锚定结尾§ 原为 r"[a-z][a-z0-9_]*"，配合 re.match 只校验前缀：
    # "a-b"、"a bc"、"a;drop" 都能通过校验写入 username。用户名会拼进
    # 各种 URL/日志/WebDAV 认证，脏字符是隐患，这里补 $ 收紧。
    RE_USERNAME = r"[a-z][a-z0-9_]*$"
    RE_PASSWORD = r'[a-zA-Z0-9!@#$%^&*()_+\-=[\]{};\':",./<>?\|]*'

    # §密码强度策略（4.6.0-19 r10）§
    # 用户要求：「不能少于6位，至少大小写、特殊字符、数字中的两种或两种以上」。
    # 老规则只查长度 6~20 + 字符白名单，`123456` / `aaaaaa` 都能过，等于没有强度。
    # 这里统一成一处的判定函数，五个调用点（注册×2、用户改密、管理员改密、
    # 管理员重置）全部走它，避免以后又漂移成各写一份。
    PASSWORD_MIN_LEN = 6
    PASSWORD_MAX_LEN = 20
    PASSWORD_MIN_KINDS = 2

    # 四类字符。注意「特殊字符」只认 RE_PASSWORD 白名单里允许的，
    # 否则前端表单能填、后端却拒收，或者反过来让 emoji 之类的脏字符混进 hash。
    _PWD_KINDS = (
        ("lower", r"[a-z]"),
        ("upper", r"[A-Z]"),
        ("digit", r"[0-9]"),
        ("special", r"[!@#$%^&*()_+\-=\[\]{};':\",./<>?\\|]"),
    )

    @classmethod
    def check_password_strength(cls, password):
        """返回 (ok, 错误码, 中文提示)。

        调用方统一按 `{"err": code, "msg": msg}` 直接返回即可。
        """
        pwd = password or ""
        if len(pwd) < cls.PASSWORD_MIN_LEN:
            return (False, "params.password.short",
                    _("密码不能少于%(n)s位") % {"n": cls.PASSWORD_MIN_LEN})
        if len(pwd) > cls.PASSWORD_MAX_LEN:
            return (False, "params.password.long",
                    _("密码不能超过%(n)s位") % {"n": cls.PASSWORD_MAX_LEN})
        if not re.match(cls.RE_PASSWORD + "$", pwd):
            return (False, "params.password.invalid",
                    _("密码只能包含字母、数字和常见符号"))
        kinds = sum(1 for _name, pat in cls._PWD_KINDS if re.search(pat, pwd))
        if kinds < cls.PASSWORD_MIN_KINDS:
            return (False, "params.password.weak",
                    _("密码太简单：需包含大写字母、小写字母、数字、符号中的至少%(n)s种")
                    % {"n": cls.PASSWORD_MIN_KINDS})
        return (True, "ok", "")

    # §出生年份（4.6.0-19 r11）§
    # 注册必填，目的是让管理员审核时能按年龄做读者分组限额（有些书不适合
    # 某个年龄段）。
    #
    # r10 存的是「填表那一刻的整数岁」，问题在于它不会自己长大：一个 12 岁
    # 的孩子注册三年后仍被判成 12 岁，本该自动解锁的书永远解锁不了，反之
    # 卡在未成年人组的成年人也要管理员手工改。改存出生年份后，任何时候用
    # 当前年份一减就是准确年龄，分组判定自然随时间推进。
    #
    # 范围：下限 1900（再往前不现实，且几乎必然是乱填），上限当前年份
    # （不允许填未来）。0 保留为「未填」，专供历史用户——老库补列就是 0，
    # 不强制回填，否则一升级全员被挡在门外。
    BIRTH_YEAR_MIN = 1900

    @classmethod
    def current_year(cls):
        """当前年份。抽成方法是为了测试能打桩，不必等到真跨年。"""
        return datetime.datetime.now().year

    @classmethod
    def birth_year_range(cls):
        return (cls.BIRTH_YEAR_MIN, cls.current_year())

    @classmethod
    def parse_birth_year(cls, raw, required=True):
        """把注册表单里的出生年份转成整数。返回 (birth_year, 错误码, 提示)。

        宽松接受字符串数字（前端 input 传来的是 str），其余一律拒绝，
        不做「四舍五入」之类的猜测。
        """
        text = str(raw if raw is not None else "").strip()
        if not text:
            if not required:
                return (0, "ok", "")
            return (0, "params.birth_year.required", _("请填写出生年份"))
        if not text.isdigit():
            return (0, "params.birth_year.invalid", _("出生年份需为四位数字"))
        year = int(text)
        lo, hi = cls.birth_year_range()
        if year < lo or year > hi:
            return (0, "params.birth_year.invalid",
                    _("出生年份需在%(a)s~%(b)s之间") % {"a": lo, "b": hi})
        return (year, "ok", "")

    @classmethod
    def age_from_birth_year(cls, birth_year):
        """由出生年份算年龄。未填（0/None）返回 0，年龄下限 0。

        注意这是「年份差」而不是「生日是否已过」的精确年龄——同一年里
        1 月 1 日出生和 12 月 31 日出生算同岁，最多差一岁。分组限额用
        这个粒度足够，且不必额外存月日。
        """
        try:
            year = int(birth_year or 0)
        except (TypeError, ValueError):
            return 0
        if year <= 0:
            return 0
        age = cls.current_year() - year
        return age if age > 0 else 0

    @property
    def age(self):
        """派生年龄（不落库）。管理员列表、分组限额都用它。"""
        return self.age_from_birth_year(self.birth_year)

    @classmethod
    def parse_age_to_birth_year(cls, raw):
        """兼容旧字段：前端若仍按「整数岁」提交 age，换算成出生年份。

        r10 的前端在原安装上升级时可能还有缓存页，直接报「参数无效」会让
        管理员以为改不动年龄。这里做一次换算，返回 (birth_year, code, msg)。
        """
        text = str(raw if raw is not None else "").strip()
        if not text:
            return (0, "params.birth_year.required", _("请填写出生年份"))
        if not text.isdigit():
            return (0, "params.birth_year.invalid", _("出生年份需为四位数字"))
        age = int(text)
        birth_year = cls.current_year() - age
        lo, hi = cls.birth_year_range()
        if age <= 0 or birth_year < lo or birth_year > hi:
            return (0, "params.birth_year.invalid",
                    _("出生年份需在%(a)s~%(b)s之间") % {"a": lo, "b": hi})
        return (birth_year, "ok", "")

    __tablename__ = "readers"
    id = Column(Integer, primary_key=True)
    username = Column(String(200))
    password = Column(String(200), default="")
    salt = Column(String(200))
    name = Column(String(100))
    email = Column(String(200))
    avatar = Column(String(200))
    admin = Column(Boolean, default=False)
    active = Column(Boolean, default=True)
    permission = Column(String(100), default="")
    create_time = Column(DateTime)
    update_time = Column(DateTime)
    access_time = Column(DateTime)
    extra = Column(MutableDict.as_mutable(JSONType), default={})
    vipquota = Column(Integer, default=0)  # VIP用户的下载配额
    vipexpire = Column(DateTime)  # VIP用户的到期时间
    read_limit = Column(Integer, default=0)
    limit_categories = Column(String(512), default="")
    limit_tags = Column(String(512), default="")
    podcast_token = Column(String(128), default="")
    total_reading_seconds = Column(Integer, default=0, nullable=False)  # 累计阅读时长（秒），来自 Reading(action=read) 心跳累加
    download_count = Column(Integer, default=0, nullable=False)  # 累计下载次数，仅 action=download 事件
    push_count = Column(Integer, default=0, nullable=False)  # 累计推送次数，仅 action=push 事件；不回填历史数据，从功能上线时刻起累计
    allow_statistic = Column(Boolean, default=True, nullable=False)  # 是否采集该用户的阅读/下载统计，默认采集（opt-out）
    show_home_recommendations = Column(Boolean, default=True, nullable=False)  # 首页展示其他用户推荐，见 plan/Social_Reading_Plan.md
    allow_review = Column(Boolean, default=True, nullable=False)  # 是否允许发表评论（管理员可禁止）
    # §出生年份（4.6.0-19 r11）§ 注册时必填，供管理员审核后做读者分组限额
    # （有些书不适合某个年龄段）。存出生年份而非整数岁，年龄由 age 属性
    # 实时算出，随时间自然增长。0 表示「历史用户未填」——老库补列时就是 0，
    # 不强制老用户回填，否则一升级全员被挡在门外。
    birth_year = Column(Integer, default=0, nullable=False)

    def __str__(self):
        return "<id=%d, username=%s, email=%s, admin:%d>" % (
            self.id,
            self.username,
            self.email,
            self.admin,
        )

    def shrink_column_extra(self):
        # Clear the unused item in the extra
        self.extra["upload_history"] = []
        self.extra["download_history"] = []
        # check whether the length of `extra` column is out of limit 32KB
        text = json.dumps(self.extra)
        shrink = min(self.OVERSIZE_SHRINK_RATE, self.SQLITE_MAX_LENGTH / len(text))
        if len(text) > self.SQLITE_MAX_LENGTH:
            for k, v in self.extra.items():
                if k.endswith("_history") and isinstance(v, list):
                    new_length = int(len(v) * shrink)
                    self.extra[k] = v[:new_length]

    def save(self):
        self.shrink_column_extra()
        result = super().save()
        from webserver.services.reader_cache import ReaderStatsCache
        ReaderStatsCache().set_allow_statistic(self.id, self.allow_statistic)
        return result

    def init_default_user(self):
        class DefaultUserInfo:
            extra_data = {"username": _("默认用户")}
            provider = ""
            uid = 123456789

        self.init(DefaultUserInfo())

    def init(self, social_user):
        self.username = self.get_social_username(social_user)
        self.create_time = datetime.datetime.now()
        self.update_time = datetime.datetime.now()
        self.access_time = datetime.datetime.now()
        self.extra = {"kindle_email": "", "allow_sending_mail": True}
        self.init_avatar(social_user)

    def reset_password(self):
        s = "%s%s%s" % (self.username, self.create_time.strftime("%s"), time.time())
        p = hashlib.md5(s.encode("UTF-8")).hexdigest()[:16]
        self.set_secure_password(p)
        return p

    def get_secure_password(self, raw_password):
        p1 = hashlib.sha256(raw_password.encode("UTF-8")).hexdigest()
        p2 = hashlib.sha256((self.salt + p1).encode("UTF-8")).hexdigest()
        return p2

    def set_secure_password(self, raw_password):
        self.salt = mksalt()
        self.password = self.get_secure_password(raw_password)

    def init_avatar(self, social_user):
        anyone = "http://tva1.sinaimg.cn/default/images/default_avatar_male_50.gif"
        url = social_user.extra_data.get("profile_image_url", anyone)
        self.avatar = url.replace("http://q.qlogo.cn", "//q.qlogo.cn")

        if social_user.provider == "github":
            self.avatar = (
                "https://avatars.githubusercontent.com/u/%s"
                % social_user.extra_data["id"]
            )

    def get_active_code(self):
        return self.get_secure_password(self.create_time.strftime("%Y-%m-%d %H:%M:%S"))

    def get_social_username(self, si):
        for k in ["username", "login"]:
            if k in si.extra_data:
                return si.extra_data[k]
        return "%s_%s" % (si.provider, si.uid)

    def check_and_update(self, social_user):
        name = self.get_social_username(social_user)
        if self.username != name:
            logging.info("userid[%s] username needs update to [%s]" % (self.id, name))
            self.username = name

    def set_permission(self, operations):
        ALL = "delprsuv"
        if not isinstance(operations, str):
            # Python 3 不能 raise 字符串：原写法 `raise "bug"` 自己就会
            # TypeError: exceptions must derive from BaseException
            raise TypeError("operations must be a string, got %r" % type(operations).__name__)
        v = list(self.permission)
        for p in operations:
            if p.lower() not in ALL:
                continue
            r = p.upper() if p.islower() else p.lower()
            try:
                v.remove(r)
            except ValueError:
                pass
            v.append(p)
        self.permission = "".join(sorted(v))

    def has_permission(self, operation, default=True):
        if operation.lower() in self.permission:
            return True
        if operation.upper() in self.permission:
            return False
        return default

    def can_delete(self):
        return self.has_permission("d")

    def can_edit(self):
        return self.has_permission("e")

    def can_login(self):
        return self.has_permission("l")

    def can_push(self):
        return self.has_permission("p")

    def can_read(self):
        return self.has_permission("r")

    def can_save(self):
        return self.has_permission("s")

    def can_upload(self):
        return self.has_permission("u")

    def can_view(self):
        return self.has_permission("v")

    def is_active(self):
        return self.active

    def is_admin(self):
        return self.admin


class ReaderLog(Base, SQLAlchemyMixin):
    ACTION_LOGIN = 1
    ACTION_DISABLE = 2
    ACTION_ENABLE = 3
    ACTION_UPDATE_EXPIRE = 10
    ACTION_UPDATE_QUOTA = 11
    ACTION_COLLECTION_DOWNLOAD = 20
    ACTION_COLLECTION_DOWNLOAD_START = 21
    ACTION_COLLECTION_DOWNLOAD_FINISHED = 22
    ACTION_PURCHASE = 30

    __tablename__ = "readerlogs"
    id = Column(Integer, primary_key=True)
    reader_id = Column(Integer, ForeignKey("readers.id"))
    action = Column(Integer, default=0)
    create_time = Column(DateTime)
    extra = Column(MutableDict.as_mutable(JSONType), default={})
    revision = Column(String(100), default=0)
    operator_id = Column(Integer, ForeignKey("readers.id"), default=0)

    def __init__(self, reader_id, action, operator_id=0, revision=""):
        super(ReaderLog, self).__init__()
        self.reader_id = reader_id
        self.action = action
        self.operator_id = operator_id
        self.revision = revision
        self.create_time = datetime.datetime.now()

    def set_extra(self, key, value):
        if not self.extra:
            self.extra = {}
        self.extra[key] = value

    def get_extra(self, key, default=None):
        if not self.extra:
            self.extra = {}
        return self.extra.get(key, default)


###
# 存放一些业务相关的Key
# 像下载业务，在下载链接后面加上一个key，防止盗链
###
class BizKey(Base, SQLAlchemyMixin):
    TYPE_DOWNLOAD = 1

    __tablename__ = "biz_key"
    id = Column(Integer, primary_key=True)
    reader_id = Column(Integer, ForeignKey("readers.id"))
    key = Column(String(100))
    expire = Column(DateTime)
    create_time = Column(DateTime)
    type = Column(Integer)

    def __init__(self, reader_id, key, expire, type=0):
        super(BizKey, self).__init__()
        self.reader_id = reader_id
        self.key = key
        self.expire = expire
        self.create_time = datetime.datetime.now()
        self.type = type


class Message(Base, SQLAlchemyMixin):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_reader_unread_id", "reader_id", "unread", "id"),
        Index("ix_messages_reader_id", "reader_id", "id"),
    )
    MAX_PER_USER = 200

    id = Column(Integer, primary_key=True)
    title = Column(String(200))
    status = Column(String(100))
    unread = Column(Boolean, default=True)
    create_time = Column(DateTime)
    update_time = Column(DateTime)
    data = Column(MutableDict.as_mutable(JSONType), default={})
    content_hash = Column(String(40))

    reader_id = Column(Integer, ForeignKey("readers.id"))
    reader = relationship(Reader, backref="messages")

    def __init__(self, user_id, status, msg):
        super(Message, self).__init__()
        self.reader_id = user_id
        self.status = status
        self.create_time = datetime.datetime.now()
        self.update_time = datetime.datetime.now()
        self.data = {"message": msg}
        self.content_hash = self.hash_content(msg)

    @staticmethod
    def hash_content(msg):
        return hashlib.sha1(str(msg).encode("utf-8")).hexdigest()

    def to_brief(self):
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "create_time": self.create_time.strftime("%Y-%m-%d %H:%M:%S"),
            "data": self.data,
        }

    @classmethod
    def unread_page(cls, session, reader_id, after_id=0, limit=50):
        query = session.query(cls).filter(cls.reader_id == reader_id, cls.unread.is_(True))
        total = query.count()
        if after_id > 0:
            query = query.filter(cls.id > after_id)
        return query.order_by(cls.id.desc()).limit(limit).all(), total

    @classmethod
    def cleanup_messages(cls, reader_id, msg_content, days=31):
        """清理指定用户内容相同的消息、过期消息，并把总量限制在 MAX_PER_USER 以内"""
        session = cls._session()
        cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
        removed_count = session.query(cls).filter(
            cls.reader_id == reader_id,
            or_(cls.content_hash == cls.hash_content(msg_content), cls.update_time < cutoff),
        ).delete(synchronize_session=False)
        edge = session.query(cls.id).filter(cls.reader_id == reader_id).order_by(cls.id.desc()).offset(cls.MAX_PER_USER - 1).limit(1).scalar()
        if edge is not None:
            removed_count += session.query(cls).filter(cls.reader_id == reader_id, cls.id <= edge).delete(synchronize_session=False)
        if removed_count > 0:
            session.commit()
        return removed_count

    @classmethod
    def cleanup_old_messages(cls, days=31):
        """清理指定天数以前的消息"""
        session = cls._session()
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
        removed_count = session.query(cls).filter(cls.create_time < cutoff_date).delete(synchronize_session=False)
        if removed_count > 0:
            session.commit()
            logging.info(f"Cleaned up {removed_count} messages older than {days} days")
        return removed_count


class Item(Base, SQLAlchemyMixin):
    # 图书信息
    __tablename__ = "items"

    book_id = Column(Integer, default=0, primary_key=True)
    count_guest = Column(Integer, default=0, nullable=False)
    count_visit = Column(Integer, default=0, nullable=False)  # 首次阅读次数：某用户首次产生该书的 Reading(action=read) 记录时 +1，由 ReadingWriteBuffer.flush() 维护
    count_download = Column(Integer, default=0, nullable=False)  # 下载+推送次数：每新增一条 Reading(action=download/push) 记录 +1，由 ReadingWriteBuffer.flush() 维护
    website = Column(String(255), default="", nullable=False)

    collector_id = Column(Integer, ForeignKey("readers.id"))
    collector = relationship(Reader, backref="items")
    sole = Column(Boolean, default=False, nullable=False)
    book_type = Column(Integer, default=0, nullable=False)
    book_count = Column(Integer, default=1, nullable=False)
    create_time = Column(DateTime)
    src_path = Column(String(4096), default="", nullable=False)

    def __init__(self):
        super(Item, self).__init__()
        self.count_guest = 0
        self.count_visit = 0
        self.count_download = 0
        self.collector_id = 1
        self.sole = False
        self.book_type = BOOK_TYPE_EBOOK  # 0:电子书, 1:实体书
        self.book_count = 1
        self.create_time = datetime.datetime.now()
        self.src_path = ""


class ScanFile(Base, SQLAlchemyMixin):
    __tablename__ = "scanfiles"
    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, default=0)
    import_id = Column(Integer, default=0)
    import_type = Column(Integer, default=0)

    name = Column(String(512))
    path = Column(String(1024))
    hash = Column(String(512))
    status = Column(String(24))

    title = Column(String(100))
    author = Column(String(100))
    publisher = Column(String(100))
    tags = Column(String(100))

    create_time = Column(DateTime)
    update_time = Column(DateTime)
    book_id = Column(Integer, default=0)
    data = Column(MutableDict.as_mutable(JSONType), default={})

    # STATUS
    NEW = "new"
    DROP = "drop"
    READY = "ready"
    EXIST = "exist"
    IMPORTED = "imported"
    INVALID = "invalid"
    MISSED = "missed"
    PERMISSION = "permission"

    def __init__(self, path, hash_value, import_id):
        super(ScanFile, self).__init__()
        self.name = os.path.basename(path)
        self.path = path
        self.hash = hash_value
        self.import_id = import_id
        self.status = self.NEW
        self.create_time = datetime.datetime.now()
        self.update_time = datetime.datetime.now()


class ScanDirSnapshot(Base, SQLAlchemyMixin):
    """扫描目录快照：增量扫描的水位线（mtime 方案）。

    每行记录一次成功整轮扫描见到的目录状态。目录自身 mtime 只反映直接子项
    变化，因此剪枝必须自顶向下逐目录比对，不能只看顶层：
    - mtime_ns + entry_count 双等才算“未变”（scandir 原始条目数，剪枝前口径，
      防隐藏目录过滤等规则漂移导致定义不一致）；
    - 任一不等/无快照/异常 → 按“变了”处理（偏安全方向，多干活不漏活）。
    随 _NEW_TABLES_AUTO_ENSURE 自动建表，纯派生数据，可随时整表重建。

    主键用目录路径的 sha256（dir_hash）而非路径本身：路径列长可能远超 MySQL/InnoDB
    索引键上限（utf8mb4 VARCHAR(2048) = 8192 字节 > 3072），直接拿长路径当主键会让
    该库 create_all 失败并 sys.exit(1)。快照表很小且总是整表读，路径无需索引。
    """
    __tablename__ = "scan_dir_snapshots"
    dir_hash = Column(String(64), primary_key=True)
    dir = Column(String(2048))
    mtime_ns = Column(BigInteger, default=0)
    entry_count = Column(Integer, default=0)
    update_time = Column(DateTime)

    @staticmethod
    def hash_for(dir_path):
        # surrogateescape：挂载点/病态文件名可能带不可编码字节，直接 encode 会让
        # 整个快照提交事务 rollback、增量剪枝永久失效；写读同函数，键自洽
        return hashlib.sha256(dir_path.encode("utf-8", "surrogateescape")).hexdigest()

    def __init__(self, dir_path, mtime_ns, entry_count):
        super(ScanDirSnapshot, self).__init__()
        self.dir_hash = ScanDirSnapshot.hash_for(dir_path)
        self.dir = dir_path
        self.mtime_ns = mtime_ns
        self.entry_count = entry_count
        self.update_time = datetime.datetime.now()


class ReaderPaidBook(Base, SQLAlchemyMixin):
    __tablename__ = "reader_paid_books"

    id = Column(Integer, primary_key=True)
    reader_id = Column(Integer, ForeignKey("readers.id"))
    book_id = Column(Integer)
    order_id = Column(String(100))
    create_time = Column(DateTime)
    price = Column(Integer, default=0)  # 价格
    reader = relationship(Reader, backref="paid_books")

    def __init__(self, reader_id, book_id, order_id=None, price=1):
        super(ReaderPaidBook, self).__init__()
        self.reader_id = reader_id
        self.book_id = book_id
        self.order_id = order_id
        self.price = price
        self.create_time = datetime.datetime.now()


# 用户对某本书的阅读状态
class ReadingState(Base, SQLAlchemyMixin):
    __tablename__ = "reading_state"

    book_id = Column(Integer, primary_key=True)
    reader_id = Column(Integer, ForeignKey("readers.id"), primary_key=True)
    favorite = Column(Integer, default=0)  # 0:为未收藏,1:已收藏
    favorite_date = Column(DateTime)
    wants = Column(Integer, default=0)  # 0:未标记为待读,1:标记为待读
    wants_date = Column(DateTime)
    read_state = Column(Integer, default=0, nullable=False)  # 0:未读, 1:在读, 2:已读完
    read_date = Column(DateTime)
    online_read = Column(Integer, default=0)  # 0:未在线阅读, 1:已在线阅读
    download = Column(Integer, default=0)  # 0:未下载,1:已下载

    # 建立关系
    reader = relationship(Reader, backref="reading_states")

    def __init__(self, book_id, reader_id):
        super(ReadingState, self).__init__()
        self.book_id = book_id
        self.reader_id = reader_id
        self.favorite = 0
        self.wants = 0
        self.read_state = 0

    def set_favorite(self, favorite_status):
        """设置收藏状态"""
        self.favorite = 1 if favorite_status else 0
        self.favorite_date = datetime.datetime.now()

    def is_favorite(self):
        """检查是否已收藏"""
        return self.favorite == 1

    def set_wants(self, wants_status):
        """设置待读状态"""
        self.wants = 1 if wants_status else 0
        self.wants_date = datetime.datetime.now()

    def is_wants(self):
        """检查是否标记为待读"""
        return self.wants == 1

    def set_read_state(self, read_state):
        """设置阅读状态 0:未读, 1:在读, 2:已读完"""
        if read_state in [0, 1, 2]:
            self.read_state = read_state
            self.read_date = datetime.datetime.now()
        if read_state > READ_STATE_UNREAD:
            self.wants = 0

    def get_read_state(self):
        """获取当前阅读状态"""
        return self.read_state

    def set_online_read(self, online_read_status):
        """设置在线阅读状态"""
        self.online_read = 1 if online_read_status else 0

    def set_download(self, download_status):
        """设置下载状态"""
        self.download = 1 if download_status else 0


# 用户对某本书的阅读/下载/推送行为记录（详见 document/Reading_Stats_Design.md）
# action=read: 每个 (reader_id, book_id, date) 只保留一行（date 是 UTC 日期，不含时间，
#              用于按天统计阅读时长），duration 是当天累计时长，start_time 是当天"最近一次
#              阅读会话"的开始时间；由 ux_readings_read 部分唯一索引 + upsert 维护（见 async_service.py）
# action=download/push: 事件制，每次都新插入一行；date 取事件发生当天，不参与唯一性约束
class Reading(Base, SQLAlchemyMixin):
    __tablename__ = "readings"

    ACTION_READ = "read"
    ACTION_DOWNLOAD = "download"
    ACTION_PUSH = "push"

    PROTOCOL_WEB = "web"          # action=read | download
    PROTOCOL_APP = "app"          # action=read（MyReader）
    PROTOCOL_OPDS = "opds"        # action=download
    PROTOCOL_WEBDAV = "webdav"    # action=download
    PROTOCOL_DEVICE = "device"    # action=push
    PROTOCOL_EMAIL = "email"      # action=push
    PROTOCOL_KOREADER = "koreader"  # action=read | download

    id = Column(Integer, primary_key=True, autoincrement=True)
    reader_id = Column(Integer, ForeignKey("readers.id"), nullable=False)
    book_id = Column(Integer, nullable=False)
    book_title = Column(String(512), default="")  # 保留字段，本轮不填充
    action = Column(String(16), nullable=False)    # read | download | push
    protocol = Column(String(16), nullable=False)  # 见 PROTOCOL_* 常量，按 action 区分含义
    date = Column(Date, nullable=False)  # 站点时区（site_timezone）下的日期，见 webserver/site_time.py；action=read 时是唯一键的一部分
    start_time = Column(DateTime, nullable=False)  # UTC；read=当天最近一次阅读会话开始时间，download/push=事件发生时间
    duration = Column(Integer, default=0, nullable=False)  # 秒；仅 action=read 有意义，download/push 恒为 0
    update_time = Column(DateTime, nullable=False)  # UTC；read=最后一次心跳时间，download/push=事件发生时间

    reader = relationship(Reader, backref="readings")

    def __init__(self, reader_id, book_id, action, protocol, start_time, duration=0, update_time=None, date=None):
        super(Reading, self).__init__()
        self.reader_id = reader_id
        self.book_id = book_id
        self.action = action
        self.protocol = protocol
        self.start_time = start_time
        self.duration = duration
        self.update_time = update_time or start_time
        # 分桶日期按站点时区切天，而不是直接取 UTC 时刻的日期：UTC+8 的读者在
        # 00:00~08:00 的阅读，UTC 日还停在前一天
        self.date = date or site_time.site_date(self.update_time)


# 单本书 · 分格式的阅读时长/进度统计
# 与 Reading 表（全局、按天分桶、不分格式）是两条并行的统计线：这张表关心"这一遍完整地
# 读了多久、从哪天开始、哪天读完"，(reader_id, book_id, format) 唯一，一行代表"当前/最近一轮"。
class BookReadingStats(Base, SQLAlchemyMixin):
    __tablename__ = "book_reading_stats"

    STATE_READING = 0
    STATE_FINISHED = 1

    id = Column(Integer, primary_key=True, autoincrement=True)
    reader_id = Column(Integer, ForeignKey("readers.id"), nullable=False)
    book_id = Column(Integer, nullable=False)
    format = Column(String(16), nullable=False)  # epub/pdf/mobi/azw3/txt 等，统一小写

    state = Column(Integer, default=STATE_READING, nullable=False)  # 0=在读 1=已完成
    total_seconds = Column(Integer, default=0, nullable=False)      # 这个格式的累计阅读时长（秒），跨轮次累加

    progress_current = Column(Integer)  # 来自 sync progress=[current,total] 的 current
    progress_total = Column(Integer)    # 来自 sync progress=[current,total] 的 total
    progress_percent = Column(Float)    # 0~100，两位小数；与 current/total 一起存，避免查询时现算

    start_time = Column(DateTime)   # UTC；当前/最近一轮的开始时间
    finish_time = Column(DateTime)  # UTC；当前/最近一轮的完成时间；重新开始阅读时清空
    start_count = Column(Integer, default=0, nullable=False)  # 开始阅读的次数（含首次）

    create_time = Column(DateTime, nullable=False)  # 这一行第一次创建的时间，不随轮次变化
    update_time = Column(DateTime, nullable=False)  # 最后一次写入时间（心跳或手动更新）

    reader = relationship(Reader)

    __table_args__ = (
        UniqueConstraint("reader_id", "book_id", "format", name="ux_book_reading_stats"),
        Index("ix_book_reading_stats_reader_book", "reader_id", "book_id"),
    )

    def format_dict(self):
        return {
            "format": self.format,
            "state": self.state,
            "total_seconds": self.total_seconds or 0,
            "progress_current": self.progress_current,
            "progress_total": self.progress_total,
            "progress_percent": 100.0 if self.state == self.STATE_FINISHED else self.progress_percent,
            # start_time/finish_time/update_time 存的是 UTC naive datetime（见类注释），
            # isoformat() 后补一个 "Z" 后缀，避免前端 `new Date(...)` 把它当成本地时间解析
            "start_time": self.start_time.isoformat() + "Z" if self.start_time else None,
            "finish_time": self.finish_time.isoformat() + "Z" if self.finish_time else None,
            "start_count": self.start_count or 0,
            "update_time": self.update_time.isoformat() + "Z" if self.update_time else None,
        }


# 管理菜单"阅读时间补录"：每 (reader_id, book_id, date) 一行，记录当前生效的补录时长。
# 再次编辑同一天是更新这一行而不是追加流水，保留 duration_seconds 是为了编辑/删除时能
# 算出与上一次的差值，增量同步到 Reading.duration / BookReadingStats.total_seconds /
# Reader.total_reading_seconds，避免统计翻倍或对不上。
class ManualReadingLog(Base, SQLAlchemyMixin):
    __tablename__ = "manual_reading_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reader_id = Column(Integer, ForeignKey("readers.id"), nullable=False)
    book_id = Column(Integer, nullable=False)
    format = Column(String(16), nullable=False)
    date = Column(Date, nullable=False)
    start_time = Column(String(5))
    end_time = Column(String(5))
    duration_seconds = Column(Integer, default=0, nullable=False)
    create_time = Column(DateTime, nullable=False)
    update_time = Column(DateTime, nullable=False)

    reader = relationship(Reader)

    __table_args__ = (
        UniqueConstraint("reader_id", "book_id", "date", name="ux_manual_reading_logs"),
        Index("ix_manual_reading_logs_reader_book", "reader_id", "book_id"),
    )

    def format_dict(self):
        return {
            "date": self.date.strftime("%Y-%m-%d"),
            "format": self.format,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds or 0,
        }


# MyBooks 云端书籍的 book_hash 形如 "cloud-8502-epub"，8502 是 Calibre book_id；
# 与 webserver/services/reading_stats_service.py::_CLOUD_BOOK_HASH_RE 保持一致（含义相同，
# 避免相互 import 造成循环依赖，两处各自维护一份同样的正则）。
_CLOUD_BOOK_HASH_RE = re.compile(r"^cloud-(\d+)-[a-zA-Z0-9]+$")


def parse_book_id_from_reading_record_hash(book_hash):
    """把 `book_hash` 换算成 ReadingRecord.book_id：

    - 云端书籍（`cloud-<id>-<fmt>`）：返回真实的正整数 Calibre book_id。
    - 本地/无法识别的 book_hash：返回一个稳定的负数占位值（同一 book_hash 每次算出来的
      结果一致），保证：① 恒为负数，天然不会撞上真实 book_id（恒为正）；② 跨用户共读查询
      只需加 `book_id > 0` 条件即可自动排除所有本地书籍，不需要额外的"是否本地书籍"标记列。
      见 document/../plan/Social_Reading_Plan.md §5.2。
    """
    if book_hash:
        m = _CLOUD_BOOK_HASH_RE.match(book_hash)
        if m:
            return int(m.group(1))
    return -(zlib.crc32((book_hash or "").encode("utf-8")) & 0x7FFFFFFF) or -1


# 用户阅读器数据同步记录（books/configs/notes 三类），替代原先按
# <MYREADER_SYNC_PATH>/<uid>/<book_hash>/{kind}.json 的文件存储方案。
# 详见 plan/Social_Reading_Plan.md §5.2、§7，以及 webserver/services/sync_service.py。
class ReadingRecord(Base, SQLAlchemyMixin):
    __tablename__ = "reading_records"

    KIND_BOOKS = "books"
    KIND_CONFIGS = "configs"
    KIND_NOTES = "notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reader_id = Column(Integer, ForeignKey("readers.id"), nullable=False)
    book_hash = Column(String(64), nullable=False)      # 原始 book_hash，记录身份仍以它为准
    book_id = Column(Integer, nullable=False)           # 从 book_hash 提取的整型 id，供跨用户查询走整型索引
    kind = Column(String(16), nullable=False)           # books | configs | notes
    record_id = Column(String(64), nullable=False)      # books/configs: 固定用 book_hash 占位；notes: 记录自带的 id
    uid = Column(Integer, nullable=False)                # 冗余存一份 reader_id，同时也是要求写入 payload 内的 "uid"
    payload = Column(MutableDict.as_mutable(JSONType), nullable=False, default={})  # 记录原始 JSON 内容
    updated_at = Column(BigInteger, nullable=False)      # 毫秒时间戳，来自 payload.updated_at，冗余出来做索引/排序
    deleted_at = Column(BigInteger, nullable=True)       # 同上，冗余自 payload.deleted_at

    reader = relationship(Reader)

    __table_args__ = (
        UniqueConstraint("reader_id", "book_hash", "kind", "record_id", name="ux_reading_record"),
        Index("ix_reading_record_lookup", "reader_id", "kind", "updated_at"),
        Index("ix_reading_record_book_kind", "book_id", "kind", "updated_at"),
    )


# KOReader 插件上报的阅读位置，与 /api/sync 的 configs.location 分开存，避免互相覆盖。
class KoreaderPosition(Base, SQLAlchemyMixin):
    __tablename__ = "koreader_position"

    reader_id = Column(Integer, ForeignKey("readers.id"), primary_key=True)
    book_id = Column(Integer, primary_key=True)
    format = Column(String(16), primary_key=True)
    xpointer = Column(Text)
    percent = Column(Float)
    client_updated_at = Column(Integer)
    device_id = Column(String(64))
    device_name = Column(String(64))
    update_time = Column(DateTime)

    reader = relationship(Reader)

    def format_dict(self):
        return {
            "xpointer": self.xpointer,
            "percent": self.percent,
            "client_updated_at": self.client_updated_at,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "update_time": self.update_time.isoformat() + "Z" if self.update_time else None,
        }


# 有声书播放进度（4.6.0-19）。此前进度只存浏览器 localStorage，换设备/换
# 浏览器/清缓存即丢。语义与前端播放器对齐：track_index 是播放列表里的
# 集/章序号，position 是该集内的秒数（audio.currentTime），duration 是该集
# 总时长（供前端校验进度有效性）。每 (reader_id, book_id) 一行。
class AudioPlayback(Base, SQLAlchemyMixin):
    __tablename__ = "audio_playback"
    __table_args__ = (
        Index("ix_audio_playback_reader_book", "reader_id", "book_id", unique=True),
    )

    id = Column(Integer, primary_key=True)
    reader_id = Column(Integer, ForeignKey("readers.id"))
    book_id = Column(Integer)
    track_index = Column(Integer, default=0)
    position = Column(Float, default=0)
    duration = Column(Float)
    updated_at = Column(DateTime)
    # 客户端「这次进度产生的时刻」（毫秒）。多设备交替播放时，服务端只接受
    # 严格更新的写入，避免后到的旧心跳把新进度盖掉。老库没有这一列时由
    # _ensure_audio_playback_columns() 启动补列，读不到就按 0（永不被拦）。
    client_ts = Column(BigInteger, default=0)

    reader = relationship(Reader)

    def __init__(self, reader_id, book_id, track_index=0, position=0, duration=None):
        super().__init__()
        self.reader_id = reader_id
        self.book_id = book_id
        self.track_index = track_index
        self.position = position
        self.duration = duration
        self.updated_at = datetime.datetime.now()

    def format_dict(self):
        return {
            "track_index": self.track_index,
            "position": self.position,
            "duration": self.duration,
            "client_ts": self.client_ts or 0,
            "updated_at": self.updated_at.isoformat() + "Z" if self.updated_at else None,
        }


# 用户对某本书的评分 + 评论（"共读"里的评价 = 推荐，见 plan/Social_Reading_Plan.md §5.1）。
# 每个用户对每本书最多一条（唯一约束），自行删除是软删除（deleted_at），管理员屏蔽是把
# status 置为 hidden（prev_status 记录屏蔽前的状态，供"恢复"用），两者语义不同、互不覆盖。
class BookReview(Base, SQLAlchemyMixin):
    __tablename__ = "book_reviews"

    STATUS_PENDING = "pending"    # 未审核
    STATUS_APPROVED = "approved"  # 通过
    STATUS_HIDDEN = "hidden"      # 管理员屏蔽

    id = Column(Integer, primary_key=True, autoincrement=True)
    reader_id = Column(Integer, ForeignKey("readers.id"), nullable=False)
    book_id = Column(Integer, nullable=False)
    rating = Column(Integer, nullable=False)             # 沿用 book.rating 刻度（0-10）
    comment = Column(Text, default="")                    # 允许为空
    status = Column(String(16), nullable=False, default=STATUS_APPROVED)
    prev_status = Column(String(16), nullable=True)       # 进入 hidden 前的状态快照，供"恢复"使用
    create_time = Column(DateTime, nullable=False)
    update_time = Column(DateTime, nullable=False)
    deleted_at = Column(DateTime, nullable=True)           # 用户自行删除（软删除）

    reader = relationship(Reader)

    __table_args__ = (
        UniqueConstraint("reader_id", "book_id", name="ux_book_review"),
        Index("ix_book_review_book", "book_id", "status", "update_time"),
    )


class Device(Base, SQLAlchemyMixin):
    """用户阅读设备"""

    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reader_id = Column(Integer, ForeignKey("readers.id"), nullable=False)
    name = Column(String(64), nullable=False, default="")
    device_type = Column(String(32), nullable=False, default="duokan")
    ip = Column(String(128), default="")
    port = Column(Integer, default=12121)
    schema = Column(String(8), default="http")
    mailbox = Column(String(2048), default="")
    create_time = Column(DateTime, default=datetime.datetime.now)
    update_time = Column(DateTime, default=datetime.datetime.now)

    reader = relationship(Reader, backref="devices")

    def __init__(
        self,
        reader_id,
        name,
        device_type="duokan",
        ip="",
        port=12121,
        schema="http",
        mailbox="",
    ):
        super(Device, self).__init__()
        self.reader_id = reader_id
        self.name = name
        self.device_type = device_type
        self.ip = ip
        self.port = port
        self.schema = schema
        self.mailbox = mailbox
        self.create_time = datetime.datetime.now()
        self.update_time = datetime.datetime.now()

    def to_dict(self):
        result = {
            "name": self.name,
            "type": self.device_type,
            "ip": self.ip,
            "port": self.port,
            "schema": self.schema,
            "mailbox": self.mailbox,
        }
        if self.device_type == "ftp":
            try:
                extra = json.loads(self.mailbox or "{}")
            except Exception:
                extra = {}
            result["ftp_username"] = extra.get("username", "")
            result["ftp_password"] = extra.get("password", "")
            result["ftp_path"] = extra.get("path", "")
            result["mailbox"] = ""
        return result


class Authors(Base, SQLAlchemyMixin):
    """作者信息, author_id为后台返回的id"""

    __tablename__ = "authors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False, unique=True)
    author_id = Column(Integer, nullable=True, default=0)
    sort = Column(String(128), nullable=True, default="")
    bio = Column(String(4096), nullable=True, default="")
    region = Column(String(128), nullable=True, default="")
    avatar = Column(String(512), nullable=True, default="")
    create_time = Column(DateTime, default=datetime.datetime.now)

    def __init__(self, name, sort, bio="", region="", avatar=""):
        super(Authors, self).__init__()
        self.name = name
        self.sort = sort
        self.bio = bio
        self.region = region
        self.avatar = avatar
        self.create_time = datetime.datetime.now()


class StickyItem(Base, SQLAlchemyMixin):
    """置顶项目 - 用于置顶作者或标签"""

    __tablename__ = "sticky_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reader_id = Column(Integer, ForeignKey("readers.id"), nullable=False)
    item_type = Column(Integer, nullable=False)  # 0:作者, 1:Tag
    value = Column(String(256), nullable=False)  # 存储具体的作者或Tag名称
    create_time = Column(DateTime, default=datetime.datetime.now)

    # 建立关系
    reader = relationship(Reader, backref="sticky_items")

    def __init__(self, reader_id, item_type, value):
        super(StickyItem, self).__init__()
        self.reader_id = reader_id
        self.item_type = item_type
        self.value = value
        self.create_time = datetime.datetime.now()


class ExpectedItem(Base, SQLAlchemyMixin):
    """缺书登记项目"""

    __tablename__ = "expected_item"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reader_id = Column(Integer, ForeignKey("readers.id"), nullable=False)
    title = Column(String(256), nullable=False)  # 书籍标题
    author = Column(String(128), nullable=True, default="")  # 书籍作者
    publisher = Column(String(256), nullable=True, default="")  # 出版社
    create_time = Column(DateTime, default=datetime.datetime.now)

    # 建立关系
    reader = relationship(Reader, backref="expected_items")

    def __init__(self, reader_id, title, author="", publisher=""):
        super(ExpectedItem, self).__init__()
        self.reader_id = reader_id
        self.title = title
        self.author = author
        self.publisher = publisher
        self.create_time = datetime.datetime.now()


class Memo(Base, SQLAlchemyMixin):
    """网站留言"""

    MEMO_TYPE_SUGGESTION = 0  # 建议
    MEMO_TYPE_BOOK_REQUEST = 1  # 求书
    MEMO_TYPE_HELP = 2  # 求助

    STAGE_NEW = "new"
    STAGE_SUSPEND = "suspend"
    STAGE_DONE = "done"

    __tablename__ = "memo"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reader_id = Column(Integer, ForeignKey("readers.id"), nullable=False, default=0)
    memo = Column(String(2048), nullable=False, default="")
    reply = Column(String(2048), nullable=False, default="")
    memo_type = Column(Integer, nullable=False, default=0)
    stage = Column(String(10), nullable=False, default="new")
    create_date = Column(DateTime, default=datetime.datetime.now)
    update_date = Column(DateTime, default=datetime.datetime.now)

    # 建立关系
    reader = relationship(Reader, backref="memos")

    def __init__(self, reader_id, memo, memo_type=0, stage="new"):
        super(Memo, self).__init__()
        self.reader_id = reader_id
        self.memo = memo
        self.memo_type = memo_type
        self.stage = stage
        self.reply = None
        self.create_date = datetime.datetime.now()
        self.update_date = datetime.datetime.now()


class InstalledTool(Base, SQLAlchemyMixin):
    """Toolbox 工具安装记录：内置工具 + 外部工具统一记录在这张表里，
    见 document/Toolbox_Dynamic_Design.md 3.3.2 节。

    MyBooks 里统一用"工具"（tool）指代 Toolbox 的功能单元，不用"插件"（plugin）这个词——
    type 只有 builtin（内置）/ tool（通过 zip 安装的非内置工具）两种。"""
    __tablename__ = "installed_tools"

    TYPE_BUILTIN = "builtin"
    TYPE_TOOL = "tool"

    SOURCE_BUNDLED = "bundled"  # 随仓库自带（仅 builtin）
    SOURCE_STORE = "store"      # 通过 mybooks.top 商店安装/更新；ENABLE_TOOLBOX_STORE=False（默认）时商店索引恒为空，实际不会产生此来源的记录
    SOURCE_DEV = "dev"          # 开发者模式本地 zip 上传安装/更新

    tool_id = Column(String(128), primary_key=True)
    type = Column(String(16), nullable=False)  # builtin | tool，写入后不再改变
    installed_revision = Column(String(32), default="", nullable=False)
    source = Column(String(16), nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)  # 仅对 type=tool 有意义，builtin 恒为 True
    install_time = Column(DateTime)
    update_time = Column(DateTime)
    installed_by = Column(Integer, ForeignKey("readers.id"), nullable=True)

    def __init__(self, tool_id, type_, source, installed_revision="", enabled=True, installed_by=None):
        super(InstalledTool, self).__init__()
        self.tool_id = tool_id
        self.type = type_
        self.source = source
        self.installed_revision = installed_revision
        self.enabled = enabled
        now = datetime.datetime.now()
        self.install_time = now
        self.update_time = now
        self.installed_by = installed_by

    @classmethod
    def get(cls, tool_id):
        return cls._query().filter_by(tool_id=tool_id).first()

    @classmethod
    def all(cls):
        return cls._query().all()

    def delete(self):
        session = self._session()
        session.delete(self)
        session.commit()

    def to_dict(self):
        return {
            "tool_id": self.tool_id,
            "type": self.type,
            "source": self.source,
            "installed_revision": self.installed_revision,
            "enabled": self.enabled,
            "install_time": self.install_time.isoformat() if self.install_time else None,
            "update_time": self.update_time.isoformat() if self.update_time else None,
            "installed_by": self.installed_by,
        }


class BookList(Base, SQLAlchemyMixin):
    """用户自建书单，见 document/BookList_Design.md。删除为物理硬删除（非关键数据，不做软删除），
    关联的 BookListBook / BookListLike 记录在 service 层同一事务里一并删除。"""

    __tablename__ = "booklists"

    COLORS = ("marine", "velvet", "night_blue", "green", "yellow", "red", "purple", "orange")
    DEFAULT_COLOR = "marine"
    MAX_PER_USER = 20

    id = Column(Integer, primary_key=True, autoincrement=True)
    reader_id = Column(Integer, ForeignKey("readers.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(String(500), default="", nullable=False)
    color = Column(String(16), nullable=False, default=DEFAULT_COLOR)
    is_public = Column(Boolean, nullable=False, default=False)
    is_sticky = Column(Boolean, nullable=False, default=False)
    sticky_order = Column(Integer, nullable=True)
    guest_read = Column(Boolean, nullable=False, default=False)
    view_count = Column(Integer, nullable=False, default=0)
    like_count = Column(Integer, nullable=False, default=0)
    book_count = Column(Integer, nullable=False, default=0)
    create_time = Column(DateTime, nullable=False)
    update_time = Column(DateTime, nullable=False)

    reader = relationship(Reader)

    __table_args__ = (
        Index("ix_booklist_reader", "reader_id", "update_time"),
        Index("ix_booklist_public", "is_public", "is_sticky", "update_time"),
    )

    def __init__(self, reader_id, name, description="", color=None, is_public=False):
        super(BookList, self).__init__()
        self.reader_id = reader_id
        self.name = name
        self.description = description or ""
        self.color = color if color in self.COLORS else self.DEFAULT_COLOR
        self.is_public = is_public
        self.is_sticky = False
        self.guest_read = False
        self.view_count = 0
        self.like_count = 0
        self.book_count = 0
        now = datetime.datetime.now()
        self.create_time = now
        self.update_time = now


class BookListBook(Base, SQLAlchemyMixin):
    """书单-书籍关联表。book_id 不建跨库外键（Calibre 库独立管理，同 Item.book_id 的做法），
    书籍被删除后本表记录成为悬空引用，展示层需要跳过/兼容。"""

    __tablename__ = "booklist_books"

    id = Column(Integer, primary_key=True, autoincrement=True)
    booklist_id = Column(Integer, ForeignKey("booklists.id"), nullable=False)
    book_id = Column(Integer, nullable=False)
    update_time = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("booklist_id", "book_id", name="ux_booklist_book"),
        Index("ix_booklist_books_booklist", "booklist_id", "update_time"),
    )

    def __init__(self, booklist_id, book_id):
        super(BookListBook, self).__init__()
        self.booklist_id = booklist_id
        self.book_id = book_id
        self.update_time = datetime.datetime.now()


class BookListLike(Base, SQLAlchemyMixin):
    """书单点赞/收藏关系表。侧边栏"收藏书单" = 当前用户在本表中的所有记录对应的书单。"""

    __tablename__ = "booklist_likes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    booklist_id = Column(Integer, ForeignKey("booklists.id"), nullable=False)
    reader_id = Column(Integer, ForeignKey("readers.id"), nullable=False)
    create_time = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("booklist_id", "reader_id", name="ux_booklist_like"),
        Index("ix_booklist_likes_reader", "reader_id", "create_time"),
    )

    def __init__(self, booklist_id, reader_id):
        super(BookListLike, self).__init__()
        self.booklist_id = booklist_id
        self.reader_id = reader_id
        self.create_time = datetime.datetime.now()


class BookVisit(Base, SQLAlchemyMixin):
    """用户最近浏览过的书籍（详情页），见 document/Share_Visits_GuestBooklist_Design.md。
    (reader_id, book_id) 为主键，重复访问只刷新 visit_time；每个用户最多保留 MAX_PER_USER 条。"""

    __tablename__ = "book_visits"

    MAX_PER_USER = 100

    reader_id = Column(Integer, ForeignKey("readers.id"), primary_key=True)
    book_id = Column(Integer, primary_key=True)
    visit_time = Column(DateTime, nullable=False)

    __table_args__ = (Index("ix_book_visits_reader_time", "reader_id", "visit_time"), )

    def __init__(self, reader_id, book_id, visit_time=None):
        super(BookVisit, self).__init__()
        self.reader_id = reader_id
        self.book_id = book_id
        self.visit_time = visit_time or datetime.datetime.now()


class BookShare(Base, SQLAlchemyMixin):
    """管理员创建的匿名分享链接，每本书至多一条。取消为 status=0，删除为物理删除。"""

    __tablename__ = "book_shares"

    STATUS_ACTIVE = 1
    STATUS_CANCELLED = 0

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, nullable=False, unique=True)
    token = Column(String(64), nullable=False, unique=True)
    password = Column(String(32), nullable=False, default="")
    allow_read = Column(Boolean, nullable=False, default=True)
    allow_download = Column(Boolean, nullable=False, default=False)
    expire_time = Column(DateTime, nullable=True)
    max_views = Column(Integer, nullable=False, default=0)
    view_count = Column(Integer, nullable=False, default=0)
    status = Column(Integer, nullable=False, default=STATUS_ACTIVE)
    creator_id = Column(Integer, ForeignKey("readers.id"), nullable=False)
    create_time = Column(DateTime, nullable=False)
    update_time = Column(DateTime, nullable=False)

    __table_args__ = (Index("ix_book_shares_status", "status", "update_time"), )

    def __init__(self, book_id, token, creator_id, password="", allow_read=True, allow_download=False, expire_time=None, max_views=0):
        super(BookShare, self).__init__()
        self.book_id = book_id
        self.token = token
        self.creator_id = creator_id
        self.password = password or ""
        self.allow_read = allow_read
        self.allow_download = allow_download
        self.expire_time = expire_time
        self.max_views = max_views or 0
        self.view_count = 0
        self.status = self.STATUS_ACTIVE
        now = datetime.datetime.now()
        self.create_time = now
        self.update_time = now

    def is_expired(self, now=None):
        return self.expire_time is not None and self.expire_time <= (now or datetime.datetime.now())

    def is_exhausted(self):
        return self.max_views > 0 and self.view_count >= self.max_views

    def is_valid(self, now=None):
        return self.status == self.STATUS_ACTIVE and not self.is_expired(now) and not self.is_exhausted()


class BookTakedown(Base, SQLAlchemyMixin):
    """版权下架记录：应版权人要求停止提供某本书的阅读与下载。

    书本身仍留在书库里（书目信息、封面、统计都保留），只是不再向任何读者
    提供正文；这样做既满足下架要求，也能在详情页展示「请购买正版」的引导。
    记录原因/操作人/书名快照是为了日后应对版权方核查时留痕。
    """

    __tablename__ = "book_takedowns"

    book_id = Column(Integer, primary_key=True)
    title = Column(String(1000), nullable=False, default="")
    reason = Column(String(2000), nullable=False, default="")
    operator = Column(String(200), nullable=False, default="")
    operator_id = Column(Integer, nullable=False, default=0)
    create_time = Column(DateTime, nullable=False)

    def __init__(self, book_id, title="", reason="", operator="", operator_id=0):
        self.book_id = int(book_id)
        self.title = title or ""
        self.reason = reason or ""
        self.operator = operator or ""
        self.operator_id = operator_id or 0
        self.create_time = datetime.datetime.now()

    def as_dict(self):
        return {
            "book_id": self.book_id,
            "title": self.title,
            "reason": self.reason,
            "operator": self.operator,
            "operator_id": self.operator_id,
            "create_time": self.create_time.isoformat() if self.create_time else None,
        }


class MyNexusBookAnalysis(Base, SQLAlchemyMixin):
    __tablename__ = "mynexus_book_analyses"

    book_id = Column(Integer, primary_key=True)
    remote_book_id = Column(String(64), nullable=False, default="")
    status = Column(String(32), nullable=False, default="pending")
    progress = Column(Integer, nullable=False, default=0)
    error_msg = Column(Text, nullable=False, default="")
    reading_guide = Column(Text, nullable=False, default="")
    response_json = Column(Text, nullable=False, default="{}")
    update_time = Column(DateTime, nullable=False)

    def __init__(self, book_id, status="pending"):
        self.book_id = book_id
        self.status = status
        self.progress = 0
        self.error_msg = ""
        self.reading_guide = ""
        self.response_json = "{}"
        self.update_time = datetime.datetime.now()


class MyNexusChatSession(Base, SQLAlchemyMixin):
    __tablename__ = "mynexus_chat_sessions"

    reader_id = Column(Integer, ForeignKey("readers.id"), primary_key=True)
    book_id = Column(Integer, primary_key=True)
    remote_session_id = Column(String(64), nullable=False)
    update_time = Column(DateTime, nullable=False)

    __table_args__ = (Index("ix_mynexus_chat_sessions_book", "book_id", "reader_id"), )

    def __init__(self, reader_id, book_id, remote_session_id):
        self.reader_id = reader_id
        self.book_id = book_id
        self.remote_session_id = remote_session_id
        self.update_time = datetime.datetime.now()


def user_syncdb(engine):
    Base.metadata.create_all(engine)


# 表结构随功能迭代新增的表，不希望依赖运维方手动重新执行 `--syncdb` 才能用上
# （`docker/start.sh` 每次启动都会跑 --syncdb，但手工部署/测试环境不一定会），
# 在正常的 make_app() 启动路径里也顺带补建一次，checkfirst=True 天然幂等。
_NEW_TABLES_AUTO_ENSURE = (ReadingRecord, BookReview, InstalledTool, BookReadingStats, BookList, BookListBook, BookListLike, ManualReadingLog, BookVisit, BookShare, BookTakedown, ScanDirSnapshot, MyNexusBookAnalysis, MyNexusChatSession, KoreaderPosition, AudioPlayback)


def ensure_new_tables(engine):
    Base.metadata.create_all(engine, tables=[m.__table__ for m in _NEW_TABLES_AUTO_ENSURE], checkfirst=True)


# 模块被重新 import 时把已绑定的 session 接过来。
#
# 触发场景：`tests/` 里有些文件为了不装 calibre 就往 sys.modules 塞假的
# `webserver` 包，事后 pop 掉；下一次 `import webserver.models` 会重新执行本
# 文件，得到一整套新的类。旧模块上的绑定若不继承，`ScanFile._session()` 之类
# 会直接退到基类默认实现。见 `_BOUND_SESSION` 上方的注释。
def _pick_up_previous_module():
    import importlib.util

    previous = None
    for mod in list(sys.modules.values()):
        if mod is None:
            continue
        if getattr(mod, "__file__", None) != __file__:
            continue
        if mod is sys.modules.get(__name__):
            continue
        if hasattr(mod, "_BOUND_SESSION"):
            previous = mod
    return previous


try:
    _inherit_session_from_previous_module(_pick_up_previous_module())
except Exception:  # noqa: BLE001 - 继承失败不该阻止模块导入
    logging.exception("models: failed to inherit bound session from previous module")
