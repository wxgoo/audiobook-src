#!/usr/bin/env python3
"""生成 test_cfi_gen.py / test_sync_import.py 需要的两个 EPUB 夹具。

## 为什么单独一个脚本

这两个文件不是「随便一本 epub」，测试用例把书里的**具体句子**写死了：

| 文件 | 用例要求的正文 | 谁在用 |
|---|---|---|
| old.epub | 「献给在二十世纪后半叶中国大地上默默苦行的民间英雄」 | test_cfi_gen（唯一匹配）|
| old.epub | 无 text、无 chapterHint → 退化成 chapter_start | test_cfi_gen |
| new.epub | 「除了杂草灌木，便是随处可见的灰白色石头，大小不一，形状各异。」 | test_cfi_gen |
| new.epub | 「形状各异。␣␣\\n␣骄阳悬空，炙烤着大地」（空白规范化）| test_cfi_gen |
| new.epub | 「凡人修仙之仙界篇」正文里出现 **5 次** → ambiguous | test_cfi_gen |
| 百年孤独 | 「他手里拿着两大块磁铁，从一座农舍走到另一座农舍」，中间夹 `<br class="calibre1"/>` | test_cfi_gen / test_sync_import |

旧的夹具被 .gitignore 掉之后就丢了，谁也不知道原文长什么样。这个脚本
用**最小但结构真实**的 EPUB 把上面每一条重新立起来，算是把契约写进代码。

用法：

    python3 tests/make_epub_fixtures.py
"""

import io
import os
import sys
import uuid
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(HERE, "cases")


def _xml(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_epub_bytes(title, author, chapters):
    """chapters: [(章节标题, body_html)] → 一个合法 EPUB 2 的字节流。

    单独抽出来是给 tests/make_fixtures.py 复用的：它建 calibre 库时要把
    《百年孤独》的正文直接塞进去（test_sync_import 靠那几句做 CFI 定位），
    不能只留一个空壳 ePub 再替换文件。
    """
    buf = io.BytesIO()
    uid = uuid.uuid5(uuid.NAMESPACE_URL, title)

    manifest, spine, navpoints = [], [], []
    for i, (chtitle, _body) in enumerate(chapters, start=1):
        manifest.append(
            '<item id="c%d" href="c%d.xhtml" media-type="application/xhtml+xml"/>' % (i, i)
        )
        spine.append('<itemref idref="c%d"/>' % i)
        navpoints.append(
            '<navPoint id="n%d" playOrder="%d"><navLabel><text>%s</text></navLabel>'
            '<content src="c%d.xhtml"/></navPoint>' % (i, i, _xml(chtitle), i)
        )

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        # mimetype 必须第一个且不压缩
        zi = zipfile.ZipInfo("mimetype")
        zi.compress_type = zipfile.ZIP_STORED
        z.writestr(zi, "application/epub+zip")

        z.writestr("META-INF/container.xml", """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf"
    media-type="application/oebps-package+xml"/></rootfiles>
</container>""")

        z.writestr(
            "OEBPS/content.opf",
            """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"
            xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>%s</dc:title>
    <dc:creator opf:role="aut">%s</dc:creator>
    <dc:language>zh</dc:language>
    <dc:identifier id="uid">urn:uuid:%s</dc:identifier>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    %s
  </manifest>
  <spine toc="ncx">%s</spine>
</package>"""
            % (_xml(title), _xml(author), uid, "\n    ".join(manifest), "".join(spine)),
        )

        z.writestr(
            "OEBPS/toc.ncx",
            """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="urn:uuid:%s"/></head>
  <docTitle><text>%s</text></docTitle>
  <navMap>%s</navMap>
</ncx>""" % (uid, _xml(title), "".join(navpoints)),
        )

        for i, (chtitle, body) in enumerate(chapters, start=1):
            # 注意：<title> 里也写书名，是为了复刻 new.epub 的真实情况——
            # 「凡人修仙之仙界篇」在 <head><title> 里也要出现，而 cfi_batch
            # 必须把 <title> 排除掉（它不算可见阅读内容），只统计 <body>
            # 里的 5 次。少了这个干扰项，ambiguous 用例就测不到点子上。
            z.writestr(
                "OEBPS/c%d.xhtml" % i,
                """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>%s</title></head>
<body><h1>%s</h1>
%s
</body></html>""" % (_xml(title), _xml(chtitle), body),
            )

    buf.seek(0)
    return buf.read()


def write_epub(path, title, author, chapters):
    data = build_epub_bytes(title, author, chapters)
    with open(path, "wb") as f:
        f.write(data)
    print("  写出 %s (%d 字节)" % (path, len(data)))


# --------------------------------------------------------------- old.epub
OLD_CHAPTERS = [
    (
        "自序",
        "<p>这本小书的主人公，是我在乡下时认识的一些人。</p>"
        "<p>献给在二十世纪后半叶中国大地上默默苦行的民间英雄</p>",
    ),
    (
        "第一章",
        "<p>我比现在年轻十岁的时候，获得了一个游手好闲的职业。</p>"
        "<p>去乡间收集民间歌谣。那一年的整个夏天，我如同一只乱飞的麻雀，"
        "游荡在知了和阳光充斥的农村。</p>"
        "<p>我喜欢喝农民那种带有苦味的茶水，他们的茶桶就平放在田埂上。</p>",
    ),
    (
        "第二章",
        "<p>那个夏天，我碰到了一个叫福贵的老人。</p>"
        "<p>他正在使唤一头老牛耕田，嘴里吆喝着一些名字。</p>"
        "<p>我走过去，问他这头牛有多少岁了。</p>",
    ),
]

# --------------------------------------------------------------- new.epub
# 「凡人修仙之仙界篇」必须在 <body> 里出现 5 次（3 章各一次 + 页眉页脚式
# 重复两次），且 <head><title> 里也有，用来验证 <title> 被排除。
_NEW_TITLE = "凡人修仙之仙界篇"
NEW_CHAPTERS = [
    (
        "第一章 荒原",
        "<p>%s</p>"
        "<p>荒原上除了杂草灌木，便是随处可见的灰白色石头，大小不一，形状各异。"
        " 骄阳悬空，炙烤着大地。</p>"
        "<p>%s</p>" % (_NEW_TITLE, _NEW_TITLE),
    ),
    (
        "第二章 石村",
        "<p>%s</p>"
        "<p>少年沿着石径往前走，脚下的碎石发出细碎的声响。</p>"
        "<p>村子里静得出奇，只有几缕炊烟从远处升起。</p>" % _NEW_TITLE,
    ),
    (
        "第三章 灵石",
        "<p>%s</p>"
        "<p>他从怀里掏出那块灵石，灵石在掌心散发着微弱的青光。</p>"
        "<p>%s</p>" % (_NEW_TITLE, _NEW_TITLE),
    ),
]


# ------------------------------------------- 百年孤独（<br> 硬换行那本）
def build_hundred_years(library_dir):
    """写进库目录，路径必须是测试里写死的那个。

    test_cfi_gen.py 里 HUNDRED_YEARS_EPUB 写的是：
        tests/library/加西亚·马尔克斯/百年孤独 (1)/百年孤独 - 加西亚·马尔克斯.epub
    少一个字都 skipTest，那个 <br> 回归就永远测不到。
    """
    rel = os.path.join("加西亚·马尔克斯", "百年孤独 (1)",
                       "百年孤独 - 加西亚·马尔克斯.epub")
    path = os.path.join(library_dir, rel)
    if os.path.exists(path):
        print("  已存在 %s" % path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # 关键：句子中间夹一个 <br class="calibre1"/>（calibre 转换后的硬换行）。
    # cfi_batch 若把 <br> 当块级边界插入分隔符，这一句就永远匹配不上。
    chapters = [
        (
            "第一章",
            "<p>许多年之后，面对行刑队，奥雷里亚诺·布恩迪亚上校将会回想起"
            "父亲带他去见识冰块的那个遥远的下午。</p>"
            "<p>那时马孔多还是个二十户人家的村落。</p>"
            "<p>他手里拿着两大块磁铁，从一座农舍走到另<br class=\"calibre1\"/>一座农舍，"
            "那块铁屑纷飞。</p>"
            "<p>满脸络腮胡子，手指瘦得象鸟的爪子。</p>",
        ),
        (
            "第二章",
            "<p>何塞·阿尔卡蒂奥·布恩迪亚是个富于幻想的人。</p>"
            "<p>他对磁铁、放大镜、炼金术都有着近乎痴迷的热情。</p>",
        ),
    ]
    write_epub(path, "百年孤独", "加西亚·马尔克斯", chapters)


def main():
    os.makedirs(CASES, exist_ok=True)
    print("生成 EPUB 夹具 → %s" % CASES)

    write_epub(os.path.join(CASES, "old.epub"), "活着", "余华", OLD_CHAPTERS)
    write_epub(os.path.join(CASES, "new.epub"), _NEW_TITLE, "忘语", NEW_CHAPTERS)

    libdir = os.path.join(HERE, "library")
    if os.path.isdir(libdir):
        build_hundred_years(libdir)
    else:
        print("  （tests/library 不存在，跳过百年孤独；先跑 make_fixtures.py）")

    print()
    print("✓ 完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
