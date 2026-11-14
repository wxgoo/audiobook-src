"""契约：所有写 #category 的调用点必须通知 audio_category_agg。

背景（r38 真实事故）：详情页改分类走 `set_field(CALIBRE_COLUMN_CATEGORY, ...)`
写进 calibre 后，分类 tab 聚合只按「有音频的书集合版本」失效，没人通知就
永远读到旧快照——书留在旧分类桶里，重启容器才自愈。

改分类入口不止详情页：批量改分类、清空分类、批量元数据编辑、MCP 改书信息、
AI 自动填信息、导入按目录名设分类、重命名分类目录、移动文件、……逐个手工
补极易再漏。这里用 AST 扫描整个 webserver/，强制每个 set_field(#category)
所在函数内必须出现 audio_category_agg 的通知调用；新增入口忘了通知会直接
让测试失败，而不是等用户在 NAS 上发现。

与 tests/test_i18n_underscore_shadowing.py 同为「静态契约 + 无运行时依赖」，
不需要 calibre / DB / 网络。
"""

import ast
import os

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WEBSERVER = os.path.join(REPO_ROOT, "webserver")

CATEGORY_NAMES = {"CALIBRE_COLUMN_CATEGORY", "COLUMN_CATEGORY"}
NOTIFY_METHODS = {"on_category_changed", "on_categories_changed", "invalidate"}


def _py_files():
    for root, _dirs, files in os.walk(WEBSERVER):
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(root, name)


def _is_category_set_field(call):
    fn = call.func
    if not (isinstance(fn, ast.Attribute) and fn.attr == "set_field"):
        return False
    if not call.args:
        return False
    arg = call.args[0]
    return ((isinstance(arg, ast.Name) and arg.id in CATEGORY_NAMES)
            or (isinstance(arg, ast.Constant) and arg.value == "#category"))


def _enclosing_function(node, parents):
    p = parents.get(node)
    while p is not None:
        if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return p
        p = parents.get(p)
    return None


def _has_notify(func):
    if func is None:
        return False
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if (isinstance(fn, ast.Attribute)
                and fn.attr in NOTIFY_METHODS
                and isinstance(fn.value, ast.Name)
                and fn.value.id == "audio_category_agg"):
            return True
    return False


def _collect():
    calls = []
    for path in _py_files():
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except SyntaxError:
            continue
        parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_category_set_field(node):
                func = _enclosing_function(node, parents)
                calls.append((path, node.lineno,
                              func.name if func else "<module>",
                              _has_notify(func)))
    return calls


def test_every_category_write_notifies_aggregation():
    calls = _collect()
    assert calls, "扫描不到任何 set_field(#category) 调用，契约失效，请检查扫描口径"
    missing = [
        (os.path.relpath(p, REPO_ROOT), line, func)
        for p, line, func, ok in calls if not ok
    ]
    assert not missing, (
        "以下写分类的入口没有通知 audio_category_agg，改完分类后 tab 会停留在旧桶：\n"
        + "\n".join(f"  {p}:{line} in {func}" for p, line, func in missing)
    )


def test_notify_api_exists():
    """通知 API 被改名/删除时给出明确失败，而不是让上面的契约静默放过。"""
    from webserver.base import audio_category_agg as agg
    for name in NOTIFY_METHODS:
        assert callable(getattr(agg, name, None)), f"缺少 {name}()"


def test_aggregation_has_meta_dirty_guard():
    """增量分支必须带 `not meta_dirty` 守卫：否则空 diff 会把旧元数据钉死。
    这里用源码文本做兜底检查（单测 test_meta_dirty_never_takes_empty_diff_path
    负责行为验证）。
    """
    src = open(os.path.join(WEBSERVER, "base", "audio_category_agg.py"),
               encoding="utf-8").read()
    assert "not meta_dirty and st[\"ids\"]" in src
    assert "_lib_version_of" in src
