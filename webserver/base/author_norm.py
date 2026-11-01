#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""作者名归一化（Author Normalization）

解决的问题：calibre 的目录结构是 ``library/<作者>/<书名> (<book_id>)/``，
作者名差一个字符就是另一个目录。而作者名来自三个都不干净的地方：

1. 有声书 ID3 标签的 ``artist`` / ``albumartist``
2. 元数据刮削源（豆瓣、百科、优书、新华书店…）
3. 电子书内嵌元数据

同一个作者因此分裂成多个目录（``J·K·罗琳`` / ``J·K. 罗琳`` / ``J·k·羅琳`` …），
存量只能人工逐个改，增量必须在这里拦住。

设计分三层（风险从低到高），详见 ``设计稿-4.6.0-9-作者归一化.md``：

- **L1 确定性清洗**：去国籍/朝代前缀、去职责后缀、去译者标记、剥英文译名括号。
  纯正则，复用 ``meta_helper.guess_authors()``。
- **L2 别名表**：把清洗后的名字压成 ``norm_key``，查人工维护的别名表。
  **只做完全相等匹配，绝不做模糊匹配。**
- **L3 启发式**：默认关闭（英文名大小写整形、去中间点）。

设计原则：**认不出就返回原值，绝不瞎猜。** 一次错误的合并（把 A 的书并到 B 名下）
比十次漏合并代价高得多——前者要人工翻遍书库才能发现，后者只是目录多一点。
"""
import json
import logging
import os
import re
import threading
import unicodedata
from typing import Dict, List, Optional, Tuple

__all__ = [
    "author_norm_key",
    "loose_author_key",
    "clean_authors",
    "resolve_alias",
    "resolve_author_list",
    "lock_author",
    "is_author_locked",
    "normalize_and_lock",
    "get_alias_store",
    "reload_alias_store",
]


# --------------------------------------------------------------------------- #
# L1：确定性清洗
# --------------------------------------------------------------------------- #

def clean_authors(raw_list: List[str]) -> Tuple[List[str], List[str]]:
    """L1 清洗。返回 ``(作者列表, 译者列表)``。

    直接复用 ``meta_helper.guess_authors``——那是项目里已经跑了很久的实现，
    国籍前缀、职责后缀、译者标记、英文括号都已覆盖。这里只做两件事：

    1. 输入防御（None / 非字符串）
    2. ``guess_authors`` 清洗后为空时**回退到原文**

    第 2 条是反直觉的，但很重要：``王学富(译)`` 会被识别成译者，作者列表变空。
    这时如果直接兜成"佚名"，就丢掉了原始信息；回退到原文至少还能让人看见、
    让人自己判断。宁可留个脏名字，也不要把有作者的书标成"佚名"。
    """
    from webserver.base.meta_helper import guess_authors

    cleaned_in = [str(x) for x in (raw_list or []) if x is not None and str(x).strip()]
    if not cleaned_in:
        return [], []

    authors, translators = guess_authors(cleaned_in)
    if authors:
        return authors, translators

    # 全是译者 / 全被过滤 —— 回退到原文，不要吞掉
    fallback = []
    for raw in cleaned_in:
        text = " ".join(str(raw).split()).strip()
        text = "".join(c for c in text if c.isprintable())
        if text and text not in fallback:
            fallback.append(text)
    return fallback, translators


# --------------------------------------------------------------------------- #
# L2：归一化键
# --------------------------------------------------------------------------- #

_OPENCC_T2S_LOCK = threading.Lock()
_OPENCC_T2S = None  # None=未初始化, False=不可用, 其它=OpenCC 实例


def _t2s(text: str) -> str:
    """繁体 → 简体。OpenCC 不可用时原样返回（不抛异常）。

    ``webserver.utils.get_opencc()`` 每次调用都 ``opencc.OpenCC(profile)`` 新建
    对象（要加载词典），全库扫描时开销明显。这里自己缓存一份实例。

    OpenCC 缺失不是错误：``J·k·羅琳`` 会算成 ``jk羅琳`` 而不是 ``jk罗琳``，
    于是它落不到 ``exact`` 档、只会出现在"疑似重复"里等人工确认——
    **安全降级，不会误合并。**
    """
    global _OPENCC_T2S
    if _OPENCC_T2S is None:
        with _OPENCC_T2S_LOCK:
            if _OPENCC_T2S is None:
                try:
                    import opencc
                    _OPENCC_T2S = opencc.OpenCC("t2s")
                except Exception as err:  # noqa: BLE001 - 任何失败都降级
                    logging.warning("[AUTHOR_NORM] OpenCC 不可用，跳过繁简归一: %s", err)
                    _OPENCC_T2S = False
    if _OPENCC_T2S is False:
        return text
    try:
        return _OPENCC_T2S.convert(text)
    except Exception as err:  # noqa: BLE001
        logging.warning("[AUTHOR_NORM] OpenCC 转换失败，原样返回: %s", err)
        return text


def author_norm_key(name: str) -> str:
    """把**已过 L1 清洗**的作者名压成比对用的键。只用于查表，不展示、不落库。

    ⚠️ 输入必须是 L1 清洗后的结果。直接拿原始名字算会出错：

        >>> author_norm_key("(法)法布尔")
        '法法布尔'          # 括号被删了，"法"留下了

    所以本函数刻意不对外暴露"从原始字符串一步到位"的接口——
    调用方一律走 ``resolve_alias()``，由它保证先 L1 再算键。
    """
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", str(name))
    s = s.lower()
    s = _t2s(s)
    s = re.sub(r"[\s·•.\-_'’]+", "", s)
    s = re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", s)
    return s


def loose_author_key(name: str) -> str:
    """比 ``norm_key`` 更松的"疑似键"：去掉英文字母，只留汉字。仅用于体检提示。

    实测局限：**纯英文名会得到空串**（``J.K. Rowling`` → ``jkrowling`` → ``""``），
    所以它抓不到"中英双写"这种最常见的分裂。那类靠 ``find_shared_book_pairs()``
    （同一本书挂两个作者）来发现。

    长度 < 2 一律丢弃：``张三`` 和 ``李三`` 都是 ``三``，会误报。
    """
    s = author_norm_key(name)
    s = re.sub(r"[a-z]", "", s)
    return s if len(s) >= 2 else ""


# --------------------------------------------------------------------------- #
# 别名表
# --------------------------------------------------------------------------- #

ALIAS_FILE_NAME = "config.json"
_DEFAULT_NEVER_MERGE = ("佚名", "未知", "未知作者", "Unknown", "unknown")


class AliasStore:
    """作者别名表。落盘在 ``/data/toolbox/author_norm/config.json``。

    结构::

        {
          "version": 1,
          "canonical": {
            "jk罗琳": {"name": "J.K.罗琳", "aliases": ["J·K·罗琳", "J.K. Rowling"], "note": ""}
          },
          "never_merge": ["佚名"]
        }

    ``canonical`` 的键是标准的 ``norm_key``。运行时不靠 ``aliases`` 匹配
    （匹配靠 ``index``），``aliases`` 只在展示、导出、以及**重建 index** 时用到——
    因为 ``J.K. Rowling`` 的键是 ``jkrowling``，不等于 ``jk罗琳``，必须为每个
    alias 单独建一条索引才能命中。
    """

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        self._canonical: Dict[str, dict] = {}
        self._index: Dict[str, str] = {}          # 任意写法的 norm_key -> canonical 键
        self._never: set = set(_DEFAULT_NEVER_MERGE)
        self._mtime: Optional[float] = None

    # -- 读写 ------------------------------------------------------------- #

    def load(self, force: bool = False) -> None:
        with self._lock:
            try:
                mtime = os.path.getmtime(self.path)
            except OSError:
                mtime = None
            if not force and mtime == self._mtime and self._index:
                return
            data = {}
            if mtime is not None:
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        data = json.load(f) or {}
                except Exception as err:  # noqa: BLE001
                    logging.error("[AUTHOR_NORM] 读取别名表失败 %s: %s", self.path, err)
                    data = {}
            self._apply(data)
            self._mtime = mtime

    def _apply(self, data: dict) -> None:
        """把磁盘内容装进内存，并重建反向索引。"""
        canonical = data.get("canonical") or {}
        if not isinstance(canonical, dict):
            canonical = {}

        self._canonical = {}
        for key, entry in canonical.items():
            if not isinstance(entry, dict):
                continue
            standard = (entry.get("name") or "").strip()
            if not standard:
                continue          # 没有标准名的条目无法使用，跳过
            self._canonical[key] = {
                "name": standard,
                "aliases": [str(a) for a in (entry.get("aliases") or []) if str(a).strip()],
                "note": entry.get("note") or "",
            }

        never = data.get("never_merge")
        self._never = set(_DEFAULT_NEVER_MERGE) | set(str(x) for x in (never or []))

        # 重建索引。⚠️ alias 是"人看的原始写法"，算键之前必须再 L1 一次，
        # 否则 "[美] 加里·布莱克伍德" 会算成 "美加里布莱克伍德" 索引不到。
        index: Dict[str, str] = {}
        for key, entry in self._canonical.items():
            index[key] = key
            cleaned, _ = clean_authors([entry["name"]])
            if cleaned:
                k = author_norm_key(cleaned[0])
                if k:
                    index[k] = key
            for alias in entry["aliases"]:
                cleaned, _ = clean_authors([alias])
                if not cleaned:
                    continue
                k = author_norm_key(cleaned[0])
                if k:
                    index[k] = key
        self._index = index

    def save(self, canonical: Dict[str, dict], never_merge: Optional[List[str]] = None) -> None:
        """整表覆盖写入。写完立刻重建索引并刷新 mtime。"""
        with self._lock:
            payload = {
                "version": 1,
                "canonical": canonical,
                "never_merge": list(never_merge if never_merge is not None else self._never),
            }
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
            self._apply(payload)
            try:
                self._mtime = os.path.getmtime(self.path)
            except OSError:
                self._mtime = None
            logging.info("[AUTHOR_NORM] 别名表已保存，%d 条规则", len(self._canonical))

    # -- 查询 ------------------------------------------------------------- #

    def resolve_key(self, norm_key: str) -> Optional[str]:
        """返回 canonical 键，未命中返回 None。"""
        if not norm_key:
            return None
        self.load()
        with self._lock:
            return self._index.get(norm_key)

    def canonical_name(self, key: str) -> Optional[str]:
        with self._lock:
            entry = self._canonical.get(key)
            return entry["name"] if entry else None

    def is_never_merge(self, name: str) -> bool:
        return (name or "").strip() in self._never

    def dump(self) -> dict:
        with self._lock:
            return {
                "version": 1,
                "canonical": json.loads(json.dumps(self._canonical, ensure_ascii=False)),
                "never_merge": sorted(self._never),
            }


_STORE: Optional[AliasStore] = None
_STORE_LOCK = threading.Lock()


def _default_alias_path() -> str:
    try:
        from webserver import loader
        root = loader.get_settings().get("toolbox_data_root") or "/data/toolbox"
    except Exception:  # noqa: BLE001
        root = "/data/toolbox"
    return os.path.join(root, "author_norm", ALIAS_FILE_NAME)


def get_alias_store() -> AliasStore:
    global _STORE
    if _STORE is None:
        with _STORE_LOCK:
            if _STORE is None:
                _STORE = AliasStore(_default_alias_path())
    return _STORE


def reload_alias_store() -> AliasStore:
    store = get_alias_store()
    store.load(force=True)
    return store


# --------------------------------------------------------------------------- #
# 对外主入口
# --------------------------------------------------------------------------- #

def resolve_alias(name: str) -> str:
    """把一个作者名归一化成标准名。**认不出就原样返回。**

    这是所有挂点唯一应该调用的函数。它内部保证"先 L1 清洗、再算键、再查表"，
    调用方不需要（也不应该）自己去拼这几步。
    """
    text = (name or "").strip()
    if not text:
        return text

    store = get_alias_store()
    if store.is_never_merge(text):
        return text

    cleaned, _ = clean_authors([text])
    candidate = cleaned[0] if cleaned else text

    if store.is_never_merge(candidate):
        return candidate

    key = author_norm_key(candidate)
    if not key:
        return candidate

    hit = store.resolve_key(key)
    if not hit:
        return candidate

    standard = store.canonical_name(hit)
    if not standard:
        return candidate
    if standard != candidate:
        logging.debug("[AUTHOR_NORM] %r -> %r (key=%s)", candidate, standard, key)
    return standard


def resolve_author_list(names: List[str]) -> List[str]:
    """对作者列表逐个归一化，保序去重。空列表原样返回。"""
    result: List[str] = []
    for raw in names or []:
        name = resolve_alias(raw)
        if name and name not in result:
            result.append(name)
    return result


def author_key_set(names) -> set:
    """把一组作者名转成归一化键的集合，用于**比较两本书的作者是否同一人**。

    供 book_dedup（同名书是否合并）与体检接口（哪些条目疑似同一人）使用。
    比较规则：任一键相交即视为同一作者；空键（无法解析）不参与比较——
    这样「一边有作者、另一边是佚名」不会被误判成不同作者而拒绝合并。
    占位标记（佚名/未知/Unknown）也算空键：它们不指向任何人，没有比较价值。
    """
    keys = set()
    for raw in names or []:
        if not raw:
            continue
        cleaned, _ = clean_authors([str(raw)])
        for name in cleaned:
            if name.strip() in _DEFAULT_NEVER_MERGE:
                continue
            key = author_norm_key(name)
            if key:
                keys.add(key)
    return keys


def authors_conflict(names_a, names_b) -> bool:
    """判断两组作者是否**确定不是同一人**。

    只有当两边都解析出了非空键、且键集合完全不相交时才算冲突；
    任一边没有可用键（脏名/佚名）时返回 False（不冲突），宁可放过不可误杀。
    """
    ka, kb = author_key_set(names_a), author_key_set(names_b)
    if not ka or not kb:
        return False
    return not (ka & kb)


# --------------------------------------------------------------------------- #
# 作者锁定（S0）
# --------------------------------------------------------------------------- #

def lock_author(calibre_db, book_id: int) -> bool:
    """把某本书标记为"作者已人工确认"，后续自动刮削不再覆盖作者字段。

    用 calibre 自定义列 ``#author_locked``（int 型，1=已锁）。项目里
    ``batch_generate_cover.py:71`` 用的是同样的 ``set_custom(book_id, value, COLUMN)``
    位置参数写法，这里保持一致。

    打锁失败不影响主流程：改作者本身是用户的核心意图，
    锁定只是"以后别再覆盖"的附加保障，失败了下次再改还会重新打。
    """
    from webserver.constants import CALIBRE_COLUMN_AUTHOR_LOCKED

    try:
        calibre_db.set_custom(book_id, 1, CALIBRE_COLUMN_AUTHOR_LOCKED)
        logging.info("[AUTHOR_NORM] 书籍 id=%d 作者已锁定", book_id)
        return True
    except Exception as err:  # noqa: BLE001
        logging.warning("[AUTHOR_NORM] 打锁失败 book_id=%d: %s", book_id, err)
        return False


def is_author_locked(calibre_db, book_id: int) -> bool:
    """查某本书的作者是否已锁定。查询失败一律当"未锁"处理（保持旧行为）。"""
    from webserver.constants import CALIBRE_COLUMN_AUTHOR_LOCKED

    try:
        value = calibre_db.get_custom(
            book_id, label=CALIBRE_COLUMN_AUTHOR_LOCKED, index_is_id=True
        )
        return value == 1
    except Exception as err:  # noqa: BLE001
        logging.debug("[AUTHOR_NORM] 读锁标记失败 book_id=%d: %s", book_id, err)
        return False


def normalize_and_lock(calibre_db, book_id: int, authors: List[str]) -> List[str]:
    """归一化 + 打锁的组合操作，供 ``edit_book`` 使用。"""
    resolved = resolve_author_list(authors)
    lock_author(calibre_db, book_id)
    return resolved
