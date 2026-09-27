"""DeepSeek 后端（历史入口，等价于 OpenAI 兼容实现）。

保留这个名字是为了兼容旧配置与旧代码；实际实现见 openai_compat 模块。
"""

from __future__ import annotations

from mchanhua.translate.openai_compat import (
    CORRECTION_NOTE,
    GLOSSARY_PREFIX,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    OpenAICompatibleTranslator,
    build_system_prompt,
    looks_like_word,
)

DeepSeekTranslator = OpenAICompatibleTranslator

__all__ = [
    "CORRECTION_NOTE",
    "GLOSSARY_PREFIX",
    "PROMPT_VERSION",
    "SYSTEM_PROMPT",
    "DeepSeekTranslator",
    "OpenAICompatibleTranslator",
    "build_system_prompt",
    "looks_like_word",
]
