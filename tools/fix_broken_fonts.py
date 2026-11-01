#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""批量清扫书库里的「坏字体 epub」。

## 这是什么

calibre 从 PDF/DJVU 转 epub 时，会把带子集加密保护的字体原样搬进输出包，
这些文件以 ASCII `FONT` 开头（0x464F4E54），不是合法 sfnt。浏览器 OTS 一律
拒绝加载：

    OTS parsing error: invalid sfntVersion: 1179602516

数据本体熵 7.992 bits/byte、256 个字节值全出现，是加密后的死数据，**无法还原**。
实测一本 3.11MB 的繁体《哈利波特》里有 1.66MB（53%）是这种死数据 —— 下载
量翻倍、弱网下打开要 50s 以上。删掉后正文改用系统字体，视觉上没有区别。

正确处理方式就是**删掉它**，顺带清掉引用它的 @font-face 和 OPF manifest 项。

## 与线上两条链路的关系

本工具处理的是**存量旧书**（三者共用 `webserver/services/epub_font_fix.py`）：

| 场景 | 入口 | 时机 |
|---|---|---|
| 新书转换 | `services/converter.py` / `services/batch_convert.py` | ebook-convert 出包后 |
| 旧书下载 | `handlers/book.py::BookDownload.epub_lite_path` | 首次下载时按需生成副本 |
| 存量清扫 | **本脚本** | 手动/定时批量 |

即使不跑本脚本，旧书首次下载时也会自动生成精简副本；本脚本的价值是把
副本提前生成好、把磁盘上的原文件也一并瘦身（省空间，同时让 OPDS/直链
下载等其他出口也受益）。

## 安全性

* **默认 dry-run**，只报告不写盘；必须显式 `--apply` 才真正修改；
* 改前自动备份为 `<书名>.epub.bak`（`--no-backup` 可关，不建议）；
* 先写临时文件 → 校验（zip 完整 + 坏字体确已清空）→ 才替换原文件，
  中途失败原文件不动；
* 只动 `.epub`，其他格式（pdf/mobi/azw3）完全不碰；
* 不依赖 calibre / mybooks 运行时，拷到任何有 python3 的机器都能跑。

## 用法

    # 1) 先看有哪些书中招（不写盘）
    python3 tools/fix_broken_fonts.py /data/books/library

    # 2) 确认无误后真改
    python3 tools/fix_broken_fonts.py /data/books/library --apply

    # 3) 容器内跑，路径用容器内路径
    docker exec -it <容器名> python3 /var/www/mybooks/tools/fix_broken_fonts.py \\
        /data/books/library --apply

    # 4) 只处理单本书 / 只要报告不要备份
    python3 tools/fix_broken_fonts.py book.epub --apply --no-backup

    # 5) 机读输出（给监控/定时任务用）
    python3 tools/fix_broken_fonts.py /data/books/library --json

退出码：0 正常（含「没有坏字体」）、1 有文件处理失败、2 参数/路径错误。
"""

import argparse
import json
import os
import sys
import time

# 允许直接 `python3 tools/fix_broken_fonts.py` 从仓库根跑
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from webserver.services.epub_font_fix import (
        strip_from_epub_file,
        find_broken_fonts,
    )
except ImportError:
    # 脱离 mybooks 仓库单独跑时（比如拷到 NAS 上），按路径直接加载模块。
    # 那个模块是自包含的，不 import 任何 webserver 里的东西。
    import importlib.util

    _mod_path = os.path.join(_ROOT, "webserver", "services", "epub_font_fix.py")
    if not os.path.exists(_mod_path):
        sys.exit("错误：找不到 webserver/services/epub_font_fix.py，请在仓库根目录运行。")
    _spec = importlib.util.spec_from_file_location("epub_font_fix", _mod_path)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    strip_from_epub_file = _mod.strip_from_epub_file
    find_broken_fonts = _mod.find_broken_fonts


def human(n):
    """字节数转人话。"""
    if n is None:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.2f}{unit}"
        n /= 1024.0
    return f"{n:.2f}GB"


def iter_epubs(paths, recursive):
    """展开输入，产出所有 epub 绝对路径（去重、保持稳定顺序）。"""
    seen = set()
    for p in paths:
        p = os.path.abspath(os.path.expanduser(p))
        if os.path.isfile(p):
            if p.lower().endswith(".epub"):
                if p not in seen:
                    seen.add(p)
                    yield p
            continue
        if not os.path.isdir(p):
            print(f"跳过（不存在）: {p}", file=sys.stderr)
            continue
        if recursive:
            for root, dirs, files in os.walk(p):
                dirs.sort()
                for fn in sorted(files):
                    if fn.lower().endswith(".epub"):
                        full = os.path.join(root, fn)
                        if full not in seen:
                            seen.add(full)
                            yield full
        else:
            for fn in sorted(os.listdir(p)):
                full = os.path.join(p, fn)
                if os.path.isfile(full) and fn.lower().endswith(".epub"):
                    if full not in seen:
                        seen.add(full)
                        yield full


def probe(path):
    """只读检查：返回坏字体条目列表，读不了返回 None。"""
    import zipfile

    try:
        with zipfile.ZipFile(path, "r") as zf:
            return find_broken_fonts(zf)
    except Exception:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="fix_broken_fonts.py",
        description="扫描并剥离 epub 里的坏字体（calibre FONT 加密占位，浏览器无法加载）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="默认 dry-run，只报告不写盘；确认后加 --apply。",
    )
    ap.add_argument("paths", nargs="+", help="书库目录或单个 epub 文件（可多个）")
    ap.add_argument("--apply", action="store_true",
                    help="真正修改文件（不加则只做 dry-run 报告）")
    ap.add_argument("--recursive", "-r", action="store_true",
                    help="递归子目录（书库是 author/title 两级结构，扫全库需要加）")
    ap.add_argument("--no-backup", action="store_true",
                    help="不留 .bak 备份（默认留，出问题可找回）")
    ap.add_argument("--quiet", "-q", action="store_true",
                    help="只输出汇总，不逐本打印")
    ap.add_argument("--json", action="store_true",
                    help="输出机器可读 JSON（给定时任务/监控用）")
    args = ap.parse_args(argv)

    # 先校验路径，参数错误用退出码 2 与「有文件失败」区分开
    bad_paths = [p for p in args.paths
                 if not os.path.exists(os.path.expanduser(p))]
    if bad_paths:
        for p in bad_paths:
            print(f"错误：路径不存在 {p}", file=sys.stderr)
        return 2

    backup_suffix = None if args.no_backup else ".bak"
    started = time.time()

    total = 0
    dirty = 0          # 含坏字体
    changed = 0        # 实际处理成功
    failed = 0         # 处理失败
    unreadable = 0     # 打不开的 zip
    bytes_before = 0
    bytes_after = 0
    fonts_total = 0
    results = []

    for path in iter_epubs(args.paths, args.recursive):
        total += 1
        broken = probe(path)
        # 单个目录入参时显示相对路径（书库层级深，全路径太长）；
        # 传的是文件、或传了多个路径时显示原路径，避免看不出是哪本。
        if len(args.paths) == 1 and os.path.isdir(os.path.expanduser(args.paths[0])):
            rel = os.path.relpath(path, os.path.abspath(os.path.expanduser(args.paths[0])))
        else:
            rel = path

        if broken is None:
            unreadable += 1
            if not args.json and not args.quiet:
                print(f"[坏包] {rel}  ← 无法作为 zip 读取，跳过")
            results.append({"file": path, "status": "bad_zip"})
            continue

        if not broken:
            if not args.quiet and not args.json:
                print(f"[干净] {rel}")
            results.append({"file": path, "status": "clean"})
            continue

        dirty += 1
        size_before = os.path.getsize(path)
        font_bytes = 0
        import zipfile
        try:
            with zipfile.ZipFile(path, "r") as zf:
                for n in broken:
                    font_bytes += zf.getinfo(n).file_size
        except Exception:
            pass

        if not args.apply:
            if not args.json and not args.quiet:
                pct = font_bytes / size_before * 100 if size_before else 0
                print(f"[待修] {rel}\n"
                      f"       {len(broken)} 个坏字体 {human(font_bytes)}"
                      f"（占全书 {pct:.0f}%），{human(size_before)} → 预计 "
                      f"{human(size_before - font_bytes * 0.98)}")
            results.append({
                "file": path, "status": "would_fix",
                "fonts": len(broken), "font_bytes": font_bytes,
                "size": size_before,
            })
            # 预估收益：被删掉的字体数据在 zip 里基本是压不动的（熵接近 8），
            # 所以原样算作节省量。整包体积还受重压缩影响，这里只做保守估计。
            bytes_before += size_before
            bytes_after += size_before - font_bytes
            fonts_total += len(broken)
            continue

        stats = strip_from_epub_file(path, backup_suffix=backup_suffix)
        if stats.get("changed"):
            changed += 1
            fonts_total += len(stats.get("fonts", []))
            bytes_before += stats["before"]
            bytes_after += stats["after"]
            if not args.json and not args.quiet:
                pct = (1 - stats["after"] / stats["before"]) * 100 if stats["before"] else 0
                print(f"[已修] {rel}\n"
                      f"       {len(stats.get('fonts', []))} 个坏字体，"
                      f"{human(stats['before'])} → {human(stats['after'])}"
                      f"（省 {pct:.0f}%）")
            results.append({"file": path, "status": "fixed", **stats})
        else:
            failed += 1
            if not args.json and not args.quiet:
                print(f"[失败] {rel}  ← {stats.get('reason', 'unknown')}")
            results.append({"file": path, "status": "error",
                            "reason": stats.get("reason")})

    elapsed = time.time() - started
    saved = bytes_before - bytes_after

    if args.json:
        print(json.dumps({
            "total": total, "dirty": dirty, "changed": changed,
            "failed": failed, "unreadable": unreadable,
            "fonts": fonts_total,
            "bytes_before": bytes_before, "bytes_after": bytes_after,
            "bytes_saved": saved, "elapsed_ms": int(elapsed * 1000),
            "dry_run": not args.apply,
            "items": results,
        }, ensure_ascii=False, indent=2))
        return 1 if failed else 0

    print("\n" + "=" * 62)
    mode = "DRY-RUN（未写盘，确认后加 --apply）" if not args.apply else "已写入"
    print(f"扫描 {total} 本 · 含坏字体 {dirty} 本 · 处理成功 {changed} 本"
          f" · 失败 {failed} · 无法读取 {unreadable}")
    if dirty:
        print(f"坏字体共 {fonts_total} 个；体积 {human(bytes_before)} → {human(bytes_after)}"
              f"，节省 {human(saved)}"
              + (f"（{saved / bytes_before * 100:.1f}%）" if bytes_before else ""))
    print(f"耗时 {elapsed:.2f}s · {mode}")
    if not args.apply and dirty:
        print("\n下一步：把命令里的路径原样再加上 --apply 即可执行。")
    print("=" * 62)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
