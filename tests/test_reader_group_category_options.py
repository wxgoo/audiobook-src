"""读者组分类下拉的数据口径（r12）。

用户反馈：分级权限的「分类」下拉跟书籍分类对不上，混进了
「哈利波特中文版」「台版」这种明显不是分类的条目。

根因：`custom_column_<n>` 是 calibre 的**值字典**，一本书从某分类下
移走后字典记录仍在（calibre 不清理）。原来直接
`SELECT DISTINCT value FROM custom_column_<n>`，把孤儿值也列了出来。

危害不只是碍眼——书籍侧判定是 `book_category in limit_categories`，
而 book_category 只可能取到**被 link 表引用**的值。管理员把孤儿值
选进白名单 → 该组一本书都看不到，界面上还看不出原因。

这里用真 sqlite 建 calibre 的最小结构，断言 SQL 口径与书籍侧一致。
"""
import os
import sqlite3
import tempfile

import pytest

COLNUM = 5  # 测试用的 colnum


@pytest.fixture()
def calibre_db():
    """造一个 calibre 的最小结构：值字典 + link 表 + books。"""
    path = tempfile.mktemp(suffix=".db")
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT);
        CREATE TABLE custom_column_5 (id INTEGER PRIMARY KEY, value TEXT, extra BLOB);
        CREATE TABLE books_custom_column_5_link (book INTEGER, value INTEGER,
                                                 PRIMARY KEY(book, value));
    """)
    # 字典里有 5 个值，但只有「小说」「绘本」真的被书引用
    c.executemany("INSERT INTO custom_column_5 (id, value) VALUES (?, ?)",
                  [(1, "小说"), (2, "绘本"), (3, "哈利波特中文版"),
                   (4, "台版"), (5, "科普")])
    c.executemany("INSERT INTO books (id, title) VALUES (?, ?)",
                  [(1, "小王子"), (2, "好饿的毛毛虫")])
    c.executemany("INSERT INTO books_custom_column_5_link (book, value) VALUES (?, ?)",
                  [(1, 1), (2, 2)])
    c.commit()
    yield c
    c.close()
    os.unlink(path)


def _new_sql(c, colnum=COLNUM):
    """与 reader_group.py 里一致的 SQL。"""
    return (
        "SELECT DISTINCT d.value FROM custom_column_%d d "
        "JOIN books_custom_column_%d_link l ON l.value = d.id "
        "WHERE d.value IS NOT NULL AND d.value != '' "
        "ORDER BY d.value" % (colnum, colnum)
    )


def _old_sql(c, colnum=COLNUM):
    return (
        "SELECT DISTINCT value FROM custom_column_%d "
        "WHERE value IS NOT NULL AND value != '' ORDER BY value" % colnum
    )


def test_old_sql_leaks_orphans(calibre_db):
    """先钉住 bug 本身：旧 SQL 会把孤儿值也列出来。"""
    rows = [r[0] for r in calibre_db.execute(_old_sql(calibre_db))]
    assert "哈利波特中文版" in rows
    assert "台版" in rows
    assert len(rows) == 5


def test_new_sql_only_lists_used_values(calibre_db):
    """新 SQL 只列真的被书引用的值。"""
    rows = [r[0] for r in calibre_db.execute(_new_sql(calibre_db))]
    assert rows == ["小说", "绘本"], rows
    assert "哈利波特中文版" not in rows
    assert "台版" not in rows


def test_new_sql_matches_book_side_judgement(calibre_db):
    """★ 核心：下拉里的每个值，都必须在书籍侧真的能匹配到至少一本书。

    这是「选了却看不到书」那个坑的根因——口径必须一致。
    """
    options = [r[0] for r in calibre_db.execute(_new_sql(calibre_db))]
    for cat in options:
        n = calibre_db.execute(
            "SELECT count(*) FROM books_custom_column_5_link l "
            "JOIN custom_column_5 d ON d.id = l.value WHERE d.value = ?", (cat,)
        ).fetchone()[0]
        assert n > 0, "下拉里的分类 %r 没有对应任何一本书" % cat


def test_new_sql_keeps_null_and_empty_out(calibre_db):
    """空值和 NULL 仍然要过滤（原行为不能丢）。"""
    calibre_db.execute("INSERT INTO custom_column_5 (id, value) VALUES (6, '')")
    calibre_db.execute("INSERT INTO custom_column_5 (id, value) VALUES (7, NULL)")
    # 让它们也被引用，否则是 JOIN 过滤掉的，测不到 WHERE 这一层
    calibre_db.execute("INSERT INTO books_custom_column_5_link (book, value) VALUES (1, 6)")
    calibre_db.execute("INSERT INTO books_custom_column_5_link (book, value) VALUES (1, 7)")
    calibre_db.commit()
    rows = [r[0] for r in calibre_db.execute(_new_sql(calibre_db))]
    assert "" not in rows
    assert None not in rows


def test_multiple_books_same_category_not_duplicated(calibre_db):
    """多本书共用一个分类时，DISTINCT 要生效。"""
    calibre_db.execute("INSERT INTO books (id, title) VALUES (3, '小王子2')")
    calibre_db.execute("INSERT INTO books_custom_column_5_link (book, value) VALUES (3, 1)")
    calibre_db.commit()
    rows = [r[0] for r in calibre_db.execute(_new_sql(calibre_db))]
    assert rows.count("小说") == 1, rows


def test_handler_source_uses_join():
    """handler 里的 SQL 必须带 JOIN link 表。

    这里不真的跑 handler：`get` 上叠了 @js + @is_admin，依赖 tornado 的
    request/cookies_cache/set_header，为了取一个 SQL 字符串去搭整套
    tornado 运行时桩不值得，而且桩一旦不完整测试就会假失败。
    改为读源码断言 + 上面的真库 SQL 测试，两层合起来够用：
      - 真库测试证明「带 JOIN 的 SQL 是对的」
      - 这个测试证明「handler 用的就是带 JOIN 的 SQL」
    """
    import os

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "webserver", "handlers", "reader_group.py")
    src = open(path, encoding="utf-8").read()

    assert "books_custom_column_%d_link" in src, (
        "reader_group.py 的分类 SQL 没有 JOIN books_custom_column_N_link，"
        "会把 calibre 值字典里的孤儿值（如「哈利波特中文版」「台版」）"
        "也列进分类下拉——用户报过这个问题"
    )

    # 旧写法特征：直接 SELECT DISTINCT value FROM custom_column_N，没有任何 JOIN
    import re

    bad = re.search(
        r"SELECT\s+DISTINCT\s+value\s+FROM\s+custom_column_%d\s+"
        r"WHERE\s+value\s+IS\s+NOT\s+NULL", src
    )
    assert not bad, "reader_group.py 仍在使用不带 JOIN 的旧分类 SQL"
