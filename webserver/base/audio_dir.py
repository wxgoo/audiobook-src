#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""有声书音频的存放位置：与电子书同目录。

历史背景
--------
早期音频统一放在 ``<audio_output_folder>/<book_id>/``（默认 ``/data/books/audios/``），
与 calibre 的 ``library/作者/书名 (id)/`` 完全分离，只用 book_id 关联。
书一多就出现两个问题：

1. 删掉 library 里的书，``audios/<id>/`` 变成没人认领的孤儿目录；
2. 从目录名看不出音频属于哪本书，只能反查数据库。

现在改成「音频跟着书目录走」：音频放进书自己的目录，
``library/<作者>/<书名> (id)/.audio/``。

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
重新算。这也是以前 ``audios/<id>/`` 唯一的好处（路径永不变），换布局时丢掉它，
就得用动态解析补回来。

兼容旧布局
----------
迁移期间（以及用户手动关掉迁移的机器）两种位置都可能存在。``audio_dir_for_
book`` 按「新位置有音频就用新的，否则回退旧位置」的规则找，调用方不用关心。
"""

import logging
import os

from webserver import constants, loader

CONF = loader.get_settings()

# 书目录内放音频的子目录名（点开头，避免被 calibre 当成书的格式文件）
AUDIO_SUBDIR = ".audio"

# 旧布局的根目录，仅用于兼容读取与迁移
LEGACY_AUDIO_ROOT = CONF.get("audio_output_folder", "/data/books/audios/")


def _library_root():
    return CONF.get("with_library", "/data/books/library/")


def _has_audio_files(path):
    try:
        return any(f.lower().endswith(tuple(constants.SUPPORTED_AUDIO_FORMATS))
                   for f in os.listdir(path))
    except OSError:
        return False


def legacy_audio_dir(book_id):
    """旧布局的音频目录：<audio_output_folder>/<book_id>/"""
    return os.path.join(LEGACY_AUDIO_ROOT, str(book_id))


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


def book_dir_of(cache, book_id):
    """取一本书在 calibre library 里的绝对目录，算不出来返回 None。

    cache 是 calibre 的 Cache（`db.new_api`，带 field_for）。必须传进来而不是
    在这里全局取，因为本模块也被导入目录监控等没有 cache 的上下文使用。
    传 LibraryDatabase 也能用（内部会取 new_api）。
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
    return os.path.join(_library_root(), rel)


def audio_dir_of(book_dir):
    """书目录下的音频子目录（不保证存在）。"""
    return os.path.join(book_dir, AUDIO_SUBDIR)


def audio_dir_for_read(cache, book_id):
    """读音频该去哪个目录：优先新位置，没有音频再回退旧位置。

    返回 (路径, 是否旧布局)。路径可能不存在，调用方自行判断。
    """
    book_dir = book_dir_of(cache, book_id)
    if book_dir:
        new_dir = audio_dir_of(book_dir)
        if os.path.isdir(new_dir) and _has_audio_files(new_dir):
            return new_dir, False
        # 新目录存在但空着，也认它（可能是刚开始写入）
        if os.path.isdir(new_dir):
            return new_dir, False
    return legacy_audio_dir(book_id), True


def audio_dir_for_write(cache, book_id):
    """写音频该去哪个目录：一律新位置（书目录内），并确保目录存在。

    书目录还不存在（书没进 library）时返回 None——这种书只可能是还没导入的
    遗留记录，调用方应跳过而不是在 library 里凭空造目录。

    但有一个例外：**书已经有旧布局音频时，继续写旧位置**。
    否则会出现「新导入的音频进 .audio/，老的还在 audios/<id>/」，一本书的
    音频被劈成两半，播放器只认其中一处。旧位置既然已经有内容，就等迁移脚本
    统一搬，写入端不要抢跑。
    """
    legacy = legacy_audio_dir(book_id)
    if _has_audio_files(legacy):
        logging.info("[AUDIO_DIR] book %s 仍在旧布局，继续写入 %s（等迁移）",
                     book_id, legacy)
        return legacy

    book_dir = book_dir_of(cache, book_id)
    if not book_dir:
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


def find_audios_by_scanning_library():
    """扫描 library，找出所有带音频的书，返回 {book_id: 音频目录}。

    用于「列出所有有声书」这类需要全量枚举的场景。以前是列
    ``audios/`` 下的数字目录，现在得走 library。

    目录名形如 ``书名 (123)``，id 取最后一对括号里的数字。解析不出来就跳过
    （calibre 的规范目录名一定带 id，没有的说明不是 calibre 建的）。
    """
    root = _library_root()
    result = {}
    if not os.path.isdir(root):
        return result
    try:
        authors = os.listdir(root)
    except OSError as err:
        logging.warning("[AUDIO_DIR] cannot list library root %s: %s", root, err)
        return result

    for author in authors:
        author_dir = os.path.join(root, author)
        if not os.path.isdir(author_dir) or author.startswith("."):
            continue
        try:
            entries = os.listdir(author_dir)
        except OSError:
            continue
        for name in entries:
            book_dir = os.path.join(author_dir, name)
            # 只认 "xxx (123)" 这种规范名
            if not name.endswith(")"):
                continue
            idx = name.rfind("(")
            if idx < 0:
                continue
            id_part = name[idx + 1:-1]
            if not id_part.isdigit():
                continue
            audio_dir = audio_dir_of(book_dir)
            if os.path.isdir(audio_dir) and _has_audio_files(audio_dir):
                result[int(id_part)] = audio_dir
    return result


def iter_audio_dirs_in_library():
    """同上，但返回 (book_id, 书目录, 音频目录)，含没有音频的书。

    给迁移和孤儿检测用：需要知道哪些书目录「本来该有音频」。
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


def legacy_audio_dirs():
    """旧布局下所有 <数字>/ 目录，返回 {book_id: 路径}。"""
    result = {}
    if not os.path.isdir(LEGACY_AUDIO_ROOT):
        return result
    try:
        for item in os.listdir(LEGACY_AUDIO_ROOT):
            path = os.path.join(LEGACY_AUDIO_ROOT, item)
            if os.path.isdir(path) and item.isdigit():
                result[int(item)] = path
    except OSError as err:
        logging.warning("[AUDIO_DIR] cannot list %s: %s", LEGACY_AUDIO_ROOT, err)
    return result
