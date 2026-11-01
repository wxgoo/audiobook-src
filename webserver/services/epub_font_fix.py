#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""坏字体（calibre `FONT` 加密占位）识别与剥离。

## 问题

calibre 从 PDF/DJVU 转 epub 时，若源文件的字体带有子集加密保护，它会把这些
字体原样搬进输出 epub，文件以 ASCII `FONT` 开头：

    46 4f 4e 54 | 00 0d 3b d8 | 00 00 00 03 | 00 00 00 2c | 00 00 00 14
       "FONT"   |  原始大小    |   段数 3    |     44      |     20

这类文件不是合法 sfnt，浏览器 OTS 直接拒绝：

    OTS parsing error: invalid sfntVersion: 1179602516      （0x464F4E54 = "FONT"）

数据本体熵接近 8.0 bits/byte、256 个字节值全部出现，是加密/混淆后的数据，
**无法还原**（4.6.0-9 实测：zlib / raw-deflate / gzip 各 5 个偏移全部失败，
fonttools 报 bad sfntVersion）。所以正确处理方式是**删除**，不是修复。

单本实测代价：一本 3.11MB 的繁体 epub 里 1.66MB（53%）是这种死数据。
删掉后正文改用系统字体，视觉效果没有区别，但下载量直接减半。

## 三处调用

- 转换流程（新书）：`strip_from_epub_file()` 在 ebook-convert 出包后处理
- 下载流程（旧书）：`build_stripped_epub()` 按需生成精简副本
- 命令行工具：`tools/fix_broken_fonts.py` 批量清扫书库
"""

import logging
import os
import re
import shutil
import tempfile
import zipfile

logger = logging.getLogger(__name__)

# 合法 sfnt 头部魔数（浏览器 OTS 能接受的集合）
SFNT_MAGIC = (
    b"\x00\x01\x00\x00",  # TrueType
    b"OTTO",              # CFF / OpenType
    b"true",              # TrueType (Apple)
    b"ttcf",              # TrueType Collection
    b"wOFF",              # WOFF
    b"wOF2",              # WOFF2
)

FONT_EXTS = (".ttf", ".otf", ".woff", ".woff2", ".ttc")

# @font-face { ... }，跨行非贪婪
_FONT_FACE_RE = re.compile(rb"@font-face\s*\{[^}]*\}", re.I)
# url(...) 里的地址
_FONT_URL_RE = re.compile(rb"""url\(\s*['"]?([^'")]+)['"]?\s*\)""", re.I)
# OPF manifest 里的一项
_MANIFEST_ITEM_RE = re.compile(rb"<item\b[^>]*/>", re.I)
_HREF_ATTR_RE = re.compile(rb"""href\s*=\s*["']([^"']+)["']""", re.I)

# 判断是不是字体资源（按扩展名）
_ITALIC_RE = re.compile(rb"font-style\s*:\s*italic", re.I)
_BOLD_RE = re.compile(rb"font-weight\s*:\s*(?:bold|[6-9]00)", re.I)
# 不是字体但名字像的事先排除
_SNIFF_LEN = 8


def is_font_path(path):
    """路径是否指向字体文件。"""
    return path.lower().endswith(FONT_EXTS)


def is_valid_font(data):
    """判断字节流是不是浏览器能加载的字体。

    只看前 4 字节魔数——这正是浏览器 OTS 的第一道也是决定性的检查。
    数据不足 4 字节一律视为无效。
    """
    if data is None or len(data) < 4:
        return False
    return data[:4] in SFNT_MAGIC


def find_broken_fonts(zf):
    """列出 zip 里所有坏字体条目名。"""
    broken = []
    for name in zf.namelist():
        if not is_font_path(name):
            continue
        try:
            with zf.open(name) as f:
                head = f.read(_SNIFF_LEN)
        except Exception:
            # 读不出来也当坏的：反正浏览器也拿不到
            broken.append(name)
            continue
        if not is_valid_font(head):
            broken.append(name)
    return broken


def _resolve_href(base_dir, href):
    """把引用地址解析成 zip 内路径（统一用 / 分隔，不带前导 ./）。"""
    href = href.split("?")[0].split("#")[0].strip()
    if not href:
        return None
    if href.startswith(("data:", "http://", "https://", "//")):
        return None
    if base_dir:
        joined = os.path.normpath(os.path.join(base_dir, href))
    else:
        joined = os.path.normpath(href)
    return joined.replace(os.sep, "/")


def strip_font_faces(css_bytes, broken_set, css_path=""):
    """从 CSS 里删掉引用了坏字体的 @font-face 整段。

    只删「所有 url 都指向坏字体」的那些段；只要有一个 url 是好的、
    或者是远程/内联字体，就整段保留，避免破坏正常排版。
    返回 (新字节, 删除段数)。
    """
    if not css_bytes or b"@font-face" not in css_bytes.lower():
        return css_bytes, 0

    base_dir = os.path.dirname(css_path).replace("\\", "/")
    removed = 0
    broken = set(broken_set)

    def repl(m):
        nonlocal removed
        block = m.group(0)
        urls = _FONT_URL_RE.findall(block)
        if not urls:
            return block
        hits = 0
        for raw in urls:
            target = raw.decode("utf-8", "replace")
            full = _resolve_href(base_dir, target)
            if full is None:
                # 远程/内联字体不归我们判断，保留整段
                return block
            if full in broken:
                hits += 1
            else:
                # 指向一个不存在或完好的字体 → 保留
                return block
        if hits:
            removed += 1
            return b""
        return block

    out = _FONT_FACE_RE.sub(repl, css_bytes)
    return out, removed


def strip_opf_manifest(opf_bytes, broken_set, opf_path=""):
    """从 OPF 的 manifest 里去掉坏字体条目，返回 (新字节, 删除数)。

    必须同步删：留着 manifest 项会让部分阅读器/校验器把书判为损坏
    （引用了一个不存在或非法的资源）。
    """
    if not opf_bytes or not broken_set:
        return opf_bytes, 0

    base_dir = os.path.dirname(opf_path).replace("\\", "/")
    removed = 0

    def repl(m):
        nonlocal removed
        item = m.group(0)
        hm = _HREF_ATTR_RE.search(item)
        if not hm:
            return item
        target = hm.group(1).decode("utf-8", "replace")
        full = _resolve_href(base_dir, target)
        if full and full in broken_set:
            removed += 1
            return b""
        return item

    out = _MANIFEST_ITEM_RE.sub(repl, opf_bytes)
    return out, removed


def _rebuild_zip(src_path, dst_path, drop_names):
    """把 src 重打成 dst，跳过 drop_names 里的条目，并清理 CSS/OPF 引用。

    返回 dict 统计。保持 mimetype 条目为第一个且不压缩（EPUB OCF 规范要求）。
    """
    drop = set(drop_names)
    stats = {"dropped": 0, "css_cleaned": 0, "font_faces_removed": 0,
             "opf_cleaned": 0, "manifest_removed": 0, "before": 0, "after": 0}

    with zipfile.ZipFile(src_path, "r") as zin:
        stats["before"] = os.path.getsize(src_path) if os.path.exists(src_path) else 0

        # mimetype 必须第一个、STORED
        names = zin.namelist()
        rest = [n for n in names if n != "mimetype"]

        with zipfile.ZipFile(dst_path, "w") as zout:
            if "mimetype" in names:
                zi = zipfile.ZipInfo("mimetype")
                zi.compress_type = zipfile.ZIP_STORED
                # 固定时间戳，保证同一本书重复处理结果一致（ETag 稳定）
                zi.date_time = (1980, 1, 1, 0, 0, 0)
                zout.writestr(zi, zin.read("mimetype"))

            for name in rest:
                if name in drop:
                    stats["dropped"] += 1
                    continue
                data = zin.read(name)
                if name.lower().endswith(".css"):
                    data2, n = strip_font_faces(data, drop, name)
                    if n:
                        stats["css_cleaned"] += 1
                        stats["font_faces_removed"] += n
                        data = data2
                elif name.lower().endswith(".opf"):
                    data2, n = strip_opf_manifest(data, drop, name)
                    if n:
                        stats["opf_cleaned"] += 1
                        stats["manifest_removed"] += n
                        data = data2

                zi = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = zin.getinfo(name).external_attr
                zout.writestr(zi, data)

    stats["after"] = os.path.getsize(dst_path)
    return stats


def strip_from_epub_file(epub_path, backup_suffix=".bak"):
    """就地剥离一本 epub 里的坏字体。没有坏字体则不做任何改动。

    返回 dict：{"changed": bool, ....}。changed=False 时文件字节不变。
    """
    if not os.path.exists(epub_path):
        return {"changed": False, "reason": "not_found"}

    try:
        with zipfile.ZipFile(epub_path, "r") as zf:
            broken = find_broken_fonts(zf)
    except (zipfile.BadZipFile, OSError) as err:
        logger.warning("[FONTFIX] 无法读取 %s: %s", epub_path, err)
        return {"changed": False, "reason": "bad_zip"}

    if not broken:
        return {"changed": False, "reason": "no_broken_font"}

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".epub", dir=os.path.dirname(epub_path))
    os.close(tmp_fd)
    try:
        stats = _rebuild_zip(epub_path, tmp_path, broken)
        # 校验产物可读、且坏字体确实没了
        with zipfile.ZipFile(tmp_path, "r") as zcheck:
            if zcheck.testzip() is not None:
                raise ValueError("重建后的 zip 校验失败")
            left = find_broken_fonts(zcheck)
            if left:
                raise ValueError("重建后仍有 %d 个坏字体" % len(left))

        if backup_suffix:
            shutil.copy2(epub_path, epub_path + backup_suffix)
        # mkstemp 建的文件是 0600，直接 move 过去会让书变成只有 owner 能读，
        # calibre / nginx worker 就读不到了。把原文件的权限和属主搬过来。
        try:
            st = os.stat(epub_path)
            os.chmod(tmp_path, st.st_mode & 0o7777)
            if hasattr(os, "chown"):
                os.chown(tmp_path, st.st_uid, st.st_gid)
            # 时间戳也沿用原文件的，避免书库的 mtime 排序被打乱
            os.utime(tmp_path, (st.st_atime, st.st_mtime))
        except OSError as err:
            logger.warning("[FONTFIX] 恢复 %s 的文件属性失败: %s", epub_path, err)
        shutil.move(tmp_path, epub_path)
        tmp_path = None

        stats["changed"] = True
        stats["fonts"] = broken
        logger.info(
            "[FONTFIX] %s: 删除 %d 个坏字体 %d -> %d 字节（省 %.0f%%）",
            os.path.basename(epub_path), len(broken),
            stats["before"], stats["after"],
            (1 - stats["after"] / stats["before"]) * 100 if stats["before"] else 0,
        )
        return stats
    except Exception as err:
        logger.error("[FONTFIX] 处理 %s 失败: %s", epub_path, err)
        return {"changed": False, "reason": str(err)}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def build_stripped_epub(src_path, dst_path):
    """生成剥离过坏字体的副本（不动源文件）。无坏字体时返回 False。"""
    try:
        with zipfile.ZipFile(src_path, "r") as zf:
            broken = find_broken_fonts(zf)
    except (zipfile.BadZipFile, OSError) as err:
        logger.warning("[FONTFIX] 无法读取 %s: %s", src_path, err)
        return False

    if not broken:
        return False

    stats = _rebuild_zip(src_path, dst_path, broken)
    logger.info(
        "[FONTFIX] 生成精简副本 %s: 删除 %d 个坏字体 %d -> %d 字节",
        os.path.basename(dst_path), len(broken), stats["before"], stats["after"],
    )
    return True
