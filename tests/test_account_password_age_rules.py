"""密码强度与年龄校验（4.6.0-19 r10）的单元测试。

不依赖 ORM / Tornado：把 Reader.check_password_strength 与
Reader.parse_age 的判定逻辑按源码原样复制成纯函数来断言。

为什么复制而不是直接 import：models.py 一开头就 import
social_sqlalchemy，沙箱里没有这个包，import 直接失败（见交接单第五节）。
所以这里保持「逻辑与源码逐行同构」，同时另有一个测试去源码里核对
关键规则没被改掉（防止复制体和源码漂移）。
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(ROOT, "webserver", "models.py")

PASSWORD_MIN_LEN = 6
PASSWORD_MAX_LEN = 20
PASSWORD_MIN_KINDS = 2
RE_PASSWORD = r'[a-zA-Z0-9!@#$%^&*()_+\-=[\]{};\':",./<>?\|]*'
_KINDS = (
    ("lower", r"[a-z]"),
    ("upper", r"[A-Z]"),
    ("digit", r"[0-9]"),
    ("special", r"[!@#$%^&*()_+\-=\[\]{};':\",./<>?\\|]"),
)
AGE_MIN, AGE_MAX = 1, 120


def check_password(pwd):
    """返回 (ok, code)。与 Reader.check_password_strength 同构。"""
    pwd = pwd or ""
    if len(pwd) < PASSWORD_MIN_LEN:
        return False, "short"
    if len(pwd) > PASSWORD_MAX_LEN:
        return False, "long"
    if not re.match(RE_PASSWORD + "$", pwd):
        return False, "invalid"
    kinds = sum(1 for _n, pat in _KINDS if re.search(pat, pwd))
    if kinds < PASSWORD_MIN_KINDS:
        return False, "weak"
    return True, "ok"


def parse_age(raw):
    """返回 (age, code)。与 Reader.parse_age 同构。"""
    text = str(raw if raw is not None else "").strip()
    if not text:
        return 0, "required"
    if not text.isdigit():
        return 0, "invalid"
    age = int(text)
    if age < AGE_MIN or age > AGE_MAX:
        return 0, "invalid"
    return age, "ok"


# ---------------- 密码 ----------------

def test_weak_digit_only_rejected():
    """用户明确要求：至少两种字符类别。纯数字不行。"""
    assert check_password("123456") == (False, "weak")
    assert check_password("123456789012") == (False, "weak")


def test_weak_lower_only_rejected():
    assert check_password("abcdef") == (False, "weak")
    assert check_password("password") == (False, "weak")


def test_two_kinds_accepted():
    # 小写 + 数字
    assert check_password("abc123")[0] is True
    # 大写 + 数字
    assert check_password("ABC123")[0] is True
    # 小写 + 符号
    assert check_password("abc!@#")[0] is True
    # 小写 + 大写
    assert check_password("abcDEF")[0] is True
    # 四类齐全
    assert check_password("aB3$xyz")[0] is True


def test_short_rejected_even_if_strong():
    """6 位是硬下限：A1b! 只有 4 位，类别够也不行。"""
    assert check_password("A1b!") == (False, "short")
    assert check_password("A1b!xy")[0] is True   # 刚好 6 位


def test_too_long_rejected():
    assert check_password("aB3" * 7)[1] == "long"   # 21 位


def test_disallowed_characters_rejected():
    """空格、中文、emoji 都不在白名单里，必须拒绝（否则能进 hash 也能进日志）。"""
    assert check_password("abc 123")[1] == "invalid"
    assert check_password("abc密码1")[1] == "invalid"
    assert check_password("abc123😀")[1] == "invalid"


def test_fullwidth_digits_not_counted_as_digit():
    """全角数字不算数字类别 —— 否则「至少两类」会被绕过。"""
    ok, code = check_password("ａｂｃ１２３")
    assert ok is False


# ---------------- 年龄 ----------------

def test_age_required():
    assert parse_age("") == (0, "required")
    assert parse_age(None) == (0, "required")
    assert parse_age("   ") == (0, "required")


def test_age_rejects_non_integer():
    assert parse_age("18.5") == (0, "invalid")
    assert parse_age("十八") == (0, "invalid")
    assert parse_age("1e2") == (0, "invalid")
    assert parse_age("-5") == (0, "invalid")


def test_age_range():
    assert parse_age("0") == (0, "invalid")
    assert parse_age("121") == (0, "invalid")
    assert parse_age("1") == (1, "ok")
    assert parse_age("120") == (120, "ok")
    assert parse_age(" 42 ") == (42, "ok")


# ---------------- 源码一致性 ----------------

def test_source_uses_shared_policy_constants():
    """确认源码里的策略常量没被改小/改松（复制体与源码不能漂移）。"""
    src = open(MODELS, encoding="utf-8").read()
    assert "PASSWORD_MIN_LEN = 6" in src
    assert "PASSWORD_MIN_KINDS = 2" in src
    assert "def check_password_strength" in src
    assert "def parse_age" in src
    assert 'AGE_MIN = 1' in src
    assert 'AGE_MAX = 120' in src


def test_all_password_call_sites_use_shared_checker():
    """五处校验（注册×2、自助改密、管理员改密、管理员建号）必须都走统一函数。

    r10 之前这五处各写一份 `len(pwd) < 6 or not re.match(RE_PASSWORD, ...)`，
    所以「加一条强度规则」要改五遍，漏一处就等于没加。
    """
    for name in ("user.py", "admin.py"):
        path = os.path.join(ROOT, "webserver", "handlers", name)
        src = open(path, encoding="utf-8").read()
        assert "RE_PASSWORD" not in src, f"{name} 里还残留手写的 RE_PASSWORD 校验"
        assert "check_password_strength" in src, f"{name} 没有走统一校验"


def test_signup_requires_age_on_both_entries():
    """两个注册入口（/user/sign_up 与 /user/new）都必须解析并写入 age。"""
    src = open(os.path.join(ROOT, "webserver", "handlers", "user.py"), encoding="utf-8").read()
    assert src.count("Reader.parse_age(age_raw)") == 2, "两个注册入口都要校验年龄"
    assert src.count("user.age = age") == 2, "两个注册入口都要落库 age"


def test_admin_cannot_set_age_for_another_admin():
    """age 属「设置类」，管理员行的白名单只放 username/password。"""
    src = open(os.path.join(ROOT, "webserver", "handlers", "admin.py"), encoding="utf-8").read()
    assert 'ADMIN_ALLOWED_FIELDS = {"username", "password"}' in src
    # 白名单守卫必须出现在 age 赋值之前，否则先改后拦等于没拦
    i_guard = src.find("ADMIN_ALLOWED_FIELDS")
    i_age = src.find('if "age" in data:')
    assert i_guard > 0 and i_age > i_guard, "age 赋值必须在管理员白名单守卫之后"
