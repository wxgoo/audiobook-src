# -*- coding: UTF-8 -*-
"""发布清单里的每个投递路径，都必须能被消费端 version_check.is_allowed() 接受。

r39 事故复盘：生成器曾用 DIST_EXACT 单方面放行 app/dist/_nuxt/LICENSES 进
dist_files，但消费端只认 DIST_SUFFIX 后缀白名单。用户点「立即更新」时
apply() 在下载任何文件之前抛「发布清单含不允许在线替换的路径」，整次更新卡死。

只校验文件 sha256 是抓不到这个的——文件本身没问题，是路径不被允许。
本测试把「清单路径 ⊆ 消费端白名单」钉成硬门禁，且直接 import 消费端真实实现，
不复制一份判定逻辑，避免两边再次漂移。
"""
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from webserver.services import version_check as vc  # noqa: E402
from webserver.services.version_check import is_allowed  # noqa: E402

MANIFEST = os.path.join(ROOT, "update", "manifest.json")
GENERATOR = os.path.join(ROOT, "scripts", "gen-update-manifest.py")
LICENSES = "app/dist/_nuxt/LICENSES"


def _manifest():
    with open(MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def _generator():
    spec = importlib.util.spec_from_file_location("gen_update_manifest_under_test", GENERATOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _all_delivery_paths(d):
    paths = [x["path"] for x in d.get("files", [])]
    paths += [x["path"] for x in d.get("dist_files", [])]
    paths += list(d.get("dist_deleted", []))
    return paths


def test_every_delivery_path_passes_consumer_allowlist():
    """核心门禁：清单里任何一个会被下载/删除的路径，都要过消费端 is_allowed。"""
    paths = _all_delivery_paths(_manifest())
    assert paths, "清单里没有任何可更新文件，等于没发版本"
    bad = [p for p in paths if not is_allowed(p)]
    assert not bad, "清单含消费端不允许在线替换的路径：%s" % bad


def test_consumer_rejects_licenses():
    """固化事实：无后缀的 LICENSES 不在消费端白名单里，别再想放行它。"""
    assert is_allowed(LICENSES) is False


def test_generator_never_puts_non_allowlisted_dist_into_dist_files():
    """生成器不得再把白名单外的 dist 路径归类为 dist（投递单元）。"""
    gen = _generator()
    for p in (LICENSES, "app/dist/_nuxt/whatever", "app/dist/foo.exe",
              "app/dist/_nuxt/evil.sh"):
        assert gen.classify(p) != "dist", "%s 不能进 dist_files" % p
        assert gen.classify(p) == "ignored", "%s 应被明确忽略" % p


def test_generator_and_consumer_allowlists_are_identical():
    """两边白名单逐字一致；生成器放行的每个后缀，消费端都必须认。"""
    gen = _generator()
    assert gen.DIST_PREFIX == vc.DIST_PREFIX
    assert tuple(gen.DIST_SUFFIX) == tuple(vc.DIST_SUFFIX)
    for ext in gen.DIST_SUFFIX:
        p = "app/dist/_nuxt/x" + ext
        assert gen.classify(p) == "dist"
        assert is_allowed(p), "生成器放行但消费端拒绝：%s" % p


def test_no_dist_exact_escape_hatch():
    """r39 的单方面放行口子必须彻底消失，防止有人「顺手」恢复。"""
    gen = _generator()
    assert not hasattr(gen, "DIST_EXACT"), (
        "生成器不得再有任何绕过消费端白名单的特例常量")


def test_ignored_paths_are_recorded_not_silently_dropped():
    """被忽略的构建副产物要在 changed.ignored 里留痕，方便核对，而不是悄悄消失。"""
    d = _manifest()
    ignored = d.get("changed", {}).get("ignored", [])
    assert LICENSES in ignored, "LICENSES 应记录在 changed.ignored，而非从清单里凭空消失"
    assert LICENSES not in [x["path"] for x in d.get("dist_files", [])]
    assert LICENSES not in list(d.get("dist_deleted", []))


def test_manifest_still_hotfixable():
    """修清单不能把整次修订顶成「必须重新部署」。"""
    d = _manifest()
    assert d.get("hotfixable") is True
    assert not d.get("changed", {}).get("blocking"), "不该出现 blocking 文件"
    if d.get("dist_files") or d.get("dist_deleted"):
        assert d.get("dist_hotfixable") is True
        assert d.get("requires_dist") is True
