"""禁止在 handler 里把 i18n 的 `_` 当局部变量用。

事故：a1d6055「取书权限前置收口」重构引入了 `_, err = self.require_book(id)`。
Python 只要在函数内给 `_` 赋过值，整个函数里的 `_` 就是局部变量，于是后面
`_("分类更新成功")` 调的是 require_book 返回的 book dict →
`TypeError: 'dict' object is not callable`。详情页改分类 / 位置 / 目录 / AI 填充
四个接口全中招，MCP token 生成里的 `for _ in range(32)` 则是 UnboundLocalError。

这类错误不会在 import 时暴露，只有具体接口被点到才炸，靠人工 review 挡不住，
所以用 AST 扫描全仓钉死：凡是 import 了 `webserver.i18n._` 的模块，任何函数里
都不允许把 `_` 作为赋值目标、循环/推导变量或参数名，只要该函数还调用了 `_()`。
"""

import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def find_shadowed(tree, filename="<source>"):
    """返回 [(函数名, 行号, 遮蔽位置)]。"""
    imports_i18n = any(
        isinstance(n, ast.ImportFrom) and any(a.name == "_" for a in n.names)
        for n in ast.walk(tree)
    )
    if not imports_i18n:
        return []

    bad = []
    fns = [n for n in ast.walk(tree)
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for fn in fns:
        stores = [n.lineno for n in ast.walk(fn)
                  if isinstance(n, ast.Name) and n.id == "_"
                  and isinstance(n.ctx, (ast.Store, ast.Del))]
        params = [a.arg for a in (list(fn.args.args) + list(fn.args.kwonlyargs))
                  if a.arg == "_"]
        calls = [n for n in ast.walk(fn)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "_"]
        if (stores or params) and calls:
            bad.append((filename, fn.name, fn.lineno, sorted(set(stores)), params))
    return bad


class TestI18nUnderscoreShadowing(unittest.TestCase):
    def test_scanner_detects_known_bad_pattern(self):
        """扫描器本身必须能抓到事故原样，防止测试退化成永远通过。"""
        src = ast.parse(
            "from webserver.i18n import _\n"
            "def post(self, id):\n"
            "    _, err = self.require_book(id)\n"
            "    return {'msg': _('分类更新成功')}\n"
        )
        self.assertEqual(len(find_shadowed(src)), 1)

    def test_scanner_detects_comprehension_target(self):
        src = ast.parse(
            "from webserver.i18n import _\n"
            "def get(self):\n"
            "    if not self.admin_user:\n"
            "        return {'msg': _('当前用户非管理员')}\n"
            "    token = ''.join(c for _ in range(32))\n"
            "    return {'token': token}\n"
        )
        self.assertEqual(len(find_shadowed(src)), 1)

    def test_scanner_allows_unused_unpack_alias(self):
        """`_book, err = ...` 这种正确写法必须放行。"""
        src = ast.parse(
            "from webserver.i18n import _\n"
            "def post(self, id):\n"
            "    _book, err = self.require_book(id)\n"
            "    return {'msg': _('分类更新成功')}\n"
        )
        self.assertEqual(find_shadowed(src), [])

    def test_no_shadowing_in_webserver(self):
        bad = []
        for p in sorted((ROOT / "webserver").rglob("*.py")):
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            bad.extend(find_shadowed(tree, str(p.relative_to(ROOT))))
        self.assertEqual(
            [], bad,
            msg="以下函数遮蔽了 i18n 的 `_`，运行时会报 "
                "'dict' object is not callable / UnboundLocalError：\n  "
                + "\n  ".join(str(x) for x in bad),
        )


if __name__ == "__main__":
    unittest.main()
