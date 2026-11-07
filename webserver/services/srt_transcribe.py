"""音频转写文稿（SRT 字幕生成）——后台任务服务。

对选中书籍 `.audio/` 目录里的音频批量生成同名 `.srt` 字幕（faster-whisper）。
网页播放器同目录字幕优先，生成后刷新播放页即可看到字幕。

- 识别内核复用仓库根 `srt-tool/srt_core.py`（与 PC 版 make_srt_gui.exe 同源：
  中文引导语、VAD、幻觉清洗、复读剔除，参数含义一致）
- 依赖 faster-whisper（requirements-optional.txt）；未安装时 available()=False，
  页面给出降级提示（改用 PC 版 srt-tool）
- 取消粒度「当前文件」：srt_core v1.2 的 should_stop 回调，正在识别的小段
  结束后中断；已写到磁盘的 .srt 保留，取消时的半截识别结果也会采用（写到
  停止点为止），下次重跑可用缓存续
"""
import logging
import os
import sys
import threading
from pathlib import Path

_log = logging.getLogger("srt_transcribe")

AUDIO_EXTS = (".mp3", ".m4a", ".flac", ".ogg", ".wav", ".wma", ".aac")

# srt-tool/ 与 webserver/ 同级（容器内 /var/www/mybooks/srt-tool）
_SRT_TOOL_DIR = Path(__file__).resolve().parents[2] / "srt-tool"
if str(_SRT_TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(_SRT_TOOL_DIR))

import srt_core  # noqa: E402  # srt_core 对 faster_whisper 是惰性导入，缺依赖也能 import

_lock = threading.Lock()
_thread = None
_stop = threading.Event()
_snapshot = {"state": "idle"}


_WIN = sys.platform == "win32"


def lp(p: str) -> str:
    """Windows 长路径前缀；非 Windows（容器）原样返回。"""
    if not _WIN:
        return p
    p = os.path.abspath(p)
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def available() -> bool:
    """容器内是否装了 faster-whisper（决定网页转写是否可用）。"""
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def list_audio_files(audio_dir: str) -> list:
    try:
        names = sorted(os.listdir(lp(audio_dir)))
    except OSError:
        return []
    return [n for n in names
            if n.lower().endswith(AUDIO_EXTS)
            and os.path.isfile(lp(os.path.join(audio_dir, n)))]


def scan_books() -> list:
    """全库扫描：返回 [{book_id, audio_dir, audio_count, srt_count}]，只含有音频的书。"""
    from webserver.base.audio_dir import find_audios_by_scanning_library
    out = []
    for bid, adir in sorted(find_audios_by_scanning_library().items()):
        if not adir:
            continue
        files = list_audio_files(adir)
        if not files:
            continue
        srt_count = sum(
            1 for f in files
            if os.path.exists(lp(os.path.join(adir, Path(f).with_suffix(".srt").name))))
        out.append({"book_id": bid, "audio_dir": adir,
                    "audio_count": len(files), "srt_count": srt_count})
    return out


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()


def task_snapshot() -> dict:
    with _lock:
        return dict(_snapshot)


def cancel():
    with _lock:
        if not is_running():
            return False, "没有进行中的转写任务"
        _stop.set()
        _snapshot["state"] = "stopping"
        _snapshot["message"] = "正在停止（当前文件识别到停止点为止，已完成的字幕保留）"
    return True, "已请求停止"


def start(books: list, model: str = "base", lang: str = "zh", overwrite: bool = False):
    """books: [{book_id, title, audio_dir}]——audio_dir 由调用方在 calibre 池内解析好。"""
    global _thread, _stop, _snapshot
    with _lock:
        if is_running():
            return False, "已有转写任务在进行中"
        if not books:
            return False, "没有选择任何书籍"
        if not available():
            return False, ("容器内未安装 faster-whisper：请在容器内执行 "
                           "pip install faster-whisper ctranslate2==4.8.5 后重启，"
                           "或改用 PC 版 srt-tool（srt-tool/make_srt_gui.exe）")
        _stop = threading.Event()
        _snapshot = {
            "state": "running", "model": model, "lang": lang,
            "books_total": len(books), "files_total": 0, "files_done": 0,
            "skipped": 0, "failed": 0, "current_index": 0,
            "current_book": "", "current_file": "", "current_pct": 0,
            "message": "准备中（首次运行会下载模型到 ~/.cache/huggingface）",
        }
    real_books = [b for b in books if b.get("audio_dir")]
    _thread = threading.Thread(
        target=_worker, args=(real_books, model, lang, overwrite), daemon=True)
    _thread.start()
    return True, "转写任务已启动"


def _set(**kw):
    with _lock:
        _snapshot.update(kw)


def _finish(state: str, message: str):
    _set(state="idle", state_last=state, message=message)


def _worker(books, model, lang, overwrite):
    files = []
    for b in books:
        adir = b["audio_dir"]
        for fn in list_audio_files(adir):
            files.append((b, adir, fn))
    _set(files_total=len(files), files_done=0, skipped=0, failed=0,
         message="共 %d 个音频文件" % len(files) if files else "没有可转写的音频文件")
    if not files:
        _finish("idle", "没有可转写的音频文件")
        return

    stopped = False
    for i, (b, adir, fn) in enumerate(files):
        if _stop.is_set():
            stopped = True
            break
        apath = os.path.join(adir, fn)
        srt_name = Path(fn).with_suffix(".srt").name
        spath = os.path.join(adir, srt_name)
        _set(current_index=i + 1, current_book=b.get("title") or "",
             current_file=fn, current_pct=0)
        if os.path.exists(lp(spath)) and not overwrite:
            _set(files_done=_snapshot.get("files_done", 0) + 1, skipped=_snapshot.get("skipped", 0) + 1)
            continue

        def _prog(done, total, _b=b, _f=fn):
            _set(current_pct=int(done * 100 / total) if total else 0,
                 current_book=_b.get("title") or "", current_file=_f)

        try:
            segs = srt_core.transcribe_audio(
                apath, model_name=model, lang=lang,
                on_progress=_prog, should_stop=_stop.is_set)
            # 取消时采用已识别到停止点的部分结果（有比没有强，缓存/跳过逻辑保证不重复劳动）
            if segs:
                srt_core.write_srt(segs, lp(spath))
                _set(files_done=_snapshot.get("files_done", 0) + 1)
            elif _stop.is_set():
                stopped = True
                break
            else:
                _set(failed=_snapshot.get("failed", 0) + 1,
                     message="%s 没有识别到内容" % fn)
        except Exception as e:  # noqa: BLE001
            _log.warning("转写失败 %s: %s", fn, e)
            _set(failed=_snapshot.get("failed", 0) + 1,
                 message="%s 转写失败: %s" % (fn, e))

    if stopped or _stop.is_set():
        _finish("stopped", "已停止：完成 %d 个，跳过 %d 个（已完成的字幕保留）"
                % (_snapshot.get("files_done", 0), _snapshot.get("skipped", 0)))
    else:
        _finish("idle", "完成：共 %d 个文件，跳过已有字幕 %d 个，失败 %d 个"
                % (_snapshot.get("files_total", 0), _snapshot.get("skipped", 0),
                   _snapshot.get("failed", 0)))
