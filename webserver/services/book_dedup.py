#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""同名重复书籍的检测与合并（迁移工具）。

背景：有声书走 `audios/<book_id>/`、电子书走 `library/`，上游导入音频时只看
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
3. **音频搬到保留书 id 下**。`audios/<重复id>/` → `audios/<保留id>/`，保持
   `audios/<book_id>/` 这条路径约定不变（播放器扫描、字幕配对都依赖它）。
   目标目录已有同名文件时跳过该文件，不覆盖。
4. **关联数据改指而非删除**。阅读进度、收藏、书单、评论、分享等全部迁移到保留书，
   避免用户"进度凭空消失"。复合主键（reading_state / book_visits）与唯一约束
   （booklist_books / book_shares）逐行判断冲突，冲突时保留已有的、丢弃冗余的。
5. **执行前自动备份**。备份 SQLite 用户库文件到 `data/backup/`，出错可回滚。
"""

import datetime
import logging
import os
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


def _list_audio_files(audio_root, book_id):
    """返回 audios/<book_id>/ 下可播放文件的文件名列表（不存在返回空表）。"""
    d = os.path.join(audio_root, str(book_id))
    if not os.path.isdir(d):
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

        merger = DuplicateBookMerger(db, session, audio_root, backup_dir)
        plan = merger.scan()          # 只读，返回方案
        merger.apply(plan)            # 执行，逐组返回结果
    """

    def __init__(self, db, session, audio_root, backup_dir=None, meta_fetcher=None):
        """meta_fetcher: 可选，签名 (ids) -> list[dict]，用于在**工作线程**里取 calibre
        元数据（handler 传 `run_calibre_async` 包装过的函数，避免阻塞 ioloop）。
        不传则退回直接调 db.get_data_as_dict（仅适合脚本/测试环境）。
        """
        self.db = db
        self.session = session
        self.audio_root = audio_root
        self.backup_dir = backup_dir
        self.meta_fetcher = meta_fetcher
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

        # 按归一化书名分桶
        buckets = {}
        for book_id, title in title_map.items():
            key = _norm_title(title)
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

        # 4.6.0-9：作者冲突检查。分组只按书名，同名不同作者的书也会聚到一起；
        # 原逻辑只看「电子书/音频分布」，一本《人生》路遥的电子书 + 一本《人生》
        # 某网络作者的音频，方向"明确"（1 电子书 + 有音频），会被误合并。
        # 现在要求：每本有音频的书与电子书那本的作者**归一化后必须相交**，
        # 否则整组跳过。作者解析不出（佚名/脏名）时不冲突，维持原有判定。
        from webserver.base.author_norm import authors_conflict

        if with_ebook:
            ebook_authors = with_ebook[0]["authors"]
            for b in with_audio:
                if b["book_id"] == with_ebook[0]["book_id"]:
                    continue
                if authors_conflict(ebook_authors, b["authors"]):
                    return {
                        "key": key,
                        "title": title,
                        "books": briefs,
                        "action": "skipped",
                        "reason": "作者不同（%s vs %s），不是重复书，请人工确认"
                                  % ("、".join(ebook_authors) or "佚名",
                                     "、".join(b["authors"]) or "佚名"),
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
        audio = _list_audio_files(self.audio_root, book_id)
        return {
            "book_id": book_id,
            "title": row.get("title") or "",
            "authors": list(row.get("authors") or []),
            "ebook_formats": _row_formats(row),
            "audio_files": audio,
            "audio_count": len(audio),
        }

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
        """audios/<from_id>/ 里的音频及配套文件搬到 audios/<to_id>/。

        返回 (搬了几个, 跳过的文件)。搬的范围：
          - 音频（_AUDIO_EXTS）
          - 封面（cover.jpg/png）——播放器在 audios/<id>/ 下找封面
          - 字幕与文稿（.srt/.vtt/.txt）——与音频同名才能自动配对
        其它未知文件（下载残留、临时文件）留在原目录，因此目录不会被删——
        这类文件可能是用户手动放的，宁可留着让人自己判断。
        """
        src_dir = os.path.join(self.audio_root, str(from_id))
        dst_dir = os.path.join(self.audio_root, str(to_id))
        moved, skipped = 0, []
        if not os.path.isdir(src_dir):
            return moved, skipped
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
