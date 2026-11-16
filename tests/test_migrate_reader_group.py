# -*- coding: utf-8 -*-
"""读者组数据迁移脚本的契约测试。

迁移脚本 plan_migrations() 是纯函数：给一组用户 + 一个 effective_limits 函数，
算出「自身无显式设置、且靠组继承到限制」的用户清单。这些用例钉住它的边界：
  - 自身已显式设置的用户不能被覆盖（否则会改掉管理员手工配的限制）；
  - 不受组限制的用户不写（保持 0=不限）；
  - group-missing 哨兵（受限且无书可读）必须被固化，否则删组后权限静默全开；
  - 写回时只动 read_limit/limit_categories/limit_tags 三个字段。
"""

import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "migrate_reader_group_to_fields.py")


def _load():
    spec = importlib.util.spec_from_file_location("migrate_rg", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeReader:
    def __init__(self, name, read_limit=0, cats="", tags=""):
        self.username = name
        self.read_limit = read_limit
        self.limit_categories = cats
        self.limit_tags = tags


def test_plan_skips_users_with_own_explicit_limits():
    mod = _load()
    # 这个用户自身配了 read_limit=1，即使组会给出别的限制也不能动他
    u = FakeReader("already_set", read_limit=1, tags="own-tag")
    eff = lambda r: {"read_limit": 2, "limit_tags": "group-tag", "source": "group"}
    assert mod.plan_migrations([u], eff) == []


def test_plan_skips_unrestricted_users():
    mod = _load()
    u = FakeReader("no_group")
    eff = lambda r: {"read_limit": 0, "source": "none"}
    assert mod.plan_migrations([u], eff) == []


def test_plan_includes_group_inherited_restrictions():
    mod = _load()
    u = FakeReader("kid")
    eff = lambda r: {"read_limit": 1, "limit_tags": "儿童,绘本",
                     "limit_categories": "", "source": "group"}
    plans = mod.plan_migrations([u], eff)
    assert len(plans) == 1
    assert plans[0][0] is u
    assert plans[0][1]["read_limit"] == 1


def test_plan_includes_group_missing_sentinel():
    """成员指向不存在的组 → effective_limits 返回受限哨兵，必须迁移。

    否则删组后用户 read_limit=0=不限，等于把「受限且无书可读」静默变成「全库可读」。
    """
    mod = _load()
    u = FakeReader("orphan")
    eff = lambda r: {"read_limit": 1, "limit_categories": "__none__",
                     "limit_tags": "__none__", "source": "group-missing"}
    plans = mod.plan_migrations([u], eff)
    assert len(plans) == 1
    assert plans[0][1]["source"] == "group-missing"


def test_plan_handles_mixed_batch():
    mod = _load()
    own = FakeReader("own", read_limit=2, tags="x")
    inherit = FakeReader("inherit")
    free = FakeReader("free")
    eff_by_name = {
        "inherit": {"read_limit": 1, "limit_tags": "kids", "source": "group"},
        "free": {"read_limit": 0, "source": "none"},
    }
    plans = mod.plan_migrations(
        [own, inherit, free], lambda r: eff_by_name.get(r.username, {"read_limit": 0})
    )
    assert [p[0].username for p in plans] == ["inherit"]


def test_script_references_effective_limits_before_delete():
    """迁移脚本必须调用 effective_limits（删除 reader_group 前的核心依赖）。"""
    src = open(SCRIPT, encoding="utf-8").read()
    assert "ReaderGroupService.effective_limits" in src
    assert "--dry-run" in src
    assert "backup" in src
