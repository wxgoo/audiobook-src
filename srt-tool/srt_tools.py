#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""srt_tools — 不跑模型的字幕后期工具（借鉴 OneAsr 的子命令设计）。

  render    读 {stem}.timeline.json，只重排版面，重新出 SRT / ASS / TXT。
            改预设 / 美化 / 字形不用重新识别，也不用音频。
  transcript 读 / 摘要 / 智能断句 / 美化一份文稿（txt 或 srt），不跑流水线。
  align     音视频 + 你自己的文稿 → 带时间轴的字幕（文稿分行就是字幕分行）。
            用 faster-whisper 的词级时间 + 序列匹配近似 ForcedAligner；
            文稿与音频一致的有声书效果最好。
  status    打印版本 / 缓存目录 / 可选依赖状态（机器可读 --json）。

用法示例：
  python srt_tools.py render --timeline book.timeline.json --preset short --beautify
  python srt_tools.py transcript split --input book.txt --preset standard --output book.split.txt
  python srt_tools.py align --audio book.mp3 --text book.txt --output book.srt
  python srt_tools.py status --json
"""
from __future__ import annotations

import argparse
import codecs
import json
import re
import sys
from pathlib import Path

from srt_core import (SUBTITLE_PRESETS, __version__, beautify_text,
                      convert_script, has_script_converter, layout_timeline,
                      write_ass, write_srt, write_txt)
from make_srt import AUDIO_EXTS, CACHE_DIR

_SRT_TIME = re.compile(r"^\s*\d{2}:\d{2}:\d{2}[,.]\d+\s*-->\s*")


# ---------------- 文稿读写 ----------------
def _read_text_smart(p: Path) -> str:
    """按文件自身编码读文稿（OneAsr v1.4.2 同款思路）。

    顺序：BOM 精确识别（utf-8-sig / utf-16）→ 严格 utf-8 → 中文常见
    gb18030（Windows 记事本 ANSI 默认）。都失败才报错并说明原因，
    不再 silent mojibake——以前 GBK 文稿走 errors="replace" 全变乱码。
    """
    data = p.read_bytes()
    if not data:
        return ""
    # BOM 头精确识别（BOM 存在时编码不容歧义）
    for bom, enc in ((codecs.BOM_UTF8, "utf-8-sig"),
                     (codecs.BOM_UTF32_LE, "utf-32"),
                     (codecs.BOM_UTF32_BE, "utf-32"),
                     (codecs.BOM_LE, "utf-16"),
                     (codecs.BOM_BE, "utf-16")):
        if data.startswith(bom):
            try:
                return data.decode(enc)
            except UnicodeDecodeError as e:
                raise ValueError(f"{p.name}：带 BOM 的 {enc} 文稿解码失败（{e}），请检查文件是否损坏") from e
    # 无 BOM：严格 utf-8 → gb18030 逐级尝试
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("gb18030")   # gb18030 是 GBK/GB2312 的超集
    except UnicodeDecodeError as e:
        raise ValueError(f"{p.name}：文稿不是 UTF-8/GBK/GB18030 编码（{e}），"
                         "请在编辑器里另存为 UTF-8 后重试") from e


def read_transcript(path: Path | str) -> list[str]:
    """读 .txt / .srt 文稿；.srt 丢掉序号与时间行，只留文本行。"""
    p = Path(path)
    raw = _read_text_smart(p)
    if p.suffix.lower() == ".srt":
        lines = []
        for ln in raw.splitlines():
            s = ln.strip()
            if not s or s.isdigit() or _SRT_TIME.match(ln):
                continue
            lines.append(s)
        return lines
    return [ln.strip() for ln in raw.splitlines() if ln.strip()]


def write_transcript(lines: list[str], path: Path | str) -> Path:
    p = Path(path)
    p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return p


def split_long_line(line: str, max_chars: int) -> list[str]:
    """只拆过长行；优先在标点处断，绝不改字（OneAsr transcript split 思路）。"""
    line = line.strip()
    if len(line) <= max_chars:
        return [line]
    out, buf = [], ""
    for ch in line:
        if len(buf) >= max_chars:          # 硬断：绝不超过上限
            out.append(buf.strip())
            buf = ""
        buf += ch
        if len(buf) >= max_chars and ch in "。！？!?；;…":
            out.append(buf.strip())
            buf = ""
        elif len(buf) >= max_chars - 2 and ch in "，,、：:":
            out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return [x for x in out if x]


# ---------------- 子命令 ----------------
def cmd_render(ap: argparse.Namespace) -> int:
    tl_path = Path(ap.timeline)
    data = json.loads(tl_path.read_text(encoding="utf-8"))
    if isinstance(data, list):                      # 兼容旧纯段列表边车
        from srt_core import build_timeline
        data = build_timeline(data)
    cues = layout_timeline(
        data, preset=ap.preset, max_chars=ap.max_chars, max_gap=ap.merge_gap,
        beautify=ap.beautify, script=ap.script)
    stem = tl_path.with_suffix("")
    if stem.name.endswith(".timeline"):   # a.timeline.json → a.srt
        stem = stem.with_name(stem.name[:-len(".timeline")])
    base = ap.output or str(stem)
    made = []
    if not ap.no_srt:
        made.append(str(write_srt(cues, base + ".srt")))
    if ap.ass:
        made.append(str(write_ass(cues, base + ".ass")))
    if ap.txt:
        made.append(str(write_txt(cues, base + ".txt")))
    if ap.json:
        print(json.dumps({"cues": len(cues), "outputs": made},
                         ensure_ascii=False))
    else:
        for m in made:
            print("[render]", m, f"({len(cues)} 段)")
    return 0


def cmd_transcript(ap: argparse.Namespace) -> int:
    lines = read_transcript(ap.input)
    if ap.action == "inspect":
        chars = sum(len(x) for x in lines)
        info = {"lines": len(lines), "chars": chars,
                "preview": lines[:3]}
        if ap.audio_seconds:
            sec = float(ap.audio_seconds)
            info["audio_seconds"] = sec
            info["chars_per_min"] = round(chars / sec * 60, 1) if sec else None
        print(json.dumps(info, ensure_ascii=False) if ap.json else
              f"行数 {len(lines)}，字数 {chars}"
              + (f"，语速 {info['chars_per_min']} 字/分钟" if sec else ""))
        return 0
    if ap.action == "split":
        cfg = SUBTITLE_PRESETS.get(ap.preset, SUBTITLE_PRESETS["standard"])
        limit = ap.max_chars or cfg["max_chars"]
        out = []
        for ln in lines:
            out.extend(split_long_line(ln, limit))
        target = ap.output
        if target:
            write_transcript(out, target)
        if ap.json:
            print(json.dumps({"lines_before": len(lines),
                              "lines_after": len(out),
                              "output": str(target) if target else None,
                              "preview": out[:5]}, ensure_ascii=False))
        else:
            print(f"断句：{len(lines)} → {len(out)} 行"
                  + (f" → {target}" if target else ""))
            if not target:
                print("\n".join(out))
        return 0
    if ap.action == "beautify":
        out = []
        for ln in lines:
            t = beautify_text(ln, spaced=not ap.no_space)
            if ap.script != "original":
                t = convert_script(t, ap.script)
            out.append(t)
        target = ap.output
        if target:
            write_transcript(out, target)
        if ap.json:
            print(json.dumps({"lines": len(out),
                              "output": str(target) if target else None,
                              "preview": out[:5]}, ensure_ascii=False))
        else:
            print(f"美化 {len(out)} 行" + (f" → {target}" if target else ""))
            if not target:
                print("\n".join(out))
        return 0
    return 2


def cmd_align(ap: argparse.Namespace) -> int:
    from srt_align import align_transcript
    lines = read_transcript(Path(ap.text))
    cues = align_transcript(
        ap.audio, lines, model_name=ap.model, lang=ap.lang,
        device=ap.device, compute_type=ap.compute_type,
        beam_size=ap.beam_size, hotwords=ap.hotwords,
        beautify=ap.beautify, script=ap.script,
        preset=ap.preset)
    out = Path(ap.output) if ap.output else Path(ap.audio).with_suffix(".srt")
    write_srt(cues, out)
    if ap.ass:
        write_ass(cues, out.with_suffix(".ass"))
    print(f"[align] {len(cues)} 条 → {out}"
          + ("（文稿匹配度低时时间轴为近似值）" if cues and cues[0].get("approx")
             else ""))
    return 0


def cmd_status(ap: argparse.Namespace) -> int:
    info = {
        "version": __version__,
        "cache_dir": str(ap.cache_dir or CACHE_DIR),
        "audio_exts": sorted(AUDIO_EXTS),
        "presets": sorted(SUBTITLE_PRESETS),
        "opencc": has_script_converter(),
        "faster_whisper": _module_ok("faster_whisper"),
    }
    print(json.dumps(info, ensure_ascii=False, indent=2) if ap.json else
          "\n".join(f"{k}: {v}" for k, v in info.items()))
    return 0


def _module_ok(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="srtmake 字幕后期工具 v" + __version__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="用 timeline 重新排版出字幕（不跑模型）")
    r.add_argument("--timeline", required=True, help="{stem}.timeline.json")
    r.add_argument("--preset", default="standard", choices=list(SUBTITLE_PRESETS))
    r.add_argument("--max-chars", type=int)
    r.add_argument("--merge-gap", type=float)
    r.add_argument("--beautify", action="store_true")
    r.add_argument("--script", default="original",
                   choices=["original", "simplified", "traditional"])
    r.add_argument("--output", help="输出前缀（默认同 timeline，去掉扩展名）")
    r.add_argument("--no-srt", action="store_true")
    r.add_argument("--ass", action="store_true")
    r.add_argument("--txt", action="store_true")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_render)

    t = sub.add_parser("transcript", help="文稿摘要 / 智能断句 / 美化")
    ts = t.add_subparsers(dest="action", required=True)
    ti = ts.add_parser("inspect", help="行数 / 字数 / 语速摘要")
    ti.add_argument("--input", required=True)
    ti.add_argument("--audio-seconds", type=float)
    ti.add_argument("--json", action="store_true")
    ti.set_defaults(func=cmd_transcript)
    tsp = ts.add_parser("split", help="只拆过长行，不写回原文件")
    tsp.add_argument("--input", required=True)
    tsp.add_argument("--preset", default="standard", choices=list(SUBTITLE_PRESETS))
    tsp.add_argument("--max-chars", type=int)
    tsp.add_argument("--output")
    tsp.add_argument("--json", action="store_true")
    tsp.set_defaults(func=cmd_transcript)
    tb = ts.add_parser("beautify", help="标点归位 + 中英文空格 + 简繁")
    tb.add_argument("--input", required=True)
    tb.add_argument("--script", default="original",
                    choices=["original", "simplified", "traditional"])
    tb.add_argument("--no-space", action="store_true", help="不要中英文间空格")
    tb.add_argument("--output")
    tb.add_argument("--json", action="store_true")
    tb.set_defaults(func=cmd_transcript)

    a = sub.add_parser("align", help="音视频 + 文稿 → 字幕（跳过识别文字）")
    a.add_argument("--audio", required=True)
    a.add_argument("--text", required=True, help=".txt / .srt，一行=一条字幕")
    a.add_argument("--model", default="base")
    a.add_argument("--lang", default="zh")
    a.add_argument("--device", default="auto")
    a.add_argument("--compute-type", default="auto")
    a.add_argument("--beam-size", type=int, default=5)
    a.add_argument("--hotwords")
    a.add_argument("--preset", default="standard", choices=list(SUBTITLE_PRESETS))
    a.add_argument("--beautify", action="store_true")
    a.add_argument("--script", default="original",
                   choices=["original", "simplified", "traditional"])
    a.add_argument("--output")
    a.add_argument("--ass", action="store_true")
    a.set_defaults(func=cmd_align)

    s = sub.add_parser("status", help="安装 / 依赖 / 缓存状态")
    s.add_argument("--cache-dir")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_status)
    return ap


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ns = build_parser().parse_args()
    try:
        return ns.func(ns)
    except Exception as e:                          # noqa: BLE001
        print(f"[srt_tools] 失败: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
