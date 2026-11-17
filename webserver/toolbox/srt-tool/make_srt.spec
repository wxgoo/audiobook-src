# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = collect_data_files("faster_whisper")
binaries = collect_dynamic_libs("ctranslate2")

a_t0 = Analysis(
    [r"make_srt.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "faster_whisper",
        "ctranslate2",
        "onnxruntime",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["torch", "tensorflow", "transformers"],
    noarchive=False,
)
pyz_t0 = PYZ(a_t0.pure)

exe_t0 = EXE(
    pyz_t0, a_t0.scripts, [],
    exclude_binaries=True,
    name='make_srt',
    console=True,
    upx=False,
)

a_t1 = Analysis(
    [r"make_srt_gui.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "faster_whisper",
        "ctranslate2",
        "onnxruntime",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["torch", "tensorflow", "transformers"],
    noarchive=False,
)
pyz_t1 = PYZ(a_t1.pure)

exe_t1 = EXE(
    pyz_t1, a_t1.scripts, [],
    exclude_binaries=True,
    name='make_srt_gui',
    console=False,
    upx=False,
)

a_t2 = Analysis(
    [r"srt_tools.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "faster_whisper",
        "ctranslate2",
        "onnxruntime",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["torch", "tensorflow", "transformers"],
    noarchive=False,
)
pyz_t2 = PYZ(a_t2.pure)

exe_t2 = EXE(
    pyz_t2, a_t2.scripts, [],
    exclude_binaries=True,
    name='srt_tools',
    console=True,
    upx=False,
)

coll = COLLECT(
    exe_t0, exe_t1, exe_t2, a_t1.binaries, a_t1.datas,
    name='make_srt',
    upx=False,
)

