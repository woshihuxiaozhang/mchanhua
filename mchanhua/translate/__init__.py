"""翻译层：DeepSeek 后端 + 缓存 + 中英混排过滤。"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from mchanhua.config import TranslateConfig
from mchanhua.translate.base import (
    Translator,
    TranslationError,
    contains_cjk,
    should_translate,
    split_translatable,
)
from mchanhua.translate.cache import TranslationCache
from mchanhua.translate.deepseek import DeepSeekTranslator
from mchanhua.translate.glossary import DEFAULT_GLOSSARY

__all__ = [
    "CachingTranslator",
    "DeepSeekTranslator",
    "TranslationCache",
    "TranslationError",
    "Translator",
    "contains_cjk",
    "create_translator",
    "DEFAULT_GLOSSARY",
    "should_translate",
    "split_translatable",
]


class CachingTranslator:
    """先查缓存，只把未命中的行发给模型。"""

    def __init__(self, inner: Translator, cache: TranslationCache, model: str, prompt_version: str) -> None:
        self.inner = inner
        self.cache = cache
        self.model = model
        self.prompt_version = prompt_version
        self.name = f"{inner.name}+cache"
        self.hits = 0
        self.misses = 0

    def translate_lines(self, lines: Sequence[str]) -> list[str]:
        sources = list(lines)
        result: list[str | None] = [None] * len(sources)
        pending: list[tuple[int, str]] = []

        for index, text in enumerate(sources):
            cached = self.cache.get(text, self.model, self.prompt_version)
            if cached is not None:
                result[index] = cached
                self.hits += 1
            else:
                pending.append((index, text))
                self.misses += 1

        if pending:
            translated = self.inner.translate_lines([text for _, text in pending])
            for (index, source), target in zip(pending, translated):
                result[index] = target
                self.cache.put(source, target, self.model, self.prompt_version)

        return [value if value is not None else source for value, source in zip(result, sources)]


def create_translator(
    config: TranslateConfig,
    api_key: str,
    cache_path: Path | None = None,
    glossary: dict[str, str] | None = None,
) -> Translator:
    if config.provider != "deepseek":
        raise TranslationError(f"暂不支持的翻译服务：{config.provider}")

    merged_glossary = {**DEFAULT_GLOSSARY, **(glossary or {})}
    engine = DeepSeekTranslator(
        api_key=api_key,
        base_url=config.base_url,
        model=config.model,
        timeout=config.timeout,
        temperature=config.temperature,
        glossary=merged_glossary,
    )
    if not config.cache_enabled:
        return engine
    if cache_path is None:
        cache_path = Path.home() / ".mchanhua" / "cache.sqlite"
    cache = TranslationCache(cache_path)
    return CachingTranslator(engine, cache, engine.model, engine.prompt_version)
