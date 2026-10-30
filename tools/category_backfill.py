#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""按现有 tags 批量回填 calibre 自定义列 #category。

用途（见 INSTALL_GUIDE.md 读者组分级权限一节）：
  读者组（ReaderGroupService）的「分类」白/黑名单匹配的是每本书的
  calibre 自定义列 #category（webserver/constants.py: CALIBRE_COLUMN_CATEGORY）。
  书库里大量书籍没填这一列时，读者组白名单会把这些书全部挡掉。
  本脚本把每本书的标签（tags）回填进 #category，让权限判定与浏览页一致。

数据源与规则：
  * 只处理 #category 为空 且 tags 非空的书，已有分类的书绝不覆盖；
  * 默认取第一个标签作为分类值（calibre 的 #category 通常是单值列）；
    --mode join 则把全部标签用「、」连接成一个值；
  * --only TAGS 只处理含指定标签的书（逗号分隔，其余书跳过）。

安全性：
  * 默认 dry-run，只打印将发生的变更，不加 --apply 不写任何数据；
  * 通过 calibredb CLI 写入（而非直连 metadata.db），与运行中的
    mybooks 服务（tornado 持有库锁）并发安全，无需停服。

用法（在 mybooks 容器内）：
  docker exec -it <容器名> python3 /var/www/mybooks/tools/category_backfill.py
  docker exec -it <容器名> python3 /var/www/mybooks/tools/category_backfill.py --apply
  docker exec -it <容器名> python3 /var/www/mybooks/tools/category_backfill.py \
      --library /data/books/library --only 绘本,教材 --apply
  # 宿主机直跑也可以，只要有 calibredb：
  python3 tools/category_backfill.py --library /path/to/library --apply
"""

import argparse
import json
import shutil
import subprocess
import sys


def find_calibredb(explicit=None):
    """定位 calibredb，找不到给出人话提示。"""
    if explicit:
        return explicit
    path = shutil.which("calibredb")
    if not path:
        sys.exit(
            "错误：找不到 calibredb。\n"
            "  - 容器内运行：mybooks 镜像自带，直接 docker exec 即可；\n"
            "  - 宿主机运行：请先安装 calibre 或用 --calibredb 指定路径。"
        )
    return path


def run_calibredb(cmd, library, args):
    """执行 calibredb 子命令，出错时带上下文抛异常。"""
    full = [args.calibredb, cmd, f"--with-library={library}"] + args.extra + cmd_args(cmd, args)
    proc = subprocess.run(full, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"calibredb {cmd} 失败 (exit {proc.returncode}):\n"
                           f"stdout: {proc.stdout}\nstderr: {proc.stderr}")
    return proc.stdout


def cmd_args(cmd, args):
    """各子命令的固定参数。"""
    if cmd == "custom_columns":
        return []
    if cmd == "list":
        # calibredb list 的自定义列要用 *label 形式（custom_columns 输出的前缀），
        # 不是 GUI 里的 #lookup_name。JSON 键同样是 *category；老版本可能给
        # #category，load_books 里两种键都兼容。
        return ["--for-machine", "--fields=id,tags,*category", "--separator=\t"]
    if cmd == "set_metadata":
        return []  # 参数在逐条调用时构造
    raise ValueError(cmd)


def load_books(library, args):
    """拉取全部书籍的 id/tags/#category，返回 [{id, tags, category}]。

    calibredb list --for-machine 输出 JSON 数组；自定义列的键在不同版本里
    可能是 *category 或 #category，统一读出来映射成 category。
    """
    out = run_calibredb("list", library, args)
    books = json.loads(out)
    for b in books:
        raw = b.pop("*category", None)
        if raw is None:
            raw = b.pop("#category", None)
        b["category"] = raw
        tags = b.get("tags")
        b["tags"] = tags if isinstance(tags, list) else ([] if not tags else [str(tags)])
    return books


def ensure_category_column(library, args):
    """确认 #category 自定义列存在（读者组依赖它）。

    calibredb custom_columns 的输出行以 *label 开头（如 *category），
    兼容 #category 形式。
    """
    out = run_calibredb("custom_columns", library, args)
    for line in out.splitlines():
        first = line.strip().lstrip("*#")
        if first == "category" or first.startswith("category "):
            return True
    sys.exit(
        "错误：书库没有 #category 自定义列（读者组分级权限依赖它）。\n"
        "先在 calibre 客户端或用 calibredb custom_columns --create 创建它，再跑本脚本。"
    )


def pick_category(tags, mode):
    """从标签里挑出要写入的 #category 值。"""
    if not tags:
        return None
    if mode == "join":
        return "、".join(tags)
    return tags[0]


def in_scope(tags, only):
    """--only 过滤：指定了标签集时，书必须至少含其中一个。"""
    if not only:
        return True
    return bool(set(tags) & only)


def main():
    parser = argparse.ArgumentParser(
        description="按现有 tags 批量回填 calibre 自定义列 #category（默认 dry-run）")
    parser.add_argument("--library", default="/data/books/library",
                        help="calibre 书库路径（容器内默认 /data/books/library）")
    parser.add_argument("--apply", action="store_true",
                        help="真正写入；缺省只打印将要做的变更")
    parser.add_argument("--mode", choices=["first", "join"], default="first",
                        help="取值规则：first=第一个标签（默认）；join=全部标签用「、」连接")
    parser.add_argument("--only", default="",
                        help="只处理含这些标签的书（逗号分隔），其余跳过")
    parser.add_argument("--calibredb", default=None,
                        help="calibredb 可执行文件路径（默认从 PATH 查找）")
    parser.add_argument("-n", "--limit", type=int, default=0,
                        help="最多处理 N 本（0=不限），用于小范围试跑")
    args, unknown = parser.parse_known_args()

    if unknown:
        # 兼容 calibredb 自身的全局参数透传，如 -v
        args.extra = unknown
    else:
        args.extra = []

    only = {t.strip() for t in args.only.split(",") if t.strip()}
    args.calibredb = find_calibredb(args.calibredb)
    ensure_category_column(args.library, args)
    books = load_books(args.library, args)

    todo = []
    for b in books:
        if b.get("category"):
            continue  # 已有分类，绝不覆盖
        if not in_scope(b["tags"], only):
            continue
        value = pick_category(b["tags"], args.mode)
        if value:
            todo.append((b["id"], b.get("title", ""), value))

    if args.limit > 0:
        todo = todo[: args.limit]

    print(f"书库共 {len(books)} 本；待回填 {len(todo)} 本（#category 为空且有标签）。")
    for bid, title, value in todo:
        print(f"  [{bid}] {title} -> #category = {value}")

    if not todo:
        print("没有需要回填的书，结束。")
        return
    if not args.apply:
        print(f"\n这是 dry-run 预览，未写入任何数据。确认无误后加 --apply 执行。")
        return

    ok = fail = 0
    for bid, _title, value in todo:
        try:
            full = [args.calibredb, "set_metadata",
                    f"--with-library={args.library}",
                    "--field", f"#category:{value}", str(bid)]
            subprocess.run(full, check=True, capture_output=True, text=True)
            ok += 1
        except subprocess.CalledProcessError as e:
            fail += 1
            print(f"  写入失败 [{bid}]: {e.stderr.strip()}", file=sys.stderr)
    print(f"\n完成：成功 {ok} 本，失败 {fail} 本。")
    print("提示：读者组的分类判定实时读库，回填后无需重启服务即可生效。")


if __name__ == "__main__":
    main()
