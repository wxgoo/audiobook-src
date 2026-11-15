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
    """被忽略的构建副产物要被归类成 ignored（而不是从清单里凭空消失）。

    这里验证的是**生成器的分类规则**，不绑定某一次具体清单的状态：
    当前仓库的清单里 ignored 可能是空的（本次没动到那些副产物），
    但只要路径被 classify 成 ignored，它就不该进 dist_files / dist_deleted。
    """
    gen = _generator()
    ignored = gen.classify(LICENSES)
    assert ignored == "ignored", "LICENSES 应被明确忽略"
    assert gen.classify(LICENSES) != "dist", "LICENSES 不能进 dist_files"

    d = _manifest()
    # 清单里的 ignored 条目（若有）不得同时出现在投递列表里
    listed = set(d.get("changed", {}).get("ignored", []))
    delivered = set(_all_delivery_paths(d))
    assert not (listed & delivered), "ignored 的路径不该同时被投递：%s" % (listed & delivered)


def test_manifest_delivery_paths_pass_allowlist_and_blocks_are_explicit():
    """清单的投递路径必须全过消费端白名单；blocking 只在「真的改了镜像级文件」时出现。

    注意：本次清单**允许**是 blocking 的（改了 Dockerfile / compose 时就是如此，
    语义是「必须重建镜像」而不是「清单坏了」）。所以这里不再断言 hotfixable 必须为真，
    改为断言：投递路径全部合法，且 blocking 为真时原因必须写清楚。
    """
    d = _manifest()
    paths = _all_delivery_paths(d)
    assert paths, "清单里没有任何可更新文件，等于没发版本"
    bad = [p for p in paths if not is_allowed(p)]
    assert not bad, "清单含消费端不允许在线替换的路径：%s" % bad

    blocking = d.get("changed", {}).get("blocking", [])
    if blocking:
        # 镜像级变更 → 必须明确告知用户「要重建镜像」，不能悄悄显示成可页内更新
        assert d.get("hotfixable") is False, "有 blocking 文件时不该标成可热更"
        reason = str(d.get("reason") or "")
        assert "IMAGE_TAG" in reason or "docker compose" in reason, \
            "blocking 时的原因必须写清重新部署怎么做：%r" % reason
    else:
        assert d.get("hotfixable") is True
        if d.get("dist_files") or d.get("dist_deleted"):
            assert d.get("dist_hotfixable") is True
            assert d.get("requires_dist") is True
