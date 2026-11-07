# -*- coding: utf-8 -*-
"""版本锁（防反弹）回归测试。

背景：本 fork 自本版起把运行期版本统一为 `4.6.0-build.21`（上游已发布 tag 4.6.0
+ 第 21 次本地构建），旧 `4.8.x` 号段封存。这里的用例把这条约定钉死：任何
回退（写回 4.8.x、写回裸 4.6.0）、被构建参数顶成空串、Dockerfile/Makefile
守卫被删除，都必须失败。

失败时打印的说明是「防版本回退 / 防被交付标签覆盖的保护，不是普通测试失败」，
不要通过删除或放宽断言来让它变绿。
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts" / "check-version-lock.py"
LOCK = "4.6.0-build.21"
FILES = [
    "webserver/version.py",
    "docker-compose.yml",
    "Dockerfile",
    "app/package.json",
    "app/package-lock.json",
    "Makefile",
]


def run(root):
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)


def make_fixture(tmp_path):
    for rel in FILES:
        src = ROOT / rel
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    return tmp_path


def mutate(root, rel, old, new):
    p = root / rel
    text = p.read_text(encoding="utf-8")
    assert old in text, "fixture 里找不到要替换的内容: %s" % old
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_repo_passes_version_lock():
    r = run(ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "版本锁检查通过" in r.stdout


def test_version_py_rollback_to_4_8_is_rejected(tmp_path):
    """回退到已封存的 4.8.x 号段必须被拦住。"""
    root = make_fixture(tmp_path)
    mutate(root, "webserver/version.py", 'VERSION = "%s"' % LOCK, 'VERSION = "v4.8.0"')
    r = run(root)
    assert r.returncode == 1, r.stdout
    assert "防版本回退" in r.stdout
    assert "补救" in r.stdout


def test_version_py_bare_upstream_tag_is_rejected(tmp_path):
    """写成不带 -build.20 的裸 4.6.0 也必须被拦住（那是上游 tag，不是我们的构建号）。"""
    root = make_fixture(tmp_path)
    mutate(root, "webserver/version.py", 'VERSION = "%s"' % LOCK, 'VERSION = "4.6.0"')
    r = run(root)
    assert r.returncode == 1, r.stdout
    assert "防版本回退" in r.stdout


def test_empty_git_version_is_rejected(tmp_path):
    root = make_fixture(tmp_path)
    mutate(root, "docker-compose.yml", 'GIT_VERSION: "%s"' % LOCK, 'GIT_VERSION: ""')
    r = run(root)
    assert r.returncode == 1, r.stdout
    assert "GIT_VERSION 为空" in r.stdout


def test_compose_mismatch_is_rejected(tmp_path):
    root = make_fixture(tmp_path)
    mutate(root, "docker-compose.yml", 'GIT_VERSION: "%s"' % LOCK, 'GIT_VERSION: "4.6.0"')
    r = run(root)
    assert r.returncode == 1, r.stdout
    assert "docker-compose.yml" in r.stdout
    assert "GIT_VERSION" in r.stdout


def test_package_json_rollback_is_rejected(tmp_path):
    root = make_fixture(tmp_path)
    mutate(root, "app/package.json", '"version": "%s"' % LOCK, '"version": "4.8.0"')
    r = run(root)
    assert r.returncode == 1, r.stdout
    assert "app/package.json" in r.stdout
    assert "semver" in r.stdout


def test_package_lock_mismatch_is_rejected(tmp_path):
    root = make_fixture(tmp_path)
    mutate(root, "app/package-lock.json", '"version": "%s"' % LOCK, '"version": "4.8.0"')
    r = run(root)
    assert r.returncode == 1, r.stdout
    assert "package-lock.json" in r.stdout


def test_dockerfile_empty_guard_missing_is_rejected(tmp_path):
    root = make_fixture(tmp_path)
    mutate(root, "Dockerfile",
           'if [ -z "${GIT_VERSION:-}" ]; then echo "ERROR: GIT_VERSION 为空，触发版本锁保护'
           '（见 scripts/check-version-lock.py）" >&2; exit 1; fi; \\',
           'if true; then :; fi; \\')
    r = run(root)
    assert r.returncode == 1, r.stdout
    assert "缺少「GIT_VERSION 为空则构建失败」的守卫" in r.stdout


def test_makefile_ver_guard_missing_is_rejected(tmp_path):
    root = make_fixture(tmp_path)
    mutate(root, "Makefile", "ifneq ($(strip $(VER)),$(VERSION_LOCK))", "ifeq (1,1)")
    r = run(root)
    assert r.returncode == 1, r.stdout
    assert "VER 不匹配时没有报错退出" in r.stdout
