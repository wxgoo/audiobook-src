#!/usr/bin/env python3
"""生成 test_cfi_gen.py / test_sync_import.py 需要的两个 EPUB 夹具。

## 为什么单独一个脚本

这两个文件不是「随便一本 epub」，测试用例把书里的**具体句子**写死了：

| 文件 | 用例要求的正文 | 谁在用 |
|---|---|---|
| old.epub | `OLD_UNIQUE_TEXT`，全文唯一匹配 | test_cfi_gen |
| old.epub | 无 text、无 chapterHint → 退化成 chapter_start | test_cfi_gen |
| new.epub | `NEW_UNIQUE_TEXT`，唯一匹配 | test_cfi_gen |
| new.epub | `WHITESPACE_SOURCE`（句号后单空格）换成 `WHITESPACE_ANCHOR` 仍要匹配 | test_cfi_gen |
| new.epub | 书名 `NEW_BOOK_TITLE` 在 `<body>` 里出现 **5 次** → ambiguous | test_cfi_gen |
| 百年孤独 | `BR_WRAPPED_TEXT` 中间夹 `<br class="calibre1"/>` | test_cfi_gen / test_sync_import |
| 百年孤独 | 书名 `LIBRARY_BOOK_TITLE` 在 `<body>` 里出现 2 次 → ambiguous | test_sync_import |

## 正文为什么是《论语》

这两个文件不进版本库（真实出版物、体积大），必须能现场造。以前这里的
正文抄的是《活着》《凡人修仙之仙界篇》《百年孤独》的真实段落——夹具不该
带版权内容，所以统一换成公有领域的《论语》节选。测试要的是「结构 + 唯一
匹配 / 多义匹配」的契约，跟句子是谁写的无关。

下面的常量同时被 test_cfi_gen.py / test_sync_import.py 引用，改文本只改
这一处，避免夹具和断言的句子各写一遍后悄悄漂移。

用法：

    python tests/make_epub_fixtures.py
"""

import io
import os
import sys
import uuid
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(HERE, "cases")

# ------------------------------------------------------------ 公有领域正文
OLD_BOOK_TITLE = "学而"
NEW_BOOK_TITLE = "论语"          # 必须在 <body> 里出现 5 次（多义匹配用例）
LIBRARY_BOOK_TITLE = "百年孤独"  # 库夹具第 1 本的书名，test_sync_import 按它定位

OLD_UNIQUE_TEXT = "学而时习之，不亦说乎"
NEW_UNIQUE_TEXT = "温故而知新，可以为师矣。"
# 源文是「三十而立。 四十而不惑，五十而知天命。」（句号后一个空格）；
# 锚点把这段空白换成两个空格 + 换行，空白规范化之后必须还能匹配。
WHITESPACE_SOURCE = "三十而立。 四十而不惑，五十而知天命。"
WHITESPACE_ANCHOR = "三十而立。  \n 四十而不惑，五十而知天命。"
# 源文在「必」和「有」之间夹了一个 <br class="calibre1"/>（calibre 转换后的
# 硬换行）。锚点按正常句子写、不留空隙，必须仍然匹配 —— 见 cfi_batch.mjs
# 里 BLOCK_TAGS/`<br>` 的注释。
BR_WRAPPED_TEXT = "三人行，必有我师焉"
OTHER_UNIQUE_TEXT = "知之为知之，不知为不知"


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
            # 注意：<title> 里也写书名，是为了复刻真实 EPUB 的情况——书名在
            # <head><title> 里也要出现，而 cfi_batch 必须把 <title> 排除掉
            #（它不算可见阅读内容），只统计 <body> 里的 5 次。少了这个干扰项，
            # ambiguous 用例就测不到点子上。
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
        "<p>这本小册子抄的是古人的话，注解是后学加的。</p>"
        "<p>%s</p>" % OLD_UNIQUE_TEXT,
    ),
    (
        "第一章",
        "<p>有朋自远方来，不亦乐乎。</p>"
        "<p>人不知而不愠，不亦君子乎。</p>",
    ),
    (
        "第二章",
        "<p>吾日三省吾身：为人谋而不忠乎。</p>"
        "<p>与朋友交而不信乎，传不习乎。</p>",
    ),
]

# --------------------------------------------------------------- new.epub
# NEW_BOOK_TITLE 必须在 <body> 里出现 5 次（第一章 2 次 + 第二章 1 次 +
# 第三章 2 次，页眉页脚式重复），且 <head><title> 里也有（验证被排除）。
NEW_CHAPTERS = [
    (
        "学而第一",
        "<p>%s</p>" % NEW_BOOK_TITLE
        + "<p>%s</p>" % WHITESPACE_SOURCE
        + "<p>%s</p>" % NEW_BOOK_TITLE,
    ),
    (
        "为政第二",
        "<p>%s</p>" % NEW_BOOK_TITLE
        + "<p>%s</p>" % NEW_UNIQUE_TEXT
        + "<p>为政以德，譬如北辰，居其所而众星共之。</p>",
    ),
    (
        "里仁第四",
        "<p>%s</p>" % NEW_BOOK_TITLE
        + "<p>君子喻于义，小人喻于利。</p>"
        + "<p>%s</p>" % NEW_BOOK_TITLE,
    ),
]


# ------------------------------------------- 百年孤独（<br> 硬换行那本）
# 库夹具第 1 本的正文：test_cfi_gen 靠 <br> 那句、test_sync_import 靠
# 「百年孤独」这四个字做多义定位。书名保持原值（元数据），正文全是
# 公有领域句子。
HUNDRED_YEARS_CHAPTERS = [
    (
        "第一章",
        "<p>%s</p>" % LIBRARY_BOOK_TITLE
        + "<p>三人行，必<br class=\"calibre1\"/>有我师焉，择其善者而从之。</p>"
        + "<p>%s</p>" % OLD_UNIQUE_TEXT
        + "<p>%s</p>" % OTHER_UNIQUE_TEXT,
    ),
    (
        "第二章",
        "<p>%s</p>" % LIBRARY_BOOK_TITLE
        + "<p>见贤思齐焉，见不贤而内自省也。</p>"
        + "<p>君子坦荡荡，小人长戚戚。</p>",
    ),
]


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
    write_epub(path, LIBRARY_BOOK_TITLE, "加西亚·马尔克斯", HUNDRED_YEARS_CHAPTERS)


def write_upload_samples():
    """只补 tests/cases/old.epub、new.epub（缺什么补什么）。"""
    os.makedirs(CASES, exist_ok=True)
    samples = [
        ("old.epub", OLD_BOOK_TITLE, OLD_CHAPTERS),
        ("new.epub", NEW_BOOK_TITLE, NEW_CHAPTERS),
    ]
    for name, title, chapters in samples:
        path = os.path.join(CASES, name)
        if os.path.exists(path):
            continue
        write_epub(path, title, "孔门弟子", chapters)


def main():
    os.makedirs(CASES, exist_ok=True)
    print("生成 EPUB 夹具 → %s" % CASES)

    write_epub(os.path.join(CASES, "old.epub"), OLD_BOOK_TITLE, "孔门弟子", OLD_CHAPTERS)
    write_epub(os.path.join(CASES, "new.epub"), NEW_BOOK_TITLE, "孔门弟子", NEW_CHAPTERS)

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
