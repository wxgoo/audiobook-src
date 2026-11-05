"""出生年份改造（4.6.0-19 r11）的行为测试。

与其他测试的差别：这里**真的**跑迁移语句和 ORM 模型，而不是读源码断言。
因为这次改动的风险不在「代码写了没写」，而在「老库能不能平滑升级」——
r10 已经给部分用户写了 age，如果迁移把值丢了或者每轮启动都被旧 age 覆盖
回去，分组限额就会静默错人。

能在沙箱里跑，是因为 models.py 依赖的 social_sqlalchemy 有桩
（/tmp/stubs），且迁移只用到 sqlite3 + SQLAlchemy Core 的 text()。
"""
import os
import sqlite3
import tempfile

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def legacy_db():
    """造一个 r10 时代的旧库：readers 表有 age，没有 birth_year。"""
    path = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE readers ("
        " id INTEGER PRIMARY KEY,"
        " username VARCHAR(200),"
        " age INTEGER NOT NULL DEFAULT 0)"
    )
    conn.executemany(
        "INSERT INTO readers (username, age) VALUES (?, ?)",
        [("kid", 12), ("unset", 0), ("adult", 30)],
    )
    conn.commit()
    conn.close()
    engine = create_engine("sqlite:///" + path)
    yield engine, sessionmaker(bind=engine)()
    session = None
    engine.dispose()


def _run_migration(session):
    """直接调用被测函数本体。AsyncService.__init__ 会连站点配置，绕过它。"""
    from webserver.services.async_service import AsyncService

    svc = AsyncService.__new__(AsyncService)
    svc.session = session
    return svc.adjust_reader_table()


def test_migration_backfills_birth_year_from_age(legacy_db):
    engine, session = legacy_db
    assert _run_migration(session) is True
    session.commit()

    rows = session.execute(
        text("SELECT username, age, birth_year FROM readers ORDER BY id")
    ).fetchall()
    now_year = session.execute(text("SELECT CAST(strftime('%Y', 'now') AS INTEGER)")).scalar()

    assert rows[0][2] == now_year - 12, "12 岁的用户出生年份应换算为当年-12"
    assert rows[1][2] == 0, "age=0 表示未填，不能凭空造一个出生年份"
    assert rows[2][2] == now_year - 30


def test_migration_idempotent(legacy_db):
    engine, session = legacy_db
    _run_migration(session)
    session.commit()
    first = session.execute(text("SELECT birth_year FROM readers ORDER BY id")).fetchall()
    _run_migration(session)
    session.commit()
    second = session.execute(text("SELECT birth_year FROM readers ORDER BY id")).fetchall()
    assert first == second, "重复启动不能改变已迁移的数据"


def test_migration_does_not_overwrite_admin_fix(legacy_db):
    """管理员手工纠正过的出生年份，不能被下一轮启动用旧 age 盖回去。

    age 列故意保留不删（回滚兜底），所以回填语句必须限定在「本次刚补列」
    的分支里——这个测试就是钉住那一点。
    """
    engine, session = legacy_db
    _run_migration(session)
    session.commit()
    session.execute(text("UPDATE readers SET birth_year = 2015 WHERE id = 1"))
    session.commit()

    _run_migration(session)
    session.commit()
    age, birth_year = session.execute(
        text("SELECT age, birth_year FROM readers WHERE id = 1")
    ).fetchone()
    assert age == 12, "旧列保持原样，供回滚用"
    assert birth_year == 2015, "手改值必须存活"


def test_migration_keeps_age_column(legacy_db):
    engine, session = legacy_db
    _run_migration(session)
    session.commit()
    cols = [r[1] for r in session.execute(text("PRAGMA table_info(readers)")).fetchall()]
    assert "birth_year" in cols
    assert "age" in cols, "SQLite 删列代价大且会破坏回滚，age 有意保留"


def test_fresh_db_has_birth_year_from_create_all():
    """全新安装走 create_all，直接就有 birth_year（不依赖 ALTER）。"""
    path = tempfile.mktemp(suffix=".db")
    engine = create_engine("sqlite:///" + path)
    from webserver.models import Reader, user_syncdb

    user_syncdb(engine)
    cols = [r[1] for r in engine.connect()
            .execute(text("PRAGMA table_info(readers)")).fetchall()]
    assert "birth_year" in cols
    assert "age" not in cols, "新库不该再建整数岁列"


def test_age_property_derives_and_never_negative():
    """Reader.age 是派生属性：未填返回 0，未来年份不返回负数。"""
    from webserver.models import Reader

    r = Reader()
    r.birth_year = 2000
    assert r.age == Reader.current_year() - 2000

    r.birth_year = 0
    assert r.age == 0

    r.birth_year = Reader.current_year() + 3
    assert r.age == 0


def test_password_and_birth_year_policies_live_in_one_place():
    """防漂移：策略常量只允许在 Reader 上定义一份，处理器里不许再写死数字。"""
    src = open(os.path.join(ROOT, "webserver", "models.py"), encoding="utf-8").read()
    assert "BIRTH_YEAR_MIN = 1900" in src
    assert src.count("BIRTH_YEAR_MIN") >= 2, "常量定义后必须真的被用于校验"
    assert "def current_year" in src, "年份必须走方法，测试才能打桩、跨年才不会错"

    for name in ("user.py", "admin.py"):
        hsrc = open(os.path.join(ROOT, "webserver", "handlers", name), encoding="utf-8").read()
        assert "1900" not in hsrc, f"{name} 里又出现了硬编码年份下限"
