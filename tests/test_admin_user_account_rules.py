"""管理员账号管理（r9）的两条规则，纯逻辑单元测试。

不依赖 Tornado / 数据库，把 handlers/admin.py 里的判断抽成纯函数后断言：

  1. 改名合法性：长度、正则、大小写归一、重名
  2. 管理员保护：对其他管理员只能改 username / password；
     不能取消其管理员、不能删除；限定类字段一律拒绝
  3. 改名时昵称的同步规则：name 与 username 相同才跟着改，用户改过的
     自定义昵称不动
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 与 webserver/models.py 的 Reader.RE_USERNAME 保持一致（已锚定结尾，
# 否则 re.match 只校验前缀，"a-b" 这类名字能通过校验）
RE_USERNAME = r"[a-z][a-z0-9_]*$"


def normalize_username(raw):
    return (raw or "").strip().lower()


def validate_username(raw):
    """返回 (ok, normalized, error)。与后端 POST 分支一致。"""
    name = normalize_username(raw)
    if not name:
        return False, name, "empty"
    if len(name) < 3 or len(name) > 20 or not re.match(RE_USERNAME, name):
        return False, name, "invalid"
    return True, name, None


def admin_guard(data, target_is_admin, is_self):
    """返回 (allowed, error_key)。data 已删掉 id 字段。"""
    if not (target_is_admin and not is_self):
        return True, None
    if "admin" in data and not data["admin"]:
        return False, "cannot_demote_other_admin"
    if "delete" in data:
        return False, "cannot_delete_admin"
    bad = [k for k in data if k not in {"username", "password"}]
    if bad:
        return False, "admin_restricted_fields"
    return True, None


def next_nickname(current_name, current_username, new_username):
    if not current_name or current_name == current_username:
        return new_username
    return current_name


def test_username_valid():
    assert validate_username("wxgoo")[0] is True
    assert validate_username("  AnnI_2 ")[1] == "anni_2"
    assert validate_username("a12")[0] is True


def test_username_invalid_length():
    assert validate_username("ab")[2] == "invalid"
    assert validate_username("a" * 21)[2] == "invalid"


def test_username_invalid_chars():
    assert validate_username("1abc")[2] == "invalid"   # 数字开头
    assert validate_username("a bc")[2] == "invalid"
    assert validate_username("a-b")[2] == "invalid"
    assert validate_username("张三")[2] == "invalid"


def test_username_empty():
    assert validate_username("   ")[2] == "empty"


def test_admin_can_change_username_and_password():
    ok, err = admin_guard({"username": "boss"}, True, False)
    assert ok is True and err is None
    ok, err = admin_guard({"password": "123456"}, True, False)
    assert ok is True and err is None
    ok, err = admin_guard({"username": "boss", "password": "123456"}, True, False)
    assert ok is True and err is None


def test_admin_cannot_be_restricted():
    for field, value in [
        ("allow_review", False),
        ("active", False),
        ("read_limit", 1),
        ("limit_categories", "x"),
        ("permission", "USED"),
        ("download_daily_quota", 0),
    ]:
        ok, err = admin_guard({field: value}, True, False)
        assert ok is False, field
        assert err == "admin_restricted_fields", field


def test_admin_cannot_delete_admin():
    ok, err = admin_guard({"delete": "boss"}, True, False)
    assert ok is False and err == "cannot_delete_admin"


def test_admin_cannot_demote_another_admin():
    ok, err = admin_guard({"admin": False}, True, False)
    assert ok is False and err == "cannot_demote_other_admin"


def test_normal_user_unaffected():
    ok, err = admin_guard({"allow_review": False}, False, False)
    assert ok is True and err is None
    ok, err = admin_guard({"delete": "anni"}, False, False)
    assert ok is True and err is None


def test_self_edit_not_blocked_by_admin_guard():
    """自己改自己：交给「不允许取消自己管理员」那条既有逻辑，这里放行。"""
    ok, err = admin_guard({"password": "123456"}, True, True)
    assert ok is True and err is None


def test_nickname_follows_username_when_default():
    assert next_nickname("anni", "anni", "anni2") == "anni2"
    assert next_nickname("", "anni", "anni2") == "anni2"


def test_nickname_kept_when_customized():
    assert next_nickname("安静读书", "anni", "anni2") == "安静读书"


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
