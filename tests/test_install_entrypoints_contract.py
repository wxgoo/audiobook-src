"""全新安装入口的防漂移契约。

背景：install-fresh.sh（git clone 路径）与 install-from-tar.sh（tar 解压路径）
曾经是两套各自维护的安装逻辑。这个项目已经因为「两处口径不一致」吃过多次
事故（r27/r33 清单、r36 统计与缓存、r38 聚合快照），所以现在强制：

- 真正的校验/配置/部署逻辑**只有一份**，在 install-fresh.sh；
- install-from-tar.sh 只能是薄封装（判定来源 + 转发），不得复制逻辑；
- 两者都不得硬依赖 git（tar 包机器上可能根本没装 git）；
- 两者都得是 POSIX sh 语法、LF 换行、不含任何凭据。
"""
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FRESH = ROOT / "scripts" / "install-fresh.sh"
FROM_TAR = ROOT / "scripts" / "install-from-tar.sh"


def _text(p):
    return p.read_text(encoding="utf-8")


def test_both_entrypoints_exist():
    assert FRESH.is_file()
    assert FROM_TAR.is_file()


@pytest.mark.parametrize("script", [FRESH, FROM_TAR])
def test_posix_sh_syntax(script):
    """能被 /bin/sh 解析（不是 bash 专用语法）。"""
    sh = shutil.which("sh")
    if not sh:
        pytest.skip("no sh")
    r = subprocess.run([sh, "-n", str(script)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("script", [FRESH, FROM_TAR])
def test_lf_only(script):
    """CRLF 会让容器里的 shebang 变成 #!/bin/sh\\r 而直接 exec 失败。"""
    data = script.read_bytes()
    assert b"\r" not in data, f"{script.name} 含 CR"


@pytest.mark.parametrize("script", [FRESH, FROM_TAR])
def test_no_credentials(script):
    """交付给别人的脚本里不能出现令牌/密码。

    刻意不写任何具体令牌字面量（连前缀都不写进公开仓库），只挡「赋值了凭据」
    和「长十六进制串」这两种形态。
    """
    t = _text(script)
    assert not re.search(r"(token|password|passwd|netrc)\s*[:=]\s*\S", t, re.I)
    assert not re.search(r"\b[0-9a-f]{32,}\b", t), "脚本里出现疑似令牌的十六进制串"


def test_tar_entrypoint_is_thin_wrapper():
    """install-from-tar.sh 只能转发，不能自己再实现一套安装逻辑。"""
    t = _text(FROM_TAR)
    assert "exec sh" in t and "install-fresh.sh" in t, "必须转发到统一入口"
    # 这些是 install-fresh.sh 的职责，薄封装里出现就说明逻辑被复制了
    for forbidden in ("cat > .env", "sh scripts/deploy.sh", "check-dist.sh",
                      "check-myreader-links.sh", "mkdir -p \"$DATA_DIR\""):
        assert forbidden not in t, f"薄封装里出现了复制的逻辑: {forbidden}"


def test_fresh_entrypoint_owns_the_logic():
    """统一入口必须真的包含校验/配置/部署三步。"""
    t = _text(FRESH)
    for required in ("check-dist.sh", "check-myreader-links.sh", "cat > .env",
                     "sh scripts/deploy.sh", "DATA_DIR"):
        assert required in t, f"统一入口缺关键环节: {required}"


def test_git_is_conditional_not_hard_requirement():
    """tar 包机器可能没装 git：不能出现裸的 command -v git || exit。"""
    t = _text(FRESH)
    assert "缺 git" not in t or "[ -d .git ]" in t
    assert not re.search(r"command -v git[^\n]*\|\|\s*\{\s*echo\s*\"!!\s*缺 git", t), \
        "仍有『缺 git 就退出』的硬依赖"
    # 只有存在 .git 时才要求 git
    assert "[ -d .git ]" in t


def test_fresh_entrypoint_accepts_check_only():
    """两条路都要支持 CHECK_ONLY（只校验不构建），方便先验收再装。"""
    t = _text(FRESH)
    assert "CHECK_ONLY" in t
    assert "docker compose config" in t


def test_no_git_pull_upgrade_hint():
    """升级提示不能写 git pull（tar 包没有 .git，会误导）。"""
    t = _text(FRESH)
    assert "git pull && docker compose up -d --build" not in t or "也可用" in t
    assert "立即更新" in t, "应引导到页内热更"
