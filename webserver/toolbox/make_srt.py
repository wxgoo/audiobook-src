#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_srt — 批量给音频文件生成 SRT 字幕（v1.3，借鉴 OneAsr）。

用法：
    python3 make_srt.py <音频目录或单个音频> [选项]

示例：
    python3 make_srt.py /data/books/imports/一本好书 --model small --lang zh
    python3 make_srt.py ./audio --overwrite --ext mp3,m4a,wav
    python3 make_srt.py ./audio --preset short --beautify --script simplified
    python3 make_srt.py ./audio --ass --txt --events-json

行为：
  - 扫描目录（含子目录）里所有音频，逐个转写，输出「同目录同名.srt」
  - 已有同名 .srt 的文件默认跳过（--overwrite 强制重做）
  - v1.3：识别产出词/字级 timeline 并缓存；排版（预设/美化/字形）在
    写出前完成，改排版参数无需重新识别。可用 srt_tools.py render 纯重出。
  - NAS（CPU）上建议 --model base 或 small；机器快可上 medium/large-v3
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from srt_core import (SUBTITLE_PRESETS, build_timeline, cache_key,
                      convert_script, layout_timeline, load_timeline,
                      save_timeline, transcribe_audio,
                      write_ass, write_srt, write_txt, __version__)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("srt")

AUDIO_EXTS = {".mp3", ".m4a", ".m4b", ".wav", ".flac", ".ogg", ".opus",
              ".aac", ".wma", ".mp4", ".mkv", ".mov", ".webm", ".aiff", ".aif",
              # OneAsr v1.4.0 的 20 种媒体格式补齐（ffmpeg 都能解，扫描不到就不处理）
              ".flv", ".ts", ".mpeg", ".mpg", ".wmv", ".3gp"}
CACHE_DIR = Path.home() / ".cache" / "srt-tool"

_EVENTS = False


def _emit(kind: str, **kw) -> None:
    """机器可读事件（--events-json），思路来自 OneAsr 的 --events=json。"""
    if _EVENTS:
        try:
            print(json.dumps({"event": kind, **kw}, ensure_ascii=False),
                  flush=True)
        except Exception:
            pass


def find_audios(root: Path, exts: set[str] | None) -> list[Path]:
    # ★ v1.1 修复：入参统一小写 —— 原来只把比较侧 lower()，「--ext MP3」
    #   会得到 {".MP3"}，永远匹配不到 suffix.lower()，一个文件都扫不出来
    exts = {e if e.startswith(".") else f".{e}" for e in (exts or AUDIO_EXTS)}
    exts = {e.lower() for e in exts}
    if root.is_file():
        return [root]
    return sorted(p for p in root.rglob("*")
                  if p.suffix.lower() in exts and p.is_file())


def main() -> int:
    global _EVENTS
    ap = argparse.ArgumentParser(description="批量生成 SRT 字幕（faster-whisper，v1.3）")
    ap.add_argument("path", help="音频目录或单个音频文件")
    ap.add_argument("--model", default="base",
                    help="模型：tiny/base/small/medium/large-v3（默认 base）")
    ap.add_argument("--lang", default="auto",
                    help="语言：zh / en / yue / ja / ko / auto（默认 auto）")
    ap.add_argument("--ext", default=None,
                    help="只处理这些扩展名，逗号分隔（如 mp3,m4a）")
    ap.add_argument("--overwrite", action="store_true",
                    help="已有同名 .srt 也重新生成")
    ap.add_argument("--device", default="auto", help="auto / cpu / cuda")
    ap.add_argument("--compute-type", default="auto",
                    help="auto / int8 / float16（CPU 建议 int8）")
    ap.add_argument("--no-cache", action="store_true", help="不使用/不写缓存")
    ap.add_argument("--cache-dir", default=None,
                    help="缓存目录（默认 ~/.cache/srt-tool）")
    ap.add_argument("--beam-size", type=int, default=5,
                    help="束搜索宽度（默认 5；CPU 上求快可传 1）")
    ap.add_argument("--condition-previous", action="store_true",
                    help="把已识别文本喂回模型当上下文（旧行为；幻觉复读"
                         "多的时候千万别开，默认关）")
    ap.add_argument("--no-word-timestamps", action="store_true",
                    help="不取词级时间（默认取，用于精细字幕断行）")
    ap.add_argument("--hotwords", default=None,
                    help="热词/专有名词，逗号分隔（提升人名书名识别率）")
    ap.add_argument("--vad-min-silence", type=int, default=500,
                    help="VAD 静音阈值毫秒（默认 500）")
    ap.add_argument("--preset", default="standard",
                    choices=list(SUBTITLE_PRESETS),
                    help="字幕断行预设 short/standard/loose（默认 standard）")
    ap.add_argument("--beautify", action="store_true",
                    help="成稿美化：中英文数字间加空格、标点旁去空格")
    ap.add_argument("--script", default="original",
                    choices=["original", "simplified", "traditional"],
                    help="中文字形（需 opencc；默认 original 不动）")
    ap.add_argument("--no-merge", action="store_true",
                    help="不合并相邻碎段（默认合并成可读字幕）")
    ap.add_argument("--merge-gap", type=float, default=None,
                    help="覆盖预设的最大合并间隔秒数")
    ap.add_argument("--max-chars", type=int, default=None,
                    help="覆盖预设的单条字幕最大字符数")
    ap.add_argument("--output-dir", default=None,
                    help="输出目录（默认写在音频同目录）")
    ap.add_argument("--save-timeline", action="store_true",
                    help="额外写出 {stem}.timeline.json 边车（可用 srt_tools render 重排）")
    ap.add_argument("--ass", action="store_true", help="额外输出 ASS（逐词卡拉OK）")
    ap.add_argument("--txt", action="store_true", help="额外输出 TXT（一行一句）")
    ap.add_argument("--events-json", action="store_true",
                    help="stdout 输出机器可读事件（OneAsr --events=json 同思路）")
    ap.add_argument("--dry-run", action="store_true", help="只列出要处理的文件")
    args = ap.parse_args()
    _EVENTS = args.events_json

    # Windows 控制台默认 GBK，遇到生僻字文件名 print 会直接崩；
    # 统一兜到 UTF-8（失败不影响运行 —— 比如输出已被重定向成无 reconfigure 的对象）
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    root = Path(args.path)
    if not root.exists():
        log.error("路径不存在: %s", root)
        return 1

    cache_dir = Path(args.cache_dir) if args.cache_dir else CACHE_DIR
    exts = {e.strip() for e in args.ext.split(",")} if args.ext else None
    audios = find_audios(root, exts)
    todo = [a for a in audios
            if args.overwrite or not a.with_suffix(".srt").exists()]
    log.info("共 %d 个音频，待处理 %d 个%s",
             len(audios), len(todo),
             "" if not args.dry_run else "（dry-run，不执行）")
    for a in todo:
        print("  ", a)
    _emit("scan", total=len(audios), todo=len(todo))
    if args.dry_run or not todo:
        _emit("done", ok=0, fail=0, cached=0, elapsed=0.0)
        return 0

    # 影响识别结果的参数进缓存键：改了参数不再命中旧缓存；
    # 排版参数（preset/beautify/script）不进键 —— 改排版直接复用 timeline。
    key_extra = (f"beam={args.beam_size}|cond={args.condition_previous}"
                 f"|wt={not args.no_word_timestamps}"
                 f"|hot={args.hotwords or ''}|vad={args.vad_min_silence}")
    output_dir = Path(args.output_dir) if args.output_dir else None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    def on_progress(done_sec, total_sec):
        pct = (done_sec / total_sec * 100) if total_sec else 0
        log.info("    进度 %.0f%%（%.0f / %.0f 秒）", pct, done_sec, total_sec)
        _emit("stage", key="transcribing", pct=round(pct),
              done=round(done_sec, 1), total=round(total_sec or 0, 1))

    ok = fail = skipped_cache = 0
    total_start = time.time()
    for i, audio in enumerate(todo, 1):
        rel = audio.with_suffix(".srt") if output_dir is None \
            else output_dir / (audio.stem + ".srt")
        key = cache_key(audio, args.model, args.lang, extra=key_extra)
        tl = None if args.no_cache else load_timeline(cache_dir, key)
        try:
            if tl is not None:
                skipped_cache += 1
                log.info("[%d/%d] %s ← 缓存（timeline）", i, len(todo), audio.name)
            else:
                log.info("[%d/%d] 识别 %s ...", i, len(todo), audio.name)
                _emit("stage", key="loading_asr", index=i, total=len(todo))
                t0 = time.time()
                segments = transcribe_audio(
                    audio, model_name=args.model, lang=args.lang,
                    device=args.device, compute_type=args.compute_type,
                    beam_size=args.beam_size,
                    condition_on_previous=args.condition_previous,
                    word_timestamps=not args.no_word_timestamps,
                    hotwords=args.hotwords,
                    vad_min_silence_ms=args.vad_min_silence,
                    on_progress=on_progress)
                log.info("    耗时 %.0fs", time.time() - t0)
                duration = None
                tl = build_timeline(segments, source=audio.name,
                                    language=args.lang)
                if not args.no_cache:
                    save_timeline(cache_dir, key, tl)

            if args.no_merge:
                # 旧路径：完全保留 v1.1「不合并」的段级语义
                from srt_core import beautify_text
                cues = []
                for s in (tl.get("segments") or []):
                    s = dict(s)
                    if args.beautify:
                        s["text"] = beautify_text(s.get("text", ""))
                    if args.script != "original":
                        s["text"] = convert_script(s.get("text", ""),
                                                   args.script)
                    cues.append(s)
            else:
                # ★ v1.3：OneAsr 式排版 —— timeline → 预设断行
                cues = layout_timeline(
                    tl, preset=args.preset, max_chars=args.max_chars,
                    max_gap=args.merge_gap, beautify=args.beautify,
                    script=args.script)

            write_srt(cues, rel)
            written = [str(rel)]
            if args.ass:
                p = rel.with_suffix(".ass")
                write_ass(cues, p)
                written.append(str(p))
            if args.txt:
                p = rel.with_suffix(".txt")
                write_txt(cues, p)
                written.append(str(p))
            if args.save_timeline:
                p = rel.with_suffix(".timeline.json")
                p.write_text(json.dumps(tl, ensure_ascii=False, indent=1),
                             encoding="utf-8")
                written.append(str(p))
            log.info("    → %s（%d 段）", rel, len(cues))
            _emit("export", output=str(rel), cues=len(cues),
                  extra=written[1:])
            ok += 1
        except KeyboardInterrupt:
            log.warning("手动中断，已完成 %d 个", ok)
            _emit("error", message="interrupted", ok=ok)
            return 130
        except Exception as e:                       # noqa: BLE001
            log.error("    失败: %s", e)
            _emit("error", message=str(e), file=audio.name)
            fail += 1

    elapsed = time.time() - total_start
    log.info("完成（srt-core v%s）：成功 %d（其中缓存命中 %d），失败 %d，"
             "总耗时 %.0fs", __version__, ok, skipped_cache, fail, elapsed)
    _emit("done", ok=ok, fail=fail, cached=skipped_cache, elapsed=round(elapsed, 1))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
