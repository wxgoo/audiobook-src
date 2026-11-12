#!/usr/bin/env python3
"""R3 合并逻辑收敛的等价性测试。

_merge_books_full / _merge_books_simple / load_books_by_ids 现在共用
BaseHandler._merge_books；这里用重构前的三份实现作为参照，逐字段比对输出，
并确认 load_books_by_ids 不再对同一个 Item 查两次。
"""

import datetime
import random
import unittest
from unittest import mock

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from webserver import models
from webserver.base import calibre_fast
from webserver.handlers import base as base_module
from webserver.handlers.base import ListHandler
from webserver.models import Item, Reader

READ_RANGE_KEY = "ALLOW_READ_RANGE_SETTING"
_FIXED_TIME = datetime.datetime(2026, 1, 1, 12, 0, 0)


class FakeCalibreDB:
    field_metadata = {"#myshelf": {"is_custom": True, "colnum": 3}}

    def __init__(self, books):
        self.books = books

    def get_data_as_dict(self, ids=None, **kwargs):
        return [dict(self.books[bid]) for bid in (ids or []) if bid in self.books]


def legacy_merge_full(handler, books):
    from webserver.handlers.audio import AudioBooksCache

    handler._build_custom_column_map()
    audio_book_ids = AudioBooksCache.get_audio_book_ids_set()
    maps, empty_item = handler._item_maps([book["id"] for book in books])

    soled_books = set()
    for book in books:
        for colnum, key in handler._custom_column_map.items():
            if colnum in book:
                book[key] = book.pop(colnum)
        if book["id"] in audio_book_ids:
            book["has_audio"] = 1
        book_item = maps.get(book["id"], empty_item)
        if book_item["sole"] and book_item["collector_id"] != handler.user_id():
            soled_books.add(book["id"])
        else:
            book.update(book_item)

    if len(soled_books) > 0 and len(books) > 0:
        books = [b for b in books if b["id"] not in soled_books]

    if base_module.CONF.get("ALLOW_READ_RANGE_SETTING", False):
        books = [b for b in books if handler.is_book_visible(b)]
    return books


def legacy_merge_simple(handler, books):
    handler._build_custom_column_map()
    maps, empty_item = handler._item_maps([book["id"] for book in books])
    for book in books:
        for colnum, key in handler._custom_column_map.items():
            if colnum not in book:
                continue
            book[key] = book.pop(colnum)
        book.update(maps.get(book["id"], empty_item))
    return books


def legacy_load_books_by_ids(handler, ids, max_count=0):
    if not ids:
        return []
    if (max_count > 0) and (len(ids) > max_count):
        ids = set(random.sample(list(ids), max_count))
    books = handler.calibre_db.get_data_as_dict(ids=ids, **calibre_fast.list_kwargs())

    ids = [book["id"] for book in books]
    sole_book_ids = (
        set(
            item.book_id
            for item in handler.sqlite_session.query(Item)
            .filter(
                Item.book_id.in_(ids),
                Item.sole == 1,
                Item.collector_id != handler.user_id(),
            )
            .all()
        )
        if ids
        else set()
    )
    books = [b for b in books if b["id"] not in sole_book_ids]

    if base_module.CONF.get(READ_RANGE_KEY, False):
        for book in books:
            for colnum, key in handler._custom_column_map.items():
                if colnum in book:
                    book[key] = book.pop(colnum)
        books = [b for b in books if handler.is_book_visible(b)]

    item = Item()
    empty_item = item.to_dict()
    empty_item["collector"] = handler.sqlite_session.query(Reader).order_by(Reader.id).first()
    remaining_ids = [book["id"] for book in books]
    items = (
        handler.sqlite_session.query(Item).filter(Item.book_id.in_(remaining_ids)).all()
        if remaining_ids
        else []
    )
    maps = {}
    for b in items:
        d = b.to_dict()
        d["collector"] = b.collector.to_dict() if b.collector else empty_item["collector"]
        maps[b.book_id] = d

    for book in books:
        book.update(maps.get(book["id"], empty_item))
    return books


class TestMergeBooksEquivalence(unittest.TestCase):

    def setUp(self):
        # Item() 的默认 create_time 是「当前时刻」：empty_item 每次新建都会差几毫秒，
        # 会让两次运行的结果无法逐字段比对，这里固定成常量。
        orig_item_init = Item.__init__

        def fixed_item_init(item_self):
            orig_item_init(item_self)
            item_self.create_time = _FIXED_TIME

        item_patcher = mock.patch.object(Item, "__init__", fixed_item_init)
        item_patcher.start()
        self.addCleanup(item_patcher.stop)

        engine = create_engine("sqlite://")
        models.Base.metadata.create_all(engine, tables=[Reader.__table__, Item.__table__])
        self.session = sessionmaker(bind=engine)()
        self.addCleanup(self.session.close)
        self.statements = []
        event.listen(
            engine,
            "before_cursor_execute",
            lambda conn, cur, stmt, *a: self.statements.append(stmt),
        )

        for reader_id, name in ((2, "owner"), (7, "me"), (8, "other")):
            reader = Reader()
            reader.id = reader_id
            reader.username = name
            reader.password = "x"
            self.session.add(reader)

        # 1: 普通书；2: 他人独有的书；3: 我自己独有的书；4: 没有 Item；5: 带音频的普通书
        for book_id, collector_id, sole in ((1, 7, False), (2, 8, True), (3, 7, True), (5, 7, False)):
            item = Item()
            item.book_id = book_id
            item.collector_id = collector_id
            item.sole = sole
            self.session.add(item)
        self.session.commit()

        self.calibre_db = FakeCalibreDB({
            book_id: {"id": book_id, "title": "B%d" % book_id, "authors": ["A"], "tags": [],
                      3: "custom-%d" % book_id}
            for book_id in (1, 2, 3, 4, 5)
        })

        self.handler = object.__new__(ListHandler)
        self.handler.sqlite_session = self.session
        self.handler.calibre_db = self.calibre_db
        self.handler.current_user = self.session.get(Reader, 7)
        self.handler.user_id = lambda: 7
        self.handler.is_admin = lambda: False

        conf_patcher = mock.patch.dict(base_module.CONF, {READ_RANGE_KEY: False})
        conf_patcher.start()
        self.addCleanup(conf_patcher.stop)

        audio_patcher = mock.patch(
            "webserver.handlers.audio.AudioBooksCache.get_audio_book_ids_set",
            return_value={5},
        )
        audio_patcher.start()
        self.addCleanup(audio_patcher.stop)

    def fresh_books(self):
        return [dict(self.calibre_db.books[book_id]) for book_id in (1, 2, 3, 4, 5)]

    def test_full_matches_legacy(self):
        expected = legacy_merge_full(self.handler, self.fresh_books())
        actual = self.handler._merge_books_full(self.fresh_books())
        self.assertEqual(actual, expected)
        self.assertEqual([b["id"] for b in actual], [1, 3, 4, 5])
        self.assertEqual(actual[3]["has_audio"], 1)
        self.assertEqual(actual[0]["#myshelf"], "custom-1")

    def test_simple_matches_legacy(self):
        expected = legacy_merge_simple(self.handler, self.fresh_books())
        actual = self.handler._merge_books_simple(self.fresh_books())
        self.assertEqual(actual, expected)
        # simple 不做 sole 过滤
        self.assertEqual([b["id"] for b in actual], [1, 2, 3, 4, 5])
        self.assertNotIn("has_audio", actual[4])

    def test_load_books_by_ids_matches_legacy(self):
        expected = legacy_load_books_by_ids(self.handler, {1, 2, 3, 4, 5})
        self.statements.clear()
        actual = self.handler.load_books_by_ids({1, 2, 3, 4, 5})
        self.assertEqual(actual, expected)
        self.assertEqual([b["id"] for b in actual], [1, 3, 4, 5])

        # 重构前 sole 查询 + 剩余 Item 查询 = 2 次 FROM items；现在只 1 次
        item_selects = [s for s in self.statements if "FROM items" in s]
        self.assertEqual(len(item_selects), 1)
        self.assertEqual(len(self.statements), 3)  # items + collectors + 兜底 reader

    def test_load_books_by_ids_empty(self):
        self.assertEqual(self.handler.load_books_by_ids(set()), [])


if __name__ == "__main__":
    unittest.main()
