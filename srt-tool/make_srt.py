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
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from srt_core import (cache_key, load_cache, save_cache, transcribe_audio,
                      write_srt)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("srt")

AUDIO_EXTS = {".mp3", ".m4a", ".m4b", ".wav", ".flac", ".ogg", ".opus",
              ".aac", ".wma", ".mp4", ".mkv"}
CACHE_DIR = Path.home() / ".cache" / "srt-tool"


def find_audios(root: Path, exts: set[str] | None) -> list[Path]:
    exts = {e if e.startswith(".") else f".{e}" for e in (exts or AUDIO_EXTS)}
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
    ap.add_argument("--dry-run", action="store_true", help="只列出要处理的文件")
    args = ap.parse_args()

    root = Path(args.path)
    if not root.exists():
        log.error("路径不存在: %s", root)
        return 1

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

    # 先加载模型（缓存命中的文件不算任务，但模型加载一次即可）
    ok = fail = skipped_cache = 0
    total_start = time.time()
    for i, audio in enumerate(todo, 1):
        rel = audio.with_suffix(".srt")
        key = cache_key(audio, args.model, args.lang)
        cached = None if args.no_cache else load_cache(CACHE_DIR, key)
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
                    device=args.device, compute_type=args.compute_type)
                log.info("    耗时 %.0fs", time.time() - t0)
                if not args.no_cache:
                    save_cache(CACHE_DIR, key, segments)
            write_srt(segments, rel)
            log.info("    → %s（%d 段）", rel, len(segments))
            ok += 1
        except KeyboardInterrupt:
            log.warning("手动中断，已完成 %d 个", ok)
            return 130
        except Exception as e:                       # noqa: BLE001
            log.error("    失败: %s", e)
            fail += 1

    log.info("完成：成功 %d（其中缓存命中 %d），失败 %d，总耗时 %.0fs",
             ok, skipped_cache, fail, time.time() - total_start)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
