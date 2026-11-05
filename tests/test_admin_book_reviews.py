#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import json

from tests.test_main import BID_EPUB, BID_TXT, TestWithUserLogin, get_db, setUpModule as init, main
from webserver.models import BookReview
from webserver.services.book_review_service import BookReviewService


def setUpModule():
    init()


class TestAdminBookReviews(TestWithUserLogin):
    """`/api/admin/book-reviews`: 管理员分页列出所有评论 + 通过/屏蔽/恢复。Reader id=1（mocked
    current_user）在 fixture 库里是管理员，见 tests/test_main.py::TestWithAdminUser。"""

    def setUp(self):
        super().setUp()
        main.CONF["REVIEW_REQUIRES_APPROVAL"] = True
        BookReviewService.invalidate_stats(BID_EPUB)
        # 每个用例都把 reader 1 在这两本书上的评论清干净。
        #
        # 本类的用例都会 POST 一条评价（有的还 delete / hide），而 tests/library
        # 是整轮测试共用的一份库，不清就会留给后面的用例：按字母序 admin 系列
        # 先跑，于是 test_book_review 里的
        # `test_get_own_review_before_any_submission` 一上来就查到前任留下的
        # pending 评价，断言 None 失败——单跑该文件永远是绿的。
        self._purge_reviews()

    def tearDown(self):
        self._purge_reviews()
        main.CONF["REVIEW_REQUIRES_APPROVAL"] = False
        super().tearDown()

    @staticmethod
    def _purge_reviews():
        """物理删掉 reader 1 在测试书上的评价 + 相关统计缓存。

        走 SQL 而不是 BookReviewService.delete：后者带状态机（只有 admin 的
        delete 才是物理删），夹具复位不需要那些语义。
        """
        db = get_db()
        db.query(BookReview).filter(
            BookReview.reader_id == 1, BookReview.book_id.in_((BID_EPUB, BID_TXT))
        ).delete(synchronize_session=False)
        db.commit()
        BookReviewService.invalidate_stats(BID_EPUB)
        BookReviewService.invalidate_stats(BID_TXT)

    def test_list_filters_by_status(self):
        self.json("/api/book/%d/review" % BID_EPUB, method="POST", body=json.dumps({"rating": 8, "comment": "x"}))

        d = self.json("/api/admin/book-reviews?status=pending")
        self.assertGreaterEqual(d["total"], 1)
        self.assertTrue(all(r["status"] == "pending" for r in d["reviews"]))
        row = next(r for r in d["reviews"] if r["book_id"] == BID_EPUB)
        self.assertEqual(row["username"], "Rex")  # reader id=1 的用户名，见 tests/cases/users.db fixture

    def test_moderate_approve_hide_restore(self):
        d = self.json("/api/book/%d/review" % BID_TXT, method="POST", body=json.dumps({"rating": 5, "comment": ""}))
        review_id = d["review"]["id"]

        d = self.json("/api/admin/book-reviews", method="POST", body=json.dumps({"id": review_id, "action": "approve"}))
        self.assertEqual(d["err"], "ok")

        d = self.json("/api/admin/book-reviews", method="POST", body=json.dumps({"id": review_id, "action": "hide"}))
        self.assertEqual(d["err"], "ok")
        hidden = self.json("/api/admin/book-reviews?status=hidden")
        self.assertTrue(any(r["id"] == review_id for r in hidden["reviews"]))

        d = self.json("/api/admin/book-reviews", method="POST", body=json.dumps({"id": review_id, "action": "restore"}))
        self.assertEqual(d["err"], "ok")
        approved = self.json("/api/admin/book-reviews?status=approved")
        self.assertTrue(any(r["id"] == review_id for r in approved["reviews"]))

    def test_delete_is_physical_and_irreversible(self):
        d = self.json("/api/book/%d/review" % BID_TXT, method="POST", body=json.dumps({"rating": 5, "comment": ""}))
        review_id = d["review"]["id"]

        d = self.json("/api/admin/book-reviews", method="POST", body=json.dumps({"id": review_id, "action": "delete"}))
        self.assertEqual(d["err"], "ok")

        # 物理删除：不出现在任意 status 过滤下（不同于 hide，hide 后还能在 status=hidden 里查到）
        for status in ("", "pending", "approved", "hidden"):
            listing = self.json("/api/admin/book-reviews?status=%s" % status)
            self.assertFalse(any(r["id"] == review_id for r in listing["reviews"]))

        # 再次删除同一条：查无此评论
        d = self.json("/api/admin/book-reviews", method="POST", body=json.dumps({"id": review_id, "action": "delete"}))
        self.assertEqual(d["err"], "params.invalid")

    def test_moderate_rejects_unknown_action(self):
        d = self.json("/api/book/%d/review" % BID_EPUB, method="POST", body=json.dumps({"rating": 5}))
        review_id = d["review"]["id"]
        d = self.json("/api/admin/book-reviews", method="POST", body=json.dumps({"id": review_id, "action": "bogus"}))
        self.assertEqual(d["err"], "params.invalid")


class TestAdminUserReviewBan(TestWithUserLogin):
    def test_toggle_allow_review(self):
        d = self.json("/api/admin/users", method="POST", body=json.dumps({"id": 2, "allow_review": False}))
        self.assertEqual(d["err"], "ok")

        d = self.json("/api/admin/users")
        user2 = next(u for u in d["users"]["items"] if u["id"] == 2)
        self.assertFalse(user2["allow_review"])

        d = self.json("/api/admin/users", method="POST", body=json.dumps({"id": 2, "allow_review": True}))
        self.assertEqual(d["err"], "ok")
        d = self.json("/api/admin/users")
        user2 = next(u for u in d["users"]["items"] if u["id"] == 2)
        self.assertTrue(user2["allow_review"])
