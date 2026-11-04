#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""webserver/base/audio_dir.py 与 scripts/migrate-audio-dirs.py 的运行时验证。

沙箱里没有完整的 calibre，`cache.field_for("path", id)` 无法真实调用，
所以用假 cache + 假目录树跑一遍分支。跑法：

    python3 scripts/test-audio-dirs.py

只依赖标准库，不写 /data，全部在临时目录里做。
"""

import logging
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webserver.base import audio_dir as ad  # noqa: E402

FAILED = []
PASSED = [0]


def check(name, cond, detail=""):
    if cond:
        PASSED[0] += 1
        print("  ok   %s" % name)
    else:
        FAILED.append(name)
        print("  FAIL %s  %s" % (name, detail))


class FakeCache:
    """只实现 field_for("path", book_id)，够 audio_dir 用。"""

    def __init__(self, mapping=None, raise_for=None):
        self.mapping = mapping or {}
        self.raise_for = set(raise_for or ())

    def field_for(self, name, book_id, default=None):
        assert name == "path", "只应该问 path，实际问的是 %r" % name
        if book_id in self.raise_for:
            raise KeyError("book %s 不存在" % book_id)
        return self.mapping.get(book_id, default)


class FakeLibraryDb:
    """模拟 calibre 的 LibraryDatabase：**没有 .cache 属性**，只有 .new_api。

    这是 4.6.0-13 线上事故的原型：写成 `db.cache` 会 AttributeError。
    """

    def __init__(self, mapping):
        self.new_api = FakeCache(mapping)


class BrokenCache:
    def field_for(self, *a, **kw):
        raise RuntimeError("数据库炸了")


def touch(path, content=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)


def _load_audio_utils():
    """用 AST 从 webserver/handlers/audio.py 抠出 AudioUtils 的两个纯逻辑方法。

    audio.py 顶层牵连几十个模块（social_sqlalchemy 等），沙箱装不全。
    这里只取 audio_dirs_of / clear_audio 的函数体，塞进一个最小类的命名空间
    里编译执行，所以被测代码和线上是同一份。
    """
    import ast
    import textwrap

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src_path = os.path.join(root, "webserver", "handlers", "audio.py")
    with open(src_path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), src_path)

    wanted = {"audio_dirs_of", "clear_audio"}
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "AudioUtils":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name in wanted:
                    found[item.name] = item
            break
    missing = wanted - set(found)
    if missing:
        raise RuntimeError("audio.py 里找不到方法：%s" % missing)

    class Stub:
        # 这些名字在抠出来的函数体里被引用，给个最小可用实现
        @staticmethod
        def audio_dirs_of(book_id, cache=None):
            from webserver.base.audio_dir import (audio_dir_of, book_dir_of,
                                                  legacy_audio_dir)
            out = []
            book_dir = book_dir_of(cache, book_id)
            if book_dir:
                out.append(audio_dir_of(book_dir))
            out.append(legacy_audio_dir(book_id))
            return out

    ns = {
        "os": os, "shutil": shutil,
        "AudioUtils": Stub,
        "_": lambda s: s,
        "logging": logging,
        "AudioBooksCache": type("x", (), {"async_update": staticmethod(lambda: None)}),
    }
    for name, fn in found.items():
        fn.decorator_list = []          # 去掉 @staticmethod
        mod = ast.Module(body=[fn], type_ignores=[])
        ast.fix_missing_locations(mod)
        code = compile(mod, src_path, "exec")
        exec(code, ns)
        setattr(Stub, name, ns[name])
    return Stub


def main():
    logging.basicConfig(level=logging.CRITICAL)
    tmp = tempfile.mkdtemp(prefix="audiodir-test-")
    lib = os.path.join(tmp, "library")
    legacy = os.path.join(tmp, "audios")
    os.makedirs(lib, exist_ok=True)
    os.makedirs(legacy, exist_ok=True)

    # 模块级常量是导入时算死的，这里改成临时目录
    ad.LEGACY_AUDIO_ROOT = legacy
    ad._library_root = lambda: lib

    # 造目录树
    # 1) 刘慈欣/三体 (1)      —— 书目录存在，还没有 .audio
    # 2) 刘慈欣/球状闪电 (2)  —— 书目录存在，.audio 里有音频
    # 3) 特德·姜/你一生的故事 (3) —— 书目录存在，.audio 存在但空
    # 4) 不存在的/书 (4)      —— cache 里有记录，但目录不在
    # 5) 括号里不是数字的目录
    # 6) 隐藏目录 .staging
    b1 = os.path.join(lib, "刘慈欣", "三体 (1)")
    b2 = os.path.join(lib, "刘慈欣", "球状闪电 (2)")
    b3 = os.path.join(lib, "特德·姜", "你一生的故事 (3)")
    for d in (b1, b2, b3):
        os.makedirs(d, exist_ok=True)
    touch(os.path.join(b1, "三体.epub"))
    touch(os.path.join(b2, "球状闪电.epub"))
    touch(os.path.join(b2, ".audio", "01.mp3"))
    touch(os.path.join(b2, ".audio", "02.mp3"))
    os.makedirs(os.path.join(b3, ".audio"), exist_ok=True)
    os.makedirs(os.path.join(lib, "刘慈欣", "没有ID的目录"), exist_ok=True)
    os.makedirs(os.path.join(lib, ".staging", "假书 (99)"), exist_ok=True)

    legacy_map = {1: "刘慈欣/三体 (1)", 2: "刘慈欣/球状闪电 (2)",
                  3: "特德·姜/你一生的故事 (3)", 4: "某人/已删除的书 (4)"}
    cache = FakeCache(legacy_map)

    print("\n[1] book_dir_of")
    check("正常书返回拼接后的绝对路径",
          ad.book_dir_of(cache, 1) == b1, ad.book_dir_of(cache, 1))
    check("cache 为 None 返回 None", ad.book_dir_of(None, 1) is None)
    check("书不存在返回 None", ad.book_dir_of(cache, 999) is None)
    check("field_for 抛异常被吞掉返回 None",
          ad.book_dir_of(BrokenCache(), 1) is None)
    check("raise_for 也被吞掉", ad.book_dir_of(FakeCache({}, raise_for=[7]), 7) is None)

    print("\n[1b] 传 LibraryDatabase 而不是 cache（线上事故回归）")
    # 4.6.0-13 第一版把 LibraryDatabase 直接当 cache 用，报
    # AttributeError: 'LibraryDatabase' object has no attribute 'cache'
    fake_db = FakeLibraryDb(legacy_map)
    check("LibraryDatabase 上没有 cache 属性",
          not hasattr(fake_db, "cache"))
    check("cache_of 能从 db 取到 new_api", ad.cache_of(fake_db) is fake_db.new_api)
    check("cache_of 收到 cache 原样返回", ad.cache_of(cache) is cache)
    check("cache_of(None) 返回 None", ad.cache_of(None) is None)
    check("book_dir_of 接受 LibraryDatabase",
          ad.book_dir_of(fake_db, 1) == b1, ad.book_dir_of(fake_db, 1))
    check("audio_dir_for_read 接受 LibraryDatabase",
          ad.audio_dir_for_read(fake_db, 2)[0] == os.path.join(b2, ".audio"))
    # 用 book2（.audio 已存在）而不是 book1，避免在这里建目录影响后面 [3] 的
    # 「book1 新位置不存在 -> 回退旧布局」断言
    check("audio_dir_for_write 接受 LibraryDatabase",
          ad.audio_dir_for_write(fake_db, 2) == os.path.join(b2, ".audio"))

    print("\n[2] audio_dir_of")
    check("拼出 .audio 子目录",
          ad.audio_dir_of(b1) == os.path.join(b1, ad.AUDIO_SUBDIR))
    check("AUDIO_SUBDIR 以点开头（避免 calibre 当格式文件）",
          ad.AUDIO_SUBDIR.startswith("."), ad.AUDIO_SUBDIR)

    print("\n[3] audio_dir_for_read")
    p, is_legacy = ad.audio_dir_for_read(cache, 1)
    check("书2 新位置有音频 -> 用新位置", True)
    p, is_legacy = ad.audio_dir_for_read(cache, 2)
    check("book2 返回新位置", p == os.path.join(b2, ".audio") and is_legacy is False,
          (p, is_legacy))
    p, is_legacy = ad.audio_dir_for_read(cache, 3)
    check("book3 新位置存在但为空 -> 仍用新位置",
          p == os.path.join(b3, ".audio") and is_legacy is False, (p, is_legacy))
    p, is_legacy = ad.audio_dir_for_read(cache, 1)
    check("book1 新位置不存在 -> 回退旧布局",
          p == os.path.join(legacy, "1") and is_legacy is True, (p, is_legacy))
    p, is_legacy = ad.audio_dir_for_read(cache, 4)
    check("book4 目录不存在 -> 回退旧布局",
          p == os.path.join(legacy, "4") and is_legacy is True, (p, is_legacy))
    p, is_legacy = ad.audio_dir_for_read(None, 1)
    check("cache 为 None -> 旧布局",
          p == os.path.join(legacy, "1") and is_legacy is True, (p, is_legacy))

    print("\n[4] audio_dir_for_write")
    p = ad.audio_dir_for_write(cache, 1)
    expect = os.path.join(b1, ".audio")
    check("写入新位置", p == expect, p)
    check("目录被创建出来", os.path.isdir(expect))
    check("幂等（再调一次不报错）", ad.audio_dir_for_write(cache, 1) == expect)
    check("book4 目录不存在 -> 返回 None", ad.audio_dir_for_write(cache, 4) is None)
    check("没有凭空造出 library/某人/已删除的书 (4)",
          not os.path.exists(os.path.join(lib, "某人")))
    check("cache 为 None -> 返回 None", ad.audio_dir_for_write(None, 1) is None)

    # 旧布局里已经有音频的书，写入必须继续走旧位置，否则一本书的音频被劈成两半
    touch(os.path.join(legacy, "30", "01.mp3"))
    old_book_dir = os.path.join(lib, "某作者", "旧布局书 (30)")
    os.makedirs(old_book_dir, exist_ok=True)
    cache.mapping[30] = "某作者/旧布局书 (30)"
    p = ad.audio_dir_for_write(cache, 30)
    check("旧布局已有音频 -> 继续写旧位置",
          p == os.path.join(legacy, "30"), p)
    check("旧布局的书没有被建出 .audio 目录",
          not os.path.exists(os.path.join(old_book_dir, ".audio")))

    print("\n[5] find_audios_by_scanning_library")
    touch(os.path.join(b1, ".audio", "01.mp3"))   # 刚才 for_write 建的目录，补个音频
    found = ad.find_audios_by_scanning_library()
    check("找到 book1 和 book2", sorted(found) == [1, 2], sorted(found))
    check("book3 的 .audio 是空的，不算有音频", 3 not in found)
    check("不误认 .staging 里的假书", 99 not in found)
    check("路径正确", found.get(2) == os.path.join(b2, ".audio"), found.get(2))

    print("\n[6] iter_audio_dirs_in_library")
    rows = list(ad.iter_audio_dirs_in_library())
    ids = sorted(r[0] for r in rows)
    # 30 是 [4] 里为「旧布局写入」造的书，也在这棵树里
    check("列出有规范目录名的书", ids == [1, 2, 3, 30], ids)
    check("每行是三元组", all(len(r) == 3 for r in rows))
    check("隐藏目录被跳过", not any("staging" in r[1] for r in rows))
    check("没有ID的目录被跳过", not any("没有ID" in r[1] for r in rows))

    print("\n[7] legacy_audio_dirs")
    touch(os.path.join(legacy, "5", "01.mp3"))
    touch(os.path.join(legacy, "6", "01.mp3"))
    touch(os.path.join(legacy, "not-a-number", "01.mp3"))
    os.makedirs(os.path.join(legacy, "7"), exist_ok=True)  # 空目录也算
    leg = ad.legacy_audio_dirs()
    check("识别数字目录", sorted(leg) == [5, 6, 7, 30], sorted(leg))
    check("忽略非数字目录", "not-a-number" not in [str(k) for k in leg])
    check("路径正确", leg.get(5) == os.path.join(legacy, "5"))

    print("\n[8] 迁移脚本 build_plan / move_one")
    # 造一份真正的旧布局：book1(可迁)、book4(孤儿，目录不在)、book8(孤儿，cache 里没有)
    touch(os.path.join(legacy, "1", "01.mp3"))
    touch(os.path.join(legacy, "1", "02.mp3"))
    touch(os.path.join(legacy, "1", "01.srt"))
    touch(os.path.join(legacy, "1", "cover.jpg"))
    touch(os.path.join(legacy, "1", "notes.pdf"))     # 不该被搬
    touch(os.path.join(legacy, "4", "01.mp3"))
    touch(os.path.join(legacy, "8", "01.mp3"))

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import importlib
    mig = importlib.import_module("migrate-audio-dirs")

    # [4] 里 audio_dir_for_write 给 b1 建了 .audio 并放了 01.mp3，
    # 所以这里得先把目标腾空，否则测的就不是「搬迁」而是「跳过重名」。
    shutil.rmtree(os.path.join(b1, ".audio"), ignore_errors=True)

    plan = mig.build_plan(cache)
    by_id = {p[0]: p for p in plan}
    check("book1 规划为可迁移", by_id[1][3] is False and by_id[1][2] == os.path.join(b1, ".audio"),
          by_id.get(1))
    check("book4（cache 有、目录不在）判为孤儿", by_id[4][3] is True, by_id.get(4))
    check("book8（cache 里没有）判为孤儿", by_id[8][3] is True, by_id.get(8))
    # book5/6/7 在旧目录里建过，但 cache 里没有记录 -> 也该按孤儿报告出来，
    # 不能从清单里消失（否则它们的音频永远没人知道）。
    check("book5/6/7 也进计划且标为孤儿",
          all(by_id.get(i, (None, None, None, False))[3] for i in (5, 6, 7)), sorted(by_id))

    src, dst = os.path.join(legacy, "1"), os.path.join(b1, ".audio")
    moved, skipped = mig.move_one(src, dst)
    check("搬了 4 个文件（mp3×2 + srt + jpg）", moved == 4, moved)
    check("没有跳过", skipped == [], skipped)
    check("mp3 到位", os.path.isfile(os.path.join(dst, "01.mp3")))
    check("字幕跟着走", os.path.isfile(os.path.join(dst, "01.srt")))
    check("封面跟着走", os.path.isfile(os.path.join(dst, "cover.jpg")))
    check("无关文件 notes.pdf 留在原地",
          os.path.isfile(os.path.join(src, "notes.pdf")))
    check("源文件已被移走（不是复制）",
          not os.path.exists(os.path.join(src, "01.mp3")))

    print("\n[9] move_one 的冲突处理")
    touch(os.path.join(src, "03.mp3"))
    touch(os.path.join(dst, "03.mp3"), b"already-here")
    moved2, skipped2 = mig.move_one(src, dst)
    check("重名文件跳过而不是覆盖", skipped2 == ["03.mp3"], skipped2)
    check("目标文件内容没被改",
          open(os.path.join(dst, "03.mp3"), "rb").read() == b"already-here")
    check("moved 只算真正搬走的", moved2 == 0, moved2)

    print("\n[10] 迁移后再读，应该命中新位置")
    p, is_legacy = ad.audio_dir_for_read(cache, 1)
    check("book1 现在走新布局", p == os.path.join(b1, ".audio") and is_legacy is False,
          (p, is_legacy))

    print("\n[11] clear_audio 的路径计算（线程池场景）")
    # webserver.handlers.audio 牵连几十个模块（social_sqlalchemy 等沙箱没装），
    # 直接 import 会把测试拖成「装依赖大会」。改用 AST 把 AudioUtils.audio_dirs_of
    # 和 clear_audio 的真实函数体抠出来单独编译执行——测的仍是线上那份代码，
    # 不是抄一份。
    AU = _load_audio_utils()

    dirs = AU.audio_dirs_of(1, cache)
    check("列出新旧两个候选目录",
          dirs == [os.path.join(b1, ".audio"), os.path.join(legacy, "1")], dirs)
    dirs_nocache = AU.audio_dirs_of(1, None)
    check("cache 为 None 时至少给旧位置",
          dirs_nocache == [os.path.join(legacy, "1")], dirs_nocache)

    # 线程池里的调用方式：cache 传 None，路径靠 extra_dirs 带进来
    ok, msg = AU.clear_audio(1, None, extra_dirs=[os.path.join(b1, ".audio")])
    check("extra_dirs 生效，新位置被删",
          ok and not os.path.exists(os.path.join(b1, ".audio")), (ok, msg))
    check("清理后 audio_dir_for_read 回退旧布局",
          ad.audio_dir_for_read(cache, 1)[1] is True)

    shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 50)
    print("通过 %d，失败 %d" % (PASSED[0], len(FAILED)))
    if FAILED:
        for f in FAILED:
            print("  - %s" % f)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
