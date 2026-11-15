"""在线安装入口（install-online.sh）的防漂移契约。

背景：r27/r33 的两次事故都是「出包链路里混进网络请求、远端内容覆盖了
包内清单」。所以新增在线取包能力时，必须把边界钉死：

- 在线脚本只负责「取包 + 校验 + 解压」，绝不复制安装逻辑，最后必须
  转交 install-from-tar.sh（薄封装），由 install-fresh.sh 统一收口；
- 绝不写 update/manifest.json，出包链路（pack.sh / deploy.sh）保持零网络请求；
- Gitee 的限制是硬约束：Release 单附件 100MB、raw 匿名 >10MB 403，
  因此 153MB 包必须分片 + 走 Release 直链，且钉死 tag 而非 master；
- 下载后必须逐片校验 + 整包 sha256 校验，防传坏 / 半截合并；
- 脚本会被别人 curl 下来直接执行，所以不能出现凭据、不能 curl | sh、
  必须是 POSIX sh + LF。
"""
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ONLINE = ROOT / "scripts" / "install-online.sh"


def _text():
    return ONLINE.read_text(encoding="utf-8")


def test_online_entrypoint_exists():
    assert ONLINE.is_file()


def test_posix_sh_syntax():
    sh = shutil.which("sh")
    if not sh:
        pytest.skip("no sh")
    r = subprocess.run([sh, "-n", str(ONLINE)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_lf_only():
    assert b"\r" not in ONLINE.read_bytes(), "CRLF 会让 #!/bin/sh 失效"


def test_no_credentials():
    t = _text()
    assert not re.search(r"(access_token|GITEE_TOKEN|password|passwd|netrc)\s*[:=]\s*\S", t, re.I)
    assert "curl" not in t or "oauth2-bearer" not in t


def test_never_pipes_download_into_shell():
    """半截下载被直接执行是灾难；必须先落盘、校验、再执行。"""
    t = _text()
    assert not re.search(r"curl[^\n]*\|\s*(sh|bash)", t)
    assert not re.search(r"wget[^\n]*\|\s*(sh|bash)", t)


def test_delegates_to_unified_installer():
    """只取包，不复制安装逻辑。"""
    t = _text()
    assert "exec sh" in t and "install-from-tar.sh" in t
    for forbidden in ("cat > .env", "sh scripts/deploy.sh", "check-dist.sh",
                      "check-myreader-links.sh", "mkdir -p \"$DATA_DIR\""):
        assert forbidden not in t, f"在线脚本里复制了安装逻辑: {forbidden}"


def test_no_git_dependency():
    assert "git clone" not in _text()
    assert "git pull" not in _text()


def test_pin_release_tag_not_master():
    """钉 tag 避免 raw 60~300 秒缓存 / master 漂移导致取到旧分片。

    脚本头部注释里给用户的「下载本脚本」链接仍是 master raw（那是脚本本体，
    不是分片地址），所以只检查 BASE_URL 定义行。
    """
    t = _text()
    assert "TAG=dist-" in t
    base = [ln for ln in t.splitlines() if ln.startswith("BASE_URL=")]
    assert len(base) == 1
    assert "/releases/download/$TAG" in base[0]
    assert "/raw/master/" not in base[0], "分片地址不能依赖 master 分支路径"


def test_parts_respect_gitee_attachment_limit():
    """153MB 包必须分片；每片 < 100MB（社区版 Release 附件上限）。"""
    t = _text()
    assert re.search(r"^PARTS=2\b", t, re.M)
    assert "100MB" in t
    assert "PART_PREFIX" in t and "part01" not in t, "分片名应由前缀 + 序号生成"


def test_verifies_every_part_and_the_whole_package():
    t = _text()
    assert "SHA256SUMS-online" in t or "SUMS=" in t
    assert "while read -r" in t, "必须逐片比对 sha256"
    assert re.search(r"^PKG_SHA256=[0-9a-f]{64}$", t, re.M), "整包 sha256 必须硬编码常量"
    assert '"$_got" = "$PKG_SHA256"' in t, "合并后必须校验整包"
    assert "禁止安装" in t


def test_download_only_and_overrides():
    """必须能只取包验收，且能换镜像源 / 工作目录（本地端到端测试靠它）。"""
    t = _text()
    for key in ("DOWNLOAD_ONLY", "ONLINE_BASE_URL", "ONLINE_WORK_DIR", "ONLINE_FORCE",
                "CHECK_ONLY", "DATA_DIR"):
        assert key in t, f"缺环境变量 {key}"


def test_no_write_to_release_manifest():
    """r27/r33：绝不能在下载链路里覆盖发布清单。"""
    t = _text()
    assert not re.search(r"(>|cp\s|mv\s)[^\n]*update/manifest\.json", t)
    assert "sh scripts/pack.sh" not in t
