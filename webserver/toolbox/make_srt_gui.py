#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_srt_gui — SRT 字幕批量生成（图形界面版）。

与命令行版 make_srt.py 完全共用 srt_core 的识别/清洗/缓存逻辑，参数含义
一致；适合不想敲命令的场景：选目录 → 选参数 → 点开始，进度和日志都在窗口里。

用法：
    python make_srt_gui.py            # 或双击打包出的 make_srt_gui.exe
    把音频目录直接拖到 make_srt_gui.exe 图标上，会自动填入路径

打包：python build.py（同时产出 make_srt.exe 命令行版 + make_srt_gui.exe 图形版）

线程模型：识别跑在 worker 线程；tkinter 只允许主线程碰 UI，所以全部通信
走 queue.Queue，主线程用 after(100) 轮询上屏。「停止」通过 threading.Event
传给 srt_core.transcribe_audio(should_stop=...)，当前小段识别完就中断。
"""
from __future__ import annotations

import json
import logging
import os
import queue
import sys
import threading
import time
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
import tkinter as tk

from make_srt import AUDIO_EXTS, CACHE_DIR, find_audios
from srt_core import (cache_key, load_cache, merge_segments, save_cache,
                      transcribe_audio, write_srt, __version__)

SETTINGS_FILE = CACHE_DIR / "gui_settings.json"
MODEL_CHOICES = ["tiny", "base", "small", "medium", "large-v3"]
LANG_CHOICES = ["auto", "zh", "en"]
DEVICE_CHOICES = ["auto", "cpu", "cuda"]
COMPUTE_CHOICES = ["auto", "int8", "float16"]

AUDIO_FILETYPES = [
    ("音频文件", " ".join("*" + e for e in sorted(AUDIO_EXTS))),
    ("所有文件", "*.*"),
]


class QueueLogHandler(logging.Handler):
    """把 logging 记录投进队列，主线程轮询上屏（tkinter 只允许主线程碰 UI）。"""

    def __init__(self, q: "queue.Queue[tuple]"):
        super().__init__(level=logging.INFO)
        self.q = q
        self.setFormatter(
            logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.q.put(("log", self.format(record)))
        except Exception:
            pass


class SrtGuiApp:
    """主窗口。重活全在 worker 线程，UI 通过 queue + after(100) 轮询刷新。"""

    def __init__(self, q: "queue.Queue[tuple]"):
        self.q = q
        self.worker: threading.Thread | None = None
        self.stop_event: threading.Event | None = None
        self.total = 0
        self.cur_name = ""

        self.root = tk.Tk()
        self.root.title(f"SRT 字幕批量生成 v{__version__}（faster-whisper）")
        self.root.geometry("860x660")
        self.root.minsize(760, 540)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_vars()
        self._build_ui()
        self._load_settings()
        self._apply_argv_path()
        self._set_running(False)

    # ---------------- UI 构建 ----------------
    def _build_vars(self) -> None:
        self.v_path = tk.StringVar()
        self.v_model = tk.StringVar(value="base")
        self.v_lang = tk.StringVar(value="auto")
        self.v_device = tk.StringVar(value="auto")
        self.v_compute = tk.StringVar(value="auto")
        self.v_ext = tk.StringVar()
        self.v_beam = tk.StringVar(value="5")
        self.v_gap = tk.StringVar(value="0.8")
        self.v_maxchars = tk.StringVar(value="50")
        self.v_overwrite = tk.BooleanVar(value=False)
        self.v_merge = tk.BooleanVar(value=True)
        self.v_cache = tk.BooleanVar(value=True)
        self.v_condprev = tk.BooleanVar(value=False)
        self.v_dryrun = tk.BooleanVar(value=False)
        self.v_status = tk.StringVar(value="就绪")

    def _build_ui(self) -> None:
        pad = {"padx": 8, "pady": 4}

        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="音频目录或单个音频：").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.v_path).grid(
            row=0, column=1, sticky="ew", padx=4)
        self.btn_dir = ttk.Button(top, text="选目录…", command=self._pick_dir)
        self.btn_dir.grid(row=0, column=2, padx=2)
        self.btn_file = ttk.Button(top, text="选音频文件…", command=self._pick_file)
        self.btn_file.grid(row=0, column=3, padx=2)
        top.columnconfigure(1, weight=1)

        opt = ttk.LabelFrame(self.root, text="参数")
        opt.pack(fill="x", **pad)
        self._opt_widgets: list = []

        def combo(parent, var, choices, width=9):
            return ttk.Combobox(parent, textvariable=var, values=choices,
                                width=width, state="readonly")

        def add_pair(parent, label, widget, after_pad=12):
            ttk.Label(parent, text=label).pack(side="left")
            widget.pack(side="left", padx=(2, after_pad))
            self._opt_widgets.append(widget)

        # 每行独立 Frame + pack：行间不共享列宽，窗口窄了也不互相挤压
        r1 = ttk.Frame(opt)
        r1.pack(fill="x", padx=4, pady=(4, 2))
        add_pair(r1, "模型", combo(r1, self.v_model, MODEL_CHOICES))
        add_pair(r1, "语言", combo(r1, self.v_lang, LANG_CHOICES, 7))
        add_pair(r1, "设备", combo(r1, self.v_device, DEVICE_CHOICES, 6))
        add_pair(r1, "计算类型", combo(r1, self.v_compute, COMPUTE_CHOICES, 6))

        r2 = ttk.Frame(opt)
        r2.pack(fill="x", padx=4, pady=2)
        add_pair(r2, "扩展名过滤",
                 ttk.Entry(r2, textvariable=self.v_ext, width=18), 16)
        add_pair(r2, "束宽beam",
                 ttk.Spinbox(r2, from_=1, to=32, width=4,
                             textvariable=self.v_beam), 16)
        add_pair(r2, "合并最大间隔(秒)",
                 ttk.Entry(r2, textvariable=self.v_gap, width=5), 16)
        add_pair(r2, "单条最大字数",
                 ttk.Entry(r2, textvariable=self.v_maxchars, width=5))
        ttk.Label(opt, text="（扩展名留空=全部支持格式，逗号分隔如 mp3,m4a；"
                            "束宽 CPU 求快可填 1）").pack(anchor="w", padx=4)

        r3 = ttk.Frame(opt)
        r3.pack(fill="x", padx=4, pady=(2, 6))

        def check(var, text):
            cb = ttk.Checkbutton(r3, text=text, variable=var)
            cb.pack(side="left", padx=(0, 10))
            self._opt_widgets.append(cb)
            return cb

        check(self.v_overwrite, "已有 .srt 也重做")
        check(self.v_merge, "合并碎段（建议开）")
        check(self.v_cache, "使用缓存")
        check(self.v_condprev, "喂回上文（易复读，不建议）")
        check(self.v_dryrun, "只列出文件")

        prog = ttk.Frame(self.root)
        prog.pack(fill="x", **pad)
        self.bar = ttk.Progressbar(prog, maximum=100.0)
        self.bar.pack(fill="x", side="top")
        ttk.Label(prog, textvariable=self.v_status, anchor="w").pack(
            fill="x", side="top", pady=(4, 0))

        btns = ttk.Frame(self.root)
        btns.pack(fill="x", padx=8)
        self.btn_start = ttk.Button(btns, text="开始生成", command=self._on_start)
        self.btn_start.pack(side="left", pady=4)
        self.btn_stop = ttk.Button(btns, text="停止", command=self._on_stop,
                                   state="disabled")
        self.btn_stop.pack(side="left", padx=8, pady=4)

        logf = ttk.LabelFrame(self.root, text="日志")
        logf.pack(fill="both", expand=True, padx=8, pady=(2, 8))
        self.txt = scrolledtext.ScrolledText(logf, height=12, wrap="word",
                                             state="disabled")
        self.txt.pack(fill="both", expand=True)

    # ---------------- 路径选择 ----------------
    def _pick_dir(self) -> None:
        init = self.v_path.get().strip().strip('"')
        if init and Path(init).is_file():
            init = str(Path(init).parent)
        d = filedialog.askdirectory(initialdir=init or str(Path.home()),
                                    title="选择音频目录（含子目录）")
        if d:
            self.v_path.set(d)

    def _pick_file(self) -> None:
        init = self.v_path.get().strip().strip('"')
        if init and Path(init).is_dir():
            init = str(init)
        f = filedialog.askopenfilename(
            initialdir=init or str(Path.home()),
            title="选择单个音频文件", filetypes=AUDIO_FILETYPES)
        if f:
            self.v_path.set(f)

    def _apply_argv_path(self) -> None:
        """支持把目录/文件拖到 exe 图标上：argv[1] 有就填进去。"""
        if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
            self.v_path.set(sys.argv[1])

    # ---------------- 参数收集 / 校验 ----------------
    def _current_settings(self) -> dict:
        return {
            "path": self.v_path.get().strip().strip('"'),
            "model": self.v_model.get(), "lang": self.v_lang.get(),
            "device": self.v_device.get(), "compute": self.v_compute.get(),
            "ext": self.v_ext.get().strip(),
            "beam": self.v_beam.get(), "gap": self.v_gap.get(),
            "maxchars": self.v_maxchars.get(),
            "overwrite": self.v_overwrite.get(), "merge": self.v_merge.get(),
            "cache": self.v_cache.get(), "condprev": self.v_condprev.get(),
            "dryrun": self.v_dryrun.get(),
        }

    def _collect_params(self) -> dict | None:
        s = self._current_settings()
        if not s["path"]:
            messagebox.showwarning("缺少路径", "请先选择音频目录或音频文件。")
            return None
        root = Path(s["path"])
        if not root.exists():
            messagebox.showerror("路径不存在", f"路径不存在：\n{root}")
            return None
        if s["model"] not in MODEL_CHOICES:
            messagebox.showerror("参数错误", f"模型必须是 {MODEL_CHOICES} 之一。")
            return None
        try:
            s["beam"] = int(s["beam"])
            assert s["beam"] >= 1
        except Exception:
            messagebox.showerror("参数错误", "束宽 beam 必须是 ≥1 的整数。")
            return None
        try:
            s["gap"] = float(s["gap"])
            assert s["gap"] >= 0
        except Exception:
            messagebox.showerror("参数错误", "合并最大间隔必须是 ≥0 的数字（秒）。")
            return None
        try:
            s["maxchars"] = int(s["maxchars"])
            assert s["maxchars"] >= 1
        except Exception:
            messagebox.showerror("参数错误", "单条最大字数必须是 ≥1 的整数。")
            return None
        return s

    # ---------------- 启动 / 停止 ----------------
    def _on_start(self) -> None:
        params = self._collect_params()
        if params is None:
            return
        self._save_settings(params)
        self.stop_event = threading.Event()
        self.total = 0
        self.cur_name = ""
        self._set_running(True)
        self._log_append("─" * 60)
        self.worker = threading.Thread(
            target=self._worker, args=(params, self.q, self.stop_event),
            daemon=True, name="srt-worker")
        self.worker.start()

    def _on_stop(self) -> None:
        if self.stop_event is not None:
            self.stop_event.set()
            self.v_status.set("正在停止（当前小段识别完即中断）…")
            self.btn_stop.config(state="disabled")

    def _set_running(self, running: bool) -> None:
        state_opt = "disabled" if running else "normal"
        for w in self._opt_widgets:
            try:
                w.config(state=state_opt)
            except Exception:
                pass
        self.btn_dir.config(state=state_opt)
        self.btn_file.config(state=state_opt)
        self.btn_start.config(state=state_opt)
        self.btn_stop.config(state="normal" if running else "disabled")
        if not running:
            self.bar["value"] = 0
            self.stop_event = None

    # ---------------- worker 线程 ----------------
    def _worker(self, params: dict, q: "queue.Queue[tuple]",
                stop_event: threading.Event) -> None:
        try:
            self._run_batch(params, q, stop_event)
        except Exception:                                  # noqa: BLE001
            q.put(("log", "发生未预期的异常："))
            for line in traceback.format_exc().splitlines():
                q.put(("log", line))
            q.put(("done", {"ok": 0, "fail": 0, "cached": 0, "elapsed": 0.0,
                            "stopped": stop_event.is_set(), "crash": True}))

    def _run_batch(self, params: dict, q: "queue.Queue[tuple]",
                   stop_event: threading.Event) -> None:
        """与 make_srt.main() 的批量逻辑一致，只是输出走队列。"""
        root = Path(params["path"])
        exts = {e.strip() for e in params["ext"].split(",") if e.strip()} or None
        audios = find_audios(root, exts)
        todo = [a for a in audios
                if params["overwrite"] or not a.with_suffix(".srt").exists()]
        q.put(("log", f"共扫描到 {len(audios)} 个音频，待处理 {len(todo)} 个"
                      + ("（只列出，不转写）" if params["dryrun"] else "")))
        for a in todo:
            q.put(("log", f"  {a}"))
        if params["dryrun"]:
            q.put(("done", {"ok": 0, "fail": 0, "cached": 0, "elapsed": 0.0,
                            "stopped": False, "dryrun": True,
                            "todo": len(todo)}))
            return
        if not todo:
            q.put(("log", "没有需要处理的文件：可能都已有同名 .srt，"
                          "勾选「已有 .srt 也重做」可强制重做。"))
            q.put(("done", {"ok": 0, "fail": 0, "cached": 0, "elapsed": 0.0,
                            "stopped": False}))
            return

        n = len(todo)
        q.put(("total", n))
        key_extra = f"beam={params['beam']}|cond={params['condprev']}"
        merge_on = params["merge"]
        ok = fail = cached_hits = 0
        t_start = time.time()

        for i, audio in enumerate(todo, 1):
            if stop_event.is_set():
                break
            srt_path = audio.with_suffix(".srt")
            q.put(("file", i, n, audio.name))
            try:
                key = cache_key(audio, params["model"], params["lang"],
                                extra=key_extra)
                cached = (load_cache(CACHE_DIR, key)
                          if params["cache"] else None)
                if cached is not None:
                    segments = cached
                    cached_hits += 1
                    q.put(("log", f"[{i}/{n}] {audio.name} ← 缓存命中"))
                else:
                    q.put(("log", f"[{i}/{n}] 识别 {audio.name} ..."))
                    t0 = time.time()

                    def on_progress(done_sec, total_sec, _i=i):
                        frac = done_sec / total_sec if total_sec else 0.0
                        q.put(("file_progress", _i, frac))

                    segments = transcribe_audio(
                        audio, model_name=params["model"],
                        lang=params["lang"], device=params["device"],
                        compute_type=params["compute"],
                        beam_size=params["beam"],
                        condition_on_previous=params["condprev"],
                        on_progress=on_progress,
                        should_stop=stop_event.is_set)
                    if stop_event.is_set():
                        q.put(("log",
                               f"已停止：{audio.name} 未完成，未写出字幕"))
                        break
                    q.put(("log", f"    耗时 {time.time() - t0:.0f}s"))
                    if params["cache"]:
                        save_cache(CACHE_DIR, key, segments)
                if merge_on:
                    segments = merge_segments(segments,
                                              max_gap=params["gap"],
                                              max_chars=params["maxchars"])
                write_srt(segments, srt_path)
                q.put(("log", f"    → {srt_path}（{len(segments)} 段）"))
                ok += 1
            except Exception as e:                         # noqa: BLE001
                q.put(("log", f"    失败: {e}"))
                fail += 1
            q.put(("overall", i / n))

        q.put(("done", {"ok": ok, "fail": fail, "cached": cached_hits,
                        "elapsed": time.time() - t_start,
                        "stopped": stop_event.is_set()}))

    # ---------------- 队列轮询（主线程） ----------------
    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._log_append(msg[1])
                elif kind == "total":
                    self.total = msg[1]
                elif kind == "file":
                    _, i, n, name = msg
                    self.total = n
                    self.cur_name = name
                    self.v_status.set(f"正在处理 {i}/{n}：{name}")
                    self._set_bar((i - 1) / n)
                elif kind == "file_progress":
                    _, i, frac = msg
                    if self.total:
                        self._set_bar((i - 1 + frac) / self.total)
                        self.v_status.set(
                            f"正在处理 {i}/{self.total}：{self.cur_name}"
                            f"（本文件 {frac * 100:.0f}%）")
                elif kind == "overall":
                    self._set_bar(msg[1])
                elif kind == "done":
                    self._on_done(msg[1])
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _on_done(self, s: dict) -> None:
        self._set_running(False)
        if s.get("dryrun"):
            text = f"扫描完成：待处理 {s.get('todo', 0)} 个（未转写）"
        elif s.get("stopped"):
            text = (f"已停止：成功 {s.get('ok', 0)}，失败 {s.get('fail', 0)}，"
                    f"耗时 {s.get('elapsed', 0):.0f}s")
        else:
            text = (f"完成：成功 {s.get('ok', 0)}"
                    f"（其中缓存命中 {s.get('cached', 0)}），"
                    f"失败 {s.get('fail', 0)}，总耗时 {s.get('elapsed', 0):.0f}s")
        self.v_status.set(text)
        self._log_append(text)
        if s.get("crash"):
            messagebox.showerror("异常", "处理过程中发生异常，详见窗口日志。")
        elif s.get("fail"):
            messagebox.showwarning("完成（有失败）", text)
        elif not s.get("stopped"):
            messagebox.showinfo("完成", text)

    def _set_bar(self, frac: float) -> None:
        self.bar["value"] = max(0.0, min(1.0, frac)) * 100.0

    def _log_append(self, text: str) -> None:
        self.txt.config(state="normal")
        self.txt.insert("end", text + "\n")
        self.txt.see("end")
        self.txt.config(state="disabled")

    # ---------------- 设置持久化 ----------------
    def _load_settings(self) -> None:
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return
        try:
            for key, var in (("path", self.v_path), ("model", self.v_model),
                             ("lang", self.v_lang), ("device", self.v_device),
                             ("compute", self.v_compute), ("ext", self.v_ext),
                             ("beam", self.v_beam), ("gap", self.v_gap),
                             ("maxchars", self.v_maxchars)):
                if isinstance(data.get(key), str):
                    var.set(data[key])
            for key, var in (("overwrite", self.v_overwrite),
                             ("merge", self.v_merge), ("cache", self.v_cache),
                             ("condprev", self.v_condprev),
                             ("dryrun", self.v_dryrun)):
                if isinstance(data.get(key), bool):
                    var.set(data[key])
        except Exception:
            pass

    def _save_settings(self, params: dict) -> None:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(
                json.dumps(params, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception:
            pass

    def _on_close(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            if not messagebox.askyesno(
                    "正在处理",
                    "任务还在进行中，退出会中断识别。\n确定退出吗？"):
                return
            if self.stop_event is not None:
                self.stop_event.set()
        self._save_settings(self._current_settings())
        self.root.destroy()

    def run(self) -> None:
        self.root.after(100, self._poll_queue)
        self.root.mainloop()


def main() -> int:
    # windowed exe（无控制台）里 stdout/stderr 可能是 None：logging/tqdm 往里写
    # 会炸，统一兜成 devnull（GUI 日志走队列，不依赖 stdout）
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            try:
                setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
            except Exception:
                pass

    q: "queue.Queue[tuple]" = queue.Queue()
    root_log = logging.getLogger()
    root_log.setLevel(logging.INFO)
    for h in list(root_log.handlers):   # 移除 import make_srt 时挂上的控制台 handler
        root_log.removeHandler(h)
    root_log.addHandler(QueueLogHandler(q))

    try:
        app = SrtGuiApp(q)
        app.run()
    except Exception:                                  # noqa: BLE001
        # 无控制台的 exe 里异常看不见，落一份日志方便排查
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            (CACHE_DIR / "gui_error.log").write_text(
                traceback.format_exc(), encoding="utf-8")
        except Exception:
            pass
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
