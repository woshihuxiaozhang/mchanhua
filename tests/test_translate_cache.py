from mchanhua.translate import CachingTranslator
from mchanhua.translate.cache import TranslationCache, cache_key


class FakeTranslator:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def translate_lines(self, lines):
        self.calls.append(list(lines))
        return [f"[译]{text}" for text in lines]


def _cache(workdir) -> TranslationCache:
    return TranslationCache(workdir / "cache.sqlite")


def test_cache_put_get_and_key_stability(workdir):
    cache = _cache(workdir)
    assert cache.get("Steel Ingot", "deepseek-chat", "v1") is None
    cache.put("Steel Ingot", "钢锭", "deepseek-chat", "v1")
    assert cache.get("Steel Ingot", "deepseek-chat", "v1") == "钢锭"
    # 模型或提示词版本变化后不再命中
    assert cache.get("Steel Ingot", "deepseek-chat", "v2") is None
    assert cache.count() == 1
    assert cache_key("a", "m", "v1") != cache_key("b", "m", "v1")
    cache.close()


def test_caching_translator_only_sends_misses(workdir):
    cache = _cache(workdir)
    cache.put("Steel Ingot", "钢锭", "deepseek-chat", "v1")
    inner = FakeTranslator()
    translator = CachingTranslator(inner, cache, "deepseek-chat", "v1")

    result = translator.translate_lines(["Steel Ingot", "Right-click to place", "Steel Ingot"])

    assert result == ["钢锭", "[译]Right-click to place", "钢锭"]
    assert inner.calls == [["Right-click to place"]]
    assert translator.hits == 2
    assert translator.misses == 1
    cache.close()


def test_results_are_cached_for_next_run(workdir):
    cache = _cache(workdir)
    inner = FakeTranslator()
    first = CachingTranslator(inner, cache, "deepseek-chat", "v1")
    first.translate_lines(["Hello there"])

    second_inner = FakeTranslator()
    second = CachingTranslator(second_inner, cache, "deepseek-chat", "v1")
    assert second.translate_lines(["Hello there"]) == ["[译]Hello there"]
    assert second_inner.calls == []          # 第二次完全命中缓存
    cache.close()
