#!/usr/bin/env python3
"""BookReadingStats.get 重构等价性测试。

只针对本次 P2 重构：4 条 count() + 逐本 get_book 收敛为
1 条条件聚合 + 1 次批量取书，要求返回 JSON 与旧实现完全一致。
"""

import asyncio
import datetime
import unittest
from unittest import mock

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from webserver import models
from webserver.handlers.book import BookReadingStats
from webserver.models import Item, Reader, ReadingState


class FakeCalibreDB:
    """只实现 _merge_books_simple 用到的成员，并记录批量取书调用。"""

    field_metadata = {}

    def __init__(self, books):
        self.books = books
        self.calls = []

    def get_data_as_dict(self, ids=None, **kwargs):
        ids = list(ids or [])
        self.calls.append(ids)
        return [dict(self.books[bid]) for bid in ids if bid in self.books]


def legacy_reading_stats(handler):
    """重构前 BookReadingStats.get 的逻辑，仅用于等价性对比。"""
    from webserver.base.formatter import BookFormatter, ReadingStateFormatter
    from webserver.site_time import site_month_bounds_server_local

    user_id = handler.user_id()
    month_start, month_end = site_month_bounds_server_local()

    total_reading = handler.sqlite_session.query(ReadingState).filter(
        ReadingState.reader_id == user_id,
        ReadingState.read_state == 1
    ).count()

    total_read_done = handler.sqlite_session.query(ReadingState).filter(
        ReadingState.reader_id == user_id,
        ReadingState.read_state == 2
    ).count()

    month_reading = handler.sqlite_session.query(ReadingState).filter(
        ReadingState.reader_id == user_id,
        ReadingState.read_state == 1,
        ReadingState.read_date >= month_start,
        ReadingState.read_date < month_end
    ).count()

    month_read_done = handler.sqlite_session.query(ReadingState).filter(
        ReadingState.reader_id == user_id,
        ReadingState.read_state == 2,
        ReadingState.read_date >= month_start,
        ReadingState.read_date < month_end
    ).count()

    month_read_done_states = handler.sqlite_session.query(ReadingState).filter(
        ReadingState.reader_id == user_id,
        ReadingState.read_state == 2,
        ReadingState.read_date >= month_start,
        ReadingState.read_date < month_end
    ).order_by(ReadingState.read_date.desc()).limit(12).all()

    month_read_done_books = []
    for state in month_read_done_states:
        book = handler.get_book(state.book_id, raise_exception=False)
        if not book:
            continue
        book_data = BookFormatter(handler, book).format()
        book_data["state"] = ReadingStateFormatter.format_reading_state(state)
        month_read_done_books.append(book_data)

    current_reading_states = handler.sqlite_session.query(ReadingState).filter(
        ReadingState.reader_id == user_id,
        ReadingState.read_state == 1
    ).order_by(ReadingState.read_date.desc()).limit(12).all()

    current_reading_books = []
    for state in current_reading_states:
        book = handler.get_book(state.book_id, raise_exception=False)
        if not book:
            continue
        book_data = BookFormatter(handler, book).format()
        book_data["state"] = ReadingStateFormatter.format_reading_state(state)
        current_reading_books.append(book_data)

    return {
        "err": "ok",
        "stats": {
            "total_reading": total_reading,
            "total_read_done": total_read_done,
            "month_reading": month_reading,
            "month_read_done": month_read_done,
            "current_year": month_start.year,
            "current_month": month_start.month,
        },
        "month_read_done_books": month_read_done_books,
        "current_reading_books": current_reading_books,
    }


class TestBookReadingStatsHandler(unittest.TestCase):

    def setUp(self):
        engine = create_engine("sqlite://")
        models.Base.metadata.create_all(
            engine, tables=[Reader.__table__, Item.__table__, ReadingState.__table__]
        )
        self.session = sessionmaker(bind=engine)()
        self.addCleanup(self.session.close)

        self.statements = []
        event.listen(
            engine,
            "before_cursor_execute",
            lambda conn, cur, stmt, *a: self.statements.append(stmt),
        )

        self._add_reader(1, "u1")
        self._add_reader(2, "u2")

        now = datetime.datetime.now()
        from webserver.site_time import site_month_bounds_server_local
        month_start, _ = site_month_bounds_server_local()
        last_month = month_start - datetime.timedelta(days=1)

        self.month_done_ids = list(range(1001, 1013))       # 12 本，本月读完
        self.reading_ids = list(range(1021, 1033))          # 12 本，在读
        self.old_done_ids = list(range(1041, 1044))         # 3 本，上月读完
        self.old_reading_ids = list(range(1051, 1054))      # 3 本，上月标记在读
        self.unread_ids = list(range(1061, 1063))           # 2 本，未读

        for bid in self.month_done_ids:
            self._add_state(bid, 1, 2, now)
        for bid in self.reading_ids:
            self._add_state(bid, 1, 1, now)
        for bid in self.old_done_ids:
            self._add_state(bid, 1, 2, last_month)
        for bid in self.old_reading_ids:
            self._add_state(bid, 1, 1, last_month)
        for bid in self.unread_ids:
            self._add_state(bid, 1, 0, now)
        # 其他用户的状态不能计入
        for bid in self.month_done_ids[:3]:
            self._add_state(bid, 2, 1, now)

        all_ids = (self.month_done_ids + self.reading_ids + self.old_done_ids
                   + self.old_reading_ids + self.unread_ids)
        for bid in all_ids:
            item = Item()
            item.book_id = bid
            item.collector_id = 1
            self.session.add(item)
        self.session.commit()

        self.calibre_db = FakeCalibreDB({
            bid: {
                "id": bid,
                "title": "Book %d" % bid,
                "authors": ["Author %d" % bid],
                "author_sort": "Author %d" % bid,
                "tags": [],
                "rating": 0,
                "timestamp": None,
                "last_modified": None,
                "publisher": "",
                "series": None,
                "series_index": None,
                "languages": [],
                "isbn": "",
                "comments": "",
                "available_formats": [],
            }
            for bid in all_ids
        })

        self.handler = object.__new__(BookReadingStats)
        self.handler.sqlite_session = self.session
        self.handler.calibre_db = self.calibre_db
        self.handler.cdn_url = ""
        self.handler.api_url = ""
        self.handler.current_user = mock.Mock(id=1)
        self.handler.user_id = lambda: 1
        self.handler.is_admin = lambda: False
        self.handler.is_book_owner = lambda book_id, user_id: user_id == 1
        self.handler.make_download_sign = lambda *a, **kw: ""
        self.handler.request = mock.Mock(headers={})
        self.handler.set_header = mock.Mock()
        self.handler.write = mock.Mock()
        self.handler.finish = mock.Mock()

        # BookFormatter 会查下架表（走 models 全局 session），这里不需要真实结果
        takedown_patcher = mock.patch(
            "webserver.base.formatter.book_takedown",
            mock.Mock(is_takedown=lambda book_id: False, notice=lambda: ""),
        )
        takedown_patcher.start()
        self.addCleanup(takedown_patcher.stop)

    def _add_reader(self, reader_id, username):
        reader = Reader()
        reader.id = reader_id
        reader.username = username
        reader.password = "x"
        self.session.add(reader)

    def _add_state(self, book_id, reader_id, read_state, read_date):
        state = ReadingState(book_id, reader_id)
        state.read_state = read_state
        state.read_date = read_date
        self.session.add(state)

    def _run_handler(self):
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(BookReadingStats.get(self.handler))
        finally:
            loop.close()
        self.assertTrue(self.handler.write.call_count >= 1)
        return self.handler.write.call_args[0][0]

    def test_response_matches_legacy_implementation(self):
        self.statements.clear()  # 去掉 setUp 里的 INSERT
        legacy = legacy_reading_stats(self.handler)
        legacy_sql = len(self.statements)
        legacy_calibre_calls = len(self.calibre_db.calls)

        self.statements.clear()
        self.calibre_db.calls.clear()
        self.handler.write.reset_mock()
        current = self._run_handler()
        current_sql = len(self.statements)
        current_calibre_calls = len(self.calibre_db.calls)

        self.assertEqual(current["err"], "ok")
        # 返回值结构与字段必须完全一致
        self.assertEqual(current, legacy)
        self.assertEqual(current["stats"], {
            "total_reading": 15,
            "total_read_done": 15,
            "month_reading": 12,
            "month_read_done": 12,
            "current_year": current["stats"]["current_year"],
            "current_month": current["stats"]["current_month"],
        })
        self.assertEqual(len(current["month_read_done_books"]), 12)
        self.assertEqual(len(current["current_reading_books"]), 12)

        # 重构前：6 条基础统计/列表 SQL + 24 本 × (items + collectors) = 54
        self.assertEqual(legacy_sql, 54)
        self.assertEqual(legacy_calibre_calls, 24)
        # 重构后：1 聚合 + 2 列表 + 1 批量 items + 1 批量 collectors = 5
        self.assertEqual(current_sql, 5)
        self.assertEqual(current_calibre_calls, 1)


if __name__ == "__main__":
    unittest.main()
