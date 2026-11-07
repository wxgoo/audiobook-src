#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_srt — 批量给音频文件生成 SRT 字幕。

用法：
    python3 make_srt.py <音频目录或单个音频> [选项]

示例：
    python3 make_srt.py /data/books/imports/一本好书 --model small --lang zh
    python3 make_srt.py ./audio --overwrite --ext mp3,m4a,wav

行为：
  - 扫描目录（含子目录）里所有音频，逐个转写，输出「同目录同名.srt」
  - 已有同名 .srt 的文件默认跳过（--overwrite 强制重做）
  - 识别结果缓存到 ~/.cache/srt-tool/，参数没变重复跑不重新识别
  - NAS（CPU）上建议 --model base 或 small；机器快可上 medium/large-v3
  - v1.1：相邻碎段自动合并成可读字幕（--no-merge 关闭）；
    默认关闭「上文条件」（幻觉复读的根源，--condition-previous 恢复旧行为）
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from srt_core import (cache_key, load_cache, merge_segments, save_cache,
                      transcribe_audio, write_srt, __version__)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("srt")

AUDIO_EXTS = {".mp3", ".m4a", ".m4b", ".wav", ".flac", ".ogg", ".opus",
              ".aac", ".wma", ".mp4", ".mkv"}
CACHE_DIR = Path.home() / ".cache" / "srt-tool"


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
    ap = argparse.ArgumentParser(description="批量生成 SRT 字幕（faster-whisper）")
    ap.add_argument("path", help="音频目录或单个音频文件")
    ap.add_argument("--model", default="base",
                    help="模型：tiny/base/small/medium/large-v3（默认 base）")
    ap.add_argument("--lang", default="auto",
                    help="语言：zh / en / auto（默认 auto）")
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
    ap.add_argument("--no-merge", action="store_true",
                    help="不合并相邻碎段（默认合并成可读字幕）")
    ap.add_argument("--merge-gap", type=float, default=0.8,
                    help="合并允许的最大间隔秒数（默认 0.8）")
    ap.add_argument("--max-chars", type=int, default=50,
                    help="单条字幕最大字符数（默认 50）")
    ap.add_argument("--dry-run", action="store_true", help="只列出要处理的文件")
    args = ap.parse_args()

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
    if args.dry_run or not todo:
        return 0

    # 影响识别结果的参数进缓存键：改了参数不再命中旧缓存
    key_extra = f"beam={args.beam_size}|cond={args.condition_previous}"
    merge_on = not args.no_merge

    def on_progress(done_sec, total_sec):
        pct = (done_sec / total_sec * 100) if total_sec else 0
        log.info("    进度 %.0f%%（%.0f / %.0f 秒）", pct, done_sec, total_sec)

    ok = fail = skipped_cache = 0
    total_start = time.time()
    for i, audio in enumerate(todo, 1):
        rel = audio.with_suffix(".srt")
        key = cache_key(audio, args.model, args.lang, extra=key_extra)
        cached = None if args.no_cache else load_cache(cache_dir, key)
        try:
            if cached is not None:
                segments = cached
                skipped_cache += 1
                log.info("[%d/%d] %s ← 缓存", i, len(todo), audio.name)
            else:
                log.info("[%d/%d] 识别 %s ...", i, len(todo), audio.name)
                t0 = time.time()
                segments = transcribe_audio(
                    audio, model_name=args.model, lang=args.lang,
                    device=args.device, compute_type=args.compute_type,
                    beam_size=args.beam_size,
                    condition_on_previous=args.condition_previous,
                    on_progress=on_progress)
                log.info("    耗时 %.0fs", time.time() - t0)
                if not args.no_cache:
                    save_cache(cache_dir, key, segments)
            if merge_on:
                segments = merge_segments(segments,
                                          max_gap=args.merge_gap,
                                          max_chars=args.max_chars)
            write_srt(segments, rel)
            log.info("    → %s（%d 段）", rel, len(segments))
            ok += 1
        except KeyboardInterrupt:
            log.warning("手动中断，已完成 %d 个", ok)
            return 130
        except Exception as e:                       # noqa: BLE001
            log.error("    失败: %s", e)
            fail += 1

    log.info("完成（srt-core v%s）：成功 %d（其中缓存命中 %d），失败 %d，"
             "总耗时 %.0fs", __version__, ok, skipped_cache, fail,
             time.time() - total_start)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
