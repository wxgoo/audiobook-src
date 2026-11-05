#!/usr/bin/env python3
"""盯住 BookDownload 的 initialize：tornado 6.5 起少一个属性就全站下载 500。

## 这条测试在防什么

`BookDownload` 继承 `web.StaticFileHandler`，但把 `initialize()` **整个覆写**
了，没有调 super()。tornado 6.5 把 `allowed_symlink_directory` 的赋值放进了
父类的 `initialize()`：

    def initialize(self, path, default_filename=None, allowed_symlink_directory=None):
        self.root = path
        self.default_filename = default_filename
        if allowed_symlink_directory is None:
            allowed_symlink_directory = path
        self.allowed_symlink_directory = allowed_symlink_directory

而 `validate_absolute_path → _resolve_symlink_target` 会直接读它：

    allowed_directory = os.path.realpath(self.allowed_symlink_directory)

于是每次 `/api/book/<id>.<fmt>` 都是：

    AttributeError: 'BookDownload' object has no attribute 'allowed_symlink_directory'

表现是「所有书籍下载 500」，但日志里只有一行 traceback，很容易被当成
tornado 的怪问题而不是我们的 initialize 少写了一行。

集成测试（test_main.py::TestBook::test_download）能抓到它，但那需要
calibre + python3.12 的完整环境。这里做一个不依赖 calibre 的快速版本，
让任何人在普通环境里 `pytest tests/test_tornado_staticfile_contract.py`
就能验证。
"""
import os
import re
import sys
import unittest
from unittest import mock

testdir = os.path.dirname(os.path.realpath(__file__))
projdir = os.path.realpath(testdir + "/../")
sys.path.append(projdir)


class StaticFileHandlerSubclassContractTest(unittest.TestCase):
    """所有覆写 initialize() 的 StaticFileHandler 子类都必须补齐新属性。"""

    def _source(self, relpath):
        return self._strip_comments(
            open(os.path.join(projdir, relpath), encoding="utf-8").read()
        )

    @staticmethod
    def _strip_comments(src):
        """去掉 # 注释，只留真代码。

        必须这么干：解释「为什么少了这个属性会 500」的注释里天然会写出
        `allowed_symlink_directory`，正文一删注释还在，assertIn 依然为真，
        测试就变成了永远通过的空转（这个坑我第一版就踩了）。
        """
        out = []
        for line in src.splitlines():
            code = line.split("#", 1)[0]
            out.append(code)
        return "\n".join(out)

    def test_book_download_sets_allowed_symlink_directory(self):
        src = self._source("webserver/handlers/book.py")
        # 定位 class BookDownload 到下一个顶层 class 之间的代码
        m = re.search(r"^class BookDownload\b.*?(?=^class |\Z)", src, re.S | re.M)
        self.assertIsNotNone(m, "找不到 BookDownload 类定义")
        body = m.group(0)

        self.assertIn(
            "allowed_symlink_directory",
            body,
            "BookDownload.initialize() 没设置 allowed_symlink_directory。\n"
            "tornado>=6.5 的 StaticFileHandler.validate_absolute_path 会读它，"
            "缺了就是所有下载 500。要么调用 super().initialize(...)，"
            "要么像现在这样自己补一行。",
        )

    def test_initialize_does_not_silently_skip_parent(self):
        """如果哪天改成调 super()，那就不需要自己赋值了——两种写法都行，但不能都没有。"""
        src = self._source("webserver/handlers/book.py")
        m = re.search(r"^class BookDownload\b.*?(?=^class |\Z)", src, re.S | re.M)
        body = m.group(0)
        init = re.search(r"def initialize\(self.*?(?=\n    def |\n    @)", body, re.S)
        self.assertIsNotNone(init)
        text = init.group(0)
        calls_super = "super().initialize(" in text or "StaticFileHandler.initialize(" in text
        sets_attr = "allowed_symlink_directory" in text
        self.assertTrue(
            calls_super or sets_attr,
            "BookDownload.initialize() 既不调父类、也没自己设 allowed_symlink_directory，"
            "下载会 500。",
        )

    def test_all_static_subclasses_are_accounted_for(self):
        """扫全仓：新写一个 StaticFileHandler 子类并覆写 initialize 时，这条会提醒。"""
        offenders = []
        handlers_dir = os.path.join(projdir, "webserver", "handlers")
        for name in sorted(os.listdir(handlers_dir)):
            if not name.endswith(".py"):
                continue
            src = self._source(os.path.join("webserver", "handlers", name))
            for m in re.finditer(
                r"^class (\w+)\(([^)]*StaticFileHandler[^)]*)\).*?(?=^class |\Z)",
                src, re.S | re.M,
            ):
                cls_name, bases = m.group(1), m.group(2)
                body = m.group(0)
                if "def initialize(" not in body:
                    # 没覆写 initialize 就走父类的，父类会自己设，安全
                    continue
                init = re.search(r"def initialize\(self.*?(?=\n    def |\n    @)", body, re.S)
                text = init.group(0)
                if "allowed_symlink_directory" in text:
                    continue
                if "super().initialize(" in text or "StaticFileHandler.initialize(" in text:
                    continue
                offenders.append("%s:%s" % (name, cls_name))
        self.assertEqual(
            offenders, [],
            "这些 StaticFileHandler 子类覆写了 initialize() 但既没调 super()、"
            "也没设 allowed_symlink_directory，下载会 500：%s" % offenders,
        )


class TornadoContractTest(unittest.TestCase):
    """确认我们对 tornado 的判断是对的：6.5 的父类确实在 initialize 里设这个属性。"""

    def test_tornado_assigns_attribute_in_initialize(self):
        import inspect

        from tornado import web

        src = inspect.getsource(web.StaticFileHandler.initialize)
        self.assertIn(
            "allowed_symlink_directory", src,
            "当前 tornado 的 StaticFileHandler.initialize 不再设置 "
            "allowed_symlink_directory——本文件的诊断前提需要更新。",
        )

    def test_missing_attribute_breaks_validate_absolute_path(self):
        """反向验证：不给属性时 validate_absolute_path 真的会炸（防止这条测试变成空转）。"""
        from tornado import web

        class Fake(web.StaticFileHandler):
            def __init__(self):
                self.root = "/"
                self.default_filename = None

        with self.assertRaises(AttributeError):
            Fake().validate_absolute_path("/", "/tmp/x")


if __name__ == "__main__":
    unittest.main()
