"""前端“静默失败”回归测试。

对应故障：书列表/详情页接口失败时，错误分支调用了不存在的成员（如 this.alert），
异常被 Promise 吞掉，页面只剩空白，没有任何提示。这里用静态断言锁住修复点。
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "app" / "src"
LIST_BOOK = SRC / "pages" / "ListBook.vue"
STORE = SRC / "store" / "index.js"
LOCALES = ROOT / "app" / "locales"
OVERLAY_LOCALES = ROOT / "delivery" / "overlay" / "files" / "app" / "locales"


def test_no_this_alert_calls():
    """注入到组件上的是 $alert，this.alert 必然抛 TypeError。"""
    offenders = []
    for path in SRC.rglob("*.vue"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"this\.alert\s*\(", text):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], f"发现 this.alert( 调用：{offenders}"


def test_list_book_error_is_visible():
    text = LIST_BOOK.read_text(encoding="utf-8")
    assert "this.$alert(" in text
    assert "load_error" in text
    assert "errorText" in text


def test_list_book_has_empty_state():
    text = LIST_BOOK.read_text(encoding="utf-8")
    for key in ("listBook.empty", "listBook.loadFailed", "listBook.retry"):
        assert key in text, f"ListBook.vue 缺少文案 key：{key}"


def test_alert_mutation_ignores_empty_message():
    text = STORE.read_text(encoding="utf-8")
    assert re.search(r"if\s*\(!v\s*\|\|\s*!v\.msg\)\s*\{?\s*return", text), \
        "alert mutation 缺少空文案保护"


@pytest.mark.parametrize("name", ["zh.json", "zh-TW.json", "en.json"])
def test_list_book_locale_keys(name):
    data = json.loads((LOCALES / name).read_text(encoding="utf-8"))
    section = data.get("listBook") or {}
    for key in ("empty", "loadFailed", "retry"):
        assert key in section, f"{name} 的 listBook 缺少 {key}"
    overlay = OVERLAY_LOCALES / name
    if overlay.exists():
        overlay_section = (json.loads(overlay.read_text(encoding="utf-8")).get("listBook") or {})
        for key in ("empty", "loadFailed", "retry"):
            assert key in overlay_section, f"delivery/overlay 的 {name} 缺少 listBook.{key}"


def test_vue_method_refs_are_clean():
    node = shutil.which("node")
    if not node:
        pytest.skip("node 不可用")
    script = ROOT / "app" / "scripts" / "check-vue-method-refs.js"
    result = subprocess.run(
        [node, str(script), "--strict"],
        cwd=str(ROOT / "app"),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


LIST_META = SRC / "pages" / "ListMeta.vue"
SYSLOG = SRC / "pages" / "admin" / "syslog.vue"
TOOLBOX = SRC / "pages" / "toolbox" / "_id.vue"
FIRST_LOAD_PAGES = [
    (LIST_BOOK, "this.init("),
    (LIST_META, "this.init("),
    (SYSLOG, "this.fetchLog("),
    (TOOLBOX, "this.loadTool("),
]


@pytest.mark.parametrize("path,marker", FIRST_LOAD_PAGES,
                         ids=["ListBook", "ListMeta", "admin-syslog", "toolbox-id"])
def test_first_load_fetches_on_mount(path, marker):
    """静态 SPA 产物里 asyncData 只在构建期执行；首屏直入/强刷必须由 mounted 补一次取数。

    没有这个入口时，页面壳正常、Console 干净、Network 里没有任何取书请求。
    """
    text = path.read_text(encoding="utf-8")
    assert re.search(r"\bmounted\s*\(\)\s*\{", text), f"{path.name} 缺少 mounted 钩子"
    idx = text.index("mounted() {")
    mounted = text[idx:idx + 600]
    assert marker in mounted, f"{path.name} 的 mounted 没有触发 {marker}，首屏不会取数"


@pytest.mark.parametrize("path,marker", FIRST_LOAD_PAGES,
                         ids=["ListBook", "ListMeta", "admin-syslog", "toolbox-id"])
def test_first_load_does_not_double_fetch(path, marker):
    """服务端已取到数据（ssr_loaded）时 mounted 不应再次请求。"""
    text = path.read_text(encoding="utf-8")
    assert "ssr_loaded" in text, f"{path.name} 缺少 ssr_loaded 标记"
    assert re.search(r"!\s*this\.ssr_loaded", text), \
        f"{path.name} 的 mounted 没有用 ssr_loaded 去重"
