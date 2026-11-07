#!/usr/bin/env python3
"""backup_run.py 三个 fail-closed 修复的回归测试（build.20 复审，2026-11-07）。

钉住的不变量（与模块 docstring 第 19 行一致）：
1. 快照里只要有文件没备上（磁盘满/权限），整份快照判失败并清理，
   绝不顶替旧的好快照（原实现只记 warning 退码 2，残缺快照反而被
   保留策略当「最新一份」优先保护）；
2. 重跑同一 --timestamp 报「目标已存在」时，异常路径不得 rmtree
   已存在的旧快照（原实现恰好会删）；
3. manifest 先写临时文件再原子替换，写入失败时本次 db/files 产物
   全部清理、退出码 3（原实现留半截 JSON + 未文档化的退出码 1）。

全部用临时目录与内存桩，不碰真实数据、不要求 root。
"""
import importlib.util
import os
import sqlite3

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "backup_run",
    os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))),
                 "scripts", "backup_run.py"))
br = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(br)


@pytest.fixture()
def env(tmp_path):
    data = tmp_path / "data"
    (data / "books" / "library").mkdir(parents=True)
    (data / "books" / "epub").mkdir(parents=True)
    conn = sqlite3.connect(str(data / "books" / "calibre-webserver.db"))
    conn.execute("CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT)")
    conn.commit()
    conn.close()
    conn = sqlite3.connect(str(data / "books" / "library" / "metadata.db"))
    conn.execute("CREATE TABLE books (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    (data / "books" / "epub" / "某书.epub").write_bytes(b"EPUB" * 1000)
    return str(data), str(tmp_path / "bak")


def run(env, ts, monkeypatch=None, patch=None):
    if monkeypatch is not None and patch:
        target, fake = patch
        monkeypatch.setattr(br, target, fake, raising=True)
    return br.main(["--data", env[0], "--backup", env[1],
                    "--timestamp", ts, "--min-free-gb", "0"])


def test_happy_path(env):
    rc = run(env, "20261107-120000")
    assert rc == 0
    bak = env[1]
    assert os.path.isfile(os.path.join(bak, "manifests", "backup-20261107-120000.json"))
    assert os.path.isfile(os.path.join(
        bak, "files", "20261107-120000", "books", "epub", "某书.epub"))
    assert os.path.isfile(os.path.join(bak, "db", "20261107-120000", "webserver.db"))


def test_rerun_same_timestamp_never_deletes_existing_snapshot(env):
    ts = "20261107-120000"
    assert run(env, ts) == 0
    # 旧实现：重跑报「目标已存在」后，异常路径 rmtree 把旧快照删掉
    assert run(env, ts) == 3
    assert os.path.isfile(os.path.join(
        env[1], "files", ts, "books", "epub", "某书.epub"))


def test_partial_snapshot_fails_closed_and_is_cleaned(env, monkeypatch):
    # 刷新 mtime 确保走复制路径（硬链接要求 size+mtime 完全一致）
    p = os.path.join(env[0], "books", "epub", "某书.epub")
    with open(p, "ab") as f:
        f.write(b"x")
    with open(os.path.join(env[0], "books", "epub", "新文件.txt"), "w") as f:
        f.write("new")

    orig = br._copy_file

    def bad_copy(src, dst, st, root_owned):
        if src.endswith("新文件.txt"):
            raise OSError(28, "ENOSPC simulated")
        return orig(src, dst, st, root_owned)

    ts = "20261107-130000"
    rc = run(env, ts, monkeypatch, patch=("_copy_file", bad_copy))
    assert rc == 3
    assert not os.path.exists(os.path.join(env[1], "files", ts))
    assert not os.path.exists(os.path.join(env[1], "manifests",
                                           "backup-%s.json" % ts))


def test_manifest_write_failure_fails_closed(env, monkeypatch):
    def bad_write(path, payload):
        raise OSError(28, "ENOSPC simulated (manifest)")

    ts = "20261107-140000"
    rc = run(env, ts, monkeypatch, patch=("_write_json_atomic", bad_write))
    assert rc == 3
    assert not os.path.exists(os.path.join(env[1], "files", ts))
    assert not os.path.exists(os.path.join(env[1], "db", ts))
    leftovers = [f for f in os.listdir(os.path.join(env[1], "manifests"))
                 if f.endswith(".tmp")]
    assert leftovers == []


def test_failed_db_backup_leaves_no_stray_file(env, monkeypatch):
    orig_connect = br.sqlite3.connect

    def bad_connect(*a, **k):
        if "calibre-webserver.db" in str(a[0] or ""):
            raise br.sqlite3.OperationalError("disk I/O error simulated")
        return orig_connect(*a, **k)

    ts = "20261107-150000"
    monkeypatch.setattr(br.sqlite3, "connect", bad_connect)
    rc = run(env, ts)
    assert rc == 2  # db 失败=警告；文件快照仍成功
    assert not os.path.exists(os.path.join(env[1], "db", ts, "webserver.db"))
    assert os.path.isfile(os.path.join(env[1], "db", ts, "calibre-metadata.db"))


def test_failed_run_never_triggers_retention(env, monkeypatch):
    # 先放两份「旧快照」在 files/ 下，失败运行不得清理它们
    for older in ("20261105-120000", "20261106-120000"):
        d = os.path.join(env[1], "files", older)
        os.makedirs(d)
        with open(os.path.join(d, "marker.txt"), "w") as f:
            f.write(older)

    p = os.path.join(env[0], "books", "epub", "某书.epub")
    with open(p, "ab") as f:
        f.write(b"x")

    orig = br._copy_file

    def bad_copy(src, dst, st, root_owned):
        if src.endswith("某书.epub"):
            raise OSError(28, "ENOSPC simulated")
        return orig(src, dst, st, root_owned)

    rc = run(env, "20261107-160000", monkeypatch, patch=("_copy_file", bad_copy))
    assert rc == 3
    for older in ("20261105-120000", "20261106-120000"):
        assert os.path.isfile(os.path.join(env[1], "files", older, "marker.txt"))
