# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

datas = collect_data_files("faster_whisper")
binaries = collect_dynamic_libs("ctranslate2")

a_cli = Analysis(
    [r"C:\Users\anan\.zcode\workspace\draft-38216ee5-4f8e-4335-b378-0cd87bdbc067\extracted\make_srt.py"],
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
pyz_cli = PYZ(a_cli.pure)

exe_cli = EXE(
    pyz_cli, a_cli.scripts, [],
    exclude_binaries=True,
    name='make_srt',
    console=True,
    upx=False,
)

a_gui = Analysis(
    [r"C:\Users\anan\.zcode\workspace\draft-38216ee5-4f8e-4335-b378-0cd87bdbc067\extracted\make_srt_gui.py"],
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
pyz_gui = PYZ(a_gui.pure)

exe_gui = EXE(
    pyz_gui, a_gui.scripts, [],
    exclude_binaries=True,
    name='make_srt_gui',
    console=False,
    upx=False,
)

coll = COLLECT(
    exe_cli, exe_gui, a_gui.binaries, a_gui.datas,
    name='make_srt',
    upx=False,
)

