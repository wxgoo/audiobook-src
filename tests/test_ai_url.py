"""测试 OpenAI 兼容接口地址规范化（修复 400 Request path cannot be relayed）。"""

import pytest

from webserver.assistant.ai_url import friendly_api_error, normalize_base_url


@pytest.mark.parametrize(
    "raw, expected",
    [
        # 正确写法保持不变
        ("https://openrouter.ai/api/v1", "https://openrouter.ai/api/v1"),
        ("https://openrouter.ai/api/v1/", "https://openrouter.ai/api/v1"),
        ("https://api.deepseek.com", "https://api.deepseek.com"),
        ("https://api.deepseek.com/v1", "https://api.deepseek.com/v1"),
        # 用户填了完整 endpoint —— 本次 bug 的核心场景
        ("https://openrouter.ai/api/v1/chat/completions", "https://openrouter.ai/api/v1"),
        ("https://openrouter.ai/api/v1/chat/completions/", "https://openrouter.ai/api/v1"),
        ("https://api.deepseek.com/v1/chat/completions", "https://api.deepseek.com/v1"),
        # 重复拼接 / 重复路径 / 双斜杠
        (
            "https://openrouter.ai/api/v1/chat/completions/chat/completions",
            "https://openrouter.ai/api/v1",
        ),
        ("https://openrouter.ai/api/v1//chat/completions", "https://openrouter.ai/api/v1"),
        ("https://openrouter.ai/api/v1/v1", "https://openrouter.ai/api/v1"),
        # 首尾空白
        ("  https://openrouter.ai/api/v1  ", "https://openrouter.ai/api/v1"),
        # 空值
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_base_url(raw, expected):
    assert normalize_base_url(raw) == expected


def test_normalize_base_url_is_idempotent():
    once = normalize_base_url("https://openrouter.ai/api/v1/chat/completions")
    assert normalize_base_url(once) == once


def test_friendly_api_error_rewrites_relay_error():
    raw = "Error code: 400 - {'error': {'message': 'Request path cannot be relayed', 'code': 400}}"
    msg = friendly_api_error(raw)
    assert "AI接口地址填写有误" in msg
    assert "/chat/completions" in msg
    assert "https://openrouter.ai/api/v1" in msg


def test_friendly_api_error_keeps_unknown_error():
    raw = "Error code: 401 - {'error': {'message': 'Invalid API key'}}"
    assert friendly_api_error(raw) == raw
