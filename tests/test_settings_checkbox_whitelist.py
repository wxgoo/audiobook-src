#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""设置页勾选框 ↔ 保存白名单 契约测试。

背景（r37）：``AdminSettings.post`` 用 ``KEYS = list(ADMIN_SETTING_KEYS)``
过滤前端提交，漏登记的键被静默丢弃；而 ``dumpfile()`` 是整份覆盖写回
``auto.py``，没登记进 PERSISTABLE_KEYS 的键还会被抹回默认值。两者都表现为
「设置页勾了/取消了，完全没反应」，且不报错、不留痕。

已经踩过的两个：
  * AUDIO_LINK_TO_EXISTING_BOOK —— auto.py 里根本没这一行
  * ENABLE_KOREADER_SERVICE   —— 在 auto.py 里，但永远是改不动的旧默认值
"""

import ast
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _checkbox_keys():
    path = os.path.join(ROOT, "app/src/pages/admin/settings.vue")
    with open(path, encoding="utf8") as f:
        src = f.read()
    keys = set()
    # [^{}]* 限定在单个对象字面量内，避免跨 field 误匹配（搜索别名表里也有 key:）。
    patterns = (
        r'\{[^{}]*key:\s*"([^"]+)"[^{}]*type:\s*"checkbox(?:_list)?"[^{}]*\}',
        r'\{[^{}]*type:\s*"checkbox(?:_list)?"[^{}]*key:\s*"([^"]+)"[^{}]*\}',
    )
    for pat in patterns:
        for m in re.finditer(pat, src, re.S):
            keys.add(m.group(1))
    return keys


def _admin_setting_keys():
    path = os.path.join(ROOT, "webserver/base/setting_saver.py")
    with open(path, encoding="utf8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "ADMIN_SETTING_KEYS" for t in node.targets
        ):
            # 末尾有 *perf.setting_keys() (Starred)，只收字面量常量
            return {
                e.value
                for e in node.value.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            }
    raise AssertionError("ADMIN_SETTING_KEYS 未找到，检查 setting_saver.py 是否被重构")


def test_every_checkbox_key_is_submittable():
    keys = _checkbox_keys()
    assert len(keys) >= 40, "解析到的勾选框过少，检查 settings.vue 结构或正则：%d" % len(keys)
    admin = _admin_setting_keys()
    missing = sorted(keys - admin)
    assert not missing, (
        "以下设置页勾选框不在 ADMIN_SETTING_KEYS，勾选值会被 AdminSettings.post 静默丢弃：\n  "
        + "\n  ".join(missing)
    )


def test_regression_keys_present():
    """r37 修的两个具体开关，防止以后被误删。"""
    admin = _admin_setting_keys()
    for key in ("AUDIO_LINK_TO_EXISTING_BOOK", "ENABLE_KOREADER_SERVICE"):
        assert key in admin, "%s 又从白名单里掉了" % key


def test_new_audio_auto_import_settings_persistable():
    """无 UI 的配置必须登记，否则手改 auto.py 会被整份覆盖抹掉。"""
    admin = _admin_setting_keys()
    for key in ("AUDIO_AUTO_IMPORT_ENABLED", "AUDIO_AUTO_IMPORT_INTERVAL"):
        assert key in admin, "%s 未登记，手工配置会被保存设置抹掉" % key
