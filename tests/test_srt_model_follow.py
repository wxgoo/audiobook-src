# -*- coding: utf-8 -*-
"""SrtMake 与 AI 聊天麦克风语音输入共用 TRANSCRIBE_MODEL 的行为测试。

设置页旧下拉已取消；SrtMake 工具页下拉是唯一选择点（model_select 保存），
AI 语音输入读同一配置自动跟随。start()：None/空 跟随 CONF；显式指定则尊重
并写回 CONF（PC 版 make_srt_gui.py 同步）。
"""

import threading
from unittest import mock

import pytest

from webserver import loader
from webserver.services import srt_transcribe as st


@pytest.fixture
def conf():
    c = loader.get_settings()
    old = c.get("TRANSCRIBE_MODEL")
    with mock.patch.object(c, "dumpfile", lambda: None):
        yield c
    if old is None:
        c.pop("TRANSCRIBE_MODEL", None)
    else:
        c["TRANSCRIBE_MODEL"] = old


def _start_capture_model(explicit=None):
    """启动 start() 并把 _worker 替换为捕获函数，返回实际生效的 model。

    注意：不要 patch threading.Thread——st.threading 就是全局 threading 模块，
    patch 它会让 mock 自身（内部用到 threading）递归爆炸。
    """
    captured = {}
    done = threading.Event()

    def fake_worker(books, model, *args, **kwargs):
        captured["model"] = model
        done.set()

    with mock.patch.object(st, "available", return_value=True), \
         mock.patch.object(st, "_worker", fake_worker):
        ok, msg = st.start([{"book_id": 1, "title": "t", "audio_dir": "/tmp/x"}],
                           model=explicit)
        assert ok, msg
        assert done.wait(5), "worker 线程未执行"
    st._stop = threading.Event()  # 复位
    st._snapshot = {}
    st._thread = None
    return captured["model"]  # _worker args: (books, model, lang, ...)


class TestStartModelFollowsSetting:
    def test_none_follows_conf(self, conf):
        conf["TRANSCRIBE_MODEL"] = "small"
        assert _start_capture_model(explicit=None) == "small"

    def test_empty_string_follows_conf(self, conf):
        conf["TRANSCRIBE_MODEL"] = "medium"
        assert _start_capture_model(explicit="") == "medium"

    def test_conf_missing_falls_back_base(self, conf):
        conf.pop("TRANSCRIBE_MODEL", None)
        assert _start_capture_model(explicit=None) == "base"

    def test_explicit_model_respected_and_saved(self, conf):
        conf["TRANSCRIBE_MODEL"] = "small"
        assert _start_capture_model(explicit="medium") == "medium"
        assert conf["TRANSCRIBE_MODEL"] == "medium"  # AI 语音输入同步跟随

    def test_large_normalized_and_saved(self, conf):
        assert _start_capture_model(explicit="large") == "large-v3"
        assert conf["TRANSCRIBE_MODEL"] == "large-v3"

    def test_bogus_model_falls_back_and_saved(self, conf):
        conf["TRANSCRIBE_MODEL"] = "small"
        assert _start_capture_model(explicit="bogus") == "base"
        assert conf["TRANSCRIBE_MODEL"] == "base"

    def test_same_as_conf_no_rewrite(self, conf):
        conf["TRANSCRIBE_MODEL"] = "small"
        assert _start_capture_model(explicit="small") == "small"
        assert conf["TRANSCRIBE_MODEL"] == "small"


class TestModelSelect:
    def test_select_saves_conf(self, conf):
        ok, msg = st.model_select("small")
        assert ok and conf["TRANSCRIBE_MODEL"] == "small"

    def test_select_normalizes_large(self, conf):
        ok, _ = st.model_select("large")
        assert ok and conf["TRANSCRIBE_MODEL"] == "large-v3"

    def test_select_rejects_unknown(self, conf):
        conf["TRANSCRIBE_MODEL"] = "base"
        ok, _ = st.model_select("bogus")
        assert not ok and conf["TRANSCRIBE_MODEL"] == "base"

    def test_current_model_reads_conf(self, conf):
        conf["TRANSCRIBE_MODEL"] = "medium"
        assert st.current_model() == "medium"
