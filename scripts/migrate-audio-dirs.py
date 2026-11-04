#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""把旧布局的音频目录搬进书目录（audios/<id>/ -> library/<作者>/<书名> (id)/.audio/）。

用法（容器内或装了 calibre 的宿主机上）：

    python3 scripts/migrate-audio-dirs.py --dry-run     # 只出清单，不动文件
    python3 scripts/migrate-audio-dirs.py --apply       # 真搬

为什么用脚本而不是纯 SQL/文件操作
---------------------------------
新位置要靠 calibre 的 `field_for("path", book_id)` 算出来——目录名是
`书名 (id)`，书改名/作者改名都会变。只有通过 calibre 的 db 才能拿到当前值，
自己按 `(id)` 反推在重名或特殊字符下会出错。

安全措施
--------
* 默认 dry-run，必须显式 --apply 才动文件
* 目标已存在同名文件时不覆盖，记为 skipped
* 单个书失败不影响其它书，最后汇总
* 搬完才删空的源目录，源目录里有别的东西就留着
* 库中不存在的 book_id（孤儿目录）只报告，不删
"""

import argparse
import logging
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webserver import constants  # noqa: E402
from webserver.base.audio_dir import (  # noqa: E402
    AUDIO_SUBDIR, book_dir_of, legacy_audio_dirs,
)

AUDIO_EXTS = tuple(constants.SUPPORTED_AUDIO_FORMATS)


def _count_audio(path):
    try:
        return sum(1 for f in os.listdir(path) if f.lower().endswith(AUDIO_EXTS))
    except OSError:
        return 0


def build_plan(cache):
    """生成迁移计划：[(book_id, 源目录, 目标目录, 是否孤儿)]。

    注意孤儿判断依赖 cache：拿不到 cache 时所有书都会被判成孤儿（因为算不出
    书目录）。调用方必须保证 cache 可用，main() 里对这一点有独立检查。
    """
    plan = []
    for book_id, src in sorted(legacy_audio_dirs().items()):
        book_dir = book_dir_of(cache, book_id)
        if not book_dir:
            plan.append((book_id, src, None, True))
            continue
        if not os.path.isdir(book_dir):
            # 库里有记录但目录不在（书被删了/路径不对），同样按孤儿处理
            plan.append((book_id, src, None, True))
            continue
        plan.append((book_id, src, os.path.join(book_dir, AUDIO_SUBDIR), False))
    return plan


def move_one(src, dst):
    """把一个目录里的音频/字幕/封面搬到 dst，返回 (搬了几个, 跳过列表)。"""
    moved, skipped = 0, []
    # 字幕和封面跟着音频走，否则播放器找不到
    movable = AUDIO_EXTS + (".srt", ".vtt", ".txt", ".jpg", ".jpeg", ".png")
    os.makedirs(dst, exist_ok=True)
    for fname in sorted(os.listdir(src)):
        src_file = os.path.join(src, fname)
        if not os.path.isfile(src_file):
            continue
        if not fname.lower().endswith(movable):
            continue
        dst_file = os.path.join(dst, fname)
        if os.path.exists(dst_file):
            skipped.append(fname)
            continue
        shutil.move(src_file, dst_file)
        moved += 1
    return moved, skipped


def main():
    ap = argparse.ArgumentParser(description="把 audio_output_folder 下的音频搬进书目录")
    ap.add_argument("--apply", action="store_true", help="真的搬；不加则只打印计划")
    ap.add_argument("--book-id", type=int, action="append", help="只处理指定 book_id（可多次）")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from webserver import loader
    conf = loader.get_settings()
    library = conf.get("with_library", "/data/books/library/")
    if not os.path.isdir(library):
        logging.error("书库目录不存在: %s", library)
        return 2

    from calibre.db.legacy import LibraryDatabase
    db = LibraryDatabase(os.path.expanduser(library))
    cache = db.new_api

    # 先验一下 cache 真能用。cache 失效时 book_dir_of 会静默返回 None，
    # 所有书都会被当成孤儿——清单看起来「没东西可迁」，其实是一条都算不出来。
    # 这种事不能悄悄发生，宁可报错退出。
    try:
        probe = next(iter(legacy_audio_dirs()), None)
        if probe is not None:
            cache.field_for("path", probe)
    except Exception as err:
        logging.error("无法从 calibre 取书目录（field_for 失败）：%s", err)
        logging.error("请确认 %s 是有效的书库目录，且 calibre 版本与容器内一致", library)
        return 2

    plan = build_plan(cache)
    if args.book_id:
        wanted = set(args.book_id)
        plan = [p for p in plan if p[0] in wanted]

    if not plan:
        logging.info("没有需要迁移的旧音频目录")
        return 0

    orphans = [p for p in plan if p[3]]
    movable = [p for p in plan if not p[3]]

    logging.info("计划：%d 个可迁移，%d 个孤儿（库里找不到对应的书）",
                 len(movable), len(orphans))
    print()
    print("%-10s %-8s %s" % ("BOOK_ID", "音频数", "源目录 -> 目标目录"))
    print("-" * 100)
    for book_id, src, dst, is_orphan in plan:
        n = _count_audio(src)
        if is_orphan:
            print("%-10d %-8d %s  ⚠ 孤儿（保留原地，请人工确认）" % (book_id, n, src))
        else:
            print("%-10d %-8d %s -> %s" % (book_id, n, src, dst))

    if not args.apply:
        print()
        print("这是预演（dry-run）。确认无误后加 --apply 执行。")
        return 0

    print()
    ok = fail = 0
    total_moved = 0
    for book_id, src, dst, is_orphan in movable:
        try:
            moved, skipped = move_one(src, dst)
            total_moved += moved
            ok += 1
            if skipped:
                logging.warning("book %s：%d 个文件目标已存在，已跳过：%s",
                                book_id, len(skipped), ", ".join(skipped[:3]))
            # 源目录空了才删
            try:
                if not os.listdir(src):
                    os.rmdir(src)
            except OSError:
                pass
            logging.info("book %s：搬了 %d 个文件", book_id, moved)
        except Exception as err:
            fail += 1
            logging.error("book %s 迁移失败：%s", book_id, err)

    print()
    logging.info("完成：成功 %d，失败 %d，共搬 %d 个文件", ok, fail, total_moved)
    if orphans:
        logging.warning("有 %d 个孤儿目录留在原地，请人工确认后再删", len(orphans))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
