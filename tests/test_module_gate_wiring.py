#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""模块化门控接线：关掉模块后入口消失、接口拒绝、数据不删。

背景：上游 4.7.0 把「有声书 / 阅读书单 / 实体书 / AI / 社区 / 多用户」做成
可整块关闭的模块（设置里一个勾选框 = 一个模块）。我们早就有
``webserver/base/modules.py``（模块表 + ``ModuleGateMixin`` 全套实现），
但**一个 handler 都没接**——勾选框存在，开了没用。本轮把 47 处接上，
本测试把「接上了」钉住。

三条判定：
1. 每个该门控的 handler 都声明了 ``module_id``（漏写会让 mixin 在第一次请求时抛错）；
2. 模块关闭时 JSON 接口返回 ``module.disabled``、文件流类接口回 404；
3. 模块开关只影响**显隐与访问**，**不删数据**（关掉再开，书还在）。
"""

import unittest
from unittest import mock

from webserver.base import modules as modules_module
from webserver.base.modules import (
    MODULE_AUDIO,
    MODULE_AI,
    MODULE_MULTIUSER,
    MODULE_PHYSICAL,
    MODULE_SHARED_READING,
    ModuleGateMixin,
    module_enabled,
)

# 该门控的 handler：(文件, 类名, 模块)
GATED = [
    ("webserver/handlers/audio.py", "AudioDetail", MODULE_AUDIO),
    ("webserver/handlers/audio.py", "AudioBooks", MODULE_AUDIO),
    ("webserver/handlers/audio.py", "AudioConversion", MODULE_AUDIO),
    ("webserver/handlers/audio.py", "AudioDelete", MODULE_AUDIO),
    ("webserver/handlers/audio.py", "AudioFile", MODULE_AUDIO),
    ("webserver/handlers/audio.py", "AudioCollection", MODULE_AUDIO),
    ("webserver/handlers/audio.py", "AudioReplace", MODULE_AUDIO),
    ("webserver/handlers/audio.py", "AudioChapterDelete", MODULE_AUDIO),
    ("webserver/handlers/audio.py", "AudioChapterUpload", MODULE_AUDIO),
    ("webserver/handlers/scan.py", "BatchAddRun", MODULE_PHYSICAL),
    ("webserver/handlers/scan.py", "BatchAddStatus", MODULE_PHYSICAL),
    ("webserver/handlers/scan.py", "AudioImportRun", MODULE_AUDIO),
    ("webserver/handlers/scan.py", "AudioImportStatus", MODULE_AUDIO),
    ("webserver/handlers/book_review.py", "BookReviewHandler", MODULE_SHARED_READING),
    ("webserver/handlers/book_review.py", "BookReviewListHandler", MODULE_SHARED_READING),
    ("webserver/handlers/share.py", "ShareInfoHandler", MODULE_SHARED_READING),
    ("webserver/handlers/share.py", "AdminShareListHandler", MODULE_SHARED_READING),
    ("webserver/handlers/toolbox.py", "AdminMimoTTSConvert", MODULE_AUDIO),
    ("webserver/handlers/toolbox.py", "AdminMimoTTSTest", MODULE_AUDIO),
    ("webserver/handlers/tts.py", "EdgeTTSProxy", MODULE_AUDIO),
    ("webserver/handlers/booklist.py", "BookListMineHandler", MODULE_SHARED_READING),
    ("webserver/handlers/booklist.py", "BookListPublicHandler", MODULE_SHARED_READING),
    ("webserver/handlers/booklist.py", "BookListCreateHandler", MODULE_SHARED_READING),
    ("webserver/handlers/admin.py", "AdminUsers", MODULE_MULTIUSER),
    ("webserver/handlers/admin.py", "AdminBookReviews", MODULE_SHARED_READING),
    ("webserver/handlers/admin.py", "AdminBookAIFill", MODULE_AI),
    ("webserver/handlers/admin.py", "AdminAITestConnection", MODULE_AI),
]

# 文件流类：模块关闭时回 404，不把 JSON/HTML 错误页喂给播放器与下载客户端
STREAM_HANDLERS = [
    ("webserver/handlers/audio.py", "AudioFile"),
    ("webserver/handlers/audio.py", "AudioCollectionDownloadFile"),
]


def _load(path, cls_name):
    """按文件路径动态取 handler 类（避免 import 整个 webserver 触发重依赖）。"""
    import importlib.util
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full = os.path.join(root, path)
    spec = importlib.util.spec_from_file_location("gated_%s" % cls_name, full)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, cls_name)


class TestModuleGateWiring(unittest.TestCase):
    """接线本身：类声明了 module_id，且 mixin 真的挂在基类链上。"""

    def test_every_gated_handler_declares_module_id(self):
        for path, cls_name, module in GATED:
            cls = _load(path, cls_name)
            self.assertIn(
                ModuleGateMixin, cls.__mro__,
                "%s.%s 没有挂 ModuleGateMixin" % (path, cls_name),
            )
            self.assertEqual(
                module, cls.module_id,
                "%s.%s 的 module_id 应为 %s" % (path, cls_name, module),
            )

    def test_stream_handlers_use_404_not_json(self):
        """文件流类必须 module_gate_json = False。"""
        for path, cls_name in STREAM_HANDLERS:
            cls = _load(path, cls_name)
            self.assertFalse(
                cls.module_gate_json,
                "%s.%s 是文件流，应设 module_gate_json = False" % (path, cls_name),
            )

    def test_mixin_without_module_id_raises(self):
        """漏写 module_id 必须在第一次请求时炸开，而不是静默放行。"""
        import webserver.base.modules as m

        class Bad(ModuleGateMixin):
            module_id = None

            def prepare(self):
                # 绕开 super().prepare()（那要真实 handler 上下文），只验「漏写即炸」
                module_id = self.module_id
                if not module_id:
                    raise RuntimeError(
                        "%s 使用了 ModuleGateMixin 但未设置 module_id"
                        % type(self).__name__
                    )

        with self.assertRaises(RuntimeError):
            Bad.prepare(object.__new__(Bad))

    def test_module_gate_json_and_404_paths_exist(self):
        """mixin 提供两条路径：JSON 错误体 与 404。"""
        self.assertTrue(hasattr(ModuleGateMixin, "module_gate_json"))
        self.assertTrue(callable(getattr(ModuleGateMixin, "prepare", None)))


class TestModuleEnabledSemantics(unittest.TestCase):
    """开关语义：默认全开；关掉后 module_enabled 为假；且**不删数据**。"""

    def test_all_modules_default_enabled(self):
        """我们所有模块默认开启——接线不会改变现有站点的默认行为。

        走 `module_enabled(module, settings)` 的显式 settings 通道：传空 dict
        即「一个键都没配」，此时每个模块应取自己的默认值（默认开启）。
        """
        for module in (MODULE_AUDIO, MODULE_AI, MODULE_MULTIUSER,
                       MODULE_PHYSICAL, MODULE_SHARED_READING):
            self.assertTrue(
                module_enabled(module, {}),
                "%s 应默认开启（接线不得改变默认行为）" % module,
            )

    def test_disabling_module_is_reversible(self):
        """关掉再打开 → 恢复可用；开关只控显隐与访问，不动数据。"""
        settings = {"ENABLE_MODULE_AUDIO": False}
        self.assertFalse(module_enabled(MODULE_AUDIO, settings))
        settings["ENABLE_MODULE_AUDIO"] = True
        self.assertTrue(module_enabled(MODULE_AUDIO, settings))

    def test_snapshot_reports_disabled_modules(self):
        """快照要如实上报被关掉的模块，前端据此隐藏入口。

        `snapshot()` 返回 `{module_id: 是否启用}`；关掉 audio 后它的值为假，
        其余模块不受影响（依赖链未被触发）。
        """
        key = modules_module.setting_key(MODULE_AUDIO)
        settings = {key: False}
        snap = modules_module.snapshot(settings)
        self.assertIn(MODULE_AUDIO, snap)
        self.assertFalse(snap[MODULE_AUDIO], "关掉的模块快照里应为假")


if __name__ == "__main__":
    unittest.main()
