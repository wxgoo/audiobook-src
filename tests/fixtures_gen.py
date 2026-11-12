#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""集成测试夹具的「缺件现场生成」入口。

## 入库的 vs 生成的

入库（静态，体积固定）：
    tests/cases/users.db
    tests/cases/metadata.db
    tests/cases/big-metadata.db
    tests/cases/title_has_0x00.pdf

生成（不入库，缺件时现造）：
    tests/cases/library/     calibre 库目录（13 本书的格式文件 + 封面）
    tests/cases/old.epub     CFI / 上传用例的样书
    tests/cases/new.epub     同上

为什么不入库：库目录里是「书」，两个 epub 曾经是 0.3 MB / 7.5 MB 的真实
出版物。收进仓库会涉及版权，而且体积会永久留在 git 历史里。它们的正文现在
全部是公有领域文本（《论语》节选），书名/作者/标签等**元数据**仍按
`test_main.py` 里写死的断言来（13 本 / 72 标签 / 15 作者 / 7 系列 /
10 出版社），否则数量断言会直接红。

## 产物落在哪

`tests/cases/library/`、`tests/cases/old.epub`、`tests/cases/new.epub`——
都被 `.gitignore` 挡在版本库外，不会污染 `git status`。

## 幂等性

缺什么补什么；已有就跳过。要强制重建用
`python tests/make_fixtures.py --force`（会连 users.db 一起重写）。

## 注意

不要两个 pytest 进程同时跑：`build_metadata_db` 会先写
`tests/cases/library.building` 再整体 move，并发时后完成的那份会把前一份
正在用的库目录换掉（表现为 `attempt to write a readonly database`）。

用法：

    python tests/fixtures_gen.py            # 缺什么补什么
    python tests/fixtures_gen.py --force    # 全部重建
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CASES = os.path.join(HERE, "cases")


def _missing() -> list:
    """返回当前缺哪些夹具（相对 tests/cases 的描述）。"""
    missing = []
    if not os.path.exists(os.path.join(CASES, "old.epub")):
        missing.append("old.epub")
    if not os.path.exists(os.path.join(CASES, "new.epub")):
        missing.append("new.epub")
    if not os.path.exists(os.path.join(CASES, "library", "metadata.db")):
        missing.append("library/")
    if not os.path.exists(os.path.join(CASES, "users.db")):
        missing.append("users.db")
    return missing


def ensure_fixtures(force: bool = False, verbose: bool = True) -> list:
    """补齐缺失的夹具，返回这次实际生成了哪些。"""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    todo = ["old.epub", "new.epub", "library/", "users.db"] if force else _missing()
    done = []
    if not todo:
        return done

    def say(msg):
        if verbose:
            print("[fixtures] " + msg, flush=True)

    # 1) 两个样书：纯 stdlib（zipfile）就能造，放最前面——
    #    build_metadata_db 里 scanfiles 的两行路径就指向它们。
    if "old.epub" in todo or "new.epub" in todo:
        say("生成 tests/cases/{old,new}.epub（公有领域正文）")
        from tests.make_epub_fixtures import write_upload_samples

        write_upload_samples()
        done.append("old.epub/new.epub")

    # 2) calibre 库目录：这一步才需要 calibre，延迟 import 避免影响
    #    不依赖整站夹具的测试文件。
    if "library/" in todo:
        say("生成 tests/cases/library/（calibre 库，13 本）…")
        from tests import make_fixtures

        make_fixtures.build_metadata_db(os.path.join(CASES, "library"))
        done.append("library/")

    # 3) users.db：已入库，只有本地被删掉时才自愈。
    if "users.db" in todo:
        say("生成 tests/cases/users.db（31 个用户）")
        from tests import make_fixtures

        make_fixtures.build_users_db(os.path.join(CASES, "users.db"))
        done.append("users.db")

    return done


def main():
    ap = argparse.ArgumentParser(description="补齐集成测试夹具（缺什么补什么）")
    ap.add_argument("--force", action="store_true", help="全部重建")
    args = ap.parse_args()

    done = ensure_fixtures(force=args.force)
    if done:
        print("[fixtures] 完成: %s" % ", ".join(done))
    else:
        print("[fixtures] 夹具齐全，无需生成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
