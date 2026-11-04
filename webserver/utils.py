#!/usr/bin/env python3
import asyncio
import contextvars
import datetime
import functools
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from webserver import constants, loader, perf

# 联网任务线程池：信息源插件搜索、AI 请求等长任务（单次可达分钟级）放这里执行。
# tornado 是单线程事件循环，在 handler 里同步等一次网络请求会把全站请求（包括不碰
# 数据库的 /api/user/info）一起冻住。
blocking_pool = ThreadPoolExecutor(max_workers=6 if perf.lite_on("LITE_POOLS_SMALL") else int(loader.get_settings().get("BLOCKING_POOL_SIZE", 20)), thread_name_prefix="mybooks-blocking")

# calibre 查询专用池：与联网长任务隔离。若混用一池，20 个并发联网搜索打满时，
# 阅读链路的毫秒级 calibre 查询（get_book_async）要排在网络任务后面，最坏等分钟级。
calibre_pool = ThreadPoolExecutor(max_workers=2 if perf.lite_on("LITE_POOLS_SMALL") else int(loader.get_settings().get("CALIBRE_POOL_SIZE", 4)), thread_name_prefix="mybooks-calibre")


def bind_threadpool_call(func, *args, **kwargs):
    """把「提交时刻的 contextvars 快照」绑定到调用上，返回可直接交给 run_in_executor 的
    无参 callable。

    ``loop.run_in_executor()`` **不会**把 contextvars 带进工作线程。mybooks 里依赖它的有
    ``webserver/i18n.py`` 的 ``_current_language``（请求语言）：不带过去的话，线程池里调
    ``_()`` 会退回 ``DEFAULT_LANGUAGE``，返回给客户端的消息就变成另一种语言（站点语言设为
    en 而系统默认 zh 时尤其明显）。每个调用都取一份新快照，用完即弃，不会污染池线程。
    """
    ctx = contextvars.copy_context()
    call = functools.partial(func, *args, **kwargs)
    return lambda: ctx.run(call)


async def run_in_threadpool(func, *args, **kwargs):
    """把联网等长阻塞任务丢到 blocking_pool 执行并返回结果。

    calibre 数据库调用走 BaseHandler.run_calibre_async（calibre_pool），不与本池混跑。
    注意：工作线程里绝不能触碰 handler 的 sqlite_session——SQLAlchemy scoped_session
    是线程本地的，mybooks 自身的 sqlite 查询必须留在 ioloop 线程；本池里的 calibre
    调用不持 db_lock，正确性由 calibre Cache 自带的读写锁保证。
    请求上下文（contextvars，含 i18n 请求语言）由 bind_threadpool_call 显式带进线程。
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        blocking_pool, bind_threadpool_call(func, *args, **kwargs)
    )


# 匹配包含z-library的括号内容，例如 (z-library.sk, 1lib.sk, z-lib.sk)
ZLIBRARY_PATTERN = re.compile(r'\([^)]*?(?:z-?lib(?:rary)?|1lib)[^)]*?\)', re.IGNORECASE)

# 日文假名 Unicode 区间：平假名 U+3040-309F，片假名 U+30A0-30FF
_KANA_PATTERN = re.compile(r'[぀-ヿ]')

# CJK 汉字区间：基本区 U+4E00-9FFF，扩展 A 区 U+3400-4DBF
_HAN_PATTERN = re.compile(r'[一-鿿㐀-䶿]')


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y年%m月%d日", "%Y年%m月", "%Y年", "%Y"):
        try:
            return datetime.datetime.strptime(date_str, fmt).replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
    return None


def meta_writable_formats():
    """可回写元数据的格式；DJVU 依赖 djvu_meta 插件，未加载时自动排除。"""
    from calibre.customize.ui import can_set_metadata

    return [f for f in constants.META_WRITABLE_FORMATS if can_set_metadata(f)]


# 文件名里作者信号的三类形态。这里只做「找」不做「拆」，找到就用，找不到就放弃。
# 1) 显式中文标注：作者：张三 / 作者 张三。
#    候选在空白或分隔符处截断——`作者：张三 三体.pdf` 里的"三体"是书名不是人名，
#    贪婪吃到 20 字会把作者+书名粘成一串写进书库。
_FN_AUTHOR_LABEL = re.compile(r'(?:作者|著者)\s*[:：]?\s*([^\s\(\)\[\]【】《》,，;；:：/\\\-–—_]{2,20})')
# 2) 独立括号包裹：`[燕晓] 书名` / `书名 (燕晓)` / `【燕晓】书名`
_FN_AUTHOR_BRACKET = re.compile(r'[\[\(【（]\s*([^\[\]\(\)【】（）]{2,20})\s*[\]\)】）]')
# 3) 分隔符分段：`书名 - 张三` / `书名_张三` / `书名 — 张三`。
#    用 finditer 逐个取段而不用「锚定结尾」，因为书源常见
#    `三体 - 刘慈欣 - 重庆出版社.pdf` 这种「书名-作者-出版社」三段式：
#    只认最后一段会取到出版社再被噪声词否掉，白白丢掉中间的真作者。
#    段内不允许空格/中点之外的停顿，`上半部 下半部` 这种描述性片段要整段拒掉。
_FN_AUTHOR_TAIL = re.compile(r'[-–—_]\s*([^\s\-–—_][^-–—_]{0,19})(?=[-–—_]|$)')
# 4) 英文 by：只认「by + 多词人名」（by Randal E. Bryant）。
#    "Stand by Me"、"Live by Night" 这类标题里 by 后面也是大写词，靠词数区分不开，
#    所以要求至少两段——西文作者署名几乎都带姓+名，单词署名交给分隔符形态处理。
_FN_AUTHOR_BY = re.compile(r'(?<![A-Za-z])by\s+([A-Z][A-Za-z.\'-]*(?:\s+[A-Z][A-Za-z.\'-]*)+)')

# 这些词出现在候选里说明抓到的不是人名（出版社/系列/文件属性之类）
_FN_AUTHOR_NOISE = ("出版", "书局", "书店", "公司", "集团", "press", "publisher",
                    "edition", "版", "卷", "册", "全集", "套装", "扫描", "整理", "编",
                    "译", "著", "pdf", "epub", "txt", "mobi", "azw3", "djvu")

# 候选必须是「像人名」的短串：不含书名号/括号/分隔符/扩展名，也不含数字
_FN_AUTHOR_BAD_CHARS = re.compile(r'[0-9,，。、;；:：!！?？"\'“”‘’（）\(\)\[\]【】《》<>/\\|@#$%^&*+=~`]')

# 全西文 + 空格分隔的人名形态（John Smith / Randal E. Bryant / J.K. Rowling）
_FN_LATIN_NAME = re.compile(r"[A-Z][A-Za-z.'\-]*(?:\s+[A-Z][A-Za-z.'\-]*)+")


def guess_author_from_filename(name):
    """从文件名里找作者，找不到返回 None。

    4.6.0-18 新增。此前扫描导入在 PDF_TILE_WITH_FILE_NAME=True 时把作者**无条件**
    改写成"佚名"，而文件名往往就写着作者（如「秒懂速解小学数字画图 - 燕晓.pdf」），
    结果书详情页显示「作者：佚名」——明明有信息却没用。

    策略是**保守**：只认三类明确信号（显式「作者：」标注、独立括号包裹、
    分隔符结尾），并且候选必须通过人名形态校验。宁可返回 None 让上层填"佚名"，
    也绝不把出版社、系列名、版本号误当作者写进书库。

    注意：本函数只负责「找作者」，标题一律不拆——标题该用内嵌元数据，
    文件名的整串在 calibre 眼里只是兜底，拆错标题比作者为空更难让用户发现。
    """
    if not name:
        return None
    text = str(name).strip()
    if not text:
        return None
    # 调用方一般已经剥掉扩展名，但函数自己再兜一层：否则 `书名 - 燕晓.pdf` 的
    # 分隔符形态会连扩展名一起吞进候选（"燕晓.pdf"），再被 _looks_like_author
    # 的 pdf 噪声词否掉，白白漏掉一个真作者。
    if "." in text:
        head, _dot, tail = text.rpartition(".")
        if head and 2 <= len(tail) <= 5 and tail.isalnum() and not tail.isdigit():
            text = head.strip()
    if not text:
        return None

    # 三类信号里取「最靠右」的那个候选：书源命名习惯是「书名在前、作者在后」，
    # 靠右的片段比靠左的更可能是作者。同位置时按 标签 > 括号 > 分隔符 的确定性排序。
    best = None  # (position, -priority, candidate)
    for priority, pattern in enumerate((_FN_AUTHOR_LABEL, _FN_AUTHOR_BRACKET, _FN_AUTHOR_TAIL, _FN_AUTHOR_BY)):
        for m in pattern.finditer(text):
            raw = next((g for g in m.groups() if g), None)
            if not raw:
                continue
            candidate = raw.strip()
            if not _looks_like_author(candidate):
                continue
            key = (m.start(), -priority)
            if best is None or key > best[0]:
                best = (key, candidate)
    return best[1] if best else None


def _looks_like_author(candidate):
    """候选片段是否像人名。宽松到能收「列夫·托尔斯泰」，严格到能挡住「延边大学出版社」。"""
    if not candidate:
        return False
    if not (2 <= len(candidate) <= 20):
        return False
    if _FN_AUTHOR_BAD_CHARS.search(candidate):
        return False
    lowered = candidate.lower()
    if any(noise in lowered for noise in _FN_AUTHOR_NOISE):
        return False
    # 含空格的候选要看形态：中文 + 空格基本是「上半部 下半部」这类描述性片段，
    # 直接拒；全西文的多词串（John Smith / Randal E. Bryant）是正常人名，放行。
    if re.search(r'[\s\u3000]', candidate) and not _FN_LATIN_NAME.fullmatch(candidate):
        return False
    # 纯数字、年份、页码之类直接否掉
    if re.fullmatch(r'\d+', candidate):
        return False
    return True


def remove_zlibrary_suffix(text):
    """移除文件名中包含z-library的括号内容"""
    if not text:
        return text
    return ZLIBRARY_PATTERN.sub('', text).strip()


def guess_title_author_from_filename(name):
    if not name:
        return name, None
    title = name.strip()
    author = None
    if "作者" in title:
        parts = re.split(r"作者[:：]", title, maxsplit=1)
        if len(parts) >= 2:
            title = parts[0].strip()
            author = parts[1].strip()
            # 去除title尾部的([（，【四种符号，author尾部的）】]四种符号
            title = re.sub(r'[\s\(\[【（，,、]+$', '', title)
            if title.startswith('《') and title.endswith('》'):
                title = title[1:-1]
            author = re.sub(r'[\s\)\]】）]+$', '', author)
    return title, author


def ascii_text(orig):
    from calibre.utils.localization import get_udc
    from calibre.constants import preferred_encoding
    udc = get_udc()
    try:
        ascii = udc.decode(orig)
    except Exception:
        if isinstance(orig, str):
            orig = orig.encode('ascii', 'replace')
        ascii = orig.decode(preferred_encoding, 'replace')
    if isinstance(ascii, bytes):
        ascii = ascii.decode('ascii', 'replace')
    return ascii.strip()


def get_title_sort(title):
    if not title:
        return title
    try:
        return ascii_text(title).lower()
    except Exception as e:
        logging.error(f"Error converting title to ASCII for sorting: {e}")
        return title


# 常见繁体中文专有字符（在 Simplified 中对应不同字形），用于 fallback 检测
_TRADITIONAL_ONLY_CHARS = frozenset(
    "書電來說話這個時會對學問國務現實際應當來們點進開關處還"
    "歡樂體動設計資訊傳說標準環境網絡變換預算發展運動認識"
    "義務條件結構機制選擇統計監督繼續識別溝通維護數據處理"
    "歷史文化藝術哲學經濟組織機構協議協作協調決策執行方針"
    "與並從內外長短廣狹強弱快慢遠近輕重高低深淺寬窄早晚"
    "後前左右東西南北上下中外新舊多少大小"
    # 常見繁體字
    "與與來來說說國國時時個個會對對學問問處還還變發電書樂"
)


@functools.lru_cache(maxsize=8)
def get_opencc(profile):
    import opencc
    return opencc.OpenCC(profile)


def _fallback_has_traditional(text: str) -> bool:
    return any(c in _TRADITIONAL_ONLY_CHARS for c in text)


def is_traditional_chinese(text: str) -> bool:
    if not text:
        return False
    # 若全为 ASCII，直接跳过
    if all(ord(c) < 128 for c in text):
        return False

    try:
        converted = get_opencc("t2s").convert(text)
        return converted != text
    except Exception as exc:
        logging.debug("[review_cht] OpenCC unavailable (%s), using fallback", exc)
        return _fallback_has_traditional(text)


def detect_title_language(text: str) -> Optional[str]:
    """检测书名文本对应的语言代码（简体中文/繁体中文/日文）。

    判定顺序：繁体中文 > 简体中文 > 日文 > 简繁同形兜底。中文的判定优先于
    日文，是因为日文汉字与繁/简体中文汉字大量重叠，若假名检测放在最前，
    会让本应识别为中文的书名（尤其是含少量假名标点的情况）被误判，因此
    仅在确认不含中文特征后才回退到假名检测。

    若标题中的汉字在简繁转换前后完全一致（即该标题不含任何简繁差异字，
    如"九命"），繁简双向转换都无法区分，此时只要标题含汉字且不含假名，
    按约定优先判定为简体中文，而非放弃判定。

    :param text: 书名文本。
    :return: `constants.TRADITIONAL_CHINESE_CODE` / `constants.DEFAULT_LANGUAGE_CODE`
             / `constants.JAPANESE_CODE`，无法判定时返回 None。
    """
    if not text:
        return None
    if all(ord(c) < 128 for c in text):
        return None

    if is_traditional_chinese(text):
        return constants.TRADITIONAL_CHINESE_CODE

    try:
        if get_opencc("s2t").convert(text) != text:
            return constants.DEFAULT_LANGUAGE_CODE
    except Exception as exc:
        logging.debug("[detect_title_language] OpenCC unavailable (%s), skip simplified check", exc)

    if _KANA_PATTERN.search(text):
        return constants.JAPANESE_CODE

    if _HAN_PATTERN.search(text):
        return constants.DEFAULT_LANGUAGE_CODE

    return None


def compare_books_by_rating_or_id(x, y):
    a = x.get("rating", 0) or 0
    b = y.get("rating", 0) or 0

    if a != b:
        return 1 if a > b else -1
    return 1 if x["id"] > y["id"] else -1


def compare_books_by_series_index_or_name(x, y):
    x_index = x.get("series_index", 0) or 0
    y_index = y.get("series_index", 0) or 0

    if x_index != y_index:
        return 1 if x_index > y_index else -1

    x_title_sort = x.get("sort", "") or ""
    y_title_sort = y.get("sort", "") or ""
    result = 1 if x_title_sort > y_title_sort else -1
    return result


def super_strip(s):
    return ''.join(c for c in s.strip() if c.isprintable())


# 「网站默认访问链接」（SITE_URL）：只接受带主机名的 http/https 绝对地址，
# 路径部分不接受查询串/片段——调用方会直接在末尾追加 /opds、/podcast 等路由。
_SITE_URL_RE = re.compile(r"^https?://[^\s/?#]+(?:/[^\s?#]*)?$")


def normalize_site_url(value):
    """规范化管理员配置的「网站默认访问链接」。

    去首尾空白与结尾斜杠（多个一并剥掉），否则会拼出 ``https://host//s/token``
    这类重复斜杠。查询串和片段也会被拒绝：它们是基地址，追加路由后 ``?``/``#``
    之后的内容会变成查询或片段，链接到不了目标页面。
    既不是合法地址也不是空串时一律返回 ""（视为未配置），调用方据此决定是报错
    还是当作清空。
    """
    text = str(value or "").strip()
    if not text or not _SITE_URL_RE.match(text):
        return ""
    return text.rstrip("/")


def is_timezone_name(value) -> bool:
    """形态校验 IANA 时区名（``auto`` 也走这条，它本身是合法形态）。

    只挡空格、引号、超长这类脏值，不查库：名字是否真的存在留给 webserver/site_time.py
    在运行时解析——精简镜像缺 tzdata 时合法名字也查不到，在这里拦会把对的也拒了。
    """
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9_+\-./]{0,63}$", str(value or "").strip()))


# 为保持向后兼容，从新位置重新导出
from webserver.base.formatter import SimpleBookFormatter, MCPBookFormatter, BookFormatter, ReadingStateFormatter

__all__ = ["SimpleBookFormatter", "MCPBookFormatter", "BookFormatter", "ReadingStateFormatter"]


if __name__ == "__main__":
    # 测试_guess_title_author_from_filename
    test_cases = [
        "《宝鉴》（校对版全本）作者：打眼",
        "《三体》作者：刘慈欣",
        "《平凡的世界（》作者：路遥",
        "《无人生还》(作者：阿加莎·克里斯蒂)",
        "《通天之路》（校对版全本）作者：无罪"
    ]
    for filename in test_cases:
        title, author = guess_title_author_from_filename(filename)
        print(f"Filename: {filename}\n  Title: {title}\n  Author: {author}\n")
