# -*- coding: utf-8 -*-
"""SrtMake 模型删除的真实结果校验。

背景（NAS 实测）：点删除提示"已删除，释放 927.4 MB"，但按钮没变成"下载"、
再点报"尚未下载"。根因是 rmtree(ignore_errors=True) 吞掉了删除错误仍回报成功。
本测试锁定：删除必须真实校验目录已清空，残留要如实报失败。
"""

import os
from unittest import mock

import pytest

from webserver.services import srt_transcribe as st


@pytest.fixture
def fake_model_dir(tmp_path, monkeypatch):
    """把一个临时目录伪装成 small 的 HF 缓存目录，并写入可读文件。"""
    d = tmp_path / "models--Systran--faster-whisper-small"
    d.mkdir()
    blob = d / "blobs"
    blob.mkdir()
    (blob / "model.bin").write_bytes(b"x" * 4096)
    monkeypatch.setattr(st, "_hf_model_dir", lambda m: d)
    monkeypatch.setattr(st, "is_running", lambda: False)
    return d


def test_delete_ok_when_dir_gone(fake_model_dir):
    ok, msg = st.model_delete("small")
    assert ok, msg
    assert "已删除" in msg and "释放" in msg
    assert not fake_model_dir.exists()
    # 删除后状态应立刻变为未下载
    status = {x["model"]: x for x in st.model_status()}
    assert status["small"]["downloaded"] is False


def test_delete_reports_failure_when_files_remain(fake_model_dir, monkeypatch):
    """rmtree 被拦截（占用/权限）导致文件残留时，必须报失败而非假成功。"""
    import shutil
    real_rmtree = shutil.rmtree

    def blocked_rmtree(path, **kwargs):
        # 只删 blobs 里的文件之外的部分，模拟删不掉 model.bin
        onerror = kwargs.get("onerror")
        if onerror:
            onerror(os.rmdir, str(fake_model_dir / "blobs"),
                    OSError(13, "Permission denied"))
        # 故意不真正删除，制造残留

    monkeypatch.setattr(shutil, "rmtree", blocked_rmtree)
    ok, msg = st.model_delete("small")
    assert ok is False
    assert "删除未完成" in msg and "残留" in msg
    # 权限错误应给出可自助的 chown 指引（PUID 改动后的旧容器常见）
    assert "chown -R mybooks:mybooks" in msg
    assert "属主" in msg


def test_delete_unknown_model():
    ok, msg = st.model_delete("no-such-model")
    assert ok is False
    assert "未知模型" in msg


def test_delete_when_not_downloaded(tmp_path, monkeypatch):
    d = tmp_path / "models--Systran--faster-whisper-small"  # 不存在
    monkeypatch.setattr(st, "_hf_model_dir", lambda m: d)
    ok, msg = st.model_delete("small")
    assert ok is False
    assert "尚未下载" in msg


def test_delete_blocked_while_running(fake_model_dir, monkeypatch):
    monkeypatch.setattr(st, "is_running", lambda: True)
    ok, msg = st.model_delete("small")
    assert ok is False
    assert "转写任务进行中" in msg
