#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""有声书导入目录轮询的契约测试（r37）。

不碰真实 DB / Calibre：用 monkeypatch 替换指纹、互斥检查与触发动作，
只验证调度语义；fingerprint() 本身用 tmp_path 的真实小文件测。
"""

import os

import pytest

from webserver.services import audio_auto_import as mod


@pytest.fixture
def svc(monkeypatch, tmp_path):
    mod.AudioAutoImportService._instance = None
    s = mod.AudioAutoImportService()
    monkeypatch.setitem(mod.CONF, "IMPORT_BY_INOTIFY", True)
    monkeypatch.setitem(mod.CONF, "AUDIO_AUTO_IMPORT_ENABLED", True)
    monkeypatch.setattr(mod, "audio_import_dir", lambda: str(tmp_path))
    return s


def _stub(svc, monkeypatch, fps, can=True):
    """把一轮轮指纹按序喂给 tick，并记录触发次数。"""
    seq = iter(fps)
    calls = []
    monkeypatch.setattr(mod, "fingerprint", lambda root: (next(seq), 1))
    monkeypatch.setattr(mod.AudioAutoImportService, "_can_import", staticmethod(lambda: can))
    monkeypatch.setattr(
        mod.AudioAutoImportService, "_trigger_import", staticmethod(lambda: calls.append(1))
    )
    return calls


# ---------- fingerprint ----------

def test_fingerprint_missing_dir(tmp_path):
    assert mod.fingerprint(str(tmp_path / "nope")) == (None, 0)


def test_fingerprint_only_audio_matters(tmp_path):
    root = tmp_path / "audiobooks"
    book = root / "哈利波特与凤凰社"
    book.mkdir(parents=True)
    (book / "001.mp3").write_bytes(b"a" * 100)

    fp1, n1 = mod.fingerprint(str(root))
    assert n1 == 1 and fp1

    # 群晖缩略图目录、封面、字幕、临时文件都不该让指纹变化
    (root / "@eaDir").mkdir()
    (root / "@eaDir" / "thumb.jpg").write_bytes(b"x")
    (book / "cover.jpg").write_bytes(b"cover")
    (book / "001.srt").write_text("subtitle")
    (book / ".~tmp.mp3.part").write_bytes(b"partial")
    assert mod.fingerprint(str(root)) == (fp1, n1)

    # 新音频 / 已有音频变大 → 指纹变化
    (book / "002.m4a").write_bytes(b"b" * 50)
    fp2, n2 = mod.fingerprint(str(root))
    assert fp2 != fp1 and n2 == 1

    (book / "001.mp3").write_bytes(b"a" * 200)
    assert mod.fingerprint(str(root))[0] != fp2


def test_fingerprint_root_audio(tmp_path):
    """音频直接扔在 audiobooks/ 根目录（AudioBookImporter 的兜底场景）。"""
    root = tmp_path / "audiobooks"
    root.mkdir()
    (root / "single.wav").write_bytes(b"x" * 10)
    fp, n = mod.fingerprint(str(root))
    assert fp and n == 0


# ---------- tick 调度 ----------

def test_two_stable_rounds_then_trigger_once(svc, monkeypatch):
    calls = _stub(svc, monkeypatch, ["A", "A", "A", "A"])
    assert svc.tick() is False          # 首轮只记录
    assert svc.tick() is True           # 稳定第 2 轮，触发
    assert calls == [1]
    assert svc.tick() is False          # 指纹没变，不重复触发
    assert svc.tick() is False
    assert calls == [1]


def test_change_resets_stability(svc, monkeypatch):
    """拷贝途中指纹变化，不能提前触发。"""
    calls = _stub(svc, monkeypatch, ["A", "B", "B", "B"])
    assert svc.tick() is False
    assert svc.tick() is False          # 变化 → 稳定计数归 1
    assert svc.tick() is True           # B 稳定第 2 轮
    assert svc.tick() is False
    assert calls == [1]


def test_busy_does_not_consume_change(svc, monkeypatch):
    """导入任务忙时跳过，但下一轮空闲仍要补触发（不「消费」这次变化）。"""
    calls = _stub(svc, monkeypatch, ["A", "A", "A"])
    busy = [True]
    monkeypatch.setattr(
        mod.AudioAutoImportService, "_can_import", staticmethod(lambda: not busy[0])
    )
    assert svc.tick() is False          # 首轮只记录稳定度
    assert svc.tick() is False          # 稳定了，但导入任务忙
    assert calls == []
    busy[0] = False
    assert svc.tick() is True           # 下一轮补上，没有把变化「消费」掉
    assert calls == [1]


def test_missing_dir_resets(svc, monkeypatch):
    calls = _stub(svc, monkeypatch, [None, "A", "A"])
    monkeypatch.setattr(mod, "fingerprint", lambda root: (None, 0))
    assert svc.tick() is False
    monkeypatch.setattr(mod, "fingerprint", lambda root: ("A", 1))
    monkeypatch.setattr(mod.AudioAutoImportService, "_can_import", staticmethod(lambda: True))
    monkeypatch.setattr(
        mod.AudioAutoImportService, "_trigger_import", staticmethod(lambda: calls.append(1))
    )
    assert svc.tick() is False          # 稳定计数从头开始
    assert svc.tick() is True
    assert calls == [1]


def test_disabled_switch(svc, monkeypatch):
    calls = _stub(svc, monkeypatch, ["A", "A"])
    monkeypatch.setitem(mod.CONF, "IMPORT_BY_INOTIFY", False)
    assert svc.tick() is False
    assert svc.tick() is False
    assert calls == []

    monkeypatch.setitem(mod.CONF, "IMPORT_BY_INOTIFY", True)
    monkeypatch.setitem(mod.CONF, "AUDIO_AUTO_IMPORT_ENABLED", False)
    assert svc.tick() is False
    assert calls == []


def test_interval_clamped(monkeypatch):
    monkeypatch.setitem(mod.CONF, "AUDIO_AUTO_IMPORT_INTERVAL", 1)
    assert mod.AudioAutoImportService.interval() == mod.MIN_INTERVAL
    monkeypatch.setitem(mod.CONF, "AUDIO_AUTO_IMPORT_INTERVAL", "bad")
    assert mod.AudioAutoImportService.interval() == mod.DEFAULT_INTERVAL
    monkeypatch.setitem(mod.CONF, "AUDIO_AUTO_IMPORT_INTERVAL", 300)
    assert mod.AudioAutoImportService.interval() == 300


def test_start_stop_idempotent(svc):
    svc.start()
    svc.start()
    assert svc._running and svc._thread is not None
    svc.stop()
    svc.stop()
    assert not svc._running and svc._thread is None
