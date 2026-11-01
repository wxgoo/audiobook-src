#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""作者归一化管理 API（管理员专用）。

配套 webserver/base/author_norm.py，提供四个能力：

1. 体检（GET /scan）：只读报告。把书库里所有作者条目按归一化键聚类，
   列出「确定重复 / 疑似重复 / 脏名候选」。**只报告，不改数据**——
   真正改存量书走既有的「作者清理」（/api/toolbox/author_clean），
   本接口的产出是「往别名表里加哪条规则」的依据。
2. 别名表读写（GET/POST /alias）：config.json 的整表读写。
3. 归一化预览（POST /test）：传一个名字，返回清洗、算键、查表的全过程。
   调规则时天天用，不用真导一本书来试。
4. 锁定管理（PUT /api/admin/book/<bid>/author_lock）：手工开锁/落锁。

为什么体检不改数据：体检按归一化键聚类只能证明「写法可能指同一人」，
不能证明「合并一定对」（张三/张叁可能是两个人）。合并决策必须人在看，
所以体检只读，把判断留给人；别名表才是落地的机制。
"""

import logging

import tornado.escape

from webserver.i18n import _
from webserver.handlers.base import BaseHandler, is_admin, js
from webserver.base.author_norm import (
    author_norm_key,
    clean_authors,
    get_alias_store,
    lock_author,
    loose_author_key,
    _DEFAULT_NEVER_MERGE,
)


def _build_report(author_map):
    """把 {作者名: 书 id 集合} 聚成体检报告。

    产出四类（按设计稿 §4）：
    - duplicates  确定重复：归一化键相同、显示名不同。高置信，建议进别名表。
    - suspects    疑似重复：清洗后一个名字包含另一个（罗琳 / J·K·罗琳）。
                  归一化键不同但可能是同一人，需要人确认。
    - dirty       脏名候选：L1 清洗后名字发生了变化（(法)法布尔 → 法布尔）。
                  这类不一定要动——别名表建好后新入库不会再产生；存量的走作者清理。
    - ok          正常条目数（前端只需要计数）。
    """
    entries = []          # [(显示名, 书数, 清洗后名, norm_key, loose_key)]
    for name, ids in (author_map or {}).items():
        name = (name or "").strip()
        if not name or name in _DEFAULT_NEVER_MERGE:
            continue
        cleaned, _ = clean_authors([name])
        clean_name = cleaned[0] if cleaned else name
        entries.append({
            "name": name,
            "count": len(ids or []),
            "clean": clean_name,
            "key": author_norm_key(clean_name),
            "loose": loose_author_key(clean_name),
        })

    # 确定重复：同 key、显示名不同。key 为空（无法解析）的跳过。
    by_key = {}
    for e in entries:
        if e["key"]:
            by_key.setdefault(e["key"], []).append(e)
    duplicates = []
    for key, group in sorted(by_key.items()):
        if len(group) < 2:
            continue
        # 标准名：优先选 L1 清洗后没变的写法（(法)法布尔 → 选 法布尔），
        # 再按书数排。书最多、名字又干净的写法大概率是人认得的那一个。
        group_sorted = sorted(
            group, key=lambda x: (x["name"] != x["clean"], -x["count"]))
        duplicates.append({
            "key": key,
            "canonical": group_sorted[0]["name"],
            "books": sum(e["count"] for e in group),
            "variants": [
                {"name": e["name"], "count": e["count"]} for e in group_sorted
            ],
        })

    # 疑似重复：清洗后的名字互为包含（长度都 ≥2，避免「王」包住一切单字）。
    # 已进确定重复组的写法不重复报；但**标准名**仍参与比对——
    # 「罗琳」和「J.K.罗琳」归一化键不同、也不是重复组，得靠疑似报出来。
    dup_keys = {d["key"] for d in duplicates}
    canonical_names = {d["canonical"] for d in duplicates}
    suspects = []
    seen_pairs = set()
    usable = [e for e in entries if e["key"] and e["key"] not in dup_keys
              and len(e["clean"]) >= 2]
    pool = usable + [e for e in entries
                     if e["name"] in canonical_names and e not in usable]
    for i, a in enumerate(pool):
        for b in pool[i + 1:]:
            if a["key"] == b["key"]:
                continue
            long, short = (a, b) if len(a["clean"]) >= len(b["clean"]) else (b, a)
            if short["clean"] in long["clean"]:
                pair = tuple(sorted((a["name"], b["name"])))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                suspects.append({
                    "canonical": long["name"],
                    "books": a["count"] + b["count"],
                    "variants": [
                        {"name": long["name"], "count": long["count"]},
                        {"name": short["name"], "count": short["count"]},
                    ],
                })
    suspects.sort(key=lambda x: -x["books"])

    dirty = [
        {"name": e["name"], "clean": e["clean"], "count": e["count"]}
        for e in entries
        if e["name"] != e["clean"] and e["name"] not in _DEFAULT_NEVER_MERGE
    ]
    dirty.sort(key=lambda x: -x["count"])

    return {
        "total": len(entries),
        "duplicates": duplicates,
        "suspects": suspects,
        "dirty": dirty,
        "ok_count": len(entries) - len(dirty),
    }


class AuthorNormScan(BaseHandler):
    """体检：全库作者条目聚类报告（只读）。"""

    @js
    @is_admin
    def get(self):
        author_map = self.get_authors_book_ids_map()
        try:
            report = _build_report(author_map)
        except Exception as err:  # noqa: BLE001
            logging.error("[AUTHOR_NORM] 体检失败: %s", err)
            return {"err": "server.error", "msg": str(err)}
        return {"err": "ok", "report": report}


class AuthorNormAlias(BaseHandler):
    """别名表整表读写。POST 与 CoreAPI.storage.set_config 同风格：整表覆盖。"""

    @js
    @is_admin
    def get(self):
        store = get_alias_store()
        store.load(force=True)
        return {"err": "ok", "data": store.dump()}

    @js
    @is_admin
    def post(self):
        try:
            data = tornado.escape.json_decode(self.request.body)
        except ValueError:
            return {"err": "params", "msg": _("请求体不是合法 JSON")}

        canonical = data.get("canonical")
        if not isinstance(canonical, dict):
            return {"err": "params", "msg": _("canonical 必须是对象")}

        # 轻校验：标准名非空；键允许空/错（重建索引时会按 name/aliases 兜底）
        cleaned = {}
        for key, entry in canonical.items():
            if not isinstance(entry, dict):
                continue
            name = (entry.get("name") or "").strip()
            if not name:
                continue
            cleaned[str(key)] = {
                "name": name,
                "aliases": [str(a).strip() for a in (entry.get("aliases") or []) if str(a).strip()],
                "note": entry.get("note") or "",
            }

        never = data.get("never_merge")
        if never is not None and not isinstance(never, list):
            return {"err": "params", "msg": _("never_merge 必须是数组")}

        try:
            store = get_alias_store()
            store.save(cleaned, never_merge=never)
        except Exception as err:  # noqa: BLE001
            logging.error("[AUTHOR_NORM] 保存别名表失败: %s", err)
            return {"err": "server.error", "msg": str(err)}
        return {"err": "ok", "msg": _("别名表已保存（%d 条规则）") % len(cleaned),
                "data": store.dump()}


class AuthorNormTest(BaseHandler):
    """归一化预览：传一个名字，返回清洗 → 算键 → 查表的全过程。"""

    @js
    @is_admin
    def post(self):
        try:
            data = tornado.escape.json_decode(self.request.body)
        except ValueError:
            return {"err": "params", "msg": _("请求体不是合法 JSON")}
        name = (data.get("name") or "").strip()
        if not name:
            return {"err": "params", "msg": _("请提供要测试的作者名")}

        store = get_alias_store()
        cleaned, translators = clean_authors([name])
        candidate = cleaned[0] if cleaned else name
        key = author_norm_key(candidate)
        hit_key = store.resolve_key(key)
        resolved = None
        if hit_key:
            resolved = store.canonical_name(hit_key)
        return {
            "err": "ok",
            "input": name,
            "l1": candidate,
            "translators": translators,
            "norm_key": key,
            "loose_key": loose_author_key(candidate),
            "resolved": resolved or candidate,
            "hit": bool(resolved),
        }


class AuthorNormLock(BaseHandler):
    """单本书的作者锁定开关。PUT body: {locked: true/false}"""

    @js
    @is_admin
    def put(self, bid):
        try:
            data = tornado.escape.json_decode(self.request.body)
        except ValueError:
            return {"err": "params", "msg": _("请求体不是合法 JSON")}
        book_id = int(bid)
        locked = bool(data.get("locked"))
        if locked:
            ok = lock_author(self.calibre_db, book_id)
        else:
            ok = _unlock(self.calibre_db, book_id)
        if not ok:
            return {"err": "server.error", "msg": _("操作失败，详见服务端日志")}
        return {"err": "ok", "book_id": book_id, "locked": locked}


def _unlock(calibre_db, book_id):
    from webserver.constants import CALIBRE_COLUMN_AUTHOR_LOCKED

    try:
        calibre_db.set_custom(book_id, 0, CALIBRE_COLUMN_AUTHOR_LOCKED)
        logging.info("[AUTHOR_NORM] 书籍 id=%d 作者已解锁", book_id)
        return True
    except Exception as err:  # noqa: BLE001
        logging.warning("[AUTHOR_NORM] 解锁失败 book_id=%d: %s", book_id, err)
        return False


def routes():
    return [
        (r"/api/admin/author_norm/scan", AuthorNormScan),
        (r"/api/admin/author_norm/alias", AuthorNormAlias),
        (r"/api/admin/author_norm/test", AuthorNormTest),
        (r"/api/admin/book/([0-9]+)/author_lock", AuthorNormLock),
    ]
