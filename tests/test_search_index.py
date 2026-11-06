"""独立中文检索索引的回归：

- 汉字逐字进索引、整段做精确过滤，保证 1~2 字查询能命中；
- calibre 高级语法（author:xxx、#tag:）仍交给原生 search；
- 从 metadata.db 建索引后，能够按中文/英文检索，并支持重建。
"""

import sqlite3

import pytest

from webserver.services.search_index import (
    SearchIndexService,
    build_match_expression,
    build_search_tokens,
    looks_like_advanced_query,
    tokenize_text,
)


def test_chinese_is_tokenized_per_char():
    terms, parts = tokenize_text("三体")
    assert terms == ["三", "体"]
    assert parts == ["三体"]


def test_match_expression_uses_and_and_prefix_for_latin():
    expr = build_match_expression(["三", "体", "harry"])
    assert expr == '"三" AND "体" AND "harry"*'


def test_advanced_calibre_syntax_falls_back():
    assert looks_like_advanced_query('author:"刘慈欣"')
    assert looks_like_advanced_query("#tag:科幻")
    assert looks_like_advanced_query("三体 AND 刘慈欣")
    assert not looks_like_advanced_query("三体")
    assert not looks_like_advanced_query("harry potter")


def test_build_tokens_splits_cjk_only():
    tokens = build_search_tokens("三体", "刘慈欣")
    assert tokens == "三 体 刘 慈 欣"


@pytest.fixture()
def library(tmp_path):
    """最小的 calibre metadata.db 结构。"""
    library_dir = tmp_path / "library"
    library_dir.mkdir()
    db = sqlite3.connect(str(library_dir / "metadata.db"))
    db.executescript(
        """
        CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, sort TEXT,
                            publisher INTEGER, series INTEGER);
        CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE books_authors_link (book INTEGER, author INTEGER);
        CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE books_tags_link (book INTEGER, tag INTEGER);
        CREATE TABLE publishers (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE series (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE comments (book INTEGER, text TEXT);
        """
    )
    db.execute("INSERT INTO authors VALUES (1, '刘慈欣')")
    db.execute("INSERT INTO books VALUES (1, '三体（全集）', 'san ti', NULL, NULL)")
    db.execute("INSERT INTO books VALUES (2, 'Harry Potter and the Philosopher', 'harry', NULL, NULL)")
    db.execute("INSERT INTO books_authors_link VALUES (1, 1)")
    db.execute("INSERT INTO comments VALUES (1, '演播：李野墨。地球往事三部曲第一部。')")
    db.commit()
    db.close()
    return library_dir


def test_rebuild_and_search_chinese(library, tmp_path):
    service = SearchIndexService(path=str(tmp_path / "search_index.db"),
                                 library_dir=str(library))
    result = service.rebuild(force=True)
    assert result["ok"] and result["docs"] == 2

    # 2 字书名：逐字 AND + 原文精确过滤
    assert service.search("三体") == [1]
    # 1 个字也能命中，但必须真的包含这个字
    assert service.search("体") == [1]
    # 演播者写在简介里，也能搜到
    assert service.search("李野墨") == [1]
    # 英文前缀
    assert 2 in service.search("harr")
    # 不存在的词
    assert service.search("红楼梦") == []
    # calibre 高级语法交回原生搜索
    assert service.search("author:刘慈欣") is None
