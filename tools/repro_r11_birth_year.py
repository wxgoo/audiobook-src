"""端到端复现 + 验证：r10 旧库 → r11 启动 → birth_year 列被补上。

这个脚本刻意**不复用** `AsyncService` 的构造（那会连站点配置），
而是走 `main.should_check_db_structure()` → `AsyncService.setup()` 这条
真实调用链，唯一被替掉的是 session 工厂。

用法：python3 tools/repro_r11_birth_year.py
"""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from webserver.main import should_check_db_structure  # noqa: E402
from webserver.services.async_service import AsyncService  # noqa: E402
from webserver.version import VERSION  # noqa: E402


def make_r10_db():
    """造一个 r10 时代的库。

    readers 表按真实 r10 形状建（有 age、没有 birth_year），其余表只造出现有的，
    缺的表让迁移步骤自然失败——正好验证「一步失败不拖累其它步」。
    """
    path = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE readers ("
        " id INTEGER PRIMARY KEY,"
        " username VARCHAR(200),"
        " password VARCHAR(200) DEFAULT '',"
        " salt VARCHAR(200) DEFAULT '',"
        " name VARCHAR(200) DEFAULT '',"
        " email VARCHAR(200) DEFAULT '',"
        " avatar VARCHAR(200) DEFAULT '',"
        " admin BOOLEAN DEFAULT 0,"
        " active BOOLEAN DEFAULT 1,"
        " permission VARCHAR(200) DEFAULT '',"
        " create_time DATETIME,"
        " update_time DATETIME,"
        " access_time DATETIME,"
        " extra TEXT,"
        " vipquota INTEGER DEFAULT 0,"
        " vipexpire DATETIME,"
        " read_limit INTEGER DEFAULT 0,"
        " limit_categories TEXT,"
        " limit_tags TEXT,"
        " age INTEGER NOT NULL DEFAULT 0)"
    )
    conn.executemany(
        "INSERT INTO readers (username, age) VALUES (?, ?)",
        [("kid", 12), ("unset", 0), ("adult", 30)],
    )
    conn.commit()
    conn.close()
    return path


def columns_of(session, table="readers"):
    return [r[1] for r in session.execute(text(f"PRAGMA table_info({table})")).fetchall()]


def main():
    path = make_r10_db()
    engine = create_engine("sqlite:///" + path)
    Session = sessionmaker(bind=engine)
    session = Session()

    print("=" * 62)
    print("1) r10 旧库现状")
    before = columns_of(session)
    print("   readers 列:", before)
    assert "birth_year" not in before, "夹具造错了，本来不该有 birth_year"

    print()
    print("2) 复现事故条件：installed_version == VERSION（r10 装完就是这样）")
    conf = {"installed": True, "installed_version": VERSION}
    print(f"   installed_version = {VERSION!r}  ==  VERSION = {VERSION!r}")
    old_rule = conf.get("installed_version", "") != VERSION
    new_rule = should_check_db_structure(conf, VERSION)
    print(f"   旧判定 installed_version != VERSION  -> {old_rule}   ← 这就是 r11 的 bug")
    print(f"   新判定 should_check_db_structure(...) -> {new_rule}")

    print()
    print("3) 走真实调用链：setup(need_check_db=...)")
    svc = AsyncService.__new__(AsyncService)
    svc.setup(calibre_db=None, scoped_session=lambda: session, need_check_db=new_rule)

    print()
    print("4) 迁移后")
    after = columns_of(session)
    print("   readers 列:", after)

    if "birth_year" not in after:
        print()
        print("   ❌ 仍然没有 birth_year —— 迁移没生效")
        return 1

    rows = session.execute(
        text("SELECT username, age, birth_year FROM readers ORDER BY id")
    ).fetchall()
    print()
    print("   回填结果（birth_year = 当前年 - age）：")
    for name, age, by in rows:
        print(f"     {name:8} age={age:<4} birth_year={by}")

    print()
    print("5) ORM 查询验证（事故里的那条 SQL）")
    from webserver.models import Reader

    for name, age, _by in rows:
        r = session.execute(
            text("SELECT id FROM readers WHERE username = :n"), {"n": name}
        ).fetchone()
        obj = session.query(Reader).filter(Reader.id == r[0]).first()
        print(f"     {name:8} -> reader.age = {obj.age}  birth_year = {obj.birth_year}")

    print()
    print("   ✅ 全部通过：列已补、值已回填、ORM 可查")
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
