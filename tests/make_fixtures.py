#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""生成 tests/cases/users.db 与 metadata.db 两个夹具库。

仓库把这两个文件 gitignore 掉了（tests/.gitignore），上游开发机上是本地遗留
产物。沙箱里没有，导致 test_main / test_admin / test_book_review 等整套
「带 HTTP 服务」的测试在 setUpModule 就 FileNotFoundError，一个都跑不起来。

这里按测试代码里写死的期望反推最小夹具：不是要让这些测试全绿（它们还依赖
真实电子书文件和 calibre），而是让它们「能进入测试函数」，从而暴露真正的
回归——比如某次改动把 Book 表结构弄炸。
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
CASES = os.path.join(ROOT, "tests", "cases")


def make_users_db(path):
    """读者库。测试里写死 reader id=1 的用户名是 Rex。"""
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE readers (
            id INTEGER PRIMARY KEY,
            username VARCHAR(200),
            password VARCHAR(200) DEFAULT '',
            salt VARCHAR(200),
            name VARCHAR(100),
            email VARCHAR(200),
            avatar VARCHAR(200),
            admin BOOLEAN DEFAULT 0,
            active BOOLEAN DEFAULT 1,
            permission VARCHAR(100) DEFAULT '',
            create_time DATETIME,
            update_time DATETIME,
            access_time DATETIME,
            extra TEXT DEFAULT '{}',
            vipquota INTEGER DEFAULT 0,
            vipexpire DATETIME,
            read_limit INTEGER DEFAULT 0,
            limit_categories VARCHAR(512) DEFAULT '',
            limit_tags VARCHAR(512) DEFAULT '',
            podcast_token VARCHAR(128) DEFAULT '',
            total_reading_seconds INTEGER NOT NULL DEFAULT 0,
            download_count INTEGER NOT NULL DEFAULT 0,
            push_count INTEGER NOT NULL DEFAULT 0,
            allow_statistic BOOLEAN NOT NULL DEFAULT 1,
            show_home_recommendations BOOLEAN NOT NULL DEFAULT 1,
            allow_review BOOLEAN NOT NULL DEFAULT 1,
            birth_year INTEGER NOT NULL DEFAULT 0
        );
    """)
    import datetime

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = [
        # id, username, name, email, admin
        (1, "rex", "Rex", "rex@example.com", 0),
        (2, "admin", "admin", "admin@example.com", 1),
    ]
    for rid, username, name, email, is_admin in rows:
        cur.execute(
            "INSERT INTO readers (id, username, name, email, admin, active,"
            " permission, create_time, update_time, access_time, extra,"
            " birth_year) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, username, name, email, is_admin, 1, "", now, now, now, "{}", 1990),
        )
    conn.commit()
    conn.close()


def make_metadata_db(path):
    """书库元数据库。结构以 models.py 的 Book 为准，用 create_all 建。"""
    if os.path.exists(path):
        os.remove(path)
    from sqlalchemy import create_engine
    from webserver import models

    engine = create_engine("sqlite:///" + path)
    models.Base.metadata.create_all(engine)
    engine.dispose()


def main():
    os.makedirs(CASES, exist_ok=True)
    make_users_db(os.path.join(CASES, "users.db"))
    make_metadata_db(os.path.join(CASES, "metadata.db"))
    print("fixtures ready:", os.listdir(CASES))


if __name__ == "__main__":
    sys.path.insert(0, ROOT)
    main()
