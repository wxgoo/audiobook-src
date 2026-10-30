#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""音频转写文稿（移植自 audiobook 的 Whisper 转写）。

把有声书音频转成可阅读的文字稿 + 可跟随的字幕。Whisper 做成**可选依赖**：
没装时 whisper_available() 返回 False，调用方（前端/接口）把功能藏起来即可，
不影响服务启动。转写耗时任务接入 mybooks 已有的 BackgroundService 进度体系。

两个后端自动选择（优先 faster-whisper，快 4 倍且不需要 torch）：
  * faster_whisper.WhisperModel   —— Dockerfile 默认安装
  * whisper.load_model            —— openai-whisper，自己 pip 装的话也能用

输出两个文件（同名不同后缀）：
  * <name>.srt —— 带时间轴的字幕，audio/_id.vue 播放器会自动加载并逐句高亮
  * <name>.txt —— 纯文本全稿，用于全文搜索、复制做笔记、离线阅读
"""

import logging
import os
import threading
import time
from pathlib import Path

# HuggingFace 下载源与传输方式：必须在 import faster_whisper 之前设好，
# 否则 huggingface_hub 已经把常量读进内存，改环境变量不生效。
#   HF_ENDPOINT        国内直连 huggingface.co 不通，默认走 hf-mirror.com
#   HF_HUB_DISABLE_XET 镜像不代理 xet 通道且需鉴权，开启会 401
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

# 支持的音频扩展名（与 audiobook 保持一致）
AUDIO_EXTS = {".mp3", ".m4a", ".m4b", ".wav", ".flac", ".ogg", ".aac", ".wma"}

# faster-whisper 的模型缓存目录：放 /data 下，容器重建后不用重新下模型。
# 优先读环境变量，其次固定到 /data/models（容器内 /data 是持久化卷）。
MODEL_DIR = os.environ.get("WHISPER_MODEL_DIR") or (
    "/data/models/whisper" if os.path.isdir("/data") else "")

_model_cache = {}
_model_lock = threading.Lock()

# 后端探测结果缓存：None = 还没探测过，否则是 "faster" / "openai" / ""
_backend = None


def _check_av_compat():
    """faster-whisper 1.2.x 调 av.open(metadata_errors=...)，av 16+ 删了这个参数，
    装了新版会在转写时抛 TypeError: unexpected keyword argument。
    这里提前检查并给出可操作的报错，而不是让用户看一长串 traceback。"""
    try:
        import av
        major = int(str(av.__version__).split(".")[0])
        if major >= 16:
            raise RuntimeError(
                "av 版本过高（%s），与 faster-whisper 不兼容。"
                "请执行：pip install 'av<16'" % av.__version__)
    except ImportError:
        pass


def detect_backend() -> str:
    """返回可用的转写后端："faster" / "openai" / ""（都没有）。"""
    global _backend
    if _backend is not None:
        return _backend
    try:
        import faster_whisper  # noqa: F401
        _check_av_compat()
        _backend = "faster"
        return _backend
    except Exception as e:
        # av 版本不兼容属于「装了但用不了」，要明确报出来而不是静默降级；
        # 没装 faster-whisper 的 ModuleNotFoundError 才继续往下试 openai-whisper。
        if type(e).__name__ != "ModuleNotFoundError":
            logging.error("[transcribe] faster-whisper 不可用：%s", e)
    try:
        import whisper  # noqa: F401
        _backend = "openai"
        return _backend
    except Exception:
        pass
    _backend = ""
    return _backend


def whisper_available() -> bool:
    """本机装没装 whisper（懒加载探测，结果缓存）。"""
    return bool(detect_backend())


def get_model(name: str = "small"):
    """加载并缓存模型（同一模型全进程只加载一次）。"""
    key = (detect_backend(), name or "small")
    with _model_lock:
        model = _model_cache.get(key)
        if model is not None:
            return model
        backend, size = key
        logging.info("[transcribe] loading %s model %s ...", backend, size)
        if backend == "faster":
            from faster_whisper import WhisperModel
            kwargs = {"device": "auto", "compute_type": "int8"}
            if MODEL_DIR:
                os.makedirs(MODEL_DIR, exist_ok=True)
                kwargs["download_root"] = MODEL_DIR
            # device="auto" 在无 CUDA 的机器上自动退回 CPU；
            # compute_type="int8" 是 CPU 上最快且质量损失可接受的选择。
            model = WhisperModel(size, **kwargs)
        elif backend == "openai":
            import whisper
            model = whisper.load_model(size)
        else:
            raise RuntimeError("服务器未安装 whisper（faster-whisper 或 openai-whisper）")
        _model_cache[key] = model
        return model


def release_model(name: str = None):
    with _model_lock:
        if name is None:
            _model_cache.clear()
        else:
            for k in [k for k in _model_cache if k[1] == name]:
                _model_cache.pop(k, None)


# ---------- 字幕格式化 ----------

def _srt_time(seconds: float) -> str:
    """秒 → SRT 时间码 00:00:03,120"""
    if seconds < 0:
        seconds = 0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _clean_cue_text(text: str) -> str:
    """去掉字幕文本里的换行和多余空白：SRT 一条 cue 里不能有裸换行。"""
    return " ".join((text or "").split())


def build_srt(segments) -> str:
    """segments: [{'start': float, 'end': float, 'text': str}] → SRT 文本。"""
    lines = []
    idx = 0
    for seg in segments:
        text = _clean_cue_text(seg.get("text"))
        if not text:
            continue
        start = float(seg.get("start") or 0)
        end = float(seg.get("end") or 0)
        if end <= start:
            # 极短片段（模型偶尔给出 end==start）补 0.5 秒，否则播放器高亮闪一下就没了
            end = start + 0.5
        idx += 1
        lines.append(str(idx))
        lines.append(f"{_srt_time(start)} --> {_srt_time(end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def _run_backend(model, audio_path: Path, lang: str, progress_cb, stop_event):
    """统一两个后端的调用方式，返回 (segments, full_text)。

    segments 统一成 [{'start','end','text'}]，两者字段名不同需要转换。
    """
    language = None if lang in ("", "auto") else lang
    backend = detect_backend()

    if backend == "faster":
        # faster-whisper 的 transcribe 返回 (segments_generator, info)。
        # 生成器是惰性的：边解码边产出，正好用来上报进度。
        seg_iter, info = model.transcribe(
            str(audio_path),
            language=language,
            beam_size=5,
            vad_filter=True,          # 去掉静音段，速度更快、断句更干净
            word_timestamps=False,    # 句级时间戳够用；开词级会慢 10~20%
        )
        total = float(getattr(info, "duration", 0) or 0)
        segments = []
        for seg in seg_iter:
            if stop_event is not None and stop_event.is_set():
                break
            segments.append({
                "start": float(seg.start or 0),
                "end": float(seg.end or 0),
                "text": seg.text or "",
            })
            if progress_cb and total > 0:
                progress_cb(min(0.95, 0.05 + 0.9 * float(seg.end or 0) / total),
                            "转写中")
    else:
        # openai-whisper：verbose=True 才在 result 里带 segments 明细
        result = model.transcribe(str(audio_path), language=language,
                                  verbose=True, word_timestamps=False)
        segments = [{
            "start": float(s.get("start") or 0),
            "end": float(s.get("end") or 0),
            "text": s.get("text") or "",
        } for s in (result.get("segments") or [])]

    full_text = " ".join(_clean_cue_text(s["text"]) for s in segments).strip()
    return segments, full_text


def transcribe_file(audio_path, out_txt=None, model_size="small",
                    lang="auto", progress_cb=None, stop_event: threading.Event = None,
                    keep_txt=True):
    """把单个音频转写为文稿 + 字幕。

    返回 (ok: bool, msg: str, txt_path: str)。
    progress_cb(frac: float, note: str) 用于上报进度（0~1）。
    stop_event 置位后在下一段开始前停止（返回已生成的部分并标记 cancelled）。
    keep_txt=False 时只写 .srt（省磁盘，但没法全文阅读/复制）。
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        return False, f"文件不存在：{audio_path}", ""
    if audio_path.suffix.lower() not in AUDIO_EXTS:
        return False, f"不支持的音频格式：{audio_path.suffix}", ""
    if not whisper_available():
        return False, ("服务器未安装 whisper（pip install faster-whisper），"
                       "功能不可用"), ""

    out_txt = Path(out_txt) if out_txt else audio_path.with_suffix(".txt")
    out_srt = out_txt.with_suffix(".srt")

    def report(frac, note=""):
        if progress_cb:
            try:
                progress_cb(max(0.0, min(1.0, frac)), note)
            except Exception:
                pass

    report(0.0, "加载模型")
    try:
        model = get_model(model_size)
        report(0.05, "开始转写")
        t0 = time.time()
        segments, text = _run_backend(model, audio_path, lang, report, stop_event)
    except Exception as e:
        logging.exception("[transcribe] failed for %s", audio_path)
        return False, str(e), ""
    if stop_event is not None and stop_event.is_set():
        return False, "已取消", ""
    if not segments:
        return False, "没有识别到有效语音（音频可能是纯音乐或静音）", ""

    out_txt.parent.mkdir(parents=True, exist_ok=True)

    # 先写 .srt：播放器靠它做逐句高亮跟随
    srt_content = build_srt(segments)
    tmp_srt = out_srt.with_suffix(".srt.tmp")
    tmp_srt.write_text(srt_content, encoding="utf-8")
    os.replace(tmp_srt, out_srt)

    # 再写 .txt：全稿，供搜索/复制/离线阅读
    if keep_txt:
        tmp = out_txt.with_suffix(".txt.tmp")
        tmp.write_text(text + "\n", encoding="utf-8")
        os.replace(tmp, out_txt)

    report(1.0, "完成")
    logging.info("[transcribe] %s -> %s + %s (%d 句, %.1fs)",
                 audio_path.name, out_txt.name, out_srt.name,
                 len(segments), time.time() - t0)
    return True, "ok", str(out_txt)


def collect_audio_files(paths, stop_event=None):
    """把用户提交的路径整理成音频文件列表：
    * 文件 → 校验扩展名后保留
    * 目录 → 递归收集其中所有受支持音频（含子目录）
    返回 (files: [str], skipped: [str])。skipped 是不存在/格式不支持的条目。"""
    files, skipped = [], []
    seen = set()
    for raw in paths or []:
        p = Path(raw)
        if p.is_dir():
            for root, _dirs, names in os.walk(p):
                if stop_event is not None and stop_event.is_set():
                    break
                for name in sorted(names):
                    if name.startswith("."):
                        continue
                    fp = Path(root) / name
                    if fp.suffix.lower() in AUDIO_EXTS:
                        key = str(fp.resolve())
                        if key not in seen:
                            seen.add(key)
                            files.append(str(fp))
        elif p.is_file() and p.suffix.lower() in AUDIO_EXTS:
            key = str(p.resolve())
            if key not in seen:
                seen.add(key)
                files.append(str(p))
        else:
            skipped.append(str(raw))
    return files, skipped


def transcribe_many(paths, model_size="small", lang="auto",
                    progress_cb=None, stop_event: threading.Event = None,
                    keep_txt=True):
    """批量转写。返回 (done, failed, results:[{path, ok, msg, txt, srt}])。"""
    done = failed = 0
    results = []
    total = len(paths)
    for i, p in enumerate(paths):
        if stop_event is not None and stop_event.is_set():
            break
        frac_base = i / max(total, 1)
        cb = (lambda f, note="", _b=frac_base, _s=1.0 / max(total, 1):
              progress_cb(_b + f * _s, note)) if progress_cb else None
        ok, msg, txt = transcribe_file(p, model_size=model_size, lang=lang,
                                       progress_cb=cb, stop_event=stop_event,
                                       keep_txt=keep_txt)
        results.append({
            "path": str(p), "ok": ok, "msg": msg, "txt": txt,
            "srt": str(Path(txt).with_suffix(".srt")) if txt else "",
        })
        if ok:
            done += 1
        else:
            failed += 1
    return done, failed, results
