"""测试翻译服务是否可用（设置界面里的"测试连接"按钮）。"""

from __future__ import annotations

from dataclasses import replace

from mchanhua.config import TranslateConfig
from mchanhua.translate import create_translator
from mchanhua.translate.base import TranslationError

PROBE_LINE = "Steel Ingot"


def test_connection(config: TranslateConfig, api_key: str, timeout: float = 20.0) -> str:
    """用一句话试翻，返回译文；失败抛 TranslationError。"""

    probe_config = replace(config, cache_enabled=False, timeout=timeout)
    translator = create_translator(probe_config, api_key=api_key)
    result = translator.translate_lines([PROBE_LINE])
    if not result or not result[0].strip():
        raise TranslationError("服务没有返回译文")
    return result[0].strip()
