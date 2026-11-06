#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""独立中文检索索引（SQLite FTS5）。

背景
----
书库搜索原先完全依赖 calibre 自带的 search：它对中文按整段切词，搜「三体」
时标题里的「三体（全集）」不一定命中，输入一半的书名也搜不到。这里给书目
元数据建一份独立的 FTS5 索引，不改 calibre 的 metadata.db，也不改现有搜索
接口：`BaseHandler.cached_search*` 先问本索引，索引不可用/查询含 calibre
高级语法时自动回退到原来的 search，行为兼容。

分词策略（针对中文）
----------------
- 拉丁字母/数字：按原词进索引，查询时允许前缀匹配（`harry*`）。
- 汉字：逐字拆开进索引，查询同样逐字做 AND，再用原文做一次精确子串过滤。
  这样「三体」「刘慈」「全集」这类 1~2 字查询都能命中，且不会因为单字
  命中而返回一堆噪声。
- 索引内容：标题、作者、标签、丛书、出版社、简介（含「演播：xxx」）。

刷新策略
--------
- 索引文件独立（默认 `/data/books/search_index.db`），整库重建后原子替换。
- 启动时若索引缺失或与 metadata.db 版本不一致，后台重建。
- 之后每 SEARCH_INDEX_REFRESH_SECONDS（默认 300 秒）检查一次 stat 版本，
  变化才重建；重建期间搜索继续用旧索引，不阻塞请求。
- 也可通过管理接口或 CLI 手动重建。
"""

import html
import logging
import os
import re
import sqlite3
import threading
import time
import urllib.parse

from webserver import loader

CONF = loader.get_settings()

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
HTML_TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
# 只保留字母/数字/汉字，其余（标点、引号、FTS 运算符）一律当分隔符
TOKEN_SPLIT_RE = re.compile(r"[^0-9a-zA-Z\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")

MAX_DOC_CHARS = 8000

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
    tokens,
    doc_text UNINDEXED,
    tokenize = "unicode61 remove_diacritics 2"
);
"""


def normalize_text(value):
    """去 HTML、反转义、压空白、小写；保留中文与字母数字。"""
    if not value:
        return ""
    text = HTML_TAG_RE.sub(" ", str(value))
    text = html.unescape(text)
    text = text.replace("\u3000", " ")
    text = SPACE_RE.sub(" ", text).strip().lower()
    return text[:MAX_DOC_CHARS]


def tokenize_text(text):
    """把原文拆成索引/查询用的 token 序列。

    返回 (terms, cjk_parts)：
    - terms：空白分隔的 token 列表（汉字每个字一个 token）；
    - cjk_parts：原文里连续汉字段落，用于结果精确过滤。
    """
    text = normalize_text(text)
    if not text:
        return [], []

    terms = []
    cjk_parts = []
    for piece in TOKEN_SPLIT_RE.split(text):
        if not piece:
            continue
        if CJK_RE.search(piece):
            # 连续汉字段：逐字进索引，同时整段留作精确过滤
            cjk_parts.append(piece)
            terms.extend(list(piece))
        else:
            terms.append(piece)
    # 去重保序
    seen = set()
    unique = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            unique.append(term)
    return unique, cjk_parts


def build_search_tokens(*fields):
    """把多个字段拼成 FTS 索引文本（拉丁词保持，汉字逐字加空格）。"""
    texts = [normalize_text(f) for f in fields if f]
    if not texts:
        return ""
    merged = " ".join(texts)
    out = []
    for piece in TOKEN_SPLIT_RE.split(merged):
        if not piece:
            continue
        if CJK_RE.search(piece):
            out.append(" ".join(piece))
        else:
            out.append(piece)
    return " ".join(out)


def looks_like_advanced_query(query):
    """calibre 高级语法（`author:xxx`、`#tag:`、`AND/OR`、括号、引号）不走本索引。"""
    q = query.strip()
    if not q:
        return True
    if any(ch in q for ch in '"\'():#'):
        return True
    if ":" in q:
        return True
    upper = q.upper()
    return any(op in upper for op in (" AND ", " OR ", " NOT ", "&&", "||"))


def _clean_token(term):
    term = TOKEN_SPLIT_RE.sub("", term)
    return term.lower()


def build_match_expression(terms):
    """构造 FTS5 MATCH 表达式：全部 AND；拉丁词允许前缀匹配。"""
    parts = []
    for term in terms:
        term = _clean_token(term)
        if not term:
            continue
        if CJK_RE.search(term):
            parts.append('"%s"' % term)
        elif len(term) >= 2:
            parts.append('"%s"*' % term)
        else:
            parts.append('"%s"' % term)
    return " AND ".join(parts)


class SearchIndexService:
    """FTS5 索引的构建、查询与刷新（进程内单例）。"""

    def __init__(self, path=None, library_dir=None):
        self.path = path or CONF.get("SEARCH_INDEX_PATH", "/data/books/search_index.db")
        self.library_dir = library_dir or CONF.get("with_library", "/data/books/library/")
        self.refresh_seconds = int(CONF.get("SEARCH_INDEX_REFRESH_SECONDS", 300) or 0)
        self.max_results = int(CONF.get("SEARCH_INDEX_MAX_RESULTS", 20000) or 20000)
        self._build_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._thread = None
        self._building = False
        self._fts_available = True
        self._last_error = ""
        self._last_build_at = 0
        self._last_build_seconds = 0
        self._doc_count = self._load_doc_count()

    # ---------------- 基础信息 ----------------
    @property
    def enabled(self):
        return bool(CONF.get("SEARCH_INDEX_ENABLED", True)) and self._fts_available

    @property
    def library_db(self):
        return os.path.join(self.library_dir, "metadata.db")

    def _library_version(self):
        try:
            st = os.stat(self.library_db)
            return "%d-%d" % (st.st_mtime_ns, st.st_size)
        except OSError:
            return ""

    def _connect_read(self):
        uri = "file:%s?mode=ro" % urllib.parse.quote(self.path)
        return sqlite3.connect(uri, uri=True, timeout=3)

    def _load_doc_count(self):
        if not os.path.isfile(self.path):
            return 0
        try:
            conn = self._connect_read()
            try:
                row = conn.execute(
                    "SELECT value FROM meta WHERE key='docs'").fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()
        except (sqlite3.Error, ValueError):
            return 0

    def _index_version(self):
        if not os.path.isfile(self.path):
            return ""
        try:
            conn = self._connect_read()
            try:
                row = conn.execute(
                    "SELECT value FROM meta WHERE key='library_version'").fetchone()
                return row[0] if row else ""
            finally:
                conn.close()
        except sqlite3.Error:
            return ""

    def status(self):
        index_version = self._index_version()
        library_version = self._library_version()
        return {
            "enabled": self.enabled,
            "path": self.path,
            "exists": os.path.isfile(self.path),
            "docs": self._doc_count,
            "index_version": index_version,
            "library_version": library_version,
            "stale": bool(library_version) and index_version != library_version,
            "building": self._building,
            "last_build_at": self._last_build_at,
            "last_build_seconds": self._last_build_seconds,
            "last_error": self._last_error,
            "refresh_seconds": self.refresh_seconds,
        }

    # ---------------- 查询 ----------------
    def search(self, query):
        """返回命中的 book_id 列表；None 表示「请回退到 calibre search」。"""
        if not self.enabled or not query:
            return None
        q = query.strip()
        if not q or looks_like_advanced_query(q):
            return None
        if not os.path.isfile(self.path):
            self.request_rebuild()
            return None

        terms, cjk_parts = tokenize_text(q)
        match = build_match_expression(terms)
        if not match:
            return None
        # 单字查询至少要有精确子串约束，否则噪声太大
        if not cjk_parts and all(len(t) < 2 for t in terms):
            return None

        try:
            conn = self._connect_read()
            try:
                rows = conn.execute(
                    "SELECT rowid, doc_text FROM docs_fts "
                    "WHERE docs_fts MATCH ? ORDER BY rank LIMIT ?",
                    (match, self.max_results),
                ).fetchall()
            finally:
                conn.close()
        except sqlite3.Error:
            logging.warning("search index query failed, fallback to calibre",
                            exc_info=True)
            return None

        if cjk_parts:
            # 汉字查询做一次原文子串过滤，消除「单字碰巧命中」的噪声
            rows = [(bid, doc) for bid, doc in rows
                    if all(part in (doc or "") for part in cjk_parts)]

        return [int(bid) for bid, _ in rows]

    # ---------------- 构建 ----------------
    def request_rebuild(self, force=False):
        """异步触发一次重建；已有构建在跑时直接返回 False。"""
        if not self.enabled:
            return False
        with self._state_lock:
            if self._building:
                return False
            self._building = True
        thread = threading.Thread(
            target=self._rebuild_task, kwargs={"force": force},
            name="search-index-build", daemon=True)
        thread.start()
        return True

    def _rebuild_task(self, force=False):
        try:
            self.rebuild(force=force)
        except Exception as exc:
            self._last_error = str(exc)
            logging.exception("search index rebuild failed")
        finally:
            with self._state_lock:
                self._building = False

    def rebuild(self, force=False):
        """全量重建索引（原子替换，旧索引在构建期间仍可用）。"""
        if not self.enabled:
            return {"ok": False, "msg": "search index disabled"}
        library_version = self._library_version()
        if not library_version:
            return {"ok": False, "msg": "library metadata.db not found"}
        if not force and self._index_version() == library_version:
            return {"ok": True, "msg": "index is up to date", "docs": self._doc_count}

        if not self._build_lock.acquire(blocking=False):
            return {"ok": False, "msg": "another rebuild is running"}
        started = time.time()
        tmp_path = "%s.tmp-%d" % (self.path, os.getpid())
        try:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)

            conn = sqlite3.connect(tmp_path)
            try:
                conn.executescript(SCHEMA)
                count = self._fill_index(conn)
                conn.execute("INSERT OR REPLACE INTO meta VALUES('library_version', ?)",
                             (library_version,))
                conn.execute("INSERT OR REPLACE INTO meta VALUES('built_at', ?)",
                             (time.strftime("%Y-%m-%d %H:%M:%S"),))
                conn.execute("INSERT OR REPLACE INTO meta VALUES('docs', ?)", (str(count),))
                conn.commit()
            finally:
                conn.close()

            os.replace(tmp_path, self.path)
            self._doc_count = count
            self._last_build_at = int(time.time())
            self._last_build_seconds = round(time.time() - started, 1)
            self._last_error = ""
            logging.info("[SEARCH_INDEX] rebuilt %d docs in %.1fs", count,
                         self._last_build_seconds)
            return {"ok": True, "docs": count,
                    "seconds": self._last_build_seconds}
        except sqlite3.OperationalError as exc:
            if "fts5" in str(exc).lower() or "no such module" in str(exc).lower():
                self._fts_available = False
                logging.warning("[SEARCH_INDEX] 当前 SQLite 不支持 FTS5，"
                                "搜索将回退到 calibre")
                return {"ok": False, "msg": "FTS5 not available"}
            raise
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            self._build_lock.release()

    def _fill_index(self, conn):
        """从 metadata.db 只读导出一遍书目元数据。"""
        src = sqlite3.connect(
            "file:%s?mode=ro" % urllib.parse.quote(self.library_db), uri=True, timeout=5)
        try:
            authors = dict(src.execute(
                "SELECT ba.book, group_concat(a.name, ' ') "
                "FROM books_authors_link ba JOIN authors a ON a.id = ba.author "
                "GROUP BY ba.book"))
            tags = dict(src.execute(
                "SELECT bt.book, group_concat(t.name, ' ') "
                "FROM books_tags_link bt JOIN tags t ON t.id = bt.tag "
                "GROUP BY bt.book"))
            rows = src.execute(
                "SELECT b.id, b.title, b.sort, p.name, s.name, c.text "
                "FROM books b "
                "LEFT JOIN publishers p ON p.id = b.publisher "
                "LEFT JOIN series s ON s.id = b.series "
                "LEFT JOIN comments c ON c.book = b.id"
            ).fetchall()
        finally:
            src.close()

        count = 0
        batch = []
        for book_id, title, sort_title, publisher, series, comments in rows:
            doc_text = normalize_text(" ".join(filter(None, [
                title, sort_title, authors.get(book_id, ""), tags.get(book_id, ""),
                series, publisher, comments,
            ])))
            tokens = build_search_tokens(
                title, sort_title, authors.get(book_id, ""), tags.get(book_id, ""),
                series, publisher, comments)
            if not tokens:
                continue
            batch.append((book_id, tokens, doc_text))
            count += 1
            if len(batch) >= 500:
                conn.executemany(
                    "INSERT INTO docs_fts(rowid, tokens, doc_text) VALUES (?, ?, ?)", batch)
                batch = []
        if batch:
            conn.executemany(
                "INSERT INTO docs_fts(rowid, tokens, doc_text) VALUES (?, ?, ?)", batch)
        return count

    # ---------------- 后台保活 ----------------
    def start_background_refresh(self):
        """启动常驻线程：索引缺失/过期时后台重建，之后定时检查。"""
        if not self.enabled:
            return
        with self._state_lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._refresh_loop, name="search-index-refresh", daemon=True)
            self._thread.start()

    def _refresh_loop(self):
        while True:
            try:
                if self._index_version() != self._library_version():
                    self.request_rebuild()
            except Exception:
                logging.exception("[SEARCH_INDEX] refresh check failed")
            if self.refresh_seconds <= 0:
                return
            time.sleep(max(30, self.refresh_seconds))


_INSTANCE = None
_INSTANCE_LOCK = threading.Lock()


def get_search_index():
    global _INSTANCE
    if _INSTANCE is None:
        with _INSTANCE_LOCK:
            if _INSTANCE is None:
                _INSTANCE = SearchIndexService()
    return _INSTANCE
