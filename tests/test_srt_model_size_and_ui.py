# -*- coding: utf-8 -*-
"""模型体积显示 & 下载后按钮状态的回归测试。

NAS 实测两个问题：
1. 标称 138 MB 的 base 下载后显示 282.1 MB —— HuggingFace 缓存里
   snapshots/<commit>/model.bin 是指向 blobs/<hash> 的符号链接，
   _dir_size 用 os.path.getsize 跟随链接，把同一份文件统计了两遍。
2. 模型下载完成后按钮仍是灰色，必须手动刷新页面才能删除 ——
   删除按钮此前 :disabled 依赖 modelDlRunning、:loading 依赖 dlBusy，
   轮询漏掉 done 时这两个状态残留，v-btn 就一直灰着。
"""

from pathlib import Path

from webserver.services import srt_transcribe as st


def test_dir_size_skips_symlinks(tmp_path):
    """符号链接不应计入占用：只累加真实文件（blob）大小。"""
    d = tmp_path / "models--Systran--faster-whisper-base"
    (d / "blobs").mkdir(parents=True)
    snap = d / "snapshots" / "commit"
    snap.mkdir(parents=True)

    blob = d / "blobs" / "realhash"
    blob.write_bytes(b"x" * 4096)
    # snapshots 里的 model.bin 只是指向 blob 的软链接
    (snap / "model.bin").symlink_to(blob)
    # 另一个真实小文件照常计入
    (snap / "config.json").write_bytes(b"y" * 10)

    assert st._dir_size(d) == 4096 + 10


def test_model_status_bytes_are_real_usage(tmp_path, monkeypatch):
    """model_status 的 bytes 应是真实占用，不含软链接重复计算。"""
    d = tmp_path / "models--Systran--faster-whisper-base"
    (d / "blobs").mkdir(parents=True)
    snap = d / "snapshots" / "commit"
    snap.mkdir(parents=True)
    blob = d / "blobs" / "realhash"
    blob.write_bytes(b"x" * 2048)
    (snap / "model.bin").symlink_to(blob)

    monkeypatch.setattr(st, "_hf_model_dir", lambda m: d)
    status = {x["model"]: x for x in st.model_status()}
    assert status["base"]["downloaded"] is True
    assert status["base"]["bytes"] == 2048
    # 标称体积不变（MODEL_SIZES 是静态文案）
    assert status["base"]["size"] == "138 MB"


def test_frontend_delete_button_not_tied_to_download_state():
    """前端：删除按钮的 loading/disabled 不得依赖 dlBusy / modelDlRunning。"""
    vue = Path(__file__).resolve().parents[1] / "app/src/pages/toolbox/srt_tool.vue"
    src = vue.read_text(encoding="utf-8")
    # 抓取 v-else 删除按钮整块（从 <v-btn v-else 到 </v-btn>）
    lines = src.splitlines()
    start = next(i for i, ln in enumerate(lines)
                 if '<v-btn v-else' in ln and 'color="error"' in ln)
    end = next(i for i in range(start, len(lines)) if '</v-btn>' in lines[i])
    block = "\n".join(lines[start:end + 1])
    assert "deleting === m.model" in block
    assert "modelDlRunning" not in block
    assert "dlBusy" not in block


def test_frontend_load_models_clears_stale_dl_busy():
    """前端：/models 返回非 running 时兜底清 dlBusy，防止按钮长期灰。"""
    vue = Path(__file__).resolve().parents[1] / "app/src/pages/toolbox/srt_tool.vue"
    src = vue.read_text(encoding="utf-8")
    assert "if (!sdl || sdl.state !== 'running') this.dlBusy = ''" in src
