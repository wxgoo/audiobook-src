"""升级守卫的行为测试（4.6.0-19 r11 补救）。

背景：r11 在 NAS 上装完直接报 `no such column: readers.birth_year`。
迁移函数 `adjust_reader_table()` 本身是对的（`test_birth_year_migration.py`
7 例全过），但**它压根没被调用**——因为：

    is_upgrade = CONF.get("installed_version", "") != VERSION

`VERSION` 从 r9 到 r11 一直是 `v4.8.0` 没动。r10 装完那次启动把
`installed_version` 写成了 `v4.8.0` 落盘；r11 升级后这个比较仍然是
「相等」，于是判定成「不是升级」，跳过整块表结构检查。

教训：**光测迁移函数不够，要测「迁移会不会被调用」**。
这里钉的就是那个调用条件。
"""
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _decide(conf, version):
    """复刻 main.py:442 的判定，供纯逻辑测试用。"""
    from webserver.main import should_check_db_structure

    return should_check_db_structure(conf, version)


def test_same_version_still_checks_structure():
    """★ 核心回归：版本号没变也必须检查表结构。

    这是 NAS 上那个 500 的根因。`installed_version == VERSION` 说明
    「装的是同一版」，但**不代表表结构是新的**——我们发布新包时
    并不总是改 VERSION，改了模型却没改版本号是常态。
    """
    assert _decide({"installed": True, "installed_version": "v4.8.0"}, "v4.8.0") is True


def test_first_install_checks_structure():
    """首次安装（没有 installed_version）当然要建表。"""
    assert _decide({"installed": False}, "v4.8.0") is True
    assert _decide({}, "v4.8.0") is True


def test_version_changed_checks_structure():
    """跨版本升级要检查。"""
    assert _decide({"installed": True, "installed_version": "v4.7.0"}, "v4.8.0") is True


def test_empty_string_version_checked():
    """老配置文件里写成空串的情况。"""
    assert _decide({"installed": True, "installed_version": ""}, "v4.8.0") is True


def test_downgrade_checked():
    """降级也要检查——降级后表里可能有新列，迁移是幂等的，跑一遍无害。"""
    assert _decide({"installed": True, "installed_version": "v4.9.0"}, "v4.8.0") is True


def test_main_uses_the_helper():
    """防止有人绕过 helper 把判定改回 `!= VERSION`。

    读源码断言是不得已：`main()` 里那一行夹在 calibre 初始化中间，
    没法在沙箱里真跑。这里只钉「用的是 helper」，不钉 helper 的实现。
    """
    with open(os.path.join(ROOT, "webserver", "main.py"), encoding="utf-8") as f:
        src = f.read()

    assert "should_check_db_structure(" in src, (
        "main.py 没有调用 should_check_db_structure()——"
        "可能在用 `installed_version != VERSION` 判定，"
        "那样版本号不变时不会迁移表结构（r11 事故根因）"
    )
    # 旧写法的特征串，出现就是回退了
    assert 'CONF.get("installed_version", "") != VERSION' not in src, (
        "main.py 仍在用 `installed_version != VERSION` 判定是否需要迁移，"
        "这正是 r11 `no such column: readers.birth_year` 的根因"
    )


def test_setup_actually_calls_adjust_reader_table():
    """`need_check_db=True` 时，adjust_reader_table 必须真的被调到。

    用 spy 替掉真实实现，只验证「调用了」，不碰数据库。
    """
    from webserver.services.async_service import AsyncService

    called = {"reader": 0}

    class FakeSession:
        def execute(self, *a, **kw):
            class R:
                def fetchall(self_inner):
                    return []

            return R()

        def commit(self):
            pass

        def rollback(self):
            pass

    svc = AsyncService.__new__(AsyncService)
    svc.db = None
    fake_session = FakeSession()
    # setup() 第一件事就是 `self.scoped_session = scoped_session`（形参覆盖属性），
    # 所以工厂必须通过实参传进去，赋给 svc.scoped_session 会被冲掉。
    scoped = lambda: fake_session

    def fake_adjust_item():
        return False, False

    def spy_reader():
        called["reader"] += 1
        return False

    svc.adjust_item_table = fake_adjust_item
    svc.adjust_reader_table = spy_reader
    svc.adjust_scanfile_table = lambda: False
    svc.adjust_readings_table = lambda: None
    svc.adjust_booklist_table = lambda: None
    svc.adjust_audio_playback_table = lambda: None
    svc.ensure_readings_indexes = lambda: None
    svc.adjust_messages_table = lambda: None

    svc.setup(scoped_session=scoped, need_check_db=True)
    assert called["reader"] == 1, "need_check_db=True 时没调用 adjust_reader_table"


def test_one_failing_step_does_not_rollback_others():
    """★ 任一步迁移失败，不能回滚其它步已做的改动。

    这是 r11 事故的第二个成因。真实环境里 `adjust_item_table()` 抛异常
    （表缺失 / 权限 / 锁），旧实现整块 `rollback()`，把已经补好的
    `readers.birth_year` 一起撤了，启动后照样 `no such column`。

    这里让 items 步必失败，断言 readers 步仍然被调用并提交。
    """
    from webserver.services.async_service import AsyncService

    committed = []

    class FakeSession:
        def execute(self, *a, **kw):
            class R:
                def fetchall(self_inner):
                    return []

            return R()

        def commit(self):
            committed.append(1)

        def rollback(self):
            pass

    svc = AsyncService.__new__(AsyncService)
    svc.db = None
    fake = FakeSession()
    scoped = lambda: fake

    def boom():
        raise RuntimeError("simulated: no such table: items")

    reader_called = {"n": 0}

    svc._step_item_table = boom
    svc._step_reader_table = lambda: reader_called.__setitem__("n", reader_called["n"] + 1)
    svc._step_scanfile_table = boom
    svc._step_readings_table = boom
    svc._step_booklist_table = boom
    svc._step_audio_playback_table = boom
    svc.ensure_readings_indexes = lambda: None
    svc.adjust_messages_table = lambda: None

    svc.setup(scoped_session=scoped, need_check_db=True)

    assert reader_called["n"] == 1, "items 步失败后，readers 步没被继续执行"
    assert len(committed) >= 1, "readers 步成功后没有提交，改动会丢"
