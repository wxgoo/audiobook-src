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

settings = {
    # ---- MyNexus AI 伴读 ----
    "ENABLE_MYNEXUS": True,
    "MYNEXUS_URL": os.environ.get("MYNEXUS_AUTO_URL", "http://mynexus"),
    "MYNEXUS_TOKEN": os.environ.get("MYNEXUS_API_TOKEN", ""),
    # ---- 全局 AI 助手（顶部导航栏 AI 按钮）----
    # URL 统一为 OpenRouter base（不带 /chat/completions，客户端会自动拼）；
    # 模型 openrouter/free 自动路由可用免费模型，避开单模型限流。
    "AI_ENABLED": True,
    "AI_DEEPSEEK_API_KEY": os.environ.get("AI_API_KEY", ""),
    "AI_API_URL": os.environ.get("AI_BASE_URL", "https://openrouter.ai/api/v1"),
    "AI_MODEL": os.environ.get("AI_MODEL", "openrouter/free"),
    "AI_MCP_TOKEN": os.environ.get("AI_MCP_TOKEN", ""),
}
