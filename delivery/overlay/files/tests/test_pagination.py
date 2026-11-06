"""游标分页工具（webserver/base/pagination.py）的回归。

- 游标是 URL 安全的不透明串，往返一致；
- 非法/空游标返回 None，调用方自动回退到 start/size；
- id 类游标区分 kind（id / audio），避免跨列表误用。
"""

from webserver.base.pagination import decode_cursor, encode_cursor, parse_id_cursor


def test_cursor_roundtrip_keeps_payload():
    token = encode_cursor({"k": "id", "id": 42})
    assert isinstance(token, str) and "=" not in token
    assert decode_cursor(token) == {"k": "id", "id": 42}


def test_cursor_keeps_non_ascii_sort_key():
    token = encode_cursor({"k": "title", "s": "红楼梦", "id": 7})
    assert decode_cursor(token) == {"k": "title", "s": "红楼梦", "id": 7}


def test_invalid_cursor_falls_back_to_none():
    assert decode_cursor("") is None
    assert decode_cursor("not-base64!!") is None
    assert decode_cursor(encode_cursor([1, 2])) is None


def test_parse_id_cursor_checks_kind():
    token = encode_cursor({"k": "audio", "id": 9})
    assert parse_id_cursor(token, "audio") == 9
    assert parse_id_cursor(token, "id") is None
    assert parse_id_cursor("bad", "audio") is None
