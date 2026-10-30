#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""同名重复书清理（services/book_dedup.py）的单元测试。

重点覆盖三条安全线：
  ① 方向不明确的组**绝不**自动合并（两本都有电子书、都没电子书、组过大）；
  ② 音频搬目录时不覆盖同名目标文件；
  ③ 关联数据是「改指」而不是「丢弃」，主键/唯一键冲突时才删冗余行。
"""

import os
import shutil
import tempfile
import unittest
from unittest import mock

from webserver.services.book_dedup import (
    DuplicateBookMerger,
    MAX_GROUP_SIZE,
    _has_ebook_file,
    _list_audio_files,
    _norm_title,
    _row_formats,
)


def _meta(book_id, title, fmts=None, paths=None):
    return {
        "id": book_id,
        "title": title,
        "authors": ["某人"],
        "available_formats": fmts or [],
        "formats": paths or [],
    }


class _FakeDB:
    """最小 calibre 库替身：只提供 get_id_map / get_data_as_dict / delete_book。"""

    def __init__(self, meta_rows, titles=None):
        self._rows = {int(r["id"]): r for r in meta_rows}
        self._titles = titles if titles is not None else {
            int(r["id"]): r["title"] for r in meta_rows}
        self.deleted = []
        self.new_api = mock.MagicMock()
        self.new_api.get_id_map.return_value = dict(self._titles)

    def get_data_as_dict(self, book_ids=None):
        if book_ids is None:
            return list(self._rows.values())
        return [self._rows[int(b)] for b in book_ids if int(b) in self._rows]

    def delete_book(self, book_id):
        self.deleted.append(book_id)
        self._rows.pop(int(book_id), None)


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dedup_test_")
        self.audio_root = os.path.join(self.tmp, "audios")
        os.makedirs(self.audio_root, exist_ok=True)
        self.meta_fetcher = None

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make_audio(self, book_id, names):
        d = os.path.join(self.audio_root, str(book_id))
        os.makedirs(d, exist_ok=True)
        for n in names:
            with open(os.path.join(d, n), "wb") as f:
                f.write(b"fake-audio")
        return d

    def merger(self, db, session=None):
        return DuplicateBookMerger(
            db, session or mock.MagicMock(), self.audio_root,
            backup_dir=os.path.join(self.tmp, "backup"),
            meta_fetcher=self.meta_fetcher)


class TestTitleNormalization(unittest.TestCase):
    """分组用的归一化：只负责「聚到一起」，不负责最终判定"""

    def test_basic_folding(self):
        self.assertEqual(_norm_title("三体"), _norm_title("三体"))

    def test_strips_and_collapses_spaces(self):
        self.assertEqual(_norm_title("  三体  "), "三体")
        self.assertEqual(_norm_title("三体   第一部"), "三体 第一部")

    def test_fullwidth_to_halfwidth(self):
        # 全角括号与数字要能匹配半角，否则"（1）"与"(1)"分组失败
        self.assertEqual(_norm_title("Harmony（1）"), _norm_title("Harmony(1)"))
        self.assertEqual(_norm_title("１２３"), "123")

    def test_english_case_insensitive(self):
        self.assertEqual(_norm_title("The Hobbit"), _norm_title("the hobbit"))

    def test_empty(self):
        self.assertEqual(_norm_title(""), "")
        self.assertEqual(_norm_title(None), "")


class TestEbookDetection(unittest.TestCase):
    def test_available_formats_wins(self):
        self.assertTrue(_has_ebook_file({"available_formats": ["EPUB"]}))

    def test_no_formats_no_paths(self):
        self.assertFalse(_has_ebook_file({"available_formats": [], "formats": []}))

    def test_existing_path_fallback(self):
        tmp = tempfile.mkdtemp()
        f = os.path.join(tmp, "a.epub")
        open(f, "wb").close()
        try:
            self.assertTrue(_has_ebook_file({"formats": [f]}))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_path(self):
        self.assertFalse(_has_ebook_file({"formats": ["/nope/x.epub"]}))

    def test_none(self):
        self.assertFalse(_has_ebook_file(None))

    def test_row_formats_from_paths(self):
        self.assertEqual(_row_formats({"formats": ["/a/b.epub", "/a/b.pdf"]}), ["EPUB", "PDF"])

    def test_row_formats_empty(self):
        self.assertEqual(_row_formats({}), [])


class TestAudioListing(_Base):
    def test_lists_only_audio(self):
        self.make_audio(7, ["01.mp3", "cover.jpg", "02.m4a"])
        files = _list_audio_files(self.audio_root, 7)
        self.assertEqual(sorted(files), ["01.mp3", "02.m4a"])

    def test_missing_dir(self):
        self.assertEqual(_list_audio_files(self.audio_root, 999), [])


class TestScanDecisions(_Base):
    """scan() 的判定：只有「恰好一本有电子书 + 存在音频」才自动合并"""

    def test_merges_ebook_plus_audio(self):
        db = _FakeDB([_meta(7, "三体", ["EPUB"]), _meta(9, "三体")])
        self.make_audio(9, ["01.mp3", "02.mp3"])
        plan = self.merger(db).scan()
        self.assertEqual(len(plan["groups"]), 1)
        g = plan["groups"][0]
        self.assertEqual(g["action"], "merge")
        self.assertEqual(g["keep_book_id"], 7)
        self.assertEqual(g["drop_book_ids"], [9])
        self.assertEqual(len(g["audio_moves"]), 1)
        self.assertEqual(g["audio_moves"][0]["from_book_id"], 9)
        self.assertEqual(g["audio_moves"][0]["to_book_id"], 7)
        self.assertEqual(plan["summary"]["mergeable"], 1)
        self.assertEqual(plan["summary"]["will_delete"], 1)
        self.assertEqual(plan["summary"]["will_move_audio"], 2)

    def test_skips_when_both_have_ebook(self):
        """两本都有电子书：可能是同名不同版本，不能自动删"""
        db = _FakeDB([_meta(7, "三体", ["EPUB"]), _meta(9, "三体", ["PDF"])])
        self.make_audio(9, ["01.mp3"])
        plan = self.merger(db).scan()
        g = plan["groups"][0]
        self.assertEqual(g["action"], "skipped")
        self.assertIn("都有电子书", g["reason"])

    def test_skips_when_no_ebook_at_all(self):
        db = _FakeDB([_meta(7, "三体"), _meta(9, "三体")])
        self.make_audio(7, ["01.mp3"])
        self.make_audio(9, ["02.mp3"])
        plan = self.merger(db).scan()
        self.assertEqual(plan["groups"][0]["action"], "skipped")

    def test_skips_too_many(self):
        n = MAX_GROUP_SIZE + 1
        rows = [_meta(i, "三体") for i in range(1, n + 1)]
        rows[0]["available_formats"] = ["EPUB"]
        db = _FakeDB(rows)
        self.make_audio(2, ["01.mp3"])
        plan = self.merger(db).scan()
        self.assertEqual(plan["groups"][0]["action"], "skipped")
        self.assertIn("过多", plan["groups"][0]["reason"])

    def test_no_duplicates(self):
        db = _FakeDB([_meta(1, "三体"), _meta(2, "活着")])
        plan = self.merger(db).scan()
        self.assertEqual(plan["groups"], [])
        self.assertEqual(plan["summary"]["total_groups"], 0)

    def test_single_book_no_group(self):
        db = _FakeDB([_meta(1, "三体", ["EPUB"])])
        self.make_audio(1, ["01.mp3"])
        plan = self.merger(db).scan()
        self.assertEqual(plan["groups"], [])

    def test_three_way_with_one_ebook_two_audio(self):
        db = _FakeDB([_meta(7, "三体", ["EPUB"]), _meta(9, "三体"), _meta(11, "三体")])
        self.make_audio(9, ["a.mp3"])
        self.make_audio(11, ["b.mp3"])
        plan = self.merger(db).scan()
        g = plan["groups"][0]
        self.assertEqual(g["action"], "merge")
        self.assertEqual(g["keep_book_id"], 7)
        self.assertEqual(sorted(g["drop_book_ids"]), [9, 11])
        self.assertEqual(len(g["audio_moves"]), 2)

    def test_empty_titles_ignored(self):
        db = _FakeDB([_meta(1, ""), _meta(2, "")])
        plan = self.merger(db).scan()
        self.assertEqual(plan["groups"], [])

    def test_get_id_map_failure_returns_error(self):
        db = _FakeDB([])
        db.new_api.get_id_map.side_effect = RuntimeError("db locked")
        plan = self.merger(db).scan()
        self.assertEqual(plan["groups"], [])
        self.assertIn("db locked", plan.get("error", ""))


class TestAudioMove(_Base):
    def test_moves_files_and_removes_empty_dir(self):
        src = self.make_audio(9, ["01.mp3", "02.mp3"])
        m = self.merger(_FakeDB([]))
        moved, skipped = m._move_audio(9, 7)
        self.assertEqual(moved, 2)
        self.assertEqual(skipped, [])
        self.assertFalse(os.path.exists(src))
        self.assertTrue(os.path.exists(os.path.join(self.audio_root, "7", "01.mp3")))
        self.assertTrue(os.path.exists(os.path.join(self.audio_root, "7", "02.mp3")))

    def test_does_not_overwrite_existing(self):
        """目标已有同名文件时保留目标内容，跳过来源"""
        self.make_audio(7, ["01.mp3"])
        target = os.path.join(self.audio_root, "7", "01.mp3")
        with open(target, "wb") as f:
            f.write(b"KEEP-ME")
        self.make_audio(9, ["01.mp3", "02.mp3"])
        m = self.merger(_FakeDB([]))
        moved, skipped = m._move_audio(9, 7)
        self.assertEqual(moved, 1)
        self.assertEqual(skipped, ["9/01.mp3"])
        with open(target, "rb") as f:
            self.assertEqual(f.read(), b"KEEP-ME")

    def test_missing_source_is_noop(self):
        m = self.merger(_FakeDB([]))
        self.assertEqual(m._move_audio(123, 7), (0, []))

    def test_moves_cover_along_with_audio(self):
        """封面和字幕是音频的配套文件，必须一起搬走——否则新 id 目录下的
        播放器找不到封面，同名字幕也配不上。源目录搬空后应被删掉。"""
        d = self.make_audio(9, ["01.mp3"])
        for extra in ("cover.jpg", "01.srt"):
            with open(os.path.join(d, extra), "wb") as f:
                f.write(b"x")
        m = self.merger(_FakeDB([]))
        moved, skipped = m._move_audio(9, 7)
        self.assertEqual(moved, 3)
        self.assertEqual(skipped, [])
        self.assertFalse(os.path.exists(d), "搬空后应删除源目录")
        for f in ("01.mp3", "cover.jpg", "01.srt"):
            self.assertTrue(
                os.path.exists(os.path.join(self.audio_root, "7", f)),
                "%s 应已搬到新目录" % f)

    def test_keeps_dir_when_unknown_files_remain(self):
        """目录里有非配套文件（比如下载残留）时，搬完不能删目录"""
        d = self.make_audio(9, ["01.mp3"])
        with open(os.path.join(d, "notes.xyz"), "wb") as f:
            f.write(b"?")
        m = self.merger(_FakeDB([]))
        m._move_audio(9, 7)
        self.assertTrue(os.path.isdir(d))


class TestApplyGuards(_Base):
    def test_refuses_to_delete_book_with_ebook(self):
        """_delete_calibre_book 的最后一道防线：仍有电子书格式就不删"""
        db = _FakeDB([_meta(9, "三体", ["EPUB"])])
        m = self.merger(db)
        with self.assertRaises(RuntimeError):
            m._delete_calibre_book(9)
        self.assertEqual(db.deleted, [])

    def test_deletes_book_without_ebook(self):
        db = _FakeDB([_meta(9, "三体")])
        m = self.merger(db)
        m._delete_calibre_book(9)
        self.assertEqual(db.deleted, [9])

    def test_apply_only_handles_merge_groups(self):
        db = _FakeDB([_meta(7, "三体", ["EPUB"]), _meta(9, "三体", ["PDF"])])
        plan = self.merger(db).scan()
        result = self.merger(db).apply(plan, do_backup=False)
        self.assertEqual(result["merged"], [])
        self.assertEqual(db.deleted, [])

    def test_apply_skips_when_nothing_mergeable(self):
        m = self.merger(_FakeDB([]))
        result = m.apply({"groups": []}, do_backup=False)
        self.assertEqual(result, {"backup": None, "merged": [], "failed": []})


class TestBackup(_Base):
    def test_backup_skips_non_sqlite(self):
        session = mock.MagicMock()
        session.get_bind.return_value.engine.url = "postgresql://x/y"
        m = DuplicateBookMerger(_FakeDB([]), session, self.audio_root,
                                backup_dir=os.path.join(self.tmp, "backup"))
        self.assertIsNone(m.backup())

    def test_backup_no_dir(self):
        m = DuplicateBookMerger(_FakeDB([]), mock.MagicMock(), self.audio_root, backup_dir="")
        self.assertIsNone(m.backup())


class TestRepointRecordsWithRealDB(unittest.TestCase):
    """关联数据迁移：用真实 SQLite 内存库跑。

    验证三件事：
      - 关联数据是「改指」而不是「丢弃」（阅读进度不能凭空消失）
      - 复合主键 / 唯一约束冲突时保留目标行、删冗余行
      - book_hash 为身份的共读记录不能只改 book_id（会串书），应删除
    """

    def setUp(self):
        import datetime as _dt
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from webserver import models as M

        self.M = M
        self.now = _dt.datetime.now()
        self.engine = create_engine("sqlite://")
        M.Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

        for uid, name in ((1, "alice"), (2, "bob")):
            r = M.Reader()
            r.id = uid
            r.username = name
            r.password = "x"
            r.email = "a@b.c"
            self.session.add(r)
        self.session.commit()

        self.tmp = tempfile.mkdtemp(prefix="dedup_db_")
        self.audio_root = os.path.join(self.tmp, "audios")
        os.makedirs(self.audio_root)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def merger(self):
        return DuplicateBookMerger(
            _FakeDB([]), self.session, self.audio_root,
            backup_dir=os.path.join(self.tmp, "backup"))

    def test_reading_and_review_are_repointed(self):
        M, s = self.M, self.session
        s.add(M.Reading(reader_id=1, book_id=9, action="read", protocol="web",
                        start_time=self.now, date=self.now.date()))
        s.add(M.BookReview(reader_id=1, book_id=9, rating=8, comment="好",
                           create_time=self.now, update_time=self.now))
        s.commit()

        self.merger()._repoint_records(9, 7)
        s.commit()

        self.assertEqual(s.query(M.Reading).filter(M.Reading.book_id == 7).count(), 1)
        self.assertEqual(s.query(M.Reading).filter(M.Reading.book_id == 9).count(), 0)
        self.assertEqual(s.query(M.BookReview).filter(M.BookReview.book_id == 7).count(), 1)

    def test_reading_state_conflict_keeps_target(self):
        M, s = self.M, self.session
        a = M.ReadingState(9, 1)
        a.read_state = 2
        b = M.ReadingState(7, 1)
        b.read_state = 1
        c = M.ReadingState(9, 2)
        c.read_state = 1
        s.add_all([a, b, c])
        s.commit()

        self.merger()._repoint_records(9, 7)
        s.commit()

        rows = s.query(M.ReadingState).filter(M.ReadingState.book_id == 7).all()
        by_reader = {r.reader_id: r for r in rows}
        self.assertEqual(sorted(by_reader), [1, 2])
        self.assertEqual(by_reader[1].read_state, 1, "冲突时保留目标书上的状态")
        self.assertEqual(s.query(M.ReadingState).filter(M.ReadingState.book_id == 9).count(), 0)

    def test_item_conflict_keeps_target(self):
        M, s = self.M, self.session
        i9, i7 = M.Item(), M.Item()
        i9.book_id, i7.book_id = 9, 7
        s.add_all([i9, i7])
        s.commit()

        self.merger()._repoint_records(9, 7)
        s.commit()

        self.assertEqual(s.query(M.Item).filter(M.Item.book_id == 7).count(), 1)
        self.assertEqual(s.query(M.Item).filter(M.Item.book_id == 9).count(), 0)

    def test_booklist_duplicate_row_dropped_and_count_fixed(self):
        M, s = self.M, self.session
        bl = M.BookList(1, "我的书单")
        bl.book_count = 2
        s.add(bl)
        s.commit()
        s.add_all([
            M.BookListBook(booklist_id=bl.id, book_id=9),
            M.BookListBook(booklist_id=bl.id, book_id=7),
        ])
        s.commit()

        self.merger()._repoint_records(9, 7)
        s.commit()

        rows = s.query(M.BookListBook).filter(M.BookListBook.booklist_id == bl.id).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].book_id, 7)
        s.refresh(bl)
        self.assertEqual(bl.book_count, 1, "删掉一行后计数要跟着减")

    def test_booklist_repoint_when_no_conflict(self):
        M, s = self.M, self.session
        bl = M.BookList(1, "单")
        bl.book_count = 1
        s.add(bl)
        s.commit()
        s.add(M.BookListBook(booklist_id=bl.id, book_id=9))
        s.commit()

        self.merger()._repoint_records(9, 7)
        s.commit()

        rows = s.query(M.BookListBook).filter(M.BookListBook.booklist_id == bl.id).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].book_id, 7)
        s.refresh(bl)
        self.assertEqual(bl.book_count, 1, "改指不改条数，计数不变")

    def test_book_share_not_duplicated(self):
        M, s = self.M, self.session
        s.add_all([
            M.BookShare(9, "tok-new", creator_id=1),
            M.BookShare(7, "tok-old", creator_id=1),
        ])
        s.commit()

        self.merger()._repoint_records(9, 7)
        s.commit()

        shares = s.query(M.BookShare).all()
        self.assertEqual(len(shares), 1)
        self.assertEqual(shares[0].book_id, 7)
        self.assertEqual(shares[0].token, "tok-old", "保留目标书上已有的分享")

    def test_book_visit_repointed(self):
        M, s = self.M, self.session
        s.add(M.BookVisit(reader_id=2, book_id=9))
        s.commit()

        self.merger()._repoint_records(9, 7)
        s.commit()

        self.assertEqual(s.query(M.BookVisit).filter(M.BookVisit.book_id == 7).count(), 1)
        self.assertEqual(s.query(M.BookVisit).filter(M.BookVisit.book_id == 9).count(), 0)

    def test_reading_records_dropped_not_repointed(self):
        """共读同步记录身份以 book_hash 为准，只改 book_id 会让 hash 与 id 串书"""
        M, s = self.M, self.session
        rr = M.ReadingRecord()
        rr.reader_id = 1
        rr.book_hash = "abc"
        rr.book_id = 9
        rr.kind = "books"
        rr.record_id = "abc"
        rr.uid = 1
        rr.payload = {}
        rr.updated_at = 1
        s.add(rr)
        s.commit()

        self.merger()._repoint_records(9, 7)
        s.commit()

        self.assertEqual(s.query(M.ReadingRecord).count(), 0)

    def test_scanfiles_relinked(self):
        M, s = self.M, self.session
        row = M.ScanFile("/data/x/1.mp3", "h1", 0)
        row.book_id = 9
        row.status = M.ScanFile.IMPORTED
        s.add(row)
        s.commit()

        self.merger()._relink_scanfiles([9], 7)
        s.commit()

        s.refresh(row)
        self.assertEqual(row.book_id, 7)


if __name__ == "__main__":
    unittest.main()
