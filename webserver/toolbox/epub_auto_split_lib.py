# -*- coding: UTF-8 -*-
"""合集 EPUB 自动分册检测引擎。

目标：给定一本“套装/全集/合集”EPUB 的章节列表（SplitEpub.get_split_lines()
的产物），自动推断出“每一册”的边界，输出若干候选分册：

    [
      {"name": "红高粱家族", "start": 2, "end": 4, "chapter_count": 3,
       "reason": "目录顶层标题 + 封面页", "confidence": 0.95},
      ...
    ]

start / end 是 split_lines 里的 num（含端点）。前端可据此做“微调”（改边界、
改名、删除、合并），再把最终分组交给 EpubAutoSplitTool.batch_split 真正拆书。

识别信号（按可靠性从高到低）：
  1. 目录顶层 navPoint 文本变化（toc[0]）——合集里顶层通常就是“书名/册名”。
  2. “封面”页——每册开头常有一张 title=封面 的页，标志新书开始。
  3. 册名文字规律——标题/目录里出现 “第X册/卷/部/集”“（上/中/下）”“全X册”
     “I / II / III”“Book N / Vol.N” 等。
  4. 章节序号回退——章号从大变小（如第三章→第一章），强烈暗示换了新书。

设计原则：宁可“多给候选、让用户微调”，也不要漏掉。所有启发式都只用来产生
候选边界并打分，最终决定权在前端用户手里（本项目选择了“自动识别可微调”）。

@author: MyBooks 定制
"""
import logging
import re

from webserver.toolbox.epub_split_lib import get_title_of_html, strip_html

logger = logging.getLogger(__name__)

# 封面页标题（大小写/空白不敏感）
_COVER_TITLES = {"封面", "cover", "封面页", "front cover", "frontcover"}
# 明显不是册名、应当忽略的目录文本
_IGNORE_TOC_TEXT = {
    "目录", "目次", "contents", "content", "toc", "前言", "序言", "序",
    "后记", "后序", "出版说明", "内容简介", "作者简介", "版权页", "版权信息",
    "扉页", "题记", "引言", "导读", "附录", "索引", "封底", "封底页",
}

# 册名规律（用于从 toc[0] / 标题里确认“这是一册书”）
_VOLUME_PATTERNS = [
    re.compile(r"第\s*[0-9〇零一二三四五六七八九十百]+\s*[册卷部集篇回]"),
    re.compile(r"[（(]\s*(上|中|下|上中下|全[一二三四五六七八九十0-9]+册?)\s*[)）]"),
    re.compile(r"\b(vol\.?|volume|book|part|series)\s*[-—_ ]?\s*[0-9ivx]+", re.I),
    re.compile(r"(全集|套装|作品集|文集|选集|丛书)\s*之?\s*[0-9一二三四五六七八九十]"),
    re.compile(r"^[IVX]+\s*[、.．]"),  # I. II. III. 作为顶层
    re.compile(r"^第?\s*[0-9]+\s*[、.．]\s*\D"),  # 1. 2. 3. 但排除纯数字章节
]

# 章节序号提取（“第X章/回/节”或 “Chapter N”），用于检测序号回退
_CHAPTER_NO_RE = re.compile(
    r"第\s*([0-9〇零一二三四五六七八九十百千]+)\s*[章节回节篇部卷]|[Cc]hapter\s*([0-9]+)"
)
_CN_NUM = {"零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_to_int(s: str):
    """把中文/阿拉伯数字串转成 int，失败返回 None。"""
    if s is None:
        return None
    s = s.strip()
    if s.isdigit():
        return int(s)
    if not s:
        return None
    # 简单中文数字（含“十”“百”的常见写法）
    if s in _CN_NUM:
        return _CN_NUM[s]
    total, section, number = 0, 0, 0
    for ch in s:
        if ch in _CN_NUM:
            number = _CN_NUM[ch]
        elif ch == "十":
            section += (number or 1) * 10
            number = 0
        elif ch == "百":
            section += (number or 1) * 100
            number = 0
        else:
            return None
    return total + section + number


def chapter_number(text: str):
    """从文本里提取章节序号；提取不到返回 None。"""
    m = _CHAPTER_NO_RE.search(text or "")
    if not m:
        return None
    return _cn_to_int(m.group(1) or m.group(2))


def _is_cover(line: dict) -> bool:
    """判断一个 split_line 是否是封面页。"""
    title = (get_title_of_html(line.get("sample", "")) or "").strip()
    if title.lower() in _COVER_TITLES:
        return True
    guide = line.get("guide")
    if guide:
        # guide 形如 ("cover", "Cover")
        gtype = guide[0] if isinstance(guide, (tuple, list)) else str(guide)
        if "cover" in str(gtype).lower():
            return True
    return False


def _top_toc(line: dict):
    """返回该行顶层目录文本（toc[0]），并做清洗；无则 None。"""
    toc = line.get("toc") or []
    if not toc:
        return None
    text = (toc[0] or "").strip()
    if not text or text in _IGNORE_TOC_TEXT:
        return None
    return text


def _looks_like_volume_name(text: str) -> bool:
    """文本是否像一册书的名字（而非普通章节名）。"""
    if not text or text in _IGNORE_TOC_TEXT:
        return False
    if any(p.search(text) for p in _VOLUME_PATTERNS):
        return True
    # 短标题（<=18字）且不显式含“第X章”，在合集语境下更可能是册名
    if len(text) <= 18 and chapter_number(text) is None:
        return True
    return False


def _clean_volume_name(text: str) -> str:
    """把目录顶层文本清理成更像书名的形式。"""
    text = (text or "").strip()
    # 去掉前置的 “第X册/卷/部 ”、“1.”、“I.” 等序号，保留真正的书名部分
    text = re.sub(r"^第\s*[0-9〇零一二三四五六七八九十百]+\s*[册卷部集篇]\s*", "", text)
    text = re.sub(r"^(全集|套装|作品集|文集|选集|丛书)\s*之\s*", "", text)
    text = re.sub(r"^[IVX]+\s*[、.．]\s*", "", text)
    text = re.sub(r"^[0-9]+\s*[、.．]\s*", "", text)
    return text.strip() or "未命名分册"


def detect_volumes(lines, source_title=""):
    """从 split_lines 检测候选分册。

    :param lines: SplitEpub.get_split_lines() 的返回值
    :param source_title: 原书书名，作为检测不到时的兜底
    :return: (volumes, diagnostics)
        volumes: [{name, start, end, chapter_count, reason, confidence, titles}]
    """
    if not lines:
        return [], {"reason": "empty"}

    n = len(lines)
    # 为每一行收集信号
    # boundary_score: 该行作为“新册起点”的得分；volume_hint: 推断出的册名
    scores = [0] * n
    hints = [None] * n
    reasons = [[] for _ in range(n)]

    prev_top = None
    prev_ch_no = None
    for i, line in enumerate(lines):
        title = (get_title_of_html(line.get("sample", "")) or "").strip()
        top = _top_toc(line)
        cover = _is_cover(line)

        # ---- 信号 1：目录顶层标题变化 ----
        if top:
            if prev_top is None or top != prev_top:
                # 顶层标题首次出现或变化 -> 可能是新册
                if _looks_like_volume_name(top):
                    scores[i] += 50
                    hints[i] = _clean_volume_name(top)
                    reasons[i].append("目录顶层标题")
                else:
                    # 顶层存在但不像册名（例如顶层就是章节名），弱信号
                    scores[i] += 8
        # ---- 信号 2：封面页 ----
        if cover:
            scores[i] += 40
            reasons[i].append("封面页")
            # 总封面（第一页且后面没有内容归属）通常不算新册起点，
            # 让后续逻辑处理；这里仍给分，靠 name 推断决定。

        # ---- 信号 3：册名文字规律（整行所有 toc + 标题）----
        all_text = " ".join((line.get("toc") or []) + [title])
        if any(p.search(all_text) for p in _VOLUME_PATTERNS):
            scores[i] += 25
            reasons[i].append("册名规律")
            if hints[i] is None:
                hints[i] = _clean_volume_name(top or title)

        # ---- 信号 4：章节序号回退 ----
        cur_no = chapter_number(all_text)
        if cur_no is not None and prev_ch_no is not None and cur_no <= prev_ch_no:
            scores[i] += 20
            reasons[i].append("章节序号回退")
        if cur_no is not None:
            prev_ch_no = cur_no

        if top:
            prev_top = top

    # ---- 选出边界 ----
    # 阈值：封面(40)+目录(50) 通常 >= 60；单靠册名规律(25)或序号回退(20)不足以独立成立，
    # 需要叠加。用 45 作为阈值，能覆盖“仅封面页”“仅目录顶层标题”“封面+目录”等情形。
    THRESHOLD = 45
    boundaries = [i for i in range(n) if scores[i] >= THRESHOLD]

    # 若无任何边界：整本当作一册（不是合集 / 识别失败）
    if not boundaries:
        return [{
            "name": (source_title or "全书").strip(),
            "start": 0, "end": n - 1, "chapter_count": n,
            "reason": "未检测到分册边界，按整本处理", "confidence": 0.5,
            "titles": [(get_title_of_html(l.get("sample", "")) or "").strip() for l in lines],
        }], {"reason": "no_boundary", "scores": scores}

    # 第一页若是总封面且没有独立书名，尝试把它并入第一册（不单独成册）
    # 若第一册边界在 index 0 且是封面，找它后面第一个有 hint 的行作为真正起点
    if boundaries[0] == 0 and _is_cover(lines[0]) and hints[0] is None:
        # 让总封面成为第一册的一部分，起点后移
        boundaries = boundaries[1:] or [0]

    # 构造分册区间
    volumes = []
    for bi, start in enumerate(boundaries):
        end = boundaries[bi + 1] - 1 if bi + 1 < len(boundaries) else n - 1
        if end < start:
            continue

        # 书名：优先该边界行的 hint；否则向后找第一个非空目录/标题
        name = hints[start]
        if not name:
            for j in range(start, end + 1):
                t = _top_toc(lines[j]) or (get_title_of_html(lines[j].get("sample", "")) or "").strip()
                if t and t not in _IGNORE_TOC_TEXT and not chapter_number(t):
                    name = _clean_volume_name(t)
                    break
        if not name:
            name = f"第{bi + 1}册"

        # 前置内容（第一个边界之前的行）并入第一册
        if bi == 0 and start > 0:
            start = 0

        titles = []
        for j in range(start, end + 1):
            t = (get_title_of_html(lines[j].get("sample", "")) or "").strip()
            if t and t not in _COVER_TITLES:
                titles.append(t)

        conf = min(0.99, 0.6 + scores[start] / 200.0)
        volumes.append({
            "name": name,
            "start": start,
            "end": end,
            "chapter_count": end - start + 1,
            "reason": "、".join(dict.fromkeys(reasons[start])) or "自动检测",
            "confidence": round(conf, 2),
            "titles": titles[:50],  # 限制回传体积
        })

    # 合并“章节数为 0 或负”的异常项
    volumes = [v for v in volumes if v["chapter_count"] > 0]
    return volumes, {"reason": "ok", "scores": scores, "boundaries": boundaries}


def build_chapter_list(lines):
    """构造给前端展示/微调用的扁平章节列表。"""
    out = []
    for line in lines:
        title = (get_title_of_html(line.get("sample", "")) or "").strip()
        toc = line.get("toc") or []
        display = " / ".join(toc)
        if title and title not in toc:
            display = (display + " [" + title + "]").strip(" /")
        if not display:
            display = title or "（无标题）"
        out.append({
            "num": line["num"],
            "title": display,
            "preview": strip_html(line.get("sample", ""))[:200],
            "is_cover": _is_cover(line),
        })
    return out
