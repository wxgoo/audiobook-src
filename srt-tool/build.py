# -*- coding: utf-8 -*-
"""一键打包 make_srt（命令行版）+ make_srt_gui（图形界面版）为 Windows 程序。

职责：依赖检查 → 清理 → 生成 spec → 调 PyInstaller → 校验产物。
依赖安装交给 build.bat（建 venv + pip install），本脚本不自动装包。

用法：
    python build.py            # 默认 onedir（推荐）：dist/make_srt/ 里同时有
                               #   make_srt.exe（命令行）和 make_srt_gui.exe（图形）
    python build.py --onefile  # 单文件两个 exe，启动慢，不推荐
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SPEC = ROOT / "make_srt.spec"
COLLECT_NAME = "make_srt"

# (exe 名, 入口脚本, 是否带控制台)。GUI 版 console=False —— 双击运行不再
# 一闪而过，参数都在窗口里选。
TARGETS = [
    ("make_srt", ROOT / "make_srt.py", True),
    ("make_srt_gui", ROOT / "make_srt_gui.py", False),
    # ★ v1.3：OneAsr 式 render / transcript / align / status 后期工具
    ("srt_tools", ROOT / "srt_tools.py", True),
]

REQUIRED_MODULES = ("faster_whisper", "ctranslate2", "PyInstaller")


def check_deps() -> None:
    """Ensure build dependencies are importable."""
    missing = []
    for mod in REQUIRED_MODULES:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        raise SystemExit(
            "[build] Missing dependencies: {}\n"
            "        Run build.bat first, or in venv run:\n"
            "        pip install faster-whisper ctranslate2==4.8.5 pyinstaller".format(
                ", ".join(missing)
            )
        )


def clean() -> None:
    """Remove previous build output and stale spec."""
    for p in (DIST, BUILD):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
    if SPEC.exists():
        SPEC.unlink()
    print("[build] Old artifacts cleaned")


def write_spec(onefile: bool) -> None:
    """Generate PyInstaller spec with faster_whisper data and ctranslate2 libs.

    每个目标各自 Analysis/PYZ/EXE；onedir 模式共用一个 COLLECT 目录，
    _internal 只存一份（GUI 版依赖是 CLI 版的超集，顺带装下 tcl/tk）。
    """
    lines = [
        "# -*- mode: python ; coding: utf-8 -*-",
        "from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs",
        "",
        'datas = collect_data_files("faster_whisper")',
        'binaries = collect_dynamic_libs("ctranslate2")',
        "",
    ]

    exe_vars: list[str] = []
    gui_tag = None
    for idx, (name, entry, console) in enumerate(TARGETS):
        tag = f"t{idx}"          # 唯一 tag：现在有两个带控制台的目标
        exe_vars.append(f"exe_{tag}")
        if not console:
            gui_tag = tag
        lines += [
            f"a_{tag} = Analysis(",
            # 用相对路径：spec 不绑死本机绝对路径（PyInstaller 以 ROOT 为 cwd 运行）
            f'    [r"{entry.relative_to(ROOT)}"],',
            '    pathex=["."],',
            "    binaries=binaries,",
            "    datas=datas,",
            "    hiddenimports=[",
            '        "faster_whisper",',
            '        "ctranslate2",',
            '        "onnxruntime",',
            "    ],",
            "    hookspath=[],",
            "    runtime_hooks=[],",
            '    excludes=["torch", "tensorflow", "transformers"],',
            "    noarchive=False,",
            ")",
            f"pyz_{tag} = PYZ(a_{tag}.pure)",
            "",
        ]
        if onefile:
            lines += [
                f"exe_{tag} = EXE(",
                f"    pyz_{tag}, a_{tag}.scripts, a_{tag}.binaries, "
                f"a_{tag}.datas, [],",
                f"    name='{name}',",
                f"    console={console},",
                "    upx=False,",
                ")",
                "",
            ]
        else:
            lines += [
                f"exe_{tag} = EXE(",
                f"    pyz_{tag}, a_{tag}.scripts, [],",
                "    exclude_binaries=True,",
                f"    name='{name}',",
                f"    console={console},",
                "    upx=False,",
                ")",
                "",
            ]

    if not onefile:
        # GUI 分析的 binaries/datas 是超集（含 tkinter 的 tcl/tk），一份共用
        bin_tag = gui_tag or "t0"
        lines += [
            "coll = COLLECT(",
            f"    {', '.join(exe_vars)}, a_{bin_tag}.binaries, "
            f"a_{bin_tag}.datas,",
            f"    name='{COLLECT_NAME}',",
            "    upx=False,",
            ")",
            "",
        ]

    SPEC.write_text("\n".join(lines) + "\n", encoding="utf-8")
    mode = "onefile" if onefile else "onedir"
    print(f"[build] Spec generated ({mode}): {SPEC}")


def run_pyinstaller() -> None:
    """Invoke PyInstaller with the generated spec."""
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(DIST),
        "--workpath",
        str(BUILD),
        str(SPEC),
    ]
    print("[build] Running:", " ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def post_check(onefile: bool) -> None:
    """Verify output exists and print key paths."""
    if onefile:
        for name, _, _ in TARGETS:
            exe = DIST / f"{name}.exe"
            if not exe.exists():
                raise SystemExit(f"[build] exe not found: {exe}")
            print(f"[build] Done: {exe}")
        return

    target = DIST / COLLECT_NAME
    for name, _, _ in TARGETS:
        exe = target / f"{name}.exe"
        if not exe.exists():
            raise SystemExit(f"[build] exe not found: {exe}")

    internal = target / "_internal"
    assets = internal / "faster_whisper" / "assets"
    # 新版 faster-whisper 叫 silero_vad_v6.onnx，旧版叫 silero_vad.onnx
    if not assets.exists() or not any(assets.glob("silero_vad*.onnx")):
        print(f"[build] Warning: silero VAD model not found under {assets}, "
              "VAD filter may fail at runtime")

    for name, _, console in TARGETS:
        print(f"[build] Done: {target / (name + '.exe')}"
              + ("" if console else "  ← 双击运行（图形界面）"))
    print(f"[build] Output directory: {target}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Package make_srt + make_srt_gui")
    ap.add_argument("--onefile", action="store_true", help="single file output (not recommended)")
    args = ap.parse_args()

    for _, entry, _ in TARGETS:
        if not entry.exists():
            print(f"[build] Entry not found: {entry}", file=sys.stderr)
            return 1

    check_deps()
    clean()
    write_spec(args.onefile)
    run_pyinstaller()
    post_check(args.onefile)
    print("[build] Note: Whisper models are not bundled. First run needs network or local cache.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
