#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""游标分页（keyset pagination）小工具。

旧接口用 `start`/`size` 的 offset 分页，深翻页时每次都要跳过前 N 条；
这里提供不透明游标（base64 JSON），把「上一页最后一条的排序键」带到
下一页，翻得再深也只处理当前页。旧参数全部保留，前端不传 `after`
时行为完全不变。
"""

import base64
import json


def encode_cursor(payload):
    """把排序键打包成 URL 安全的短字符串。"""
    if not isinstance(payload, dict):
        return None
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(token):
    """解析游标；非法/空值返回 None（调用方按 offset 处理）。"""
    if not token:
        return None
    try:
        padded = token + "=" * (-len(token) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def parse_id_cursor(token, kind):
    """取出 id 类游标（kind=id/audio）里的 last_id；不匹配返回 None。"""
    data = decode_cursor(token)
    if not data or data.get("k") != kind:
        return None
    try:
        return int(data.get("id"))
    except (TypeError, ValueError):
        return None
