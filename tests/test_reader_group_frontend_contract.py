# -*- coding: utf-8 -*-
"""前端产物与源码一致性回归。

背景：ReaderGroupEditor.vue 曾把 `modeText` 写在 `computed` 里，模板却按
`modeText(groups[name].mode)` 带参调用。Vue 会先把 computed 无参求值成字符串，
再把它当函数调用，运行时抛 `TypeError: e.modeText is not a function`，整个组件
渲染中断，列表停在转圈。这里锁死两个不变量：
  1. 模板里带参调用的标识符，不能出现在 `computed` 里；
  2. `modeText` 必须定义在 `methods` 里；
  3. 若仓库带 `app/dist`，则产物必须包含源码里的兜底文案（防止 dist 与 src 不同批）。
"""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VUE = os.path.join(ROOT, "app", "src", "components", "ReaderGroupEditor.vue")
DIST_NUXT = os.path.join(ROOT, "app", "dist", "_nuxt")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _block(src, name):
    """取出 `name: {` 到同缩进的 `},` 之间的内容。"""
    m = re.search(r"^  %s: \{\s*$" % re.escape(name), src, re.M)
    if not m:
        return ""
    start = m.end()
    end = re.search(r"^  \},?\s*$", src[start:], re.M)
    return src[start:start + end.start()] if end else ""


def _keys(block):
    return set(re.findall(r"^    ([A-Za-z_$][\w$]*)\s*[:(]", block, re.M))


def _template(src):
    """模板段：从开头的 <template> 到最后一个 </template>（内部可能有具名 slot 的
    嵌套 <template>，用第一个 </template> 会截断，测试就变成空转）。"""
    return src[:src.rindex("</template>")]


def test_computed_members_are_not_called_with_args():
    src = _read(VUE)
    computed = _keys(_block(src, "computed"))
    called = set(re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(", _template(src)))
    # 模板里出现、且被当函数调用的名字，不能是 computed 成员
    bad = sorted(computed & called)
    assert not bad, "computed 被当方法调用，会在渲染期抛 TypeError: %s" % bad


def test_mode_text_is_a_method():
    src = _read(VUE)
    methods = _keys(_block(src, "methods"))
    computed = _keys(_block(src, "computed"))
    assert "modeText" in methods
    assert "modeText" not in computed


@pytest.mark.skipif(not os.path.isdir(DIST_NUXT), reason="仓库未带 app/dist")
def test_dist_contains_src_only_strings():
    """dist 必须与 src 同批：源码新增的兜底文案要能在产物里找到。"""
    blob = []
    for name in os.listdir(DIST_NUXT):
        if name.endswith(".js"):
            blob.append(_read(os.path.join(DIST_NUXT, name)))
    merged = "\n".join(blob)
    for key in ("reader_group_load_timeout", "reader_group_retry"):
        assert key in merged, "app/dist 落后于 src：缺少 %s" % key
