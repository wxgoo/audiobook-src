#!/usr/bin/env python3
"""在线更新「允许替换哪些路径」的边界测试（webserver/services/version_check.py）。

这段逻辑是安全边界：清单来自网络（Gitee raw），一旦允许越权路径，
等价于把容器内任意文件交给远端覆盖。r13 起额外允许 `app/dist/**` 的静态产物，
所以要同时锁住两件事：

  1. 前端产物只认 app/dist/ 下、且后缀在白名单里的文件；
  2. 任何 `..`、反斜杠、绝对路径、非静态后缀（.sh / .py / .conf）一律拒绝。

直接按文件加载模块，绕开 webserver.services 包的 __init__（那里会 import
models，测试机不一定装了 social_sqlalchemy，与本模块无关）。
"""
import importlib.util
import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "webserver", "services", "version_check.py")


def _load():
    # version_check 只依赖 webserver.version.VERSION，用桩替掉，避免拉起整个 models
    if "webserver" not in sys.modules:
        pkg = types.ModuleType("webserver")
        pkg.__path__ = [os.path.join(ROOT, "webserver")]
        sys.modules["webserver"] = pkg
    ver = types.ModuleType("webserver.version")
    ver.VERSION = "4.6.0-build.27"
    sys.modules["webserver.version"] = ver
    spec = importlib.util.spec_from_file_location("vc_under_test", TARGET)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


VC = _load()


class TestAllowedPaths(unittest.TestCase):

    def test_python_hotfix_paths_allowed(self):
        for p in ("server.py", "webserver/handlers/book.py",
                  "webserver/base/category_icons.py"):
            self.assertTrue(VC.is_allowed(p), p)

    def test_dist_static_files_allowed(self):
        for p in ("app/dist/index.html", "app/dist/_nuxt/abc123.js",
                  "app/dist/_nuxt/css/abc123.css", "app/dist/200.html",
                  "app/dist/logo/favicon.ico", "app/dist/fonts/x.woff2"):
            self.assertTrue(VC.is_allowed(p), p)

    def test_traversal_rejected(self):
        for p in ("app/dist/../../webserver/server.py",
                  "../server.py", "/etc/passwd", "app\\dist\\index.html"):
            self.assertFalse(VC.is_allowed(p), p)

    def test_non_static_suffix_in_dist_rejected(self):
        # 前端目录里不该出现可执行脚本/服务端代码，出现即视为清单被污染
        for p in ("app/dist/evil.sh", "app/dist/run.py", "app/dist/nginx.conf",
                  "app/dist/x.php"):
            self.assertFalse(VC.is_allowed(p), p)

    def test_source_and_config_rejected(self):
        for p in ("app/src/pages/index.vue", "app/package.json",
                  "conf/nginx/mybooks.conf", "docker/start.sh", "Dockerfile"):
            self.assertFalse(VC.is_allowed(p), p)


class TestDistConstants(unittest.TestCase):

    def test_dist_prefix_matches_code_root_layout(self):
        # CODE_ROOT 是 /var/www/mybooks（容器内），dist 就在它下面
        self.assertEqual(VC.DIST_PREFIX, "app/dist/")
        self.assertTrue(VC.CODE_ROOT.endswith("/var/www/mybooks") or os.path.isdir(VC.CODE_ROOT))

    def test_suffix_whitelist_covers_entry_assets(self):
        for suffix in (".js", ".css", ".html", ".woff2", ".ico"):
            self.assertIn(suffix, VC.DIST_SUFFIX)


if __name__ == "__main__":
    unittest.main()
