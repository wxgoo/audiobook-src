#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""站点时区：把 UTC 时刻换算成「站点的一天」。

阅读统计按天分桶（``readings.date``；书级 ``book_reading_stats`` 只有时刻列，判天时同样
按站点时区现算），而库里所有时刻存的都是 UTC naive datetime。分桶用的日期必须落在站点时区上：UTC+8 的读者在北京时间 00:00~08:00
的阅读，UTC 日期还停在前一天，会被记到前一天（跨天连击、热力图、今日时长全部跟着错），
补录当天的阅读还会被判成「未来时间」。

容器时区设成 Asia/Shanghai 也解决不了这个问题——分桶点是硬编码的 ``utcnow().date()``，
跟 OS 时区无关。所以这里显式给出一份「站点的一天」的定义：

- ``site_timezone`` 显式配置（IANA 名，如 ``Asia/Shanghai``）时用它；
- 留空或 ``auto`` 时跟随站点语言：简繁中文 UTC+8、英文 UTC（``site_language`` 也是
  ``auto`` 时按服务器系统语言判，而不是按请求的 Accept-Language——按天分桶是站点级
  决定，同一个站点不能因为访客浏览器语言不同就把同一次阅读算到不同的两天）。

时区名的解析结果按 (site_timezone, site_language) 缓存，管理员改设置后无需重启即生效。
"""

import datetime
import logging
from typing import Optional

from webserver import loader
from webserver.i18n import detect_system_language, normalize_language

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9
    ZoneInfo = None

CONF = loader.get_settings()

AUTO = "auto"

# 站点语言 → 默认时区。规范化语言不在表里（含空值）时按默认语言 zh 处理，即 UTC+8。
TIMEZONE_BY_LANGUAGE = {
    "zh": "Asia/Shanghai",
    "zh-TW": "Asia/Shanghai",
    "en": "UTC",
}
FALLBACK_TIMEZONE = TIMEZONE_BY_LANGUAGE["zh"]

# zoneinfo 取不到 tzdata 时的兜底（Windows 未装 tzdata / 精简镜像）：只覆盖设置页可选的
# 常用时区，夏令时地区按标准时偏移折算，误差最多 1 小时，不会因为查不到库而退回 UTC
# 把整个站点的日期算错 8 小时。
FALLBACK_UTC_OFFSETS = {
    "UTC": 0,
    "Asia/Shanghai": 8,
    "Asia/Hong_Kong": 8,
    "Asia/Taipei": 8,
    "Asia/Singapore": 8,
    "Asia/Tokyo": 9,
    "Asia/Seoul": 9,
    "Asia/Bangkok": 7,
    "Asia/Kolkata": 5.5,
    "Europe/Berlin": 1,
    "Europe/London": 0,
    "America/Sao_Paulo": -3,
    "America/New_York": -5,
    "America/Los_Angeles": -8,
    "Australia/Sydney": 10,
}

# 名字在 FALLBACK_UTC_OFFSETS 之外、本机又取不到 tzdata 时的粗粒度兜底：按 IANA 名的
# 大区前缀取近似偏移（同样按标准时折算，夏令时地区最多差 1 小时）。比直接退回站点语言
# 默认更贴近管理员的意图——中文站的 ``America/Chicago`` 应为 -6 左右，退回语言默认会变成
# +8，差 14 小时；按前缀给 -5 只差 1 小时。命中时会打 warning 说明这是近似值。
FALLBACK_REGION_OFFSETS = (
    ("Asia/", 8),
    ("Europe/", 1),
    ("America/", -5),
    ("Australia/", 10),
    ("Pacific/", 10),
    ("Africa/", 1),
    ("Atlantic/", 0),
    ("Indian/", 5.5),
    ("Etc/", 0),
    ("US/", -5),
)


def _fallback_offset_by_region(name: str) -> Optional[float]:
    """按大区前缀猜一个近似 UTC 偏移；没有匹配的前缀返回 None。"""
    for prefix, offset in FALLBACK_REGION_OFFSETS:
        if name.startswith(prefix):
            return offset
    return None


def _tzdata_available() -> bool:
    """本机能否真正按 IANA 名加载 tzinfo（Windows 未装 tzdata / 精简镜像时为 False）。"""
    if ZoneInfo is None:
        return False
    try:
        ZoneInfo(FALLBACK_TIMEZONE)
        return True
    except Exception:
        return False


# 单条缓存：键是设置项原文，管理员改完设置下次调用自然重算，不用注册任何失效回调。
_cached_key = None
_cached_name = None
_cached_tz = None


def default_timezone_name(lang: str = "") -> str:
    """站点语言对应的默认时区名（简繁中文 UTC+8，英文 UTC）。"""
    return TIMEZONE_BY_LANGUAGE.get(normalize_language(lang), FALLBACK_TIMEZONE)


def _language_default_name() -> str:
    """站点语言（``auto`` 时再退到服务器系统语言）推导出的默认时区名。"""
    lang = CONF.get("site_language", "")
    if normalize_language(lang) not in TIMEZONE_BY_LANGUAGE:
        lang = detect_system_language()
    return default_timezone_name(lang)


def resolve_timezone_name() -> str:
    """当前生效的时区名（已校验；填错时是回退后的那个名字）。"""
    return _resolve()[0]


def _load_tzinfo(name: str) -> Optional[datetime.tzinfo]:
    """按 IANA 名加载 tzinfo；名字不认识时返回 None，由调用方决定兜底。"""
    if ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    offset = FALLBACK_UTC_OFFSETS.get(name)
    if offset is not None:
        return datetime.timezone(datetime.timedelta(hours=offset), name)
    return None


def _resolve():
    """(生效时区名, tzinfo)。按设置项原文缓存，管理员改完设置下次调用自然重算。

    设置项填错（IANA 名拼错等）时回退到语言默认，而不是 UTC：一个笔误的时区名退回
    UTC，正好把站点又按错 8 小时，正是这个设置项要修的问题。
    """
    global _cached_key, _cached_name, _cached_tz
    key = (
        str(CONF.get("site_timezone", AUTO) or "").strip(),
        str(CONF.get("site_language", "")),
    )
    if key != _cached_key:
        raw = key[0]
        name = raw if raw and raw.lower() != AUTO else _language_default_name()
        tz = _load_tzinfo(name)
        if tz is None:
            # 分辨「IANA 名拼错」与「本机没有 tzdata」：后者连站点默认时区都加载不出来，
            # 说明名字本身大概率没错，只是查不到库——按大区前缀给近似偏移并保留原名；
            # 前者（能加载默认时区、唯独这个名字不行）才回退到语言默认。
            region_offset = None if _tzdata_available() else _fallback_offset_by_region(name)
            if region_offset is not None:
                logging.warning(
                    "site_timezone %s 无法解析（可能未安装 tzdata），暂按大区近似偏移 UTC%+g 处理",
                    name,
                    region_offset,
                )
                tz = datetime.timezone(datetime.timedelta(hours=region_offset), name)
        if tz is None:
            fallback = _language_default_name()
            logging.warning("site_timezone %s 无法识别，回退到 %s", name, fallback)
            name = fallback
            tz = _load_tzinfo(name) or datetime.timezone.utc
        _cached_name = name
        _cached_tz = tz
        _cached_key = key
        logging.info("站点时区：%s", name)
    return _cached_name, _cached_tz


def get_tzinfo() -> datetime.tzinfo:
    """当前生效时区的 tzinfo。"""
    return _resolve()[1]


def site_date(instant: Optional[datetime.datetime] = None) -> datetime.date:
    """把 UTC 时刻换算成站点时区下的日期。

    入参是库里那种 naive UTC datetime（``utcnow()`` / calibre 存法）；带 tzinfo 的时刻也接受。
    不传则取当前时刻。
    """
    if instant is None:
        instant = datetime.datetime.now(datetime.timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=datetime.timezone.utc)
    return instant.astimezone(get_tzinfo()).date()


def site_today() -> datetime.date:
    """站点时区下的今天。"""
    return site_date()


def site_now() -> datetime.datetime:
    """站点时区下带 tzinfo 的当前时刻。"""
    return datetime.datetime.now(datetime.timezone.utc).astimezone(get_tzinfo())


def site_month_bounds_server_local(
        day: Optional[datetime.date] = None,
        server_tz: Optional[datetime.tzinfo] = None):
    """本月起止，返回可用于 SQL 过滤的服务器本地 naive datetime 边界。

    上游 v4.6.1 的做法：阅读统计里的「本月」不能按容器时区切（``extract('month',
    read_date)`` 用的就是容器时区），站点时区设成别的（比如 UTC-5）时，月初那几
    小时会被算进上个月。这里取「站点时区的本月 1 号 00:00」和「下月 1 号 00:00」，
    各自转回 **naive 的服务器本地时刻**——因为库里时刻列都是 naive UTC、
    ``read_date`` 比较时用的也是这个口径，直接拿带 tzinfo 的量去比会错位。

    返回 ``(start, end)``，半开区间：``start <= read_date < end``。

    ``day`` 指定「哪个月」（默认取站点时区的今天），``server_tz`` 指定服务器时区
    （默认按本机时区，测试里注入 UTC 用）；两者都不传时行为与原来完全一致。
    """
    tz = get_tzinfo()
    if day is None:
        day = datetime.datetime.now(tz).date()
    month_start = datetime.datetime(day.year, day.month, 1, tzinfo=tz)
    year, month = month_start.year, month_start.month
    if month == 12:
        next_month = month_start.replace(year=year + 1, month=1)
    else:
        next_month = month_start.replace(month=month + 1)

    def to_server_naive(aware):
        # 站点时刻 → 服务器本地 naive。read_date 存的是 datetime.now()
        # （容器本地、naive，见 models.py ReadingState），比较口径必须一致；
        # astimezone() 不带参数即按服务器本地时区转换（测试可注入 server_tz）。
        if server_tz is not None:
            return aware.astimezone(server_tz).replace(tzinfo=None)
        return aware.astimezone().replace(tzinfo=None)

    return to_server_naive(month_start), to_server_naive(next_month)


def timezone_label() -> str:
    """展示串，例如 ``UTC+08:00 (Asia/Shanghai)``，用于设置页提示与启动日志。"""
    offset = site_now().utcoffset() or datetime.timedelta(0)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    return "UTC%s%02d:%02d (%s)" % (
        sign,
        total_minutes // 60,
        total_minutes % 60,
        resolve_timezone_name(),
    )
