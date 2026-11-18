# -*- coding: utf-8 -*-
"""版本锁（防反弹）回归测试。

背景：本 fork 自本版起把运行期版本统一为 `4.7.0-build.08`（上游已发布 tag 4.6.0
+ 第 08 次本地构建），旧 `4.8.x` 号段封存。这里的用例把这条约定钉死：任何
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
LOCK = "4.7.0-build.08"
FILES = [
    "webserver/version.py",
    "docker-compose.yml",
    ".env.example",
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


def test_compose_image_tag_rollback_is_rejected(tmp_path):
    """compose 是纯镜像形态（无 build 段）时：镜像 tag 的构建号回退必须被拦住。

    旧形态（compose 带 build: 段）查的是 GIT_VERSION；新形态下版本由**镜像内**的
    version.py 决定，compose 不参与注入——但 image tag 仍必须指向本版构建号，
    否则用户会拉起一个旧镜像却以为自己是新版。这里把 tag 改回旧构建号，
    检查器必须拦下。
    """
    root = make_fixture(tmp_path)
    mutate(root, "docker-compose.yml",
           "ghcr.io/wxgoo/audiobooks:%s" % LOCK,
           "ghcr.io/wxgoo/audiobooks:4.6.0-build.27")
    r = run(root)
    assert r.returncode == 1, r.stdout
    assert "docker-compose.yml" in r.stdout
    assert "构建号" in r.stdout


def test_compose_image_tag_without_build_number_is_rejected(tmp_path):
    """镜像 tag 里没有构建号段 = 无法校验版本口径，必须拦下。"""
    root = make_fixture(tmp_path)
    mutate(root, "docker-compose.yml",
           "ghcr.io/wxgoo/audiobooks:%s" % LOCK,
           "ghcr.io/wxgoo/audiobooks:latest")
    r = run(root)
    assert r.returncode == 1, r.stdout
    assert "docker-compose.yml" in r.stdout


def test_compose_with_build_section_still_checks_git_version(tmp_path):
    """compose 若带 build: 段（开发者本机构建形态），GIT_VERSION 必须校验。

    两种形态都要守住：带 build 段查 GIT_VERSION，只带 image 查 tag 构建号。
    """
    root = make_fixture(tmp_path)
    p = root / "docker-compose.yml"
    text = p.read_text(encoding="utf-8")
    # 塞一个 build 段进去，且故意把 GIT_VERSION 写成旧构建号
    text = text.replace(
        "    image: ${IMAGE_TAG:-ghcr.io/wxgoo/audiobooks:%s}" % LOCK,
        "    build:\n      context: .\n      args:\n        GIT_VERSION: \"4.6.0-build.27\"\n"
        "    image: ${IMAGE_TAG:-ghcr.io/wxgoo/audiobooks:%s}" % LOCK,
        1,
    )
    p.write_text(text, encoding="utf-8")
    r = run(root)
    assert r.returncode == 1, r.stdout
    assert "docker-compose.yml" in r.stdout
    assert "GIT_VERSION" in r.stdout


def test_base_rollback_to_previous_upstream_tag_is_rejected(tmp_path):
    """基线段回退到跟上游前的旧 tag 必须被拦住（本次 r43→r44 的核心改动点）。

    之前版本号写死 4.6.0，跟到上游 4.7.0 后必须改判：
    - 基线段回退（4.7.0 → 4.6.0）：回退，拦；
    - 同基线内构建号回退（build.01 → build.00）：回退，拦；
    - 换到更新的基线且构建号重置为 1：合法，放行。
    """
    root = make_fixture(tmp_path)
    # 基线段回退
    mutate(root, "webserver/version.py", 'VERSION = "%s"' % LOCK, 'VERSION = "4.6.0-build.99"')
    r = run(root)
    assert r.returncode == 1, r.stdout
    assert "回退" in r.stdout
    # 同基线构建号回退
    mutate(root, "webserver/version.py", 'VERSION = "4.6.0-build.99"', 'VERSION = "%s"' % LOCK)
    mutate(root, "webserver/version.py", 'VERSION = "%s"' % LOCK, 'VERSION = "%s"' % LOCK[:-2] + "00")
    r = run(root)
    assert r.returncode == 1, r.stdout
    assert "回退" in r.stdout


def test_set_accepts_new_base_and_rejects_sealed(tmp_path):
    """--set 接受换基线（4.6.0 → 4.7.0），拒绝封存号段（4.8.x）与裸 tag。"""
    root = make_fixture(tmp_path)
    r = subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root), "--set", "4.7.0-build.08"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    src = (root / "webserver" / "version.py").read_text(encoding="utf-8")
    assert 'VERSION = "4.7.0-build.08"' in src

    for bad in ("4.8.0-build.01", "4.7.0", "4.7.1-build.01"):
        r = subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(root), "--set", bad],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        assert r.returncode != 0, "%s 应被拒绝：%s" % (bad, r.stdout)


def test_set_auto_updates_compose_image_tag_no_manual_step(tmp_path):
    """--set 必须自动改写纯镜像形态 compose 的 image tag，无需任何手工补刀。

    回归点：CARRIERS 曾把 compose 预期写死「2 处」（本地构建形态的
    GIT_VERSION + 注释示例），但当前 compose 是与上游一致的纯镜像形态，
    只有 1 处 image tag，于是 --set 因 1 != 2 拒绝盲改，每次发版都得
    手工改 compose。此用例把「一键改全部载体（含 compose）」钉死。

    做法：构造完整载体副本（含脚本自身与测试文件），在副本上跑 --set 到
    「当前 LOCK 的下一个 build 号」，再用副本里那份「常量已随 --set 同步改写」
    的脚本复检，应全绿。目标号由当前 LOCK 动态推导、不绑定具体版本字面量——
    本测试文件自身也是 --set 载体，静态写死的版本号会被 --set 连带改写而失效。
    """
    base, cur_n = LOCK.rsplit("-build.", 1)
    target = "%s-build.%02d" % (base, int(cur_n) + 1)   # 如 build.06 → build.07

    full_files = FILES + ["scripts/check-version-lock.py", "tests/test_version_lock.py"]
    for rel in full_files:
        src = ROOT / rel
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)

    checker = tmp_path / "scripts" / "check-version-lock.py"
    r = subprocess.run(
        [sys.executable, str(checker), "--root", str(tmp_path), "--set", target],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr

    comp = (tmp_path / "docker-compose.yml").read_text(encoding="utf-8")
    assert "ghcr.io/wxgoo/audiobooks:%s" % target in comp, \
        "compose 的 image tag 没被 --set 自动改写：\n" + comp
    assert LOCK not in comp, \
        "compose 里还残留旧构建号 %s：\n%s" % (LOCK, comp)

    # 改完后用同一份（常量已同步）的脚本复检：证明一键改完即可发版，无手工步骤
    r2 = subprocess.run(
        [sys.executable, str(checker), "--root", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    assert r2.returncode == 0, \
        "--set 改完后版本锁复检应通过（说明无需手工补刀）：\n" + r2.stdout + r2.stderr


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
