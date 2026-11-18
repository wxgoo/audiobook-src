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

# 识别内核 srt_core.py / make_srt*.py 平铺在 webserver/toolbox/ 下（与其它工具模块
# 同层，随 webserver/ 一起 COPY 进镜像）；srt_core 对 faster_whisper 惰性导入。
# 必须容错：就算镜像缺文件，也只能让本工具降级不可用，
# 绝不能拖垮整个应用启动（build.22 交付事故教训）。
try:
    from webserver.toolbox import srt_core  # noqa: E402
    SRT_CORE_OK = True
except ImportError:
    srt_core = None
    SRT_CORE_OK = False

_lock = threading.Lock()
_thread = None
_stop = threading.Event()
_snapshot = {"state": "idle"}
_install_thread = None
_PIP_SPECS = ["faster-whisper>=1.0", "ctranslate2==4.8.5"]


_WIN = sys.platform == "win32"


def lp(p: str) -> str:
    """Windows 长路径前缀；非 Windows（容器）原样返回。"""
    if not _WIN:
        return p
    p = os.path.abspath(p)
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def available() -> bool:
    """容器内是否具备网页转写条件：srt_core 可导入且 faster-whisper 已安装。"""
    if not SRT_CORE_OK:
        return False
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


# ==================== 依赖安装（页面一键装 faster-whisper） ====================

def _pip_install(specs):
    """pip 安装；默认源失败自动重试清华镜像。返回 (ok, 输出)。"""
    import subprocess
    def _run(extra):
        cmd = [sys.executable, "-m", "pip", "install"] + specs + extra
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")
    try:
        ok, out = _run([])
        if not ok:
            ok2, out2 = _run(["-i", "https://pypi.tuna.tsinghua.edu.cn/simple"])
            return ok2, out + "\n== 默认源失败，重试清华镜像 ==\n" + out2
        return ok, out
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def install_deps():
    """后台线程安装 faster-whisper（页面一键触发，输出进 snapshot.install.log）。"""
    global _install_thread
    with _lock:
        if is_running():
            return False, "转写任务进行中，请稍后再安装依赖"
        if _install_thread is not None and _install_thread.is_alive():
            return False, "依赖安装已在进行中"
        if available():
            return False, "依赖已安装，无需重复安装"
        _snapshot["install"] = {"state": "running", "log": "启动 pip install…"}
    inst = threading.Thread(target=_install_worker, daemon=True)
    _install_thread = inst
    inst.start()
    return True, "依赖安装已开始"


def _install_worker():
    ok, out = _pip_install(_PIP_SPECS)
    with _lock:
        inst = _snapshot.setdefault("install", {})
        inst["state"] = "done" if ok else "failed"
        inst["log"] = out[-6000:]
        inst["message"] = ("安装完成，点「重启服务」生效" if ok
                           else "安装失败（见日志；可改用 PC 版 srt-tool）")
    _log.info("[srt_tool] pip install faster-whisper ok=%s", ok)


def restart_tornado():
    """分离子进程重启 tornado（本进程随重启退出，必须立刻返回）。"""
    import subprocess
    subprocess.Popen(["supervisorctl", "restart", "tornado"],
                     start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True, "正在重启 tornado，页面约 20 秒后恢复"


# v1.3 排版选项的合法值（与 srt_core.SUBTITLE_PRESETS / convert_script 对齐）
PRESET_CHOICES = ("short", "standard", "loose")
SCRIPT_CHOICES = ("original", "simplified", "traditional")
HOTWORDS_MAX_LEN = 300


def start(books: list, model: str = "base", lang: str = "zh", overwrite: bool = False,
          keep_txt: bool = True, preset: str = "standard", script: str = "original",
          write_ass: bool = False, hotwords: str = ""):
    """books: [{book_id, title, audio_dir}]——audio_dir 由调用方在 calibre 池解析好。

    v1.3 选项：preset 断行预设（short/standard/loose）、script 字幕文字转换
    （original/simplified/traditional，opencc 未装时自动原样）、write_ass 额外输出
    卡拉 OK 扫光 .ass、hotwords 热词（人名/术语，逗号分隔）。
    """
    global _thread, _stop, _snapshot
    if preset not in PRESET_CHOICES:
        preset = "standard"
    if script not in SCRIPT_CHOICES:
        script = "original"
    hotwords = (hotwords or "").strip()[:HOTWORDS_MAX_LEN]
    with _lock:
        if is_running():
            return False, "已有转写任务在进行中"
        if not books:
            return False, "没有选择任何书籍"
        if not available():
            if not SRT_CORE_OK:
                return False, ("容器内缺少 srt-tool/srt_core.py（镜像未携带），"
                               "请更新部署包；或改用 PC 版 srt-tool（srt-tool/make_srt_gui.exe）")
            return False, ("容器内未安装 faster-whisper：请在容器内执行 "
                           "pip install faster-whisper ctranslate2==4.8.5 后重启，"
                           "或改用 PC 版 srt-tool（srt-tool/make_srt_gui.exe）")
        _stop = threading.Event()
        _snapshot = {
            "state": "running", "model": model, "lang": lang, "keep_txt": keep_txt,
            "preset": preset, "script": script, "write_ass": bool(write_ass),
            "books_total": len(books), "files_total": 0, "files_done": 0,
            "skipped": 0, "failed": 0, "current_index": 0,
            "current_book": "", "current_file": "", "current_pct": 0,
            "message": "准备中（首次运行会下载模型到 ~/.cache/huggingface）",
        }
    real_books = [b for b in books if b.get("audio_dir")]
    _thread = threading.Thread(
        target=_worker, args=(real_books, model, lang, overwrite, keep_txt,
                              preset, script, bool(write_ass), hotwords), daemon=True)
    _thread.start()
    return True, "转写任务已启动"


def _set(**kw):
    with _lock:
        _snapshot.update(kw)


def _finish(state: str, message: str):
    _set(state="idle", state_last=state, message=message)


def _worker(books, model, lang, overwrite, keep_txt,
            preset="standard", script="original", write_ass=False, hotwords=""):
    files = []
    for b in books:
        adir = b["audio_dir"]
        for fn in list_audio_files(adir):
            files.append((b, adir, fn))
    _set(files_total=len(files), files_done=0, skipped=0, failed=0,
         message="共 %d 个音频文件" % len(files) if files else "没有可转写的音频文件")
    if not files or srt_core is None:
        _finish("idle", "没有可转写的音频文件" if files else "srt_core 不可用")
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
                hotwords=hotwords or None,
                on_progress=_prog, should_stop=_stop.is_set)
            # 取消时采用已识别到停止点的部分结果（有比没有强，缓存/跳过逻辑保证不重复劳动）
            if segs:
                # ★ v1.3：timeline 排版——识别结果按预设断行、按需做字形转换，
                #   计时取词级边界（比 v1.2 的段级直出更精细）。
                tl = srt_core.build_timeline(segs, source=fn, language=lang)
                cues = srt_core.layout_timeline(
                    tl, preset=preset, script=script, beautify=True)
                written = []
                srt_core.write_srt(cues, lp(spath))
                written.append(srt_name)
                if write_ass:
                    ass_name = Path(fn).with_suffix(".ass").name
                    srt_core.write_ass(cues, lp(os.path.join(adir, ass_name)))
                    written.append(ass_name)
                if keep_txt:
                    txt_name = Path(fn).with_suffix(".txt").name
                    srt_core.write_txt(cues, lp(os.path.join(adir, txt_name)))
                    written.append(txt_name)
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
