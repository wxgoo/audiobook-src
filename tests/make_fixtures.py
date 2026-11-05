#!/usr/bin/env python3
"""重建集成测试用的数据库夹具（metadata.db + users.db）。

## 为什么需要这个脚本

`tests/test_main.py` 有 63 个用例，用 `TestApp`/`TestWithUserLogin` 基类
真启动整站、发 HTTP 请求。但它们一直「永远红」，原因是两个夹具库
`tests/cases/metadata.db`（calibre 库）和 `tests/cases/users.db` 从来没有
进版本库——`tests/.gitignore` 里就写着 `users.db` 和 `library/`。

结果：任何一个新克隆的仓库、任何一台 CI，这 63 个用例都跑不起来。
**这不是测试写得不对，是环境造不出来。**

## 数据集规模怎么定的

`test_main.py` 里写死了一批数量断言，本脚本造的库必须**精确**满足它们，
否则一改就被误判成「代码 bug」。这些数字就是原始夹具的指纹：

| 断言 | 出处 |
|---|---|
| 13 本书 | `test_user_info` → `sys.books == 13` |
| 72 个标签 | `test_tag` |
| 15 个作者 | `test_author` |
| 7 个系列 | `test_series` |
| 10 个出版社 | `test_publisher` |
| 评分桶 4★/5★ | `test_rating`（原始 7/8/9 分 → 5 星制只剩 2 桶）|
| `search?name=A` ≥ 6 本 | `test_search` |
| `/api/index?random=7&recent=9` | `test_index` |
| 31 个用户 | `test_admin_users` |
| id=1 是 EPUB、id=2 是 TXT、id=5 是 PDF | `BID_EPUB/BID_TXT/BID_PDF` |

前 6 本是 `test_main.py` 顶部注释里点名的书（百年孤独、慢慢自由路……），
格式也照抄注释：1=EPUB 2=TXT 3=MOBI 4=AZW3 5=PDF 6=EPUB。

## 前置条件

必须用 **python3.12**（calibre 只支持 3.12），且系统装了 calibre：

    apt install calibre python3.12 libzbar0
    python3.12 -m pip install --break-system-packages -r requirements.txt

用法：

    python3.12 tests/make_fixtures.py            # 夹具已存在则跳过
    python3.12 tests/make_fixtures.py --force    # 强制重建
"""
import argparse
import os
import random
import shutil
import sqlite3
import sys
import uuid

# ---- calibre 引导：必须在 import calibre 之前注入这些 sys 属性 ----
# 照抄 /usr/bin/calibre 的做法。缺一个就 AttributeError: extensions_location。
_CALIBRE_PY = os.environ.get("CALIBRE_PYTHON_PATH", "/usr/lib/calibre")
if os.path.isdir(_CALIBRE_PY) and _CALIBRE_PY not in sys.path:
    sys.path.insert(0, _CALIBRE_PY)
if not hasattr(sys, "extensions_location"):
    sys.resources_location = os.environ.get("CALIBRE_RESOURCES_PATH", "/usr/share/calibre")
    sys.extensions_location = os.environ.get(
        "CALIBRE_EXTENSIONS_PATH", os.path.join(_CALIBRE_PY, "calibre", "plugins"))
    sys.executables_location = os.environ.get("CALIBRE_EXECUTABLES_PATH", "/usr/bin")
    sys.system_plugins_location = None
# -------------------------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = os.path.join(ROOT, "tests", "cases")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("CALIBRE_CONFIG_DIRECTORY", "/tmp/calibre-fixture-conf")

# ---------------------------------------------------------------- 数据集定义
# 前 6 本：test_main.py 顶部注释点名的书，格式/书名照抄，不要改。
# 后 7 本：为凑够 72 标签 / 15 作者 / 7 系列 / 10 出版社 而补，题材刻意分散，
#         让 /api/search?name=A 至少能命中 6 本（书名或作者含 a/A）。

BOOKS = [
    # (title, authors, fmt, tags, series, series_index, publisher, rating, pubdate)
    ("Bai Nian Gu Du", ["Jia Xi Ya Ma Er Ke Si"], "EPUB",
     ["小说", "外国文学", "经典", "魔幻现实主义"], None, None, "南海出版公司", 9, "2011-06-01"),
    ("Man Man Zi You Lu", ["Unknown", "韩寒"], "TXT",
     ["回忆录", "历史", "美国"], None, None, "广西师范大学出版社", 8, "2014-03-01"),
    ("An Tu Sheng Tong Hua", ["An Tu Sheng"], "MOBI",
     ["童话", "外国文学", "经典", "丹麦"], None, None, "译林出版社", 8, "2009-01-01"),
    ("Mai Ken Xi Fang Fa", ["Ai Sen La Sai Er", "Barbara Minto"], "AZW3",
     ["管理", "商业", "思维"], None, None, "机械工业出版社", 7, "2015-09-01"),
    ("E Yu Pa Pa Ya Yi Pa Pa", ["Unknown", "Tuono Takashi"], "PDF",
     ["绘本", "儿童", "小说"], None, None, "明天出版社", 9, "2007-05-01"),
    ("Tang Shi San Bai Shou", ["Wei Zhi", "Heng Tang Tui Shi"], "EPUB",
     ["诗词", "古典", "中国文学", "经典"], None, None, "中华书局", 9, "2010-01-01"),

    ("Hai Ming Wei Wen Ji", ["Hai Ming Wei"], "EPUB",
     ["小说", "外国文学", "美国", "短篇"], None, None, "上海译文出版社", 8, "2012-08-01"),
    ("Hong Lou Meng", ["Cao Xue Qin"], "EPUB",
     ["古典", "中国文学", "小说", "名著"], "四大名著", 1.0, "人民文学出版社", 9, "1996-12-01"),
    ("Xi You Ji", ["Wu Cheng En"], "EPUB",
     ["古典", "中国文学", "小说", "名著", "神魔"], "四大名著", 2.0, "人民文学出版社", 8, "1996-12-01"),
    ("Shui Hu Zhuan", ["Shi Nai An"], "TXT",
     ["古典", "中国文学", "小说", "名著"], "四大名著", 3.0, "人民文学出版社", 7, "1996-12-01"),
    ("San Guo Yan Yi", ["Luo Guan Zhong"], "PDF",
     ["古典", "中国文学", "小说", "名著", "历史"], "四大名著", 4.0, "人民文学出版社", 8, "1996-12-01"),
    ("A Q Zheng Zhuan", ["Lu Xun"], "EPUB",
     ["中国文学", "小说", "短篇", "现代"], "鲁迅全集", 1.0, "人民文学出版社", 9, "2005-11-01"),
    ("Zhong Guo Xiao Shuo Shi Lue", ["Lu Xun"], "TXT",
     ["中国文学", "学术", "文学史"], "鲁迅全集", 9.0, "人民文学出版社", 7, "2005-11-01"),
]

# ---------------------------------------------------------------------------
# 下面三张表是「配平表」，作用是把标签/系列/出版社的数量顶到 test_main.py
# 写死的数字上。它们都作用在**已有的 13 本书**上，不新增书（书数也被断言）。
#
# 为什么不用「再加几本书」来凑：加书会同时改变 4 个计数，改一个数字要重算
# 四个，非常容易顾此失彼。分离成三张表后，每个期望值只由一张表负责。
# ---------------------------------------------------------------------------

# 标签：基础 23 个 + 下面 49 个 = 72。集合必须与基础标签不相交，
# 否则重复的会被 calibre 合并，数量就少了。
EXTRA_TAGS = {
    1: ["拉美文学", "诺贝尔奖", "家族史", "孤独", "翻译文学"],
    2: ["自传", "社会学", "非虚构", "阶层"],
    3: ["寓言", "安徒生", "儿童文学", "插图本"],
    4: ["营销", "战略", "决策"],
    5: ["图画书", "亲子", "幽默"],
    6: ["唐诗", "诗歌", "国学"],
    7: ["海明威", "冰山理论", "硬汉"],
    8: ["红楼梦", "曹雪芹", "清代", "红学"],
    9: ["西游记", "吴承恩", "神话", "取经"],
    10: ["水浒传", "施耐庵", "英雄", "梁山"],
    11: ["三国演义", "罗贯中", "谋略", "演义"],
    12: ["鲁迅", "国民性", "白话文", "讽刺"],
    13: ["小说史", "讲义", "民国学术", "文献"],
}

# 系列：基础 2 个（四大名著、鲁迅全集）+ 下面 5 个 = 7
EXTRA_SERIES = {
    6: ("唐诗选本", 1.0),
    7: ("海明威短篇集", 1.0),
    3: ("安徒生童话全集", 1.0),
    5: ("五味太郎绘本", 1.0),
    12: ("鲁迅小说单行本", 1.0),
}

# 出版社：基础 8 个 + 下面 2 个 = 10。
# 原理：13 本书里原有一批共用「人民文学出版社」，把其中两本改挂到新出版社，
# 总数就是 8 - 0 + 2 = 10（人民文学还在，没被消灭）。
EXTRA_PUBLISHERS = {
    8: "作家出版社",        # 红楼：人民文学 → 作家出版社（人民文学还有 9-13 在用）
    12: "北新书局",         # 阿Q：人民文学 → 北新书局（鲁迅初版社，考据上说得通）
}

# 10 个出版社、15 个作者、7 个系列必须是精确值，这里做自检。
EXPECTED_TAGS = 72
EXPECTED_AUTHORS = 15
EXPECTED_SERIES = 7
EXPECTED_PUBLISHERS = 10
EXPECTED_BOOKS = 13
EXPECTED_RATING_BUCKETS = 2

# 读者：id=1 必须是 Rex（多个用例断言了用户名），且是 admin。
READER = {
    "id": 1,
    "username": "Rex",
    "name": "Rex",
    "password": "8d788385431273d11e8b43bb78f3aa41",
    "salt": "c5627e43b6c66d97",
    "email": "rex@example.com",
    "admin": True,
    "active": True,
    "permission": "p,d,r",
}

# test_admin_users 断言 31 个用户（含 Rex）
TOTAL_USERS = 31


def log(msg):
    print("  " + msg)


# ------------------------------------------------------------ 造各种格式文件
def _epub_bytes(title, author):
    """用 calibre 的 EPUB 输出生成一个合法 epub。失败则退回最小手写 epub。"""
    try:
        from calibre.ebooks.metadata.book.base import Metadata
        from calibre.ebooks.metadata.epub import stream_metadata  # noqa: F401

        from calibre.ebooks.conversion.plumber import Plumber

        raise ImportError  # 走手写路径更可控
    except Exception:
        pass
    return _minimal_epub(title, author)


def _minimal_epub(title, author):
    """手写一个最小但合法的 EPUB 3 文件。calibre 能读、能取封面、能转格式。"""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        # mimetype 必须第一个且不压缩
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")
        z.writestr("META-INF/container.xml", """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf"
    media-type="application/oebps-package+xml"/></rootfiles>
</container>""")
        z.writestr("OEBPS/content.opf", """<?xml version="1.0" encoding="UTF-8"?>
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
    <item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="ncx"><itemref idref="c1"/></spine>
</package>""" % (_xml(title), _xml(author or "Unknown"), uuid.uuid5(uuid.NAMESPACE_URL, title)))
        z.writestr("OEBPS/toc.ncx", """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="urn:uuid:%s"/></head>
  <docTitle><text>%s</text></docTitle>
  <navMap><navPoint id="n1" playOrder="1"><navLabel><text>%s</text></navLabel>
    <content src="c1.xhtml"/></navPoint></navMap>
</ncx>""" % (uuid.uuid5(uuid.NAMESPACE_URL, title), _xml(title), _xml(title)))
        body = ("<p>这是《%s》的正文段落，用于集成测试。</p>\n" % _xml(title)) * 30
        z.writestr("OEBPS/c1.xhtml", """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>%s</title></head>
<body><h1>%s</h1>%s</body></html>""" % (_xml(title), _xml(title), body))
    buf.seek(0)
    return buf.read()


def _xml(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _txt_bytes(title, author=None):
    paras = ["《%s》" % title, ""]
    for i in range(40):
        paras.append("第 %d 段。这是一本用于集成测试的纯文本书，包含中文与 English 混排。" % (i + 1))
        paras.append("")
    return "\n".join(paras).encode("utf-8")


def _pdf_bytes(title, author=None):
    return _reportlab_pdf(title)


def _reportlab_pdf(title):
    from reportlab.lib.pagesizes import A5
    from reportlab.pdfgen import canvas

    import io

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A5)
    for page in range(3):
        c.setFont("Helvetica", 16)
        c.drawString(40, 500, "Fixture Book %d" % (page + 1))
        c.setFont("Helvetica", 10)
        c.drawString(40, 470, "title: %s" % "".join(ch if ord(ch) < 128 else "?" for ch in title))
        for i in range(12):
            c.drawString(40, 440 - i * 18, "Line %d of fixture content for integration tests." % (i + 1))
        c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()


def _mobi_bytes(title, author=None):
    """MOBI 用 calibre 从 epub 转；转不了就退回 epub 字节（扩展名不改，
    calibre 按扩展名存盘但内容无所谓——测试只校验能取到文件）。"""
    try:
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "a.epub")
            with open(src, "wb") as f:
                f.write(_minimal_epub(title, "Unknown"))
            out = subprocess.run(
                ["ebook-convert", src, os.path.join(td, "a.mobi")],
                capture_output=True, timeout=120,
            )
            dst = os.path.join(td, "a.mobi")
            if out.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 1000:
                with open(dst, "rb") as f:
                    return f.read()
    except Exception:
        pass
    return _minimal_epub(title, "Unknown")


def _azw3_bytes(title, author=None):
    try:
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "a.epub")
            with open(src, "wb") as f:
                f.write(_minimal_epub(title, "Unknown"))
            dst = os.path.join(td, "a.azw3")
            out = subprocess.run(["ebook-convert", src, dst], capture_output=True, timeout=120)
            if out.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 1000:
                with open(dst, "rb") as f:
                    return f.read()
    except Exception:
        pass
    return _minimal_epub(title, "Unknown")


def _cover_bytes(title, seed):
    """生成一张纯色带文字的封面 JPG。"""
    import io

    from PIL import Image, ImageDraw

    rnd = random.Random(seed)
    bg = (rnd.randint(30, 200), rnd.randint(30, 200), rnd.randint(30, 200))
    img = Image.new("RGB", (600, 800), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 580, 780], outline=(255, 255, 255), width=4)
    ascii_title = "".join(ch if ord(ch) < 128 else "?" for ch in title)
    d.text((50, 380), ascii_title[:34], fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


FORMAT_BUILDERS = {
    "EPUB": _epub_bytes,
    "TXT": _txt_bytes,
    "PDF": _pdf_bytes,
    "MOBI": _mobi_bytes,
    "AZW3": _azw3_bytes,
}


# --------------------------------------------------------------- 建 metadata
def build_metadata_db(target):
    """用真 calibre 建库 → 导入书 → 补 MyBooks 自建表。"""
    tmp = target + ".building"
    if os.path.exists(tmp):
        shutil.rmtree(tmp)
    os.makedirs(tmp)

    log("用 calibre 建 metadata.db ...")
    from calibre.db.backend import DB
    from calibre.db.cache import Cache

    # 注意：DB 是底层 apsw 封装，只有 add_format/set_cover 这类原语；
    # create_book_entry / add_books 在上一层的 Cache 上。两层都要关。
    backend = DB(tmp)
    cache = Cache(backend)
    # 必须先 init()：它负责从 backend 拉字段表并建立 self.fields，
    # 否则 create_book_entry → _has_book 会 KeyError: 'title'。
    cache.init()
    try:
        _populate_books(cache)
    finally:
        for closer in (cache, backend):
            try:
                closer.close()
            except Exception:
                pass

    meta_path = os.path.join(tmp, "metadata.db")
    if not os.path.exists(meta_path):
        raise RuntimeError("calibre 没生成 metadata.db")

    n = sqlite3.connect(meta_path).execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    log("calibre 表数量: %d" % n)

    log("补 MyBooks 自建表（items/readings/...）...")
    from sqlalchemy import create_engine

    from webserver import models

    engine = create_engine("sqlite:///" + meta_path)
    models.Base.metadata.create_all(engine)
    models.ensure_new_tables(engine)
    # social-auth 的三张表（user_social_auth / nonce / association）不在
    # models.Base 里，是 main.py 启动时用 init_social 建的。夹具不做这一步，
    # /api/admin/users 会因为查不到 social_auth_usersocialauth 直接 500。
    try:
        from social_tornado.models import init_social
        from sqlalchemy.orm import sessionmaker

        from webserver import loader

        init_social(models.Base, sessionmaker(bind=engine), loader.get_settings())
        models.Base.metadata.create_all(engine)
    except Exception as e:  # pragma: no cover - 装了 social-auth 才有
        log("警告：init_social 失败（%s），社交账号相关用例会红" % e)
    engine.dispose()


    con = sqlite3.connect(meta_path)
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    for must in ("items", "readings", "book_visits", "booklists", "readers"):
        if must not in tables:
            raise RuntimeError("缺表 %s，自建表没建全" % must)
    log("总表数: %d（含 items/readings/readers 等）" % len(tables))
    con.close()

    # ---- 自检：数量必须和 test_main.py 的硬断言对上 ----
    _verify(meta_path)

    # 整个库目录一起搬走：calibre 把书的格式文件和封面存在
    # <库根>/<作者>/<书名 (id)>/ 下面，光搬 metadata.db 会让 /api/book/1.epub
    # 之类的请求 404（库里记着有这本书，磁盘上却找不到文件）。
    if os.path.exists(target):
        os.remove(target) if os.path.isfile(target) else shutil.rmtree(target)
    shutil.move(tmp, target)
    nfiles = sum(len(fs) for _, _, fs in os.walk(target))
    log("写出 %s（%.0f KB，库内共 %d 个文件）" % (
        target, os.path.getsize(os.path.join(target, "metadata.db")) / 1024, nfiles))


def _populate_books(db):
    from calibre.ebooks.metadata.book.base import Metadata
    from calibre.utils.date import parse_date

    log("导入 %d 本书 ..." % len(BOOKS))
    for idx, (title, author, fmt, tags, series, sidx, publisher, rating, pubdate) in enumerate(BOOKS, start=1):
        authors = list(author)
        # 第 idx 本（1 起，和 calibre 的 book_id 一致）的配平项
        tags = list(tags) + list(EXTRA_TAGS.get(idx, []))
        if idx in EXTRA_SERIES:
            series, sidx = EXTRA_SERIES[idx]
        publisher = EXTRA_PUBLISHERS.get(idx, publisher)

        mi = Metadata(title, authors)
        mi.title_sort = title
        mi.authors = authors
        mi.author_sort = authors[0]
        mi.tags = tags
        mi.publisher = publisher
        mi.rating = rating          # calibre 内部 0-10
        try:
            mi.pubdate = parse_date(pubdate, as_utc=False)
        except Exception:
            pass
        if series:
            mi.series = series
            mi.series_index = sidx if sidx else 1.0
        mi.language = "zh"
        mi.comments = "《%s》的简介，用于集成测试。" % title
        mi.isbn = "978%010d" % (1000000000 + idx)

        data = FORMAT_BUILDERS[fmt](title, authors[0])
        cover = _cover_bytes(title, idx)
        book_id = db.create_book_entry(mi, add_duplicates=False)
        if book_id is None:
            raise RuntimeError("calibre 拒绝导入《%s》" % title)
        # run_hooks=False：导入插件会去猜格式（拿 bytes 当路径处理，直接 TypeError），
        # 而夹具这里格式已经确定，不需要它猜。
        import io

        db.add_format(book_id, fmt, io.BytesIO(data), run_hooks=False)
        db.set_cover({book_id: cover})
        log("  id=%-2d %-26s %s" % (book_id, title, fmt))

    log("calibre books 表: %d 本" % len(db.all_book_ids()))


def _verify(meta_path):
    """把 test_main.py 里写死的数量断言全部核一遍，不符就报错。"""
    con = sqlite3.connect(meta_path)
    q = lambda s: con.execute(s).fetchone()[0]

    books = q("SELECT count(*) FROM books")
    tags = q("SELECT count(*) FROM tags")
    authors = q("SELECT count(*) FROM authors")
    series = q("SELECT count(*) FROM series")
    publishers = q("SELECT count(*) FROM publishers")
    # calibre 里 rating 存 0-10，5 星制 = (rating+1)//2；桶数即不同星级数
    buckets = q("SELECT count(DISTINCT (r.rating+1)/2) FROM books_ratings_link l "
                "JOIN ratings r ON r.id=l.rating")
    con.close()

    checks = [
        ("书籍", books, EXPECTED_BOOKS),
        ("标签", tags, EXPECTED_TAGS),
        ("作者", authors, EXPECTED_AUTHORS),
        ("系列", series, EXPECTED_SERIES),
        ("出版社", publishers, EXPECTED_PUBLISHERS),
        ("评分桶", buckets, EXPECTED_RATING_BUCKETS),
    ]
    bad = [(n, got, want) for n, got, want in checks if got != want]
    for n, got, want in checks:
        log("自检 %-6s %3d / %3d %s" % (n, got, want, "✓" if got == want else "✗"))
    if bad:
        raise RuntimeError(
            "数据集规模和 test_main.py 的硬断言不符：%s\n"
            "  要么改 BOOKS 补数据，要么改测试断言——别放着让测试随机红。"
            % ", ".join("%s %d!=%d" % b for b in bad))


# ----------------------------------------------------------------- 建 users
def build_users_db(target):
    """建 readers 表并塞 Rex + 30 个填充用户（test_admin_users 断言 31）。"""
    log("建 users.db ...")
    tmp = target + ".building"
    if os.path.exists(tmp):
        os.remove(tmp)

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from webserver import models

    engine = create_engine("sqlite:///" + tmp)
    models.Base.metadata.create_all(engine)
    models.ensure_new_tables(engine)

    S = sessionmaker(bind=engine)
    s = S()
    R = models.Reader

    import datetime

    now = datetime.datetime(2024, 1, 1, 12, 0, 0)

    def add(**kw):
        r = R()
        for k, v in kw.items():
            setattr(r, k, v)
        if hasattr(R, "birth_year"):
            r.birth_year = kw.get("birth_year", 0)
        # Reader.create_time/update_time/access_time 都没有 default，
        # 不填就是 NULL，/api/user/info 里 user.create_time.strftime 直接 500。
        r.create_time = kw.get("create_time", now)
        r.update_time = kw.get("update_time", now)
        r.access_time = kw.get("access_time", now)
        s.add(r)
        return r

    add(**READER)

    # 填充用户：第 0 个故意不带 birth_year（管理员页「补填」入口的测试对象）
    for i in range(1, TOTAL_USERS):
        add(
            username="user%02d" % i,
            name="User %02d" % i,
            password=READER["password"],
            salt=READER["salt"],
            email="user%02d@example.com" % i,
            admin=False,
            active=True,
            permission="r",
            birth_year=0 if i % 3 == 0 else 1980 + (i % 25),
        )
    s.commit()
    n = s.query(R).count()
    s.close()
    engine.dispose()

    if n != TOTAL_USERS:
        raise RuntimeError("用户数 %d != %d（test_admin_users 断言）" % (n, TOTAL_USERS))
    log("用户数: %d ✓" % n)

    # WAL 模式的边车文件会让拷贝出的库丢数据，测试要的是单文件
    for suffix in ("-wal", "-shm"):
        p = tmp + suffix
        if os.path.exists(p):
            os.remove(p)

    if os.path.exists(target):
        os.remove(target)
    shutil.move(tmp, target)
    log("写出 %s (%.0f KB)" % (target, os.path.getsize(target) / 1024))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="覆盖已存在的夹具")
    args = ap.parse_args()

    meta = os.path.join(CASES, "library")
    users = os.path.join(CASES, "users.db")

    if not args.force and os.path.exists(os.path.join(meta, "metadata.db")) and os.path.exists(users):
        print("夹具已存在。要重建请加 --force")
        return 0

    if sys.version_info < (3, 12):
        print("✗ 必须用 python3.12 运行（calibre 只支持 3.12）")
        print("  当前: %s" % sys.version.split()[0])
        return 1

    os.makedirs(CASES, exist_ok=True)
    print("重建夹具 → %s" % CASES)
    try:
        build_metadata_db(meta)
        build_users_db(users)
    except Exception as e:
        print("✗ 失败: %s" % e)
        import traceback

        traceback.print_exc()
        return 1

    print()
    print("✓ 完成。现在可以跑集成测试：")
    print("    python3.12 -m pytest tests/test_main.py -q")
    return 0


if __name__ == "__main__":
    sys.exit(main())
