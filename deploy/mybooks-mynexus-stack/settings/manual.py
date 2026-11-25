#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
# 预置设置（MyBooks + MyNexus 二合一部署包）
#
# 原理：MyBooks 的设置加载链是 settings.py → auto.py → manual.py，
# 后者覆盖前者。本文件由 docker-compose 只读挂载到
# /data/books/settings/manual.py，因此：
#   - 优先级最高，打开设置页就能看到已填好的 MyNexus / AI 助手配置；
#   - 只读挂载 + 不在 prebuilt 里，不会被首次启动的拷贝逻辑覆盖；
#   - 你在设置页手动改的设置保存在 auto.py，与本文件互不干扰。
#
# 所有密钥从环境变量读取，与 .env 保持单一来源。

import os
import re


def _clean_key(value):
    """拒绝占位符/含中文的 key，避免写进设置页后在 openai SDK 构造
    Authorization 头时触发 'ascii' codec can't encode characters 崩溃。
    真实 API key 一定是纯 ASCII；占位符（如「sk-or-v1-你的OpenRouter密钥」）
    宁可当成空，让用户看到空输入框去填真实值，也不要预填一个会崩的坏值。"""
    if not value:
        return ""
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        return ""
    if re.search(
        r"在这里填|your[_-]*(api[_-]*)?key|your[_-]*token|placeholder|"
        r"please[_-]?change|replace[_-]?me|xxxx+|示例|example|<[^>]+>",
        value,
        re.IGNORECASE,
    ):
        return ""
    return value


# 关键修复：设置加载链是 settings.py → auto.py → manual.py，本文件最后加载、优先级最高。
# 早前这里无条件用 .env 的值覆盖 auto.py，导致一个死循环：
#   用户在设置页把 URL/模型改成 DeepSeek（写进数据卷的 auto.py）→ 容器一重启，
#   manual.py 又用 .env 里的 openrouter 默认值盖回去 → 每次 onekey 重装都“回到默认”。
# 现在改为「预填而非覆盖」：auto.py 里用户已保存过非空值（如 https://api.deepseek.com
# 或 deepseek-flash），一律尊重；只有该键在 auto.py 里为空/不存在时，才用 .env 预填。
# 这样：全新安装仍能从 .env 自动填好；用户在设置页改过的值能跨重启、跨重装保留。
try:
    import auto as _auto_settings_module
    _user_saved = getattr(_auto_settings_module, "settings", {}) or {}
except Exception:
    _user_saved = {}


def _prefill(key, env_value):
    """用户已在设置页保存过该键（auto.py 非空）则用用户值，否则用 .env 预填值。"""
    saved = _user_saved.get(key)
    if saved is not None and str(saved).strip():
        return saved
    return env_value


def _mynexus_static_token(env_static):
    """AI 伴读的 token 只能用 .env 的静态集成 token（MYNEXUS_API_TOKEN）。

    MyNexus 的鉴权中间件对带 X-MyBooks-User-ID 的 chat 请求（/api/v1/chat/*）
    只接受静态集成 token；在 MyNexus 后台「API Token」页生成的 mnx_ 开头
    per-user token 会被它用 403
      external user identity requires the MyNexus integration token
    拒绝。用户若照着后台指引把 mnx_ token 填进设置页，以前会被 manual.py 的
    「预填不覆盖」永久保留，导致 AI 伴读一直报上面这个错。这里忽略这类误填
    值、回落到 .env 静态值，把坑堵死。
    """
    saved = _user_saved.get("MYNEXUS_TOKEN")
    if isinstance(saved, str) and saved.strip().lower().startswith("mnx_"):
        return env_static
    return _prefill("MYNEXUS_TOKEN", env_static)


settings = {
    # ---- MyNexus AI 伴读 ----
    "ENABLE_MYNEXUS": True,
    "MYNEXUS_URL": _prefill("MYNEXUS_URL", os.environ.get("MYNEXUS_AUTO_URL", "http://mynexus")),
    "MYNEXUS_TOKEN": _mynexus_static_token(os.environ.get("MYNEXUS_API_TOKEN", "")),
    # ---- 全局 AI 助手（顶部导航栏 AI 按钮）----
    # URL 统一为 OpenRouter base（不带 /chat/completions，客户端会自动拼）；
    # 模型 openrouter/free 自动路由可用免费模型，避开单模型限流。
    "AI_ENABLED": True,
    # key 特殊：占位符要清洗成空，不能在 auto.py 里存了中文占位符导致 SDK 崩；
    # 只有清洗后非空的用户值才保留，否则回落到 .env（同样清洗）。
    "AI_DEEPSEEK_API_KEY": _clean_key(_prefill("AI_DEEPSEEK_API_KEY", os.environ.get("AI_API_KEY", ""))),
    "AI_API_URL": _prefill("AI_API_URL", os.environ.get("AI_BASE_URL", "https://openrouter.ai/api/v1")),
    "AI_MODEL": _prefill("AI_MODEL", os.environ.get("AI_MODEL", "openrouter/free")),
    "AI_MCP_TOKEN": _prefill("AI_MCP_TOKEN", os.environ.get("AI_MCP_TOKEN", "")),
}
