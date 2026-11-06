#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""同名重复书籍的检测与合并（迁移工具）。

背景：早期有声书走 `audios/<book_id>/`、电子书走 `library/`，上游导入音频时只看
"这本书有没有音频目录"，没有就新建一本书。于是「先导 epub、后加同名音频」必然
在书库里多出一条同名记录。v4.8.0 修了导入逻辑，但**已经产生的重复记录不会自愈**
（该 ScanFile 行已是 IMPORTED，重扫被跳过，没有再比标题的时机），需要一次性迁移。

本模块只做检测与合并的**计算**和**执行**，不负责 HTTP、不负责 UI。
设计约束：

1. **先预览、后执行**。`scan()` 只读，返回每个重复组的具体处置方案（保留哪本、
   删哪本、哪些关联数据要改指、哪个音频目录要搬），供页面展示；`apply()` 才落盘。
2. **成对才动手**。只有「一组里恰好一本有电子书文件、且至少一本有音频目录」
   这种情况才自动合并。方向不明确（两本都有电子书、两本都有音频、都没有电子书）
   的组只报告不处理——宁可漏修，不可误删。
3. **音频搬到保留书目录的 .audio/ 下**。音频跟着书走（`library/<作者>/<书名>
   (id)/.audio/`，4.6.0-15 起唯一布局），合并时把重复书目录里的音频搬进保留书
   目录。目标目录已有同名文件时跳过该文件，不覆盖。
4. **关联数据改指而非删除**。阅读进度、收藏、书单、评论、分享等全部迁移到保留书，
   避免用户"进度凭空消失"。复合主键（reading_state / book_visits）与唯一约束
   （booklist_books / book_shares）逐行判断冲突，冲突时保留已有的、丢弃冗余的。
5. **执行前自动备份**。备份 SQLite 用户库文件到 `data/backup/`，出错可回滚。
"""

import datetime
import json
import logging
import os
import re
import shutil

from webserver.models import (
    BookList,
    BookListBook,
    BookReadingStats,
    BookReview,
    BookShare,
    BookVisit,
    Item,
    ManualReadingLog,
    Reading,
    ReadingRecord,
    ReadingState,
)
from webserver.services.book_review_service import BookReviewService
from webserver.services.book_share_service import BookShareService

# 音视频扩展名（与 constants.SUPPORTED_AUDIO_FORMATS 口径一致，这里独立一份是为了
# 迁移工具不被常量变更牵连——迁移只关心"这个目录里有没有可播放文件"）
_AUDIO_EXTS = (".mp3", ".m4a", ".m4b", ".flac", ".wav", ".ogg", ".aac", ".opus", ".wma")

# 音频的配套文件：封面、字幕、转写文稿。改名/移库时必须跟音频一起走，
# 否则新目录下的播放器找不到封面、同名字幕也配不上。
_COMPANION_EXTS = (".jpg", ".jpeg", ".png", ".srt", ".vtt", ".txt")

# 一个重复组超过这个体量就不自动处理（防误判造成大批量删除）
MAX_GROUP_SIZE = 8


def _norm_title(title):
    """归一化书名用于分组。

    比 calibre 的 icu_lower 更宽松一档：额外去首尾空白、合并连续空白、全角转半角。
    用于**分组**（把可能重复的书聚到一起），不用于最终判定——最终仍以
    books_with_same_title 的结果为准，避免把"看起来像但实际不同"的书误并。
    """
    if not title:
        return ""
    text = str(title)
    # 全角 → 半角（仅字母数字与括号，避免影响中文）
    out = []
    for ch in text:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        elif code == 0x3000:
            out.append(" ")
        else:
            out.append(ch)
    text = "".join(out)
    return " ".join(text.split()).lower()


# --------------------------------------------------------------------------- #
# 书名宽松归一键（4.6.0-9 修订）
#
# 为什么原来的 _norm_title 不够用：它只做全角转半角 + 合并空白 + 小写，
# 两个书名差一个字就落进不同的桶，重复书永远配不上（用户实测"一直搜不到"）。
#
# 现实里同一本书的两种记录，书名常见差异：
#   三体              / 三体（全集）
#   活着              / 活着 修订版
#   斗罗大陆          / 斗罗大陆 第1册
#   万历十五年        / 万历十五年.txt          ← 导入时把扩展名带进了书名
#   百年孤独          / 【精校】百年孤独
#
# 所以候选桶按「去噪后的书名」聚合，扩大召回。但**这只决定谁和谁摆到一起看**，
# 是否真是同一本由 _build_group 里的 _same_book 严格判定，绝不靠书名相似就合并。
# --------------------------------------------------------------------------- #

# 版本/装帧/收录类噪声词：出现在书名末尾（或括号里）都不影响「是不是同一本书」。
# 注意这些词不能整串去掉就当成新书名，只在边界位置剥离。
_EDITION_NOISE = (
    "修订版", "修订本", "增订版", "增订本", "新版", "第2版", "第二版", "第3版", "第三版",
    "插图版", "插图本", "彩图版", "典藏版", "精装版", "平装版", "珍藏版", "纪念版",
    "全集", "全本", "足本", "完本", "完整版", "未删节版", "校勘版", "评注版", "注释版",
    "套装", "盒装", "epub", "mobi", "azw3", "txt", "pdf",
)

# 卷册标记：第N卷/册/集/部/篇，或「上下」「上中下」这类分卷写法。
_VOLUME_RE = re.compile(
    r"(第\s*[0-9一二三四五六七八九十百]+\s*[卷册集部篇辑])"
    r"|([上下中]{1,3}\s*[册卷])"
    r"|(\d+\s*/\s*\d+)"
)

# 书名主体外包裹的装饰符号与括号
_BRACKET_RE = re.compile(r"[\(\[【〔<《]([^\)\]】〕>》]*)[\)\]】〕>》]")
_LEADING_JUNK_RE = re.compile(r"^[\s\-_·—…\.、,，:：;；!！?？\'\"“”‘’]+")


def _strip_edition_noise(s):
    """剥掉版本词、卷册标记、文件扩展名。只剥边界，不挖书名中间的字。"""
    prev = None
    while prev != s:
        prev = s
        # 扩展名（.txt/.epub 这类）
        s = re.sub(r"\.(txt|epub|mobi|azw3?|pdf|djvu|fb2|cbz)\s*$", "", s, flags=re.I)
        # 末尾的版本词，可能反复叠加（"全集 修订版"）
        for w in _EDITION_NOISE:
            s = re.sub(r"[\s\-_·—]*" + re.escape(w) + r"\s*$", "", s, flags=re.I)
        # 卷册标记
        s = _VOLUME_RE.sub("", s)
    return s


def _title_core(title):
    """宽松归一的书名主体：去装饰、去括号补充、去版本词卷册、去标点空白。

    只用于「把候选书聚到一起」，不用于判定同一性。
    """
    if not title:
        return ""
    text = str(title)
    # 全角 → 半角
    out = []
    for ch in text:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        elif code == 0x3000:
            out.append(" ")
        else:
            out.append(ch)
    text = "".join(out)

    s = _LEADING_JUNK_RE.sub("", text.strip())

    # 括号补充（"三体（全集）"的括号内容、"【精校】"前缀）先剥离，
    # 但只在剥离后主体不为空时才采用——否则《(无题)》这类书名会被清空。
    stripped = _BRACKET_RE.sub("", s).strip()
    if stripped:
        s = stripped

    s = _strip_edition_noise(s).strip()
    # 去掉所有空白与常见分隔标点，中文书名里这些差异纯属录入习惯
    s = re.sub(r"[\s\-_·—…\.、,，:：;；!！?？\'\"“”‘’]+", "", s)
    return s.lower()


def _isbn_digits(identifiers):
    """从 calibre identifiers 里取 ISBN（10/13 位纯数字）。

    identifiers 形如 {"isbn": "9787536692930", "isbn13": "...", "douban": "1234567"}；
    也兼容 amzn/其他源里夹带的 ISBN。返回集合，方便求交。
    """
    out = set()
    if not identifiers:
        return out
    if isinstance(identifiers, str):
        try:
            identifiers = json.loads(identifiers)
        except (ValueError, TypeError):
            return out
    if not isinstance(identifiers, dict):
        return out
    for k, v in identifiers.items():
        if not v:
            continue
        if not re.search(r"isbn", str(k), re.I):
            continue
        digits = re.sub(r"[^0-9Xx]", "", str(v)).upper()
        # ISBN-10（9 位数字 + 校验位 0-9/X）或 ISBN-13
        if len(digits) == 13 and digits.isdigit():
            out.add(digits)
        elif len(digits) == 10 and digits[:9].isdigit():
            out.add(digits)
    return out


def _translators_of(authors):
    """从作者字段里剥离出译者名集合。

    中文书库普遍把译者塞进 authors：
      「陀思妥耶夫斯基，荣如德 译」
      「[俄] 陀思妥耶夫斯基 著 / 荣如德 译」
      「译者：荣如德」
    这里只提取**明确标注为译者**的那部分，不瞎猜——没写"译"就不当译者，
    否则会把正常的第二作者误判成译者。
    """
    out = set()
    for raw in authors or []:
        if not raw:
            continue
        s = str(raw)
        # 形式一：「译者：XX」整体标注（名字后面不带"译"字）
        m = re.match(r"^\s*译者\s*[:：]\s*(.+)$", s)
        if m:
            for part in re.split(r"[,，/、;；]", m.group(1)):
                name = part.strip(" 　,，/、;；:：[]【】()（）")
                name = re.sub(r"[\(（\[【].*?[\)）\]】]", "", name).strip()
                if name:
                    out.add(name.lower())
            continue
        # 形式二：「XX 译」「XX译」（译者混在作者列表里）
        for m in re.finditer(r"(?:译者\s*[:：]\s*)?([^,，/、;；\[\]【】]{1,20}?)\s*译(?:\b|$)", s):
            name = m.group(1).strip(" 　,，/、;；:：[]【】()（）")
            # 去掉可能的「著」「作者」残留与括注
            name = re.sub(r"^(著|作者|编者|主编)\s*[:：]?\s*", "", name).strip()
            name = re.sub(r"[\(（\[【].*?[\)）\]】]", "", name).strip()
            if name:
                out.add(name.lower())
    return out


def _publisher_norm(pub):
    """出版社名归一：去空格标点、剥掉「出版社/出版公司/集团」这类通用后缀。

    目的是让「人民文学出版社」「人民文学」「人民文学出版公司」判为同一家，
    避免同一版本因为录入写法不同被当成两个出版社而拒绝合并。
    """
    if not pub:
        return ""
    s = str(pub).strip()
    out = []
    for ch in s:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(ch)
    s = "".join(out)
    s = re.sub(r"[\s\-_·—…\.、,，:：;；]+", "", s)
    # 反复剥后缀（"出版集团"、"出版社"可能叠加），直到稳定
    prev = None
    while prev != s:
        prev = s
        for suf in ("出版集团", "出版公司", "出版社", "书局", "印书馆", "传媒", "集团", "出版"):
            if s.endswith(suf) and len(s) > len(suf):
                s = s[: -len(suf)]
                break
    return s.lower()



def _list_audio_files(cache, book_id, library_root=None):
    """返回某书 .audio/ 目录下可播放文件的文件名列表（没有音频返回空表）。"""
    from webserver.base.audio_dir import audio_dir_for_read

    d, _legacy = audio_dir_for_read(cache, book_id, library_root)
    if not d or not os.path.isdir(d):
        return []
    try:
        return [f for f in os.listdir(d)
                if os.path.isfile(os.path.join(d, f)) and f.lower().endswith(_AUDIO_EXTS)]
    except OSError:
        return []


def _has_ebook_file(row):
    """calibre 记录里是否有实体电子书文件。

    row 来自 db.get_data_as_dict()：`available_formats` 是扩展名列表，
    `formats` 是实际文件路径。两者都看，路径再看一眼是否存在——
    有的库 available_formats 有值但文件已被手工删掉。
    """
    if not row:
        return False
    fmts = row.get("available_formats")
    if fmts:
        return True
    paths = row.get("formats") or []
    if isinstance(paths, str):
        paths = [paths]
    return any(p and os.path.exists(str(p)) for p in paths)


def _row_formats(row):
    """取格式列表（大写），用于展示。"""
    if not row:
        return []
    fmts = row.get("available_formats")
    if fmts:
        return [str(f).upper() for f in fmts]
    out = []
    for p in (row.get("formats") or []):
        ext = os.path.splitext(str(p))[1].lstrip(".").upper()
        if ext:
            out.append(ext)
    return sorted(set(out))


class DuplicateBookMerger(object):
    """同名重复书记录的检测与合并。

    用法::

        merger = DuplicateBookMerger(db, session, backup_dir)
        plan = merger.scan()          # 只读，返回方案
        merger.apply(plan)            # 执行，逐组返回结果
    """

    def __init__(self, db, session, backup_dir=None, meta_fetcher=None,
                 library_root=None):
        """meta_fetcher: 可选，签名 (ids) -> list[dict]，用于在**工作线程**里取 calibre
        元数据（handler 传 `run_calibre_async` 包装过的函数，避免阻塞 ioloop）。
        不传则退回直接调 db.get_data_as_dict（仅适合脚本/测试环境）。
        library_root: 可选，书库根目录（测试注入用）；默认走 CONF 的 with_library。
        """
        self.db = db
        self.session = session
        self.backup_dir = backup_dir
        self.meta_fetcher = meta_fetcher
        self.library_root = library_root
        self.errors = []

    def _fetch_meta(self, ids):
        if self.meta_fetcher is not None:
            return self.meta_fetcher(ids)
        return self.db.get_data_as_dict(book_ids=ids)

    # ------------------------------------------------------------------ 扫描

    def scan(self):
        """扫描全库，返回 {groups: [...], summary: {...}}。

        只读，不改任何数据。每个 group 是一份完整的处置方案。
        """
        groups = []
        try:
            title_map = self.db.new_api.get_id_map("title")
        except Exception as err:
            logging.error("[DEDUP] 读取书库标题失败: %s", err)
            return {"groups": [], "summary": self._empty_summary(), "error": str(err)}

        # 按宽松归一的书名分桶（扩大召回；是否同一本由 _build_group 严格判定）
        buckets = {}
        for book_id, title in title_map.items():
            key = _title_core(title)
            if not key:
                continue
            buckets.setdefault(key, []).append(book_id)

        candidates = {k: sorted(v) for k, v in buckets.items() if len(v) > 1}
        if not candidates:
            return {"groups": [], "summary": self._empty_summary()}

        # 一次性取出所以候选书的元数据
        all_ids = sorted({bid for ids in candidates.values() for bid in ids})
        try:
            data = self._fetch_meta(all_ids) or []
        except Exception as err:
            logging.error("[DEDUP] 读取书籍元数据失败: %s", err)
            return {"groups": [], "summary": self._empty_summary(), "error": str(err)}
        meta = {}
        for row in data:
            bid = row.get("id")
            if bid is not None:
                meta[int(bid)] = row

        for key, ids in sorted(candidates.items()):
            group = self._build_group(key, ids, meta)
            if group:
                groups.append(group)

        return {"groups": groups, "summary": self._summarize(groups)}

    def _build_group(self, key, ids, meta):
        """把一组同 id 聚成处置方案；无法确定方向时标记为 skipped。"""
        if len(ids) > MAX_GROUP_SIZE:
            return {
                "key": key,
                "title": (meta.get(ids[0]) or {}).get("title") or key,
                "books": [self._book_brief(bid, meta) for bid in ids],
                "action": "skipped",
                "reason": "同名书籍过多（%d 本），超出自动处理上限，请人工确认" % len(ids),
            }

        briefs = [self._book_brief(bid, meta) for bid in ids]
        with_ebook = [b for b in briefs if b["ebook_formats"]]
        with_audio = [b for b in briefs if b["audio_files"]]
        empty = [b for b in briefs if not b["ebook_formats"] and not b["audio_files"]]

        title = briefs[0]["title"] if briefs else key

        # 4.6.0-9：同一性严格判定。
        # 候选桶按宽松书名聚合（去了版本词/括号/扩展名），必然会把
        # 「三体」和「三体（全集）」聚到一起，也可能把同名不同书聚到一起。
        # 这里逐本与被保留的电子书比对，任何一本判定为"不是同一本"就整组跳过。
        # 判定口径见 _same_book：ISBN 相同 → 同一本；出版社/译者/作者不同 → 否。
        if with_ebook:
            anchor = with_ebook[0]
            for b in briefs:
                if b["book_id"] == anchor["book_id"]:
                    continue
                same, why = self._same_book(anchor, b)
                if not same:
                    return {
                        "key": key,
                        "title": title,
                        "books": briefs,
                        "action": "skipped",
                        "reason": "#%d 与 #%d 不是同一本书：%s" % (
                            anchor["book_id"], b["book_id"], why),
                    }

        # 方向明确才动手：恰好一本有电子书，且存在有音频的记录
        if len(with_ebook) == 1 and with_audio:
            keep = with_ebook[0]
            drop = [b for b in briefs if b["book_id"] != keep["book_id"]]
            if not empty:
                # 只有能解释清楚的组才自动合并：每本被删的书要么有音频、要么是真冗余
                return {
                    "key": key,
                    "title": title,
                    "books": briefs,
                    "action": "merge",
                    "keep_book_id": keep["book_id"],
                    "keep_title": keep["title"],
                    "drop_book_ids": [b["book_id"] for b in drop],
                    "audio_moves": [
                        {
                            "from_book_id": b["book_id"],
                            "to_book_id": keep["book_id"],
                            "files": b["audio_files"],
                        }
                        for b in with_audio if b["book_id"] != keep["book_id"]
                    ],
                    "reasons": self._explain(briefs, keep, drop),
                }

        # 两本都有电子书：内容可能真的不同（同名的不同版本/上下册），不自动合并
        if len(with_ebook) >= 2:
            return {
                "key": key,
                "title": title,
                "books": briefs,
                "action": "skipped",
                "reason": "%d 本都有电子书文件，可能是同名的不同版本，请人工确认" % len(with_ebook),
            }

        # 一本电子书都没有：全是音频记录，合并方向不明
        return {
            "key": key,
            "title": title,
            "books": briefs,
            "action": "skipped",
            "reason": "没有电子书文件，无法判断该保留哪一本" if briefs else "无可用记录",
        }

    def _book_brief(self, book_id, meta):
        row = meta.get(book_id) or {}
        audio = _list_audio_files(self.db, book_id, self.library_root)
        return {
            "book_id": book_id,
            "title": row.get("title") or "",
            "authors": list(row.get("authors") or []),
            "publisher": row.get("publisher") or "",
            "isbn": sorted(_isbn_digits(row.get("identifiers"))),
            "ebook_formats": _row_formats(row),
            "audio_files": audio,
            "audio_count": len(audio),
        }

    @staticmethod
    def _same_book(a, b):
        """严格判定两本书是否**同一本**（返回 (bool, 理由)）。

        候选桶已经按宽松书名聚过，这里必须收紧，否则「同名不同书」会被误合并。
        用户的判定口径（同时也是豆瓣/Goodreads/OpenLibrary 等主流图书馆的通行做法）：

          * **出版社不同 → 不是同一本**。中文书尤其如此，同一书名在不同出版社
            是不同版本、不同编校、甚至不同内容（公版书重排最典型）。
          * **译者不同 → 不是同一本**。外文书的译者差异等同不同作品，
            译者信息一般在作者字段里以「作者，译者」或「XX 译」形式存在。
          * **作者不同 → 不是同一本**。
          * **ISBN 相同 → 基本可判定同一本**。ISBN 是按"版本"分配的，
            同 ISBN 意味着同一出版物的同一版本，这是最强的证据，优先于前三条：
            出版社名录入不一致（"人民文学出版社" vs "人民文学"）不应推翻它。
          * **作者（或含译者）归一后相交，且书名主体一致 → 视为同一本**。

        注意：先判 ISBN（最强证据），再判出版社/译者/作者（否决项）。
        """
        from webserver.base.author_norm import author_key_set

        # ① ISBN 相同 —— 最强证据，直接认定同一本
        isbn_a, isbn_b = set(a.get("isbn") or []), set(b.get("isbn") or [])
        if isbn_a and isbn_b and (isbn_a & isbn_b):
            return True, "ISBN 相同（%s）" % sorted(isbn_a & isbn_b)[0]

        # ② 出版社不同 —— 否决（中文书分社出版是不同版本，不能并）
        pub_a, pub_b = _publisher_norm(a.get("publisher")), _publisher_norm(b.get("publisher"))
        if pub_a and pub_b and pub_a != pub_b:
            return False, "出版社不同（%s vs %s）" % (a.get("publisher"), b.get("publisher"))

        # ③ 译作：先把作者字段里的「XX 译」剥出来单独比对。
        #    外文书的作者字段常拼成「陀思妥耶夫斯基，荣如德译」或
        #    「作者：X / 译者：Y」。原作者一定相同，如果只用"作者键相交"判断，
        #    译者差异会被原作者掩盖 → 把荣如德译本和朱海观译本当成同一本，
        #    这正是用户明确说「译者不同是不同书」要防的情况。
        ta, tb = _translators_of(a.get("authors")), _translators_of(b.get("authors"))
        if ta and tb and not (ta & tb):
            return False, "译者不同（%s vs %s）" % ("、".join(sorted(ta)), "、".join(sorted(tb)))

        # ④ 作者键集合：任一边解析不出（佚名/脏名）时不否决，维持原有判定
        ka, kb = author_key_set(a.get("authors")), author_key_set(b.get("authors"))
        if ka and kb:
            if not (ka & kb):
                return False, "作者不同（%s vs %s）" % (
                    "、".join(a.get("authors") or []) or "佚名",
                    "、".join(b.get("authors") or []) or "佚名")
            return True, "作者相同（%s）" % "、".join(sorted(ka & kb))

        # ⑤ 某一边作者缺失：书名主体已一致，判为同一本（宁可漏修不可误删的
        #    方向在这里已经由 _build_group 的"恰好一本有电子书"条件把住）
        return True, "书名主体一致，作者信息不全"

    @staticmethod
    def _explain(briefs, keep, drop):
        """生成给用户看的一句话说明。"""
        parts = []
        for b in briefs:
            if b["book_id"] == keep["book_id"]:
                parts.append("#%d 有电子书(%s)" % (b["book_id"], "/".join(b["ebook_formats"]) or "-"))
            else:
                if b["audio_files"]:
                    parts.append("#%d 有 %d 个音频" % (b["book_id"], b["audio_count"]))
                else:
                    parts.append("#%d 空记录" % b["book_id"])
        return " + ".join(parts)

    @staticmethod
    def _empty_summary():
        return {"total_groups": 0, "mergeable": 0, "skipped": 0,
                "will_delete": 0, "will_move_audio": 0}

    @staticmethod
    def _summarize(groups):
        mergeable = [g for g in groups if g.get("action") == "merge"]
        return {
            "total_groups": len(groups),
            "mergeable": len(mergeable),
            "skipped": len(groups) - len(mergeable),
            "will_delete": sum(len(g.get("drop_book_ids") or []) for g in mergeable),
            "will_move_audio": sum(
                len(m.get("files") or [])
                for g in mergeable for m in (g.get("audio_moves") or [])
            ),
        }

    # ------------------------------------------------------------------ 预览详情

    def preview(self, keep_book_id, drop_book_ids):
        """列出合并会涉及的关联数据条数，供页面二次确认。只读。"""
        out = {}
        for bid in drop_book_ids:
            out[bid] = {
                "reading_state": self.session.query(ReadingState).filter(ReadingState.book_id == bid).count(),
                "readings": self.session.query(Reading).filter(Reading.book_id == bid).count(),
                "book_reading_stats": self.session.query(BookReadingStats).filter(BookReadingStats.book_id == bid).count(),
                "manual_reading_logs": self.session.query(ManualReadingLog).filter(ManualReadingLog.book_id == bid).count(),
                "book_reviews": self.session.query(BookReview).filter(BookReview.book_id == bid).count(),
                "book_visits": self.session.query(BookVisit).filter(BookVisit.book_id == bid).count(),
                "booklist_books": self.session.query(BookListBook).filter(BookListBook.book_id == bid).count(),
                "book_shares": self.session.query(BookShare).filter(BookShare.book_id == bid).count(),
                "items": self.session.query(Item).filter(Item.book_id == bid).count(),
                "reading_records": self.session.query(ReadingRecord).filter(ReadingRecord.book_id == bid).count(),
            }
        return out

    # ------------------------------------------------------------------ 备份

    def backup(self):
        """SQLite 用户库做一份完整拷贝，返回备份文件路径（失败返回 None）。

        用 python sqlite3 的在线备份接口而不是 shutil.copy：WAL 模式下直接拷文件
        可能拿到不一致快照。
        """
        if not self.backup_dir:
            return None
        try:
            os.makedirs(self.backup_dir, exist_ok=True)
            bind = self.session.get_bind()
            url = str(bind.engine.url)
            if not url.startswith("sqlite"):
                return None
            src_path = bind.engine.url.database
            if not src_path or not os.path.exists(src_path):
                return None
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            dest_path = os.path.join(self.backup_dir, "dedup_%s.db" % stamp)
            import sqlite3
            src = sqlite3.connect(src_path)
            try:
                dst = sqlite3.connect(dest_path)
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
            logging.info("[DEDUP] 用户库已备份到 %s", dest_path)
            return dest_path
        except Exception as err:
            logging.error("[DEDUP] 备份失败（仍继续，请自行确认风险）: %s", err)
            return None

    # ------------------------------------------------------------------ 执行

    def apply(self, plan, do_backup=True):
        """执行合并。plan 为 scan() 的返回值（只处理 action == merge 的组）。

        返回 {backup, merged: [...], failed: [...]}。逐组独立事务：一组失败只回滚
        该组，不影响其它组。
        """
        result = {"backup": None, "merged": [], "failed": []}
        groups = [g for g in (plan.get("groups") or []) if g.get("action") == "merge"]
        if not groups:
            return result

        if do_backup:
            result["backup"] = self.backup()

        for group in groups:
            keep_id = group["keep_book_id"]
            drop_ids = group.get("drop_book_ids") or []
            try:
                detail = self._merge_one(group)
                self.session.commit()
                result["merged"].append({
                    "title": group.get("title"),
                    "keep_book_id": keep_id,
                    "drop_book_ids": drop_ids,
                    "detail": detail,
                })
            except Exception as err:
                self.session.rollback()
                logging.error("[DEDUP] 合并《%s》失败: %s", group.get("title"), err)
                logging.error("[DEDUP] %s", __import__("traceback").format_exc())
                result["failed"].append({
                    "title": group.get("title"),
                    "keep_book_id": keep_id,
                    "drop_book_ids": drop_ids,
                    "error": str(err),
                })
        return result

    def _merge_one(self, group):
        """合并单组：搬音频 → 迁关联数据 → 删重复书。"""
        keep_id = group["keep_book_id"]
        drop_ids = list(group.get("drop_book_ids") or [])
        detail = {"moved_files": 0, "skipped_files": [], "records": {},
                  "deleted_books": []}

        # 1) 音频目录搬到保留书 id 下
        for move in (group.get("audio_moves") or []):
            moved, skipped = self._move_audio(move["from_book_id"], move["to_book_id"])
            detail["moved_files"] += moved
            detail["skipped_files"].extend(skipped)

        # 2) 关联数据改指（而不是删除）
        for bid in drop_ids:
            counts = self._repoint_records(bid, keep_id)
            for k, v in counts.items():
                detail["records"][k] = detail["records"].get(k, 0) + v

        # 3) 删除 calibre 侧重复书 + 应用侧残留
        for bid in drop_ids:
            self._delete_calibre_book(bid)
            detail["deleted_books"].append(bid)

        # 4) 修正 ScanFile 指向：原来记着重复书 id 的扫描记录改指保留书，
        #    否则下次扫描会认为"这本书已导入"，而它其实已经不存在了
        self._relink_scanfiles(drop_ids, keep_id)

        BookReviewService.invalidate_stats(keep_id)
        BookShareService.invalidate_cache()
        return detail

    def _move_audio(self, from_id, to_id):
        """重复书目录 .audio/ 里的音频及配套文件搬进保留书目录的 .audio/。

        返回 (搬了几个, 跳过的文件)。搬的范围：
          - 音频（_AUDIO_EXTS）
          - 封面（cover.jpg/png）——播放器在 .audio/ 下找封面
          - 字幕与文稿（.srt/.vtt/.txt）——与音频同名才能自动配对
        其它未知文件（下载残留、临时文件）留在原目录，因此目录不会被删——
        这类文件可能是用户手动放的，宁可留着让人自己判断。
        """
        from webserver.base.audio_dir import audio_dir_for_read, audio_dir_for_write

        src_dir, _legacy = audio_dir_for_read(self.db, from_id, self.library_root)
        if not src_dir or not os.path.isdir(src_dir):
            return 0, []
        dst_dir = audio_dir_for_write(self.db, to_id, self.library_root)
        if not dst_dir:
            raise RuntimeError("无法确定保留书 %s 的音频目录" % to_id)
        moved, skipped = 0, []
        movable = _AUDIO_EXTS + _COMPANION_EXTS
        try:
            os.makedirs(dst_dir, exist_ok=True)
            for fname in sorted(os.listdir(src_dir)):
                src = os.path.join(src_dir, fname)
                if not os.path.isfile(src):
                    continue
                if not fname.lower().endswith(movable):
                    continue
                dst = os.path.join(dst_dir, fname)
                if os.path.exists(dst):
                    # 目标已存在同名文件：保留目标，不覆盖（可能是更完整的版本）
                    skipped.append("%s/%s" % (from_id, fname))
                    continue
                shutil.move(src, dst)
                moved += 1
            # 源目录空了才删，避免误删还在使用的目录
            try:
                if not os.listdir(src_dir):
                    os.rmdir(src_dir)
            except OSError:
                pass
        except Exception as err:
            logging.error("[DEDUP] 搬音频 %s -> %s 失败: %s", from_id, to_id, err)
            raise
        # 事件驱动缓存：搬完就把「有音频」标志挪过去（build.20 复审补）。
        # 原来要等 6 小时兜底扫描：期间保留书不进有声书列表、被合并书还挂在列表里。
        if moved:
            try:
                from webserver.handlers.audio import AudioBooksCache
                AudioBooksCache.mark_has_audio(to_id)
                AudioBooksCache.mark_no_audio(from_id)
            except Exception:
                logging.warning("[DEDUP] 更新音频缓存失败: %s -> %s", from_id, to_id,
                                exc_info=True)
        return moved, skipped

    def _repoint_records(self, from_id, to_id):
        """把 from_id 上的关联数据改指到 to_id，返回各表处理条数。

        复合主键/唯一约束的表逐行处理：目标已有同键记录时，保留目标、删掉冗余行
        （冗余行本来就没有独立信息，例如"同一用户对同一本书的阅读状态"）。
        """
        counts = {}

        # 单列主键 book_id 的表：直接 UPDATE 即可（这些表 book_id 不是主键，
        # 不存在"目标已有同键"的冲突）
        for model in (Reading, BookReadingStats, ManualReadingLog, BookReview):
            n = self.session.query(model).filter(model.book_id == from_id).update(
                {model.book_id: to_id}, synchronize_session=False)
            counts[model.__tablename__] = n
        # 把上面的 UPDATE 落盘，避免后续步骤的 autoflush 交错执行
        self.session.flush()

        # Item：book_id 是主键，目标已有就不动
        counts["items"] = self._merge_pk_table(Item, "book_id", from_id, to_id)

        # ReadingState / BookVisit：(book_id, reader_id) 复合主键
        counts["reading_state"] = self._merge_composite(
            ReadingState, from_id, to_id, ["book_id", "reader_id"])
        counts["book_visits"] = self._merge_composite(
            BookVisit, from_id, to_id, ["book_id", "reader_id"])

        # BookListBook：(booklist_id, book_id) 唯一。目标书单里已有这本就删冗余行，
        # 同时扣减书单 book_count（重复行也算过一次计数）
        counts["booklist_books"] = self._merge_booklist(from_id, to_id)

        # BookShare：book_id 唯一。目标已有分享就删掉来源分享（分享链接不重复发两个）
        counts["book_shares"] = self._merge_pk_table(BookShare, "book_id", from_id, to_id)

        counts["reading_records"] = self._merge_reading_records(from_id, to_id)
        return counts

    def _merge_reading_records(self, from_id, to_id):
        """共读同步记录：身份以 book_hash 为准，book_id 只是便于整型索引的冗余列。

        直接改 book_id 会让 hash 与 id 指向不同的书（下次同步按 hash 查就串了），
        所以这里删掉来源书的记录、不做改指——这类是设备端同步快照，客户端下次同步
        会重新灌入，删掉没有长期损失。返回删除条数。
        """
        n = 0
        try:
            rows = self.session.query(ReadingRecord).filter(
                ReadingRecord.book_id == from_id).all()
            for row in rows:
                self.session.delete(row)
                n += 1
        except Exception as err:
            logging.warning("[DEDUP] 清理 book_id=%s 的共读同步记录失败: %s", from_id, err)
        return n

    def _merge_pk_table(self, model, pk_col, from_id, to_id, filter_col="book_id"):
        """目标已有同主键记录时，删除来源记录；否则改指。

        用于 Item（book_id 主键）、BookShare（book_id 唯一）这类"一本书只能有一条"
        的表：两本重复书各自都有关联行时，合并后只能留一条，保留目标那条
        （保留书是用户真正在用的那本，其上的标记更有意义）。

        必须先删后改：SQLAlchemy 的 autoflush 会在执行 UPDATE 前把挂起的 DELETE
        刷下去，若顺序反了，UPDATE 会与尚在表中的目标行撞主键/唯一约束。
        """
        n = 0
        rows = self.session.query(model).filter(getattr(model, filter_col) == from_id).all()
        if not rows:
            return n

        if pk_col == filter_col:
            # 主键就是 book_id（Item / BookShare）：只要目标书已存在一行，
            # 所有来源行都是冗余——删来源、保留目标。
            target_exists = self.session.query(model).filter(
                getattr(model, filter_col) == to_id).first() is not None
            if target_exists:
                for row in rows:
                    self.session.delete(row)
                self.session.flush()
                return 0
            # 目标没有：改指即可（只有一行可能，主键是 book_id）
            for row in rows:
                setattr(row, filter_col, to_id)
                n += 1
            self.session.flush()
            return n

        # 主键与 book_id 不同列：逐行判断目标是否已占用该主键值
        pk_vals = {getattr(r, pk_col) for r in rows}
        taken = {
            getattr(r, pk_col)
            for r in self.session.query(model).filter(
                getattr(model, pk_col).in_(pk_vals),
                getattr(model, filter_col) == to_id).all()
        }
        for row in rows:
            if getattr(row, pk_col) in taken:
                self.session.delete(row)
        if taken:
            self.session.flush()
        for row in rows:
            if getattr(row, pk_col) not in taken:
                setattr(row, filter_col, to_id)
                n += 1
        self.session.flush()
        return n

    def _merge_composite(self, model, from_id, to_id, key_cols):
        """复合主键表（reading_state / book_visits）：来源行与目标行同键时删来源，
        保留目标已有状态；不同键的改指过来。先删后改，理由同 _merge_pk_table。"""
        n = 0
        rows = self.session.query(model).filter(model.book_id == from_id).all()
        if not rows:
            return n
        other_cols = [c for c in key_cols if c != "book_id"]
        # 目标书已有的键集合
        taken = set()
        for r in self.session.query(model).filter(model.book_id == to_id).all():
            taken.add(tuple(getattr(r, c) for c in other_cols))
        to_drop, to_move = [], []
        for row in rows:
            key = tuple(getattr(row, c) for c in other_cols)
            (to_drop if key in taken else to_move).append(row)
        for row in to_drop:
            self.session.delete(row)
        if to_drop:
            self.session.flush()
        for row in to_move:
            row.book_id = to_id
            n += 1
        self.session.flush()
        return n

    def _merge_booklist(self, from_id, to_id):
        """书单关联：目标书单已有保留书则删冗余行并扣减计数，否则改指。"""
        n = 0
        rows = self.session.query(BookListBook).filter(BookListBook.book_id == from_id).all()
        if not rows:
            return n
        # 目标书在哪些书单里已经存在
        taken = {
            r.booklist_id
            for r in self.session.query(BookListBook).filter(
                BookListBook.book_id == to_id,
                BookListBook.booklist_id.in_([x.booklist_id for x in rows])).all()
        }
        to_drop = [r for r in rows if r.booklist_id in taken]
        to_move = [r for r in rows if r.booklist_id not in taken]
        for row in to_drop:
            self.session.delete(row)
            bl = self.session.query(BookList).filter(BookList.id == row.booklist_id).first()
            if bl is not None:
                bl.book_count = max(0, (bl.book_count or 0) - 1)
                bl.update_time = datetime.datetime.now()
        if to_drop:
            self.session.flush()
        for row in to_move:
            row.book_id = to_id
            n += 1
        self.session.flush()
        return n

    def _delete_calibre_book(self, book_id):
        """删除 calibre 侧书籍记录。仅当该记录确实没有任何电子书格式时才删，
        避免把用户真正想保留的电子书删掉。"""
        try:
            data = self._fetch_meta([book_id]) or []
            row = data[0] if data else None
            if row and _has_ebook_file(row):
                raise RuntimeError(
                    "book_id=%s 仍有电子书格式(%s)，拒绝删除"
                    % (book_id, "/".join(_row_formats(row))))
            self.db.delete_book(book_id)
            logging.info("[DEDUP] 已删除重复书籍 book_id=%s", book_id)
        except Exception as err:
            logging.error("[DEDUP] 删除 book_id=%s 失败: %s", book_id, err)
            raise

    def _relink_scanfiles(self, drop_ids, keep_id):
        """扫描记录里指向被删书籍的行改指保留书，避免下次扫描判定"已导入"却找不到书。"""
        try:
            from webserver.models import ScanFile
            if not drop_ids:
                return 0
            n = self.session.query(ScanFile).filter(ScanFile.book_id.in_(drop_ids)).update(
                {ScanFile.book_id: keep_id}, synchronize_session=False)
            return n
        except Exception as err:
            logging.warning("[DEDUP] 改指扫描记录失败（不影响合并结果）: %s", err)
            return 0
