"""OpenAI 兼容接口地址（base URL）规范化工具。

背景：OpenAI SDK 会自行在 base_url 后拼接 ``/chat/completions``。用户在
「系统设置 → 刮削与AI → AI接口地址」里经常从别处复制了**完整 endpoint**
（例如 ``https://openrouter.ai/api/v1/chat/completions``），SDK 再补一遍就
变成 ``.../chat/completions/chat/completions``，网关无法中继该路径，返回
``400 Request path cannot be relayed``。

同一个 ``AI_API_URL`` 同时被两处使用：
  1. 刮削与AI 的「测试AI设置」 → BookAIClient
  2. AI 助手（含麦克风语音对话） → ai_assistant_agent.ChatOpenAI

因此把规范化逻辑收敛到这里，两处共用，保证行为一致。
"""

import re

# OpenAI / LangChain SDK 会自动追加的 endpoint 路径片段（按从长到短处理）。
_ENDPOINT_SUFFIXES = (
    "/chat/completions",
    "/completions",
)


def normalize_base_url(url: str) -> str:
    """把用户填写的 OpenAI 兼容接口地址规范为 SDK 可接受的 base URL。

    处理规则（幂等）：
      - 去掉首尾空白与结尾的 ``/``；
      - 若末尾是 ``/chat/completions`` 或 ``/completions``，去掉它（SDK 会自己补）；
      - 合并路径中重复的 ``/``（协议头的 ``://`` 除外）；
      - 合并重复的 ``/v1/v1``（部分中转网关会写重）。

    保留用户原本的路径层级（如 ``/api/v1``、``/v1``），不做任何域名/路径重写，
    以兼容 DeepSeek、OpenRouter 及各类中转网关。
    """
    value = str(url or "").strip().rstrip("/")
    if not value:
        return value

    # 反复剥离自动补全的 endpoint，防止出现 .../chat/completions/chat/completions
    changed = True
    while changed:
        changed = False
        lowered = value.lower()
        for suffix in _ENDPOINT_SUFFIXES:
            if lowered.endswith(suffix):
                value = value[: -len(suffix)].rstrip("/")
                changed = True
                break

    # 合并路径里重复的斜杠，但保留 scheme 的 ://
    parts = re.split(r"(https?://)", value, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 3:
        scheme, rest = parts[1], parts[2]
        rest = re.sub(r"/{2,}", "/", rest)
        value = scheme + rest
    else:
        value = re.sub(r"/{2,}", "/", value)

    # 合并重复的 /v1/v1、/api/v1/api/v1 之类（中转网关常见笔误）
    value = re.sub(r"(/v1)+/?$", "/v1", value, flags=re.IGNORECASE) if re.search(r"(/v1){2,}", value, flags=re.IGNORECASE) else value

    return value.rstrip("/")


def friendly_api_error(exc) -> str:
    """把底层 SDK/网关的英文报错转成可操作的中文提示。

    只针对已知的“路径拼接错误”做改写，其余错误原样返回，避免掩盖真实问题。
    """
    text = str(exc or "")
    lowered = text.lower()
    if "request path cannot be relayed" in lowered or "chat/completions/chat/completions" in lowered:
        return (
            "AI接口地址填写有误：地址末尾多写了 /chat/completions，SDK 重复拼接后"
            "网关无法中继该路径。请把「AI接口地址」改为只到 /v1 为止，"
            "例如 https://openrouter.ai/api/v1（不要带 /chat/completions）。原始错误：" + text
        )
    return text
