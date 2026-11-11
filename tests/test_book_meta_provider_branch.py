# -*- coding: utf-8 -*-
"""BookRefer 的 provider 分支：禁止再依赖已下线的 douban v1。

背景：douban v1 插件在 build.27-r12 注销、r13 删除模块，但 `book.py` 的
`BookRefer.post` 里留了一句 `if provider_key == douban.KEY:`。`douban` 这个名字
没有任何 import，于是**任意 provider** 的元数据更新 POST 都会在这一行抛
`NameError: name 'douban' is not defined`，接口 500。这里锁死两个不变量：

1. `_resolve_refer_mi` 在没有任何豆瓣 v1 模块时，对任意 provider_key 都能返回结果；
2. 运行时代码里不允许出现未绑定的 `douban` 属性访问（静态兜底）。
"""
import ast
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from webserver.handlers import book as book_handler  # noqa: E402


class _MI:
    def __init__(self):
        self.authors = ["某作者"]
        self.author_sort = "某作者"
        self.cover_data = None


def _make_handler(plugin_result=None, cover=b"IMG"):
    h = book_handler.BookRefer.__new__(book_handler.BookRefer)
    h.calls = []
    h.plugin_get_book_meta = lambda *a, **k: (h.calls.append("meta"), plugin_result)[1]
    h.plugin_fill_book_cover = lambda *a, **k: (h.calls.append("cover"), cover)[1]
    h._convert_to_metadata = lambda md: _MI() if md else None
    return h


@pytest.mark.parametrize("provider_key", ["douban", "douban_v2", "xhsd", "bookbarn"])
def test_provider_branch_returns_without_douban_v1(provider_key):
    """库里存量的 provider_key="douban" 也不能再触发 NameError。"""
    mi = _MI()
    h = _make_handler()
    out = book_handler.BookRefer._resolve_refer_mi(
        h, provider_key, "value", None, mi, "", "")
    assert out is mi


def test_douban_v2_placeholder_comments_still_calls_plugin():
    mi = _MI()
    h = _make_handler(plugin_result=_MI())
    out = book_handler.BookRefer._resolve_refer_mi(
        h, "douban_v2", "v", {"comments": ".....", "cover_url": None}, mi, "", "")
    assert "meta" in h.calls
    assert out is not None


def test_cover_is_filled_unless_only_meta():
    mi = _MI()
    h = _make_handler()
    out = book_handler.BookRefer._resolve_refer_mi(
        h, "xhsd", "v", {"comments": "", "cover_url": "http://x/cover.jpg"}, mi, "", "")
    assert out.cover_data == b"IMG"

    h2 = _make_handler()
    out2 = book_handler.BookRefer._resolve_refer_mi(
        h2, "xhsd", "v", {"comments": "", "cover_url": "http://x/cover.jpg"}, mi, "yes", "")
    assert "cover" not in h2.calls
    assert out2 is not None


def _runtime_py_files():
    base = os.path.join(ROOT, "webserver")
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", "node_modules")]
        for f in filenames:
            if f.endswith(".py"):
                yield os.path.join(dirpath, f)


def test_no_unbound_douban_attribute():
    """`douban.xxx` 必须有同名 import 绑定；v1 删除后全仓应为 0 处。"""
    bad = []
    for path in _runtime_py_files():
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src)
        bound = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    bound.add(a.asname or a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for a in node.names:
                    bound.add(a.asname or a.name)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                    and node.value.id == "douban" and "douban" not in bound):
                bad.append("%s:%d" % (os.path.relpath(path, ROOT), node.lineno))
    assert not bad, "存在未绑定的 douban 引用：%s" % ", ".join(bad)


def test_douban_v1_module_is_gone():
    d = os.path.join(ROOT, "webserver", "plugins", "meta", "douban")
    srcs = [f for f in os.listdir(d) if f.endswith(".py")] if os.path.isdir(d) else []
    assert not srcs, "douban v1 源码仍在：%s" % srcs
