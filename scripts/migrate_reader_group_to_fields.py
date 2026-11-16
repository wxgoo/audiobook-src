#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""读者组 → 用户字段 一次性数据迁移（删除 reader_group 定制层前运行）。

背景
----
我们相对上游 4.7.0 多了一套「读者组分级权限」：组定义存 CONF["READER_GROUPS"]、
成员归属存 Reader.extra["reader_group"]，用户的生效限制通过 effective_limits() 计算
（自身显式设置优先，否则回退到组配置）。这套定制与上游不一致且是权限判化的最大源头，
决定删除。上游本身保留「阅读范围限制」能力（每个用户自己的
read_limit / limit_tags / limit_categories 字段 + ALLOW_READ_RANGE_SETTING 开关），
所以我们只需把「靠组继承的那部分限制」固化到用户自己的字段里，删除后行为不变。

做什么
------
遍历所有 Reader：
  * 若用户自身已显式设置（read_limit>0 或 limit_tags/limit_categories 非空）→ 跳过（保持原值）；
  * 否则调用删除前的 ReaderGroupService.effective_limits(reader) 算出生效限制：
      - 若结果受限（read_limit>0）→ 写回该用户的 read_limit/limit_tags/limit_categories；
      - 若结果不受限（read_limit==0）→ 无需写（保持 0 即不限）。
  * 「成员指向不存在的组」（source=group-missing，effective_limits 返回哨兵 __none__）
    同样固化：这是「受限且无书可读」的兜底，写回后不会出现权限静默全开。

运行方式
--------
**在容器内运行**（能 import webserver、CONF 自动加载 /data/books/settings/ 的真实设置）：

    # 1) 先预览，不写库
    python3 scripts/migrate_reader_group_to_fields.py --data-dir /data --dry-run

    # 2) 确认清单无误后正式执行（自动备份 user db）
    python3 scripts/migrate_reader_group_to_fields.py --data-dir /data

也可在宿主机运行，但必须能 import webserver 且 settings 指向同一份配置：
    python3 scripts/migrate_reader_group_to_fields.py --data-dir /path/to/data --settings-path /path/to/data/books/settings

选项
----
  --data-dir PATH       DATA_DIR（默认 /data）；用户库默认 <data-dir>/books/calibre-webserver.db
  --db-url URL          显式指定 sqlalchemy 数据库 URL（覆盖 --data-dir 推导）
  --settings-path PATH  显式指定 settings 目录（含 auto.py/manual.py），覆盖 CONF 默认值
  --dry-run             只打印将要变更的用户，不写库、不备份
  --no-backup           正式执行时跳过备份（不推荐）
  -y, --yes             跳过交互确认

退出码：0 成功；1 失败（参数错误 / 连库失败 / 写库异常）。
"""

import argparse
import os
import shutil
import sys
from datetime import datetime


def plan_migrations(readers, effective_limits_fn):
    """算出需要迁移的用户清单（纯函数，便于单测）。

    readers: 可迭代的 Reader 对象（需有 read_limit/limit_tags/limit_categories/extra/username）。
    effective_limits_fn: reader -> dict（传 ReaderGroupService.effective_limits）。
    返回 [(reader, eff_dict), ...]，仅含「自身无显式设置 且 生效限制为受限」的用户。
    """
    plans = []
    for r in readers:
        own_limit = int(getattr(r, "read_limit", 0) or 0)
        own_cats = (getattr(r, "limit_categories", "") or "").strip()
        own_tags = (getattr(r, "limit_tags", "") or "").strip()
        if own_limit > 0 or own_cats or own_tags:
            continue  # 自身已显式设置，保持原值
        try:
            eff = effective_limits_fn(r)
        except Exception:
            continue
        if int(eff.get("read_limit") or 0) <= 0:
            continue  # 生效限制为不限，无需写回
        plans.append((r, eff))
    return plans


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="读者组 → 用户字段 一次性数据迁移")
    p.add_argument("--data-dir", default="/data", help="DATA_DIR（默认 /data）")
    p.add_argument("--db-url", default=None, help="显式 sqlalchemy db URL（覆盖 --data-dir 推导）")
    p.add_argument("--settings-path", default=None, help="显式 settings 目录（含 auto.py/manual.py）")
    p.add_argument("--dry-run", action="store_true", help="只预览，不写库")
    p.add_argument("--no-backup", action="store_true", help="正式执行时跳过备份")
    p.add_argument("-y", "--yes", action="store_true", help="跳过交互确认")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    # 让 loader 能找到真实的 auto.py/manual.py：必须在 import webserver.loader 之前，
    # 把 settings 目录塞进 sys.path（loader.set_store_path 也读 CONF["settings_path"]）。
    settings_path = args.settings_path or os.path.join(args.data_dir, "books", "settings")
    if os.path.isdir(settings_path):
        if settings_path not in sys.path:
            sys.path.insert(0, settings_path)
    else:
        print("[warn] settings 目录不存在：%s（将用代码内置默认配置，可能读不到读者组定义）"
              % settings_path, file=sys.stderr)

    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker, scoped_session
        from webserver import loader
        from webserver import models
        from webserver.services.reader_group import ReaderGroupService
    except Exception as e:
        print("[error] import 失败（需在能 import webserver 的环境运行，如容器内）：%s" % e,
              file=sys.stderr)
        return 1

    # 显式覆盖 CONF 的 settings_path，确保 loader 若再次 set_store_path 时仍指向这里
    loader.CONF["settings_path"] = settings_path

    # data_dir=/data → /data/books/calibre-webserver.db → sqlite:////data/books/calibre-webserver.db
    # （绝对路径拼 sqlite URL 是 4 个斜杠：sqlite:/// + /path）
    if args.db_url:
        db_url = args.db_url
        db_path = db_url.replace("sqlite:////", "/", 1).replace("sqlite:///", "", 1)
    else:
        db_path = os.path.abspath(os.path.join(args.data_dir, "books", "calibre-webserver.db"))
        db_url = "sqlite:///" + db_path

    print("数据库：%s" % db_path)
    if not os.path.isfile(db_path):
        print("[error] 数据库文件不存在：%s" % db_path, file=sys.stderr)
        return 1

    try:
        engine = create_engine(db_url)
        session = scoped_session(sessionmaker(bind=engine, autoflush=False))
        models.bind_session(session)
        readers = session.query(models.Reader).all()
    except Exception as e:
        print("[error] 连库/查询失败：%s" % e, file=sys.stderr)
        return 1

    CONF = loader.get_settings()
    print("读者组定义条目数：%d（READER_GROUPS_ENABLED=%s, READER_GROUP_STRICT=%s）"
          % (len(CONF.get("READER_GROUPS") or {}),
             CONF.get("READER_GROUPS_ENABLED", True),
             CONF.get("READER_GROUP_STRICT", True)))

    # 计算将变更的清单
    def _eff(r):
        try:
            return ReaderGroupService.effective_limits(r)
        except Exception as e:
            print("[warn] 读取 %s 的生效限制失败：%s" % (getattr(r, "username", "?"), e),
                  file=sys.stderr)
            return {"read_limit": 0}

    plans = plan_migrations(readers, _eff)

    if not plans:
        print("\n没有需要迁移的用户（所有人要么已自行设置限制，要么不受组限制）。")
        return 0

    print("\n将迁移 %d 个用户：" % len(plans))
    print("%-20s %-12s %-6s %-24s %s" % ("用户名", "来源", "limit", "categories", "tags"))
    for r, eff in plans:
        print("%-20s %-12s %-6s %-24s %s" % (
            getattr(r, "username", "?"), eff.get("source", ""), eff.get("read_limit"),
            (eff.get("limit_categories") or "")[:24], eff.get("limit_tags") or ""))

    if args.dry_run:
        print("\n[dry-run] 未写库、未备份。")
        return 0

    if not args.yes:
        try:
            ans = input("\n确认写回上述 %d 个用户？[y/N] " % len(plans)).strip().lower()
        except EOFError:
            ans = ""
        if ans not in ("y", "yes"):
            print("已取消。")
            return 0

    # 备份
    if not args.no_backup:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = db_path + ".bak-migrate-%s" % stamp
        try:
            shutil.copyfile(db_path, backup)
            print("\n已备份：%s" % backup)
        except Exception as e:
            print("[error] 备份失败：%s" % e, file=sys.stderr)
            return 1

    # 写回
    try:
        for r, eff in plans:
            r.read_limit = int(eff.get("read_limit") or 0)
            r.limit_categories = eff.get("limit_categories") or ""
            r.limit_tags = eff.get("limit_tags") or ""
        session.commit()
        print("已写回 %d 个用户。" % len(plans))
    except Exception as e:
        session.rollback()
        print("[error] 写库失败（已回滚）：%s" % e, file=sys.stderr)
        return 1
    finally:
        session.remove()

    print("\n迁移完成。现在可以安全删除 reader_group 定制层。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
