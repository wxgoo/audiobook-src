"""密码强度与出生年份校验（4.6.0-19 r11）的单元测试。

不依赖 ORM / Tornado：把 Reader.check_password_strength /
parse_birth_year / age_from_birth_year 的判定逻辑按源码原样复制成纯函数
来断言。

r10 存的是「整数岁」，跨年不会自然长大（12 岁注册的孩子三年后仍判 12 岁，
本该解锁的书永远解锁不了），r11 改为存出生年份、年龄实时算出。

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
BIRTH_YEAR_MIN = 1900
# 与 Reader.current_year() 对齐；测试里固定这一年，避免跨年当天挂掉
CUR_YEAR = 2026


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


def parse_birth_year(raw, required=True, cur_year=CUR_YEAR):
    """返回 (birth_year, code)。与 Reader.parse_birth_year 同构。"""
    text = str(raw if raw is not None else "").strip()
    if not text:
        return (0, "required") if required else (0, "ok")
    if not text.isdigit():
        return 0, "invalid"
    year = int(text)
    if year < BIRTH_YEAR_MIN or year > cur_year:
        return 0, "invalid"
    return year, "ok"


def age_from_birth_year(birth_year, cur_year=CUR_YEAR):
    """与 Reader.age_from_birth_year 同构。"""
    try:
        year = int(birth_year or 0)
    except (TypeError, ValueError):
        return 0
    if year <= 0:
        return 0
    age = cur_year - year
    return age if age > 0 else 0


def parse_age_to_birth_year(raw, cur_year=CUR_YEAR):
    """与 Reader.parse_age_to_birth_year 同构（旧字段 age 兼容）。"""
    text = str(raw if raw is not None else "").strip()
    if not text:
        return 0, "required"
    if not text.isdigit():
        return 0, "invalid"
    age = int(text)
    year = cur_year - age
    if age <= 0 or year < BIRTH_YEAR_MIN or year > cur_year:
        return 0, "invalid"
    return year, "ok"


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


# ---------------- 出生年份 ----------------

def test_birth_year_required():
    assert parse_birth_year("") == (0, "required")
    assert parse_birth_year(None) == (0, "required")
    assert parse_birth_year("   ") == (0, "required")


def test_birth_year_optional_for_old_field():
    """旧字段补填路径允许空（表示维持未填），但不能把空当成合法年份。"""
    assert parse_birth_year("", required=False) == (0, "ok")


def test_birth_year_rejects_non_digits():
    assert parse_birth_year("1998.5") == (0, "invalid")
    assert parse_birth_year("一九九八") == (0, "invalid")
    assert parse_birth_year("98") == (0, "invalid")     # 两位年份不接受，避免 98 被当成公元 98 年
    assert parse_birth_year("1e3") == (0, "invalid")
    assert parse_birth_year("-1998") == (0, "invalid")


def test_birth_year_range():
    assert parse_birth_year("1899") == (0, "invalid")
    assert parse_birth_year("1900") == (1900, "ok")
    assert parse_birth_year(str(CUR_YEAR)) == (CUR_YEAR, "ok")
    assert parse_birth_year(str(CUR_YEAR + 1)) == (0, "invalid")   # 不允许填未来
    assert parse_birth_year(" 1998 ") == (1998, "ok")


def test_age_derived_from_birth_year():
    """核心：年龄由出生年份实时算出，所以随时钟自然增长。"""
    assert age_from_birth_year(2000) == CUR_YEAR - 2000
    # 同一用户，三年后年龄自动 +3 —— 这正是 r10「存整数岁」做不到的
    assert age_from_birth_year(2000, cur_year=CUR_YEAR + 3) == CUR_YEAR + 3 - 2000


def test_age_zero_when_unset():
    assert age_from_birth_year(0) == 0
    assert age_from_birth_year(None) == 0
    assert age_from_birth_year("") == 0
    assert age_from_birth_year("abc") == 0
    # 未来年份不该算出负数年龄
    assert age_from_birth_year(CUR_YEAR + 5) == 0


def test_legacy_age_field_converted():
    """r10 老前端若仍提交整数岁，换算成出生年份，不直接报参数错误。"""
    assert parse_age_to_birth_year("12") == (CUR_YEAR - 12, "ok")
    assert parse_age_to_birth_year("0") == (0, "invalid")
    assert parse_age_to_birth_year("") == (0, "required")
    assert parse_age_to_birth_year("abc") == (0, "invalid")
    # 年龄大到出生年份早于 1900，必须拒绝而不是算出 1800 年
    assert parse_age_to_birth_year("500") == (0, "invalid")


# ---------------- 源码一致性 ----------------

def test_source_uses_shared_policy_constants():
    """确认源码里的策略常量没被改小/改松（复制体与源码不能漂移）。"""
    src = open(MODELS, encoding="utf-8").read()
    assert "PASSWORD_MIN_LEN = 6" in src
    assert "PASSWORD_MIN_KINDS = 2" in src
    assert "def check_password_strength" in src
    assert "def parse_birth_year" in src
    assert "BIRTH_YEAR_MIN = 1900" in src
    assert "def age_from_birth_year" in src
    # 整数岁列必须已经换掉，不能两套并存（并存必然有人读错那个）
    assert "Reader.parse_age(" not in src
    assert "age = Column(Integer" not in src


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


def test_signup_requires_birth_year_on_both_entries():
    """两个注册入口（/user/sign_up 与 /user/new）都必须解析并写入 birth_year。"""
    src = open(os.path.join(ROOT, "webserver", "handlers", "user.py"), encoding="utf-8").read()
    assert src.count('self.get_argument("birth_year"') == 2, "两个注册入口都要读 birth_year"
    assert src.count("Reader.parse_birth_year(birth_year_raw)") == 2, "两个注册入口都要校验出生年份"
    assert src.count("user.birth_year = birth_year") == 2, "两个注册入口都要落库 birth_year"
    # 老字段不能再被读取，否则前端改了名字后端还在等 age，永远 required
    assert 'self.get_argument("age"' not in src


def test_admin_cannot_set_age_for_another_admin():
    """出生年份属「设置类」，管理员行的白名单只放 username/password。"""
    src = open(os.path.join(ROOT, "webserver", "handlers", "admin.py"), encoding="utf-8").read()
    assert 'ADMIN_ALLOWED_FIELDS = {"username", "password"}' in src
    # 白名单守卫必须出现在赋值之前，否则先改后拦等于没拦
    i_guard = src.find("ADMIN_ALLOWED_FIELDS")
    i_assign = src.find('if "birth_year" in data or "age" in data:')
    assert i_guard > 0 and i_assign > i_guard, "birth_year 赋值必须在管理员白名单守卫之后"


def test_admin_lists_birth_year_alongside_derived_age():
    """列表要同时给出 birth_year 与派生 age：前端展示年龄，改对话框回填年份。"""
    src = open(os.path.join(ROOT, "webserver", "handlers", "admin.py"), encoding="utf-8").read()
    assert '"birth_year": user.birth_year or 0' in src
    assert '"age": user.age or 0' in src


def test_migration_adds_birth_year_and_backfills_from_age():
    """老库升级：补列 + 用旧 age 回填 birth_year，且只回填一次。"""
    src = open(os.path.join(ROOT, "webserver", "services", "async_service.py"),
               encoding="utf-8").read()
    assert "ADD COLUMN birth_year INTEGER NOT NULL DEFAULT 0" in src
    # 回填语句要与补列同处一个 if 分支，否则每轮启动都会拿旧 age 覆盖手改值
    i_col = src.find("ADD COLUMN birth_year")
    i_backfill = src.find("SET birth_year = CAST(strftime('%Y', 'now') AS INTEGER) - age")
    assert i_col > 0 and i_backfill > i_col, "回填必须紧跟补列，且位于同一分支内"
    assert "WHERE age > 0" in src
