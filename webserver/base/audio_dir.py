#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""有声书音频的存放位置：与电子书同目录。

当前位置
--------
音频放在书自己的目录里：``library/<作者>/<书名> (id)/.audio/``。

历史布局（4.6.0-15 起**不再支持**）
----------------------------------
早期音频统一放在 ``<audio_output_folder>/<book_id>/``（默认 ``/data/books/audios/``），
与 calibre 的 ``library/作者/书名 (id)/`` 完全分离，只用 book_id 关联。
书一多就出现两个问题：

1. 删掉 library 里的书，``audios/<id>/`` 变成没人认领的孤儿目录；
2. 从目录名看不出音频属于哪本书，只能反查数据库。

4.6.0-15 把旧布局彻底移除了：读、写、扫描、删除、播客、重复书合并且全部只认
``.audio/``。升级前必须确认 ``audios/`` 里已经没有内容
（``describe_leftover_legacy_audio()`` 会检查并给出说明）。

为什么多一层 ``.audio/`` 而不是直接放书目录根
--------------------------------------------
用户的本意是「和书同目录」，这一点由「在书目录内部」满足。但书目录根是 calibre
管理的地盘，它按 ``metadata.db`` 里登记的 formats 维护格式文件，同层多出 mp3
有被当成未登记文件的风险（calibre 各版本行为不一致，未逐一实测）。
``.audio`` 以点开头，calibre 遍历时按惯例忽略隐藏目录，风险最小。

路径必须动态解析
----------------
calibre 的书目录名是 ``书名 (id)``，**书改名/作者改名时目录名会跟着变**。
所以绝不能把路径缓存起来当常量用，每次都要通过 ``field_for("path", book_id)``
重新算。这也是以前 ``audios/<id>/`` 唯一的好处（路径永不变），换成 `.audio/`
之后就得用动态解析补回来。
"""

import logging
import os

from webserver import constants, loader

CONF = loader.get_settings()

# 书目录内放音频的子目录名（点开头，避免被 calibre 当成书的格式文件）
AUDIO_SUBDIR = ".audio"

# 已废弃的旧布局根目录。现在只用于「升级前检查是否还有残留」，
# 任何读写路径都不再使用它。
OBSOLETE_AUDIO_ROOT = CONF.get("audio_output_folder", "/data/books/audios/")


def _library_root(override=None):
    return override or CONF.get("with_library", "/data/books/library/")


def _has_audio_files(path):
    try:
        return any(f.lower().endswith(tuple(constants.SUPPORTED_AUDIO_FORMATS))
                   for f in os.listdir(path))
    except OSError:
        return False


def cache_of(db):
    """从 calibre 的 LibraryDatabase 取它的 cache（new_api）。

    **不要写 `db.cache`**——LibraryDatabase 上根本没有这个属性，只有 `new_api`。
    （4.6.0-13 第一版就是因为写成 `self.db.cache` 导致有声书导入全军覆没，
    报 `AttributeError: 'LibraryDatabase' object has no attribute 'cache'`。）

    已经是 cache 对象时原样返回，这样调用方传 db 或传 cache 都能工作。
    """
    if db is None:
        return None
    if hasattr(db, "field_for"):
        return db          # 已经是 new_api / Cache
    return getattr(db, "new_api", None)


def book_dir_of(cache, book_id, library_root=None):
    """取一本书在 calibre library 里的绝对目录，算不出来返回 None。

    cache 是 calibre 的 Cache（`db.new_api`，带 field_for）。必须传进来而不是
    在这里全局取，因为本模块也被导入目录监控等没有 cache 的上下文使用。
    传 LibraryDatabase 也能用（内部会取 new_api）。
    library_root 供测试/工具注入自定义书库根；默认走 CONF。
    """
    cache = cache_of(cache)
    if cache is None:
        return None
    try:
        rel = cache.field_for("path", book_id)
    except Exception as err:
        logging.debug("[AUDIO_DIR] field_for failed for book %s: %s", book_id, err)
        return None
    if not rel:
        return None
    return os.path.join(_library_root(library_root), rel)


def audio_dir_of(book_dir):
    """书目录下的音频子目录（不保证存在）。"""
    return os.path.join(book_dir, AUDIO_SUBDIR)


def audio_dir_for_read(cache, book_id, library_root=None):
    """读音频该去哪个目录：书目录内的 .audio/。

    返回 (路径, False)。路径可能不存在，调用方自行判断。
    第二个返回值是兼容老调用方的占位（以前表示「是否旧布局」），现在恒为 False。

    书不在 library 里（field_for 算不出路径）时返回 (None, False)——
    调用方要按「没有音频」处理，绝对不能退回用 id 拼出来的路径。
    """
    book_dir = book_dir_of(cache, book_id, library_root)
    if not book_dir:
        return None, False
    return audio_dir_of(book_dir), False


def audio_dir_for_write(cache, book_id, library_root=None):
    """写音频该去哪个目录：书目录内的 .audio/，并确保目录存在。

    书目录还不存在（书没进 library）时返回 None——这种书只可能是还没导入的
    遗留记录，调用方应跳过而不是在 library 里凭空造目录。
    """
    book_dir = book_dir_of(cache, book_id, library_root)
    if not book_dir:
        logging.warning("[AUDIO_DIR] book %s 在 library 里没有目录，无法确定音频位置",
                        book_id)
        return None
    if not os.path.isdir(book_dir):
        logging.warning("[AUDIO_DIR] book dir missing for %s: %s", book_id, book_dir)
        return None
    target = audio_dir_of(book_dir)
    try:
        os.makedirs(target, exist_ok=True)
    except OSError as err:
        logging.error("[AUDIO_DIR] cannot create %s: %s", target, err)
        return None
    return target


def iter_audio_dirs_in_library():
    """返回 (book_id, 书目录, 音频目录)，含没有音频的书。

    给统计和孤儿检测用：需要知道哪些书目录「本来该有音频」。
    目录名形如 ``书名 (123)``，id 取最后一对括号里的数字；解析不出来就跳过
    （calibre 的规范目录名一定带 id，没有的说明不是 calibre 建的）。
    """
    root = _library_root()
    if not os.path.isdir(root):
        return
    try:
        authors = os.listdir(root)
    except OSError:
        return
    for author in authors:
        author_dir = os.path.join(root, author)
        if not os.path.isdir(author_dir) or author.startswith("."):
            continue
        try:
            entries = os.listdir(author_dir)
        except OSError:
            continue
        for name in entries:
            if not name.endswith(")"):
                continue
            idx = name.rfind("(")
            if idx < 0:
                continue
            id_part = name[idx + 1:-1]
            if not id_part.isdigit():
                continue
            book_dir = os.path.join(author_dir, name)
            if not os.path.isdir(book_dir):
                continue
            yield int(id_part), book_dir, audio_dir_of(book_dir)


def find_audios_by_scanning_library():
    """扫描 library，找出所有带音频的书，返回 {book_id: 音频目录}。

    用于「列出所有有声书」这类需要全量枚举的场景。
    """
    return {bid: path for bid, _book_dir, path in iter_audio_dirs_in_library()
            if os.path.isdir(path) and _has_audio_files(path)}


def obsolete_audio_dirs():
    """已废弃的 audios/<数字>/ 目录，返回 {book_id: 路径}。

    只给升级检查和诊断脚本用，**不要在任何读写路径上调用**。
    """
    result = {}
    if not os.path.isdir(OBSOLETE_AUDIO_ROOT):
        return result
    try:
        for item in os.listdir(OBSOLETE_AUDIO_ROOT):
            path = os.path.join(OBSOLETE_AUDIO_ROOT, item)
            if os.path.isdir(path) and item.isdigit():
                result[int(item)] = path
    except OSError as err:
        logging.warning("[AUDIO_DIR] cannot list %s: %s", OBSOLETE_AUDIO_ROOT, err)
    return result


def describe_leftover_legacy_audio():
    """检查废弃的 audios/ 里还有没有内容，返回人类可读说明（空串表示干净）。

    4.6.0-15 移除了旧布局，升级脚本和启动自检用这个函数在**动手之前**提醒：
    旧目录里如果还躺着书，升级完就再也读不到了。
    """
    leftovers = obsolete_audio_dirs()
    if not leftovers:
        return ""
    with_files = [(bid, p) for bid, p in leftovers.items() if _has_audio_files(p)]
    if not with_files:
        return ("%s 下还有 %d 个空目录（旧布局残留，可整目录删除）"
                % (OBSOLETE_AUDIO_ROOT, len(leftovers)))
    sample = ", ".join(str(bid) for bid, _ in sorted(with_files)[:10])
    more = "" if len(with_files) <= 10 else " 等"
    return ("%s 下仍有 %d 本书的音频（book_id: %s%s），"
            "新版本不再读取该目录，这些音频会变成孤儿。"
            "请先把它们移入对应书目录的 .audio/ 再升级。"
            % (OBSOLETE_AUDIO_ROOT, len(with_files), sample, more))
