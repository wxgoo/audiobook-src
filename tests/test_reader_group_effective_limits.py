"""读者组权限的「生效值」口径一致性（r12）。

用户批评「头疼医头脚疼医脚」之后做的一次横向扫描：同一个权限概念
（read_limit / limit_categories / limit_tags）在系统里有两种读法——

  ① 直接读用户字段   r.read_limit / r.limit_tags
  ② 合并读者组后的生效值  ReaderGroupService.effective_limits(r)

凡是应该用 ② 而用了 ① 的地方，就是「读者组配了但不生效」。
本文件钉住这个不变量。
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


def _func_body(src, name):
    """粗略取出一个方法体（到下一个同缩进的 def 为止）。"""
    i = src.find("def " + name)
    assert i > 0, "找不到方法 " + name
    lines = src[i:].split("\n")
    out = [lines[0]]
    for ln in lines[1:]:
        if re.match(r"^    (async )?def ", ln):
            break
        out.append(ln)
    return "\n".join(out)


def test_meta_filter_tags_uses_effective_limits():
    """★ 标签云过滤必须走 effective_limits。

    以前 meta.py 的 _filter_tags 直接读 current_user.read_limit：
    一个用户靠读者组拿到白名单、自身字段是 0 时，标签云完全不过滤，
    被禁的分类仍显示在侧栏，还能顺着标签点进去。
    """
    body = _func_body(_src("webserver/handlers/meta.py"), "_filter_tags")
    assert "effective_limits" in body, (
        "_filter_tags 没有使用 ReaderGroupService.effective_limits，"
        "读者组配置对它不生效"
    )
    assert "current_user.limit_tags" not in body, (
        "_filter_tags 仍在直接读 current_user.limit_tags，绕过了读者组"
    )


def test_base_is_book_in_reading_range_uses_effective_limits():
    """书籍可见性判定同理（这是原有正确实现，防退化）。"""
    body = _func_body(_src("webserver/handlers/base.py"), "is_book_in_reading_range")
    assert "effective_limits" in body


def test_no_handler_reads_user_limit_fields_directly():
    """扫描所有 handler，除了「写字段」和「管理员列表展示」外，
    不该再有直接拿 user.read_limit 做判定的地方。

    白名单：admin.py 是编辑/展示（改字段值），models.py 是定义，
    services/reader_group.py 是 effective_limits 本身。
    """
    offenders = []
    handlers_dir = os.path.join(ROOT, "webserver", "handlers")
    for fn in sorted(os.listdir(handlers_dir)):
        if not fn.endswith(".py"):
            continue
        if fn in ("admin.py",):
            continue  # 编辑/展示用途
        src = open(os.path.join(handlers_dir, fn), encoding="utf-8").read()
        # 逐行扫，跳过注释——注释里会提到 current_user.read_limit 作为反面说明
        for ln_no, line in enumerate(src.split("\n"), 1):
            code = line.split("#", 1)[0]
            for m in re.finditer(
                r"current_user\.(read_limit|limit_tags|limit_categories)", code
            ):
                offenders.append("%s:%d %s" % (fn, ln_no, m.group(0)))

    assert not offenders, (
        "这些地方直接读了用户的限制字段而不是 effective_limits，"
        "读者组可能不生效：\n  " + "\n  ".join(offenders)
    )


def test_effective_limits_is_the_single_source():
    """effective_limits 必须真的合并组配置，而不是直通用户字段。"""
    src = _src("webserver/services/reader_group.py")
    body = _func_body(src, "effective_limits")
    # 它得读组定义
    assert "_groups(" in body or "group_of(" in body, body[:400]
