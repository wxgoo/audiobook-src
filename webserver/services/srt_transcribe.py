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

AUDIO_EXTS = (".mp3", ".m4a", ".m4b", ".flac", ".ogg", ".wav", ".wma",
              ".aac", ".opus", ".aiff", ".aif",
              ".mp4", ".mkv", ".mov", ".webm", ".flv", ".ts", ".mpg", ".wmv")

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


# ==================== 模型管理（借鉴外部「有声书字幕」工具） ====================
# faster-whisper 的模型在首次使用时按需下载到 HF 缓存（~/.cache/huggingface/hub）。
# 国内 NAS 直连 huggingface.co 常年超时，这里统一走 SRT_HF_MIRROR 镜像；
# 模型管理面板提供「按需下载 / 查看占用 / 删除释放」三个动作，镜像内置 small 兜底。

MODEL_ORDER = ("tiny", "base", "small", "medium", "large-v3")
MODEL_SIZES = {"tiny": "72 MB", "base": "138 MB", "small": "463 MB",
               "medium": "1.4 GB", "large-v3": "2.9 GB"}
_MODEL_REPO = "Systran/faster-whisper-{name}"
_model_dl_thread = None


def hf_mirror() -> str:
    """当前配置的 HF 镜像地址（空串 = 官方源）。"""
    from webserver import loader
    return str(loader.get_settings().get("SRT_HF_MIRROR") or "").strip()


def apply_hf_env():
    """把镜像配置写进进程环境：huggingface_hub 下载前会读 HF_ENDPOINT。

    必须在 WhisperModel/snapshot_download 之前调用；重复调用幂等。
    """
    mirror = hf_mirror()
    if mirror:
        os.environ["HF_ENDPOINT"] = mirror
    else:
        os.environ.pop("HF_ENDPOINT", None)


def _hf_model_dir(model: str) -> Path:
    """某档模型在 HF 缓存里的目录（可能不存在）。"""
    return Path.home() / ".cache" / "huggingface" / "hub" / (
        "models--Systran--faster-whisper-%s" % model)


def _dir_size(path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0
    return "%d B" % n


def model_status() -> list:
    """五档模型的状态表：[{model, size, downloaded, bytes}]（tiny→large-v3）。"""
    out = []
    for name in MODEL_ORDER:
        d = _hf_model_dir(name)
        n = _dir_size(d) if d.is_dir() else 0
        out.append({"model": name, "size": MODEL_SIZES.get(name, ""),
                    "downloaded": n > 0, "bytes": n})
    return out


def _set_model_dl(**kw):
    with _lock:
        _snapshot.setdefault("model_dl", {}).update(kw)


def model_download(model: str):
    """后台线程预下载模型（走镜像）。返回 (ok, msg)。"""
    global _model_dl_thread
    model = (model or "").strip()
    if model not in MODEL_ORDER:
        return False, "未知模型：%s" % model
    with _lock:
        if is_running():
            return False, "转写任务进行中，请稍后再下载模型"
        if _model_dl_thread is not None and _model_dl_thread.is_alive():
            return False, "模型下载已在进行中"
        if _hf_model_dir(model).is_dir() and _dir_size(_hf_model_dir(model)) > 0:
            return False, "模型 %s 已下载" % model
        _snapshot["model_dl"] = {
            "state": "running", "model": model,
            "log": "开始下载 %s（%s）…" % (model, MODEL_SIZES.get(model, "?"))}
    th = threading.Thread(target=_model_dl_worker, args=(model,), daemon=True)
    _model_dl_thread = th
    th.start()
    return True, "模型 %s 开始下载" % model


def _model_dl_worker(model: str):
    ok, msg = False, ""
    try:
        apply_hf_env()
        from huggingface_hub import snapshot_download
        _set_model_dl(log="下载中（走 %s）…" % (hf_mirror() or "huggingface.co"))
        snapshot_download(repo_id=_MODEL_REPO.format(name=model))
        ok = True
        msg = "模型 %s 下载完成" % model
        _set_model_dl(state="done", log=msg)
    except Exception as e:  # noqa: BLE001
        msg = "模型 %s 下载失败：%s" % (model, e)
        _set_model_dl(state="failed", log=str(msg)[-2000:])
    _log.info("[srt_tool] model download %s ok=%s", model, ok)


def model_delete(model: str):
    """删除某档模型的本地缓存，释放磁盘。返回 (ok, msg)。"""
    model = (model or "").strip()
    if model not in MODEL_ORDER:
        return False, "未知模型：%s" % model
    d = _hf_model_dir(model)
    if not d.is_dir() or _dir_size(d) == 0:
        return False, "模型 %s 尚未下载" % model
    if is_running():
        return False, "转写任务进行中，模型可能正被使用，请稍后再删除"
    n = _dir_size(d)
    import shutil
    # 不能用 ignore_errors=True：那样即使被占用/权限不足删不掉，也会回报"已删除释放"，
    # 前端据假成功刷新后状态不变，用户再点就报"尚未下载"。这里收集残留并以真实结果为准。
    errs = []
    def _onerror(func, path, exc):  # shutil.rmtree 的 onerror 回调
        errs.append("%s: %s" % (getattr(exc, "strerror", None) or exc, path))
    try:
        shutil.rmtree(d, onerror=_onerror)
        if srt_core is not None:
            srt_core._model_cache.clear()  # 已加载实例一并清掉，下次重新加载
    except Exception as e:  # noqa: BLE001
        return False, "删除失败：%s" % e
    # 真实校验：目录仍在且仍有内容 => 判定为删除失败，把残留与原因如实回报
    if d.is_dir() and _dir_size(d) > 0:
        left = _human(_dir_size(d))
        detail = ("；原因：" + errs[0]) if errs else ""
        # 权限不足多为 PUID 改动后模型缓存目录属主仍是构建期 uid（旧容器常见）。
        # 给出可直接执行的自助命令，无需等新镜像。
        if any("Permission" in e or "denied" in e or "13" in e for e in errs):
            hint = ("。这是目录属主与运行用户不一致（改过 PUID 的旧容器常见）；"
                    "请在 NAS 上执行：docker exec -u root <容器名> chown -R mybooks:mybooks "
                    "/var/www/mybooks/.cache，然后重试；或导入新镜像重建容器自动修复")
            return False, ("删除未完成，仍残留 %s%s%s" % (left, detail, hint))
        return False, ("删除未完成，仍残留 %s%s。可能文件被占用，"
                       "请停止转写/确认无进程使用后重试" % (left, detail))
    return True, "已删除模型 %s，释放 %s" % (model, _human(n))


def save_hf_mirror(mirror: str):
    """保存镜像地址到 CONF 并落盘 auto.py。返回 (ok, msg)。"""
    from webserver import loader
    conf = loader.get_settings()
    mirror = str(mirror or "").strip().rstrip("/")
    conf["SRT_HF_MIRROR"] = mirror
    apply_hf_env()
    try:
        conf.dumpfile()
        return True, "已保存镜像配置：%s" % (mirror or "官方源")
    except Exception as e:  # noqa: BLE001
        return False, "已对本次运行生效，但落盘失败：%s" % e


def current_model() -> str:
    """当前生效的转写档位（CONF["TRANSCRIBE_MODEL"]，SrtMake 与 AI 聊天麦克风共用）。"""
    from webserver import loader
    return str(loader.get_settings().get("TRANSCRIBE_MODEL", "base") or "base").strip()


def model_select(model: str):
    """保存转写档位到系统设置（SrtMake 工具页下拉，设置页旧下拉已取消）。

    TRANSCRIBE_MODEL 是 SrtMake 与 AI 聊天麦克风语音输入的共用配置，
    这里保存后 AI 语音输入立即跟随。返回 (ok, msg)。
    """
    from webserver import loader
    model = (model or "").strip()
    if model == "large":
        model = "large-v3"
    if model not in MODEL_ORDER:
        return False, "未知模型：%s" % model
    conf = loader.get_settings()
    conf["TRANSCRIBE_MODEL"] = model
    try:
        conf.dumpfile()
        return True, "已保存模型档位：%s（AI 聊天语音输入同步生效）" % model
    except Exception as e:  # noqa: BLE001
        return False, "已对本次运行生效，但落盘失败：%s" % e


def start(books: list, model=None, lang: str = "zh", overwrite: bool = False,
          keep_txt: bool = True, preset: str = "standard", script: str = "original",
          write_ass: bool = False, hotwords: str = ""):
    """books: [{book_id, title, audio_dir}]——audio_dir 由调用方在 calibre 池解析好。

    model：转写档位。None/空 时跟随系统设置 TRANSCRIBE_MODEL；显式指定（网页端
    下拉 / PC 版 make_srt_gui.py）则尊重传入值，并**同步写回** TRANSCRIBE_MODEL——
    它与 AI 聊天麦克风语音输入共用，转写用哪档，语音输入就跟哪档。
    v1.3 选项：preset 断行预设（short/standard/loose）、script 字幕文字转换
    （original/simplified/traditional，opencc 未装时自动原样）、write_ass 额外输出
    卡拉 OK 扫光 .ass、hotwords 热词（人名/术语，逗号分隔）。
    """
    global _thread, _stop, _snapshot
    model = (model or "").strip()
    if model:
        if model == "large":
            model = "large-v3"
        if model not in MODEL_ORDER:
            model = "base"
        if model != current_model():
            model_select(model)  # 写回共用配置，落盘失败不影响本次转写
    else:
        model = current_model()
        if model == "large":
            model = "large-v3"
        if model not in MODEL_ORDER:
            model = "base"
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
    apply_hf_env()  # 模型若未内置/未预下载，转写时自动补下载走镜像
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
        if overwrite and os.path.exists(lp(spath)):
            # 重新生成前把旧字幕改名留档（借鉴外部「有声书字幕」：覆盖不丢旧版）。
            # .srt.bak 不匹配字幕扩展名，播放器与后续扫描都不会误读。
            try:
                os.replace(lp(spath), lp(spath + ".bak"))
            except OSError as err:
                _log.warning("旧字幕备份失败 %s: %s", spath, err)

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
