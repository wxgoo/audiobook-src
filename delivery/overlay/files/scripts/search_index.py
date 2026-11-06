#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""中文检索索引的命令行入口（不依赖 Web 服务）。

用法（在容器内或源码根目录执行）：

    python3 scripts/search_index.py status      # 查看索引状态
    python3 scripts/search_index.py rebuild     # 强制全量重建
    python3 scripts/search_index.py search 三体  # 调试：打印命中的 book_id

容器里推荐：

    docker exec -u 0 audiobook-mybooks-1 python3 scripts/search_index.py rebuild

重建是原子替换：构建期间线上搜索继续用旧索引，完成后一次性切换。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webserver.services.search_index import get_search_index  # noqa: E402


def main(argv):
    service = get_search_index()
    cmd = argv[1] if len(argv) > 1 else "status"

    if cmd == "status":
        print(json.dumps(service.status(), ensure_ascii=False, indent=2))
        return 0

    if cmd == "rebuild":
        result = service.rebuild(force=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1

    if cmd == "search":
        if len(argv) < 3:
            print("用法: python3 scripts/search_index.py search <关键词>")
            return 1
        ids = service.search(" ".join(argv[2:]))
        if ids is None:
            print("该查询会走 calibre 原生 search（高级语法或索引不可用）")
            return 0
        print(json.dumps({"count": len(ids), "book_ids": ids[:200]},
                         ensure_ascii=False, indent=2))
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
