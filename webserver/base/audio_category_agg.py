# ============================================================
# audio_category_agg —— 「有音频的书 × #category 自定义列」共享聚合
#
# podcast（分类/标签/作者 feed）与有声书页的分类 tab 都需要
# 「有音频的书按 #category 归桶」。以前 podcast 在本模块位置之外
# 自己维护一份 180s TTL 的聚合，有声书侧要用还得再写一份，
# 两份缓存的失效时机互不知晓。现在收敛到这里：
#
#   - 书源：AudioBooksCache（文件系统扫描缓存，本模块永不扫盘）
#   - 失效：跟随 AudioBooksCache.get_version()（集合每实际变化 +1）
#   - 增量：版本变化时先 diff，增删 ≤ DIFF_SYNC_THRESHOLD 本就在调用
#     线程同步补齐（O(diff)，毫秒级）；变更过大（全库扫描后、首次冷启动）
#     才转后台线程全量重建，请求线程只拿现成数据，不阻塞 ioloop
#     （维护约定：同步 IO 不进 ioloop）。
#   - force=True：调用方坚持同步全量构建（podcast 保持原有
#     「请求即有数据」语义用；受 REBUILD_MIN_INTERVAL 节流防导入高峰反复重算）
#
# 分类名口径与 podcast 原实现一致（沿用，避免 feed 内容突变）：
#   mi.get("#category") 为 str → 整串一个分类（"A/B" 不拆分）；
#   list/tuple → 逐个；空串/None → 不入桶（这类书只出现在「全部」里）。
#
# 调用方需传入 calibre db 的 new_api（BaseHandler.calibre_db_cache），
# 本模块不做任何全局查找，避免与 handlers 形成循环 import。
# ============================================================
import logging
import threading
import time

from webserver.constants import CALIBRE_COLUMN_CATEGORY

# 增删少于这个数本时走同步增量；超过（含首次冷启动）转后台全量重建
DIFF_SYNC_THRESHOLD = 50
# force 全量重建的最小间隔（秒）。podcast 原实现就是 180s TTL，语义不变。
REBUILD_MIN_INTERVAL = 180.0

_lock = threading.RLock()
_rebuild_lock = threading.Lock()
_state = {
    "version": -1,
    "ids": set(),
    "categories": {},   # {分类名: [book_id]}
    "book_meta": {},    # {book_id: {"tags": [...], "authors": [...], "#category": str}}
}


def _snapshot():
    st = _state
    return {
        "categories": st["categories"],
        "book_meta": st["book_meta"],
    }


def _book_category(mi):
    """单本书的 #category 值 → 分类名列表（口径见模块 docstring）。"""
    try:
        cat_val = mi.get(CALIBRE_COLUMN_CATEGORY)
    except Exception:
        return []
    if isinstance(cat_val, (list, tuple)):
        return [str(c) for c in cat_val if c]
    if cat_val:
        return [str(cat_val)]
    return []


def _add_book(st, cache, book_id):
    """单本书并入聚合（增量路径）。取不到元数据则跳过。"""
    try:
        mi = cache.get_metadata(book_id, get_cover=False, get_user_categories=False)
    except Exception as e:
        logging.error("audio agg: fetch metadata of %s failed: %s", book_id, e)
        return
    if not mi:
        return
    cats = _book_category(mi)
    for c in cats:
        st["categories"].setdefault(c, []).append(book_id)
    st["book_meta"][book_id] = {
        "tags": list(mi.tags or []),
        "authors": list(mi.authors or []),
        CALIBRE_COLUMN_CATEGORY: cats[0] if cats else "",
    }


def _drop_book(st, book_id):
    """单本书移出聚合（增量路径）。"""
    st["book_meta"].pop(book_id, None)
    for name in list(st["categories"].keys()):
        ids = st["categories"][name]
        if book_id in ids:
            ids.remove(book_id)
            if not ids:
                del st["categories"][name]


def _build_full(cache, audio_ids):
    """全量重建（后台线程或 force 调用）。返回新的 (categories, meta)。"""
    categories = {}
    meta = {}
    n_err = 0
    for book_id in audio_ids:
        try:
            mi = cache.get_metadata(book_id, get_cover=False, get_user_categories=False)
        except Exception as e:
            n_err += 1
            if n_err <= 5:
                logging.error("audio agg: fetch metadata of %s failed: %s", book_id, e)
            continue
        if not mi:
            continue
        cats = _book_category(mi)
        for c in cats:
            categories.setdefault(c, []).append(book_id)
        meta[book_id] = {
            "tags": list(mi.tags or []),
            "authors": list(mi.authors or []),
            CALIBRE_COLUMN_CATEGORY: cats[0] if cats else "",
        }
    if n_err > 5:
        logging.error("audio agg: full rebuild had %d metadata failures (suppressed)", n_err)
    return categories, meta


def _apply_full(st, audio_ids, categories, meta):
    st["categories"] = categories
    st["book_meta"] = meta
    st["ids"] = set(audio_ids)


def get_audio_aggregation(cache, audio_ids=None, version=None, force=False):
    """取聚合结果。返回 {"categories": {...}, "book_meta": {...}}。

    Args:
        cache: calibre db new_api（BaseHandler.calibre_db_cache）。
        audio_ids / version: 缺省时从 AudioBooksCache 自取（lazy import 避免循环）。
        force: 版本过期且变更过大时，改为同步全量重建（受节流），调用线程等待。

    返回的数据可能是上一版聚合（冷启动后台未建完、或节流窗内）——
    调用方不该假设它反映「此刻」的全库状态；tab/统计类的展示数字允许
    秒级滞后，这是用一致口径换请求路径零阻塞的代价。
    """
    if audio_ids is None or version is None:
        from webserver.handlers.audio import AudioBooksCache
        if audio_ids is None:
            audio_ids = AudioBooksCache.get_audio_book_ids_set()
        if version is None:
            version = AudioBooksCache.get_version()

    with _lock:
        st = _state
        if st["version"] == version:
            # 版本号没变 ⇔ 书集合没变（version 随集合实际变化递增），直接返回。
            # 空库也一样：后台已按空集建过，不再反复 kick。
            return _snapshot()
        added = audio_ids - st["ids"]
        removed = st["ids"] - audio_ids
        if st["ids"] and len(added) + len(removed) <= DIFF_SYNC_THRESHOLD:
            # 小变更：同步补齐。单书 get_metadata 命中 calibre 缓存层，毫秒级。
            for bid in removed:
                _drop_book(st, bid)
            for bid in added:
                _add_book(st, cache, bid)
            st["ids"] = set(audio_ids)
            st["version"] = version
            return _snapshot()
        # 首次冷启动或全库扫描后的大变更
        if force:
            built_at = st.get("built_at", 0.0)
            if st["ids"] and (time.time() - built_at) < REBUILD_MIN_INTERVAL:
                # 节流窗内：返回旧版，避免导入高峰把请求线程拖进全量重建
                return _snapshot()
            categories, meta = _build_full(cache, audio_ids)
            _apply_full(st, audio_ids, categories, meta)
            st["version"] = version
            st["built_at"] = time.time()
            return _snapshot()
        _kick_rebuild(cache, audio_ids, version)
        return _snapshot()


def _kick_rebuild(cache, audio_ids, version):
    """后台线程全量重建（单飞）。已有线程在建则直接返回。"""
    if not _rebuild_lock.acquire(False):
        return

    def _work():
        try:
            categories, meta = _build_full(cache, audio_ids)
            with _lock:
                _apply_full(_state, audio_ids, categories, meta)
                _state["version"] = version
                _state["built_at"] = time.time()
            logging.info(
                "audio agg: rebuilt in background: %d books, %d categories",
                len(meta), len(categories))
        except Exception:
            logging.exception("audio agg: background rebuild failed")
        finally:
            _rebuild_lock.release()

    threading.Thread(target=_work, name="audio-agg-rebuild", daemon=True).start()


def get_audio_categories(cache, audio_ids=None, version=None):
    """便捷入口：{分类名: [book_id]}。语义见 get_audio_aggregation。"""
    return get_audio_aggregation(cache, audio_ids, version)["categories"]
