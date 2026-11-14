# ============================================================
# audio_category_agg —— 「有音频的书 × #category 自定义列」共享聚合
#
# podcast（分类/标签/作者 feed）与有声书页的分类 tab 都需要
# 「有音频的书按 #category 归桶」。以前 podcast 在本模块位置之外
# 自己维护一份 180s TTL 的聚合，有声书侧要用还得再写一份，
# 两份缓存的失效时机互不知晓。现在收敛到这里：
#
#   - 书源：AudioBooksCache（文件系统扫描缓存，本模块永不扫盘）
#   - 失效：两个维度，任一变化都必须重算——
#       (1) 书集合：跟随 AudioBooksCache.get_version()（集合每实际变化 +1）；
#       (2) 书元数据（#category/tags）：改分类入口调 on_category_changed()
#           按新值即时挪桶；漏网的写入（set_metadata、外部 calibre 工具、
#           导入脚本）由 library_version()（metadata.db 文件 mtime）感知，
#           触发后台全量重建。
#     只跟 version 是不够的：详情页改 #category 不改变「有音频的书集合」，
#     version 纹丝不动，而 tab 计数和 ?category=X 过滤都读本模块的快照，
#     于是「明明改成教育了却没进教育分类」，重启容器才自愈（r38 实测）。
#   - 增量：集合变化时先 diff，增删 ≤ DIFF_SYNC_THRESHOLD 本就在调用
#     线程同步补齐（O(diff)，毫秒级）；变更过大（全库扫描后、首次冷启动）
#     或元数据脏时转后台线程全量重建，请求线程只拿现成数据，不阻塞 ioloop
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
# 后台重建的最小发起间隔：库版本持续变化（或重建反复失败）时不至于每次请求
# 都 kick 一轮全量扫描。单飞锁之外再加一层时间节流。
REBUILD_KICK_MIN_INTERVAL = 20.0

_lock = threading.RLock()
_rebuild_lock = threading.Lock()
_state = {
    "version": -1,
    "ids": set(),
    "categories": {},   # {分类名: [book_id]}
    "book_meta": {},    # {book_id: {"tags": [...], "authors": [...], "#category": str}}
    "lib_version": None,   # 上次构建时的 calibre 库版本（元数据变更兜底）
    "meta_dirty": False,   # 有写入未通知，需后台全量重建
    "built_at": 0.0,
    "last_kick": 0.0,
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


def _categories_from_value(value):
    """改分类接口传来的新值 → 分类名列表，口径与 _book_category 一致。"""
    if isinstance(value, (list, tuple)):
        raw = [str(c) for c in value if c]
    elif value:
        raw = [str(value)]
    else:
        raw = []
    # 去重：同一分类名重复会出现在多个桶里，_drop_book 只 remove 一次
    return list(dict.fromkeys(raw))


def _lib_version_of(cache):
    """calibre 库文件 mtime（含 -wal），用作「元数据被写过」的兜底信号。

    与 BaseHandler.library_version() / catalog_categories() 同一口径：任何写
    metadata.db 的操作都会推进它。取不到（mock、异常）时返回 None，兜底自动
    关闭，不影响主流程，也不让单测依赖真实文件。
    """
    try:
        from webserver.base.query_cache import library_version
        return library_version(cache.backend)
    except Exception:
        return None


def _apply_one(st, bid, cats):
    """锁内：把 bid 从旧桶移除并按 cats 重新入桶，保留 tags/authors。"""
    old_meta = dict(st["book_meta"].get(bid) or {})
    _drop_book(st, bid)                     # 会 pop book_meta
    for c in cats:
        st["categories"].setdefault(c, []).append(bid)
    old_meta[CALIBRE_COLUMN_CATEGORY] = cats[0] if cats else ""
    st["book_meta"][bid] = old_meta


# 批量通知超过这个本数就退化成「标记脏、后台重建」，避免请求线程在锁内
# 做 O(书数 × 分类数) 的遍历。
BATCH_NOTIFY_THRESHOLD = 200


def on_category_changed(book_id, new_value):
    """改分类专用即时通知：把某本书按新值挪到正确的桶里，O(1)。

    由所有 set_field(#category, ...) 的成功分支调用。刻意**不读 calibre
    元数据**，直接用调用方手上的新值：绕开 new_api 的元数据缓存层（set_field
    之后 get_metadata 未必立刻反映新值），也不在请求线程里做 IO。

    只处理已在有声书集合里的书；集合未建好或该书无音频时直接忽略（下次全量
    构建会读最新 DB）。绝不抛异常——分类写库已经成功，通知失败不该让接口报错。

    保留该书原有的 tags/authors，只替换 #category：受限用户的可见性判定
    （_visible_audio_ids）读的就是这份 book_meta。
    """
    try:
        bid = int(book_id)
        cats = _categories_from_value(new_value)
        with _lock:
            st = _state
            if st["version"] < 0 or bid not in st["ids"]:
                return
            _apply_one(st, bid, cats)
    except Exception:
        logging.exception("audio agg: on_category_changed failed for %r", book_id)


def on_categories_changed(updates):
    """批量改分类：{book_id: new_value}。一次加锁处理，量大时退化为后台重建。"""
    try:
        if not updates:
            return
        if len(updates) > BATCH_NOTIFY_THRESHOLD:
            invalidate()
            return
        prepared = [(int(b), _categories_from_value(v)) for b, v in updates.items()]
        with _lock:
            st = _state
            if st["version"] < 0:
                return
            for bid, cats in prepared:
                if bid in st["ids"]:
                    _apply_one(st, bid, cats)
    except Exception:
        logging.exception("audio agg: on_categories_changed failed")


def invalidate():
    """标记元数据脏：下次取聚合时后台全量重建。

    供拿不到逐本新分类值的写入路径（set_metadata、外部 calibre 工具、导入
    脚本）兜底。library_version() 也会自动感知，显式调用只是更快自愈。
    """
    with _lock:
        _state["meta_dirty"] = True


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

    失效判定同时看「书集合版本」与「calibre 库版本」：后者变化说明有人
    改过元数据（含外部工具、set_metadata），但书集合可能一个都没变。此时
    不能走集合增量分支（added/removed 为空、什么都不重算却把 version 推到
    最新，会把旧元数据永久钉死），必须全量重建。

    返回的数据可能是上一版聚合（冷启动后台未建完、或节流窗内）——
    调用方不该假设它反映「此刻」的全库状态；tab/统计类的展示数字允许
    秒级滞后，这是用一致口径换请求路径零阻塞的代价。站内改分类走
    on_category_changed() 即时生效，不依赖这份滞后。
    """
    if audio_ids is None or version is None:
        from webserver.handlers.audio import AudioBooksCache
        if audio_ids is None:
            audio_ids = AudioBooksCache.get_audio_book_ids_set()
        if version is None:
            version = AudioBooksCache.get_version()

    lib_v = _lib_version_of(cache) if cache is not None else None

    with _lock:
        st = _state
        meta_dirty = bool(st["meta_dirty"])
        if (not meta_dirty and lib_v is not None
                and st["lib_version"] is not None
                and st["lib_version"] != lib_v):
            # 有人绕过通知改了 calibre 元数据：集合没变、version 不变，
            # 只有库文件 mtime 会推进。
            meta_dirty = True
        if st["version"] == version and not meta_dirty:
            # 书集合与元数据都没变 ⇔ 直接返回。空库也一样：后台已按空集
            # 建过，不再反复 kick。
            return _snapshot()

        added = audio_ids - st["ids"]
        removed = st["ids"] - audio_ids
        # 纯集合小变更（元数据没脏）→ 同步增量补齐，毫秒级。
        # meta_dirty 时绝不能走这条：diff 为空却会把 version 推到最新。
        if (not meta_dirty and st["ids"]
                and len(added) + len(removed) <= DIFF_SYNC_THRESHOLD):
            for bid in removed:
                _drop_book(st, bid)
            for bid in added:
                _add_book(st, cache, bid)
            st["ids"] = set(audio_ids)
            st["version"] = version
            st["lib_version"] = lib_v
            return _snapshot()

        # 首次冷启动 / 全库扫描后的大变更 / 元数据脏 → 全量重建
        if force:
            built_at = st.get("built_at", 0.0)
            if st["ids"] and (time.time() - built_at) < REBUILD_MIN_INTERVAL:
                # 节流窗内：返回旧版，避免导入高峰把请求线程拖进全量重建。
                # podcast 本来就是 180s TTL，元数据同步滞后同样符合其语义。
                return _snapshot()
            categories, meta = _build_full(cache, audio_ids)
            _apply_full(st, audio_ids, categories, meta)
            st["version"] = version
            st["lib_version"] = lib_v
            st["meta_dirty"] = False
            st["built_at"] = time.time()
            return _snapshot()
        _kick_rebuild(cache, audio_ids, version, lib_v)
        return _snapshot()


def _kick_rebuild(cache, audio_ids, version, lib_version=None):
    """后台线程全量重建（单飞 + 时间节流）。已有线程在建则直接返回。

    节流是必要的：若重建反复失败，或库版本在导入高峰持续推进，没有它就会
    每个请求 kick 一轮全库 metadata 读取。
    """
    now = time.time()
    with _lock:
        if now - _state.get("last_kick", 0.0) < REBUILD_KICK_MIN_INTERVAL:
            return
        _state["last_kick"] = now
    if not _rebuild_lock.acquire(False):
        return

    def _work():
        try:
            categories, meta = _build_full(cache, audio_ids)
            with _lock:
                _apply_full(_state, audio_ids, categories, meta)
                _state["version"] = version
                _state["lib_version"] = lib_version
                _state["meta_dirty"] = False
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
