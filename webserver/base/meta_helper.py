#!/usr/bin/env python3
"""书籍元数据处理工具：作者/译者解析、标题清洗等。"""
import re
from typing import List, Tuple


# 姓名前的地区/朝代标记，如 [明]、【美】、（清）、(英)、[唐]、［美］（全角方括号）等
_DYNASTY_REGION_PREFIX = re.compile(r'^[\[［【\(（][^\]］】\)）]*[\]］】\)）]\s*')

# 姓名前的职责词，如 "插画[美国]安德鲁·格拉斯"、"插画：张三"、"绘画 李四"。
# 4.6.0-9 新增：这类脏名是"职责词 + 方括号国籍"叠在开头，原来的
# _DYNASTY_REGION_PREFIX 要求方括号在字符串首位，够不着。
# ⚠️ 刻意不含"译者"：译者标记由 _TRANSLATOR_SUFFIX 处理，进这里会把译者
#    误当作者（"译者：张三" 的张三应该是译者，不是作者）。
_DUTY_PREFIX = re.compile(r'^(?:插画|绘画|插图|摄影)\s*[：:]?\s*')

# 姓名前的"原作："类角色前缀，如 原作：面堂兄、原作:面堂兄
_ORIGINAL_AUTHOR_PREFIX = re.compile(r'^原作\s*[:：]\s*')

# 姓名尾部的作者标识：可选空格/连字符 + 著/编/编著/author/editor；或括号包裹
# 注意中文后缀允许直接紧贴姓名（如 "温德著"），故使用 \s*
# "主" 是"主编"被截断后的残留（如 "韦东山 主"），只在前面有空格时才当作角色后缀去除，
# 避免误伤名字本身以"主"结尾的情况（无空格时不匹配）。
#
# 4.6.0-9：扩到 绘/校/注/原著/改编/主编/插图。三个约束必须同时满足：
#   1. 单字（绘|校|注）**必须前面有空格**（\s+），否则 "图图"→"图"、"绘心"→"绘"
#   2. 刻意不含单字 "图"、"文"：中文人名里"文文""图图"很常见，一定误伤
#   3. 多字词（原著|改编|主编|插图）允许紧贴，因为它们本身足够长，不会误伤
_AUTHOR_SUFFIX = re.compile(
    r'(?:'
    r'\s*(?:著|编|编著|原著|改编|主编|插图)|'
    r'\s+(?:绘|校|注|译)|'
    r'\s*[-–]\s*(?:著|编|编著|绘|校|注)|'
    r'\s+(?:author|Author|editor|Editor|illustrator|Illustrator)|'
    r'\s*[-–]\s*(?:author|Author|editor|Editor|illustrator|Illustrator)|'
    r'\s*[\(\（]\s*(?:著|编|编著|绘|校|注|author|editor|illustrator)\s*[\)\）]|'
    r'\s+主'
    r')$'
)

# 姓名尾部的译者标识：空格/连字符 + 译/translator；或括号包裹
_TRANSLATOR_SUFFIX = re.compile(
    r'(?:'
    r'\s+译|\s*[-–]\s*译|\s*[\(\（]\s*译\s*[\)\）]|'
    r'\s+(?:translator|Translator)|\s*[-–]\s*(?:translator|Translator)|'
    r'\s*[\(\（]\s*(?:translator|Translator)\s*[\)\）]'
    r')$'
)

# 多人分隔符：/ 、 , ; ；（英文逗号、中英文分号、中文逗号）
# 4.6.0-9：补上中文逗号"。原来顿号分开的 "李绍山、陈存军" 会拆，
# 中文逗号分开的 "王惟恒，李艳" 却不拆——同样的合著两种行为，无法解释。
# 副作用是 "Rowling,J.K." 会被拆成两段，由 _looks_like_initial() 挡住。
_MULTI_AUTHOR_SEP = re.compile(r'[/、,;；，]')

# 首字母缩写，如 J.K. / JK / J. K. / J.K
# 用于避免把 "Rowling,J.K." 这类西文"姓, 名"格式拆坏
_AUTHOR_INITIAL = re.compile(r'(?:[A-Za-z]\.?\s*){1,4}\Z')

# 末尾的英文译名括号，如（Jean-Michel Frodon）、(John Smith)
# 内容至少含一个英文字母，允许空格、连字符、·、.、' 等姓名常用符号
_ENGLISH_NAME_BRACKET = re.compile(
    r'\s*[\(\（]\s*[A-Za-z][A-Za-z\s\-·\'.]+\s*[\)\）]$'
)

# 需要过滤掉的无名氏标记
_ANONYMOUS_MARKERS = frozenset({'佚名', 'Unknown', 'unknown', '', None})

# 无效 tag：开头为这些词（不区分大小写）
_INVALID_TAG_PREFIX = re.compile(
    r'^(?:关注|标题|制作|下载|出版社|http|ftp|mail|isbn)', re.IGNORECASE
)

# 无效 tag：含有这些内容（不区分大小写）
_INVALID_TAG_CONTAINS = re.compile(
    r'(?:\s|公众号|微信|下载|下載|汇书网|书屋|，|www\.|\.com|出品|@|商务印书馆|SANQIU|VERYCD)', re.IGNORECASE
)

# 无效 tag：结尾为这些词
_INVALID_TAG_SUFFIX = re.compile(r'(?:制作|印刷)$')

# 无效 tag：纯数字
_PURE_DIGITS = re.compile(r'^\d+$')

# 无效 tag：开头为(或（，且结尾为)或）
_WRAPPED_IN_BRACKETS = re.compile(r'^[\(（].*[\)）]$')

# 分隔符：单个 tag 内混杂多个词，用；或;隔开的，拆成多个独立 tag
_TAG_SPLIT = re.compile(r'[;；]')


def normalize_author_name(value: str) -> str:
    """合并连续空白字符为单个空格，并去除首尾空白。"""
    if not value:
        return ''
    return ' '.join(value.split()).strip().replace('•', '·')


def guess_authors(authors: List[str]) -> Tuple[List[str], List[str]]:
    """解析原始作者字符串列表，返回 (作者列表, 译者列表)。
    返回的两个列表均已去重、过滤空值、去除首尾空白。
    """
    author_result: List[str] = []
    translator_result: List[str] = []

    for raw in authors or []:
        if raw is None:
            continue
        original = normalize_author_name(str(raw))
        if not original or original in _ANONYMOUS_MARKERS:
            continue

        # 1. 去除前导的"原作："角色前缀，再去除职责词，再去除地区/朝代标记。
        #    顺序不能换："插画[美国]安德鲁·格拉斯" 里 "插画" 挡在 "[" 前面，
        #    先走 _DYNASTY_REGION_PREFIX 的话它匹配不到 ^\[，国籍就剥不掉。
        name = _ORIGINAL_AUTHOR_PREFIX.sub('', original).strip()
        name = _DUTY_PREFIX.sub('', name).strip()
        name = _DYNASTY_REGION_PREFIX.sub('', name).strip()
        if not name or name in _ANONYMOUS_MARKERS:
            continue

        # 2. 判断尾部是译者还是作者标识（译者优先匹配，因为 "译" 短于 "translator"）
        is_translator = bool(_TRANSLATOR_SUFFIX.search(name))
        name = _TRANSLATOR_SUFFIX.sub('', name).strip()
        name = _AUTHOR_SUFFIX.sub('', name).strip()
        if not name or name in _ANONYMOUS_MARKERS:
            continue

        # 3. 去除末尾的英文译名括号（角色后缀已处理完，不会误伤 (译) / (editor) 等）
        name = _ENGLISH_NAME_BRACKET.sub('', name).strip()
        if not name or name in _ANONYMOUS_MARKERS:
            continue

        # 4. 按 / 、 , ; ； ， 分割多人。
        #    但如果任意一段是首字母缩写（J.K. / JK），说明这是西文 "姓, 名" 格式，
        #    整体保留不拆——否则 "Rowling,J.K." 会变成两个作者。
        parts = [normalize_author_name(p) for p in _MULTI_AUTHOR_SEP.split(name)]
        parts = [p for p in parts if p and p not in _ANONYMOUS_MARKERS]
        if len(parts) > 1 and any(_AUTHOR_INITIAL.match(p) for p in parts):
            parts = [name]

        target = translator_result if is_translator else author_result
        for p in parts:
            cleaned = ''.join(c for c in p.strip() if c.isprintable())
            if cleaned and cleaned not in target:
                target.append(cleaned)

    return author_result, translator_result


def _is_invalid_tag(tag: str) -> bool:
    """判断单个 tag 是否为无效标签（广告/推广/网址/纯数字/纯括号包裹等）。"""
    if not tag:
        return True
    if _INVALID_TAG_PREFIX.match(tag):
        return True
    if _INVALID_TAG_CONTAINS.search(tag):
        return True
    if _INVALID_TAG_SUFFIX.search(tag):
        return True
    if _PURE_DIGITS.match(tag):
        return True
    if _WRAPPED_IN_BRACKETS.match(tag):
        return True
    return False


def guess_tags(tags: List[str]) -> List[str]:
    """清理原始 tags 列表，过滤掉广告/推广类无效标签，返回去重后的有效 tags。

    单个 tag 内如果用；或;混杂了多个词，会先拆成多个独立 tag，再逐个校验；拆分/清理后
    长度不超过 1 个字符的片段一并丢弃。
    """
    result: List[str] = []
    for raw in tags or []:
        if raw is None:
            continue
        tag = str(raw).strip()
        if not tag:
            continue
        for part in _TAG_SPLIT.split(tag):
            part = part.strip()
            if len(part) <= 1 or _is_invalid_tag(part):
                continue
            cleaned = ''.join(c for c in part if c.isprintable())
            if cleaned and cleaned not in result:
                result.append(cleaned)
    return result


if __name__ == "__main__":
    # 测试 guess_authors
    print("=" * 60)
    print("=== guess_authors ===")
    author_tests = [
        # (输入, 期望作者列表, 期望译者列表, 说明)
        (["鲁迅"], ["鲁迅"], [], "单作者，无标记"),
        (["[明] 施耐庵 著"], ["施耐庵"], [], "朝代前缀 + 著"),
        (["【美】海明威"], ["海明威"], [], "地区前缀"),
        (["（清）曹雪芹 编著"], ["曹雪芹"], [], "朝代前缀 + 编著"),
        (["阿加莎·克里斯蒂 编"], ["阿加莎·克里斯蒂"], [], "编 标识"),
        (["佚名"], [], [], "佚名 过滤"),
        (["Unknown"], [], [], "Unknown 过滤"),
        ([""], [], [], "空字符串过滤"),
        (["译者A 译"], [], ["译者A"], "译者标记"),
        (["鲁迅", "周树人"], ["鲁迅", "周树人"], [], "多作者各自独立"),
        (["[清]蒲松龄 著", "老舍"], ["蒲松龄", "老舍"], [], "混合前缀和无前缀"),
        (["作者A / 作者B"], ["作者A", "作者B"], [], "斜杠分割多人"),
        (["张三、李四、王五"], ["张三", "李四", "王五"], [], "顿号分割多人"),
        (["John, Jane, Bob"], ["John", "Jane", "Bob"], [], "英文逗号分割多人"),
        (["鲁迅, 茅盾, 巴金"], ["鲁迅", "茅盾", "巴金"], [], "中文作者逗号分割多人"),
        (["作者A, 作者B 著"], ["作者A", "作者B"], [], "逗号分割多人+尾部著"),
        (["作者A 著", "译者B 译"], ["作者A"], ["译者B"], "作者+译者混合"),
        (["[法]加缪 著", "【美】史密斯 译"], ["加缪"], ["史密斯"], "带前缀的作者和译者"),
        (["鲁迅/茅盾 著"], ["鲁迅", "茅盾"], [], "斜杠+著 组合"),
        (["译者A、译者B 译"], [], ["译者A", "译者B"], "顿号+译 组合"),
        (["译者A/译者B 译"], [], ["译者A", "译者B"], "斜杠+译 组合"),
        (["[明]吴承恩", "[明]罗贯中"], ["吴承恩", "罗贯中"], [], "多朝代前缀"),
        (["  张三  ", "  李四  "], ["张三", "李四"], [], "首尾空格清理"),

        # --- 扩展：括号/连字符形式的角色后缀 ---
        (["译者A (译)"], [], ["译者A"], "英文括号 译"),
        (["译者A（译）"], [], ["译者A"], "中文括号 译"),
        (["译者A - 译"], [], ["译者A"], "连字符 译"),
        (["译者A (translator)"], [], ["译者A"], "英文括号 translator"),
        (["译者A - translator"], [], ["译者A"], "连字符 translator"),
        (["作者A (编)"], ["作者A"], [], "英文括号 编"),
        (["作者A (editor)"], ["作者A"], [], "英文括号 editor"),
        (["作者A - 编著"], ["作者A"], [], "连字符 编著"),
        (["作者A (author)"], ["作者A"], [], "英文括号 author"),
        (["鲁迅/茅盾 (编)"], ["鲁迅", "茅盾"], [], "斜杠+括号 editor"),
        (["  鲁迅    著  "], ["鲁迅"], [], "首尾+中间多余空格归一化"),
        (["译者A\t译"], [], ["译者A"], "制表符归一化"),
        (["张三  /  李四  著"], ["张三", "李四"], [], "斜杠两侧空格归一化"),
        (["[美]  海明威    (译)"], [], ["海明威"], "前缀+多余空格+括号译者"),

        # --- 扩展：末尾英文译名括号 ---
        (["让-米歇尔·付东（Jean-Michel Frodon）"], ["让-米歇尔·付东"], [], "中文姓名+法语译名括号"),
        (["鲁迅 (Lu Xun)"], ["鲁迅"], [], "中文姓名+英文译名括号"),
        (["老舍（Lao She）"], ["老舍"], [], "中文姓名+英式译名括号"),
        (["张三/李四（John Smith）"], ["张三", "李四"], [], "斜杠+英文译名括号仅在后者"),
        (["鲁迅（Lu Xun） 著"], ["鲁迅"], [], "译名括号+著"),
        (["译者A（John Doe） 译"], [], ["译者A"], "译者+译名括号+译"),

        # --- 扩展：全角/半角括号与无空格后缀 ---
        (["（德）温德著"], ["温德"], [], "全角地区前缀+无空格著"),
        (["(德)温德著"], ["温德"], [], "半角地区前缀+无空格著"),
        (["陈惠雅（译）"], [], ["陈惠雅"], "全角括号译者"),
        (["陈惠雅(译)"], [], ["陈惠雅"], "半角括号译者"),

        # --- 扩展：分号分隔与"原作："前缀 ---
        (["李政初；双福"], ["李政初", "双福"], [], "中文分号分割多人"),
        (["李政初;双福"], ["李政初", "双福"], [], "英文分号分割多人"),
        (["原作：面堂兄"], ["面堂兄"], [], "原作：前缀"),
        (["原作:面堂兄"], ["面堂兄"], [], "半角冒号 原作:前缀"),
        (["原作：面堂兄 著"], ["面堂兄"], [], "原作：前缀+著"),
    ]
    all_pass = True
    for idx, (inp, exp_auth, exp_trans, desc) in enumerate(author_tests, 1):
        got_auth, got_trans = guess_authors(inp)
        ok_auth = got_auth == exp_auth
        ok_trans = got_trans == exp_trans
        ok = ok_auth and ok_trans
        all_pass = all_pass and ok
        status = "PASS" if ok else "FAIL"
        print(f"\n[{status}] #{idx} {desc}")
        print(f"  输入:       {inp}")
        if not ok_auth:
            print(f"  期望作者:   {exp_auth}")
            print(f"  实际作者:   {got_auth}")
        else:
            print(f"  作者:       {got_auth}  ✓")
        if not ok_trans:
            print(f"  期望译者:   {exp_trans}")
            print(f"  实际译者:   {got_trans}")
        else:
            print(f"  译者:       {got_trans}  ✓")

    print(f"\n{'=' * 60}")
    print(f"共 {len(author_tests)} 个测试，{'全部通过 ✓' if all_pass else '存在失败 ✗'}")

    # 测试 guess_tags
    print("\n" + "=" * 60)
    print("=== guess_tags ===")
    tag_tests = [
        # (输入, 期望输出, 说明)
        (["小说", "文学"], ["小说", "文学"], "正常 tags 保留"),
        (["关注公众号"], [], "开头 关注"),
        (["标题：xxx"], [], "开头 标题"),
        (["制作组"], [], "开头 制作"),
        (["下载地址"], [], "开头 下载"),
        (["出版社信息"], [], "开头 出版社"),
        (["http://example.com"], [], "开头 http"),
        (["HTTP://example.com"], [], "开头 http 大写不区分"),
        (["ftp://xxx"], [], "开头 ftp"),
        (["mail:xxx@xxx.com"], [], "开头 mail"),
        (["ISBN 978-x"], [], "开头 isbn 大写不区分"),
        (["小说 精选"], [], "含空格"),
        (["扫描公众号获取"], [], "含公众号"),
        (["加微信xxx"], [], "含微信"),
        (["小说，文学"], [], "含中文逗号"),
        (["www.example.com"], [], "含 www."),
        (["访问xxx.com"], [], "含 .com"),
        (["xxx出品"], [], "含出品"),
        (["联系邮箱a@b.com"], [], "含 @"),
        (["商务印书馆藏书"], [], "含商务印书馆"),
        (["SANQIU小组"], [], "含 SANQIU"),
        (["sanqiu小组"], [], "含 sanqiu 大写不区分"),
        (["独家制作"], [], "结尾 制作"),
        (["精美印刷"], [], "结尾 印刷"),
        (["12345"], [], "纯数字"),
        (["(备注内容)"], [], "半角括号包裹"),
        (["（备注内容）"], [], "全角括号包裹"),
        (["小说", "小说"], ["小说"], "去重"),
        ([""], [], "空字符串过滤"),
        ([None], [], "None 过滤"),
        (["  小说  "], ["小说"], "首尾空格清理"),
        (["历史", "关注公众号", "小说，", "12306", "(x)", "科幻"], ["历史", "科幻"], "混合过滤"),
    ]
    all_pass = True
    for idx, (inp, exp, desc) in enumerate(tag_tests, 1):
        got = guess_tags(inp)
        ok = got == exp
        all_pass = all_pass and ok
        status = "PASS" if ok else "FAIL"
        print(f"\n[{status}] #{idx} {desc}")
        print(f"  输入: {inp}")
        if not ok:
            print(f"  期望: {exp}")
            print(f"  实际: {got}")
        else:
            print(f"  结果: {got}  ✓")

    print(f"\n{'=' * 60}")
    print(f"共 {len(tag_tests)} 个测试，{'全部通过 ✓' if all_pass else '存在失败 ✗'}")


# ===== 从已下线的豆瓣（插件）源迁来的公共函数 =====
# 原住 webserver/plugins/meta/douban/，baike 与 handlers/book.py 还在用，搬进公共层。
import datetime  # noqa: E402

from webserver.constants import DEFAULT_ISBN  # noqa: E402
from webserver.i18n import _  # noqa: E402


def str2date(s):
    """把豆瓣风格的中文/数字日期串解析成 aware datetime，解析不了返回 None"""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", _("%Y年"), _("%Y年%m月"), _("%Y年%m月%d日"), "%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).replace(tzinfo=datetime.timezone.utc)
        except Exception:
            continue
    return None


def has_proper_book(books, title, isbn, publisher=None):
    """检查搜索结果中是否包含合适的图书（ISBN 精确命中，或题名+出版社双匹配）"""
    if not books or not isbn or isbn == DEFAULT_ISBN:
        return False

    for b in books:
        if isbn == b.get("isbn13", "xxx"):
            return True
        if publisher and title == b.get("title") and publisher == b.get("publisher"):
            return True
    return False
