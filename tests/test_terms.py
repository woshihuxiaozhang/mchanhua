"""自动术语表：模型顺手认出的专有名词（人名、地名…）怎么攒、怎么过期。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

from mchanhua.app import Application
from mchanhua.config import Config, load_config, save_config
from mchanhua.ocr.base import OcrLine, OcrResult
from mchanhua.pipeline import run_from_ocr
from mchanhua.terms import TermStore, term_key
from mchanhua.translate.cache import TranslationCache, cache_key
from mchanhua.translate.glossary import DEFAULT_GLOSSARY, select_relevant
from mchanhua.translate.openai_compat import OpenAICompatibleTranslator
from tests.fakes import DecodingTranslator, FakeGrabber, FakeOcr, FakeWindow, wait_for

NOW = datetime(2026, 9, 30, 22, 0, 0)


# ---- TermStore ----


def test_remember_and_active(workdir: Path):
    store = TermStore(workdir / "terms.json")

    assert store.remember("Mychael", "米迦勒", NOW) is True
    assert store.remember("POISON", "毒渊", NOW) is True
    assert store.remember("Mychael", "米迦勒", NOW) is False      # 见过的不算新词

    assert store.active() == {"Mychael": "米迦勒", "POISON": "毒渊"}
    assert len(store) == 2


def test_first_seen_spelling_wins(workdir: Path):
    """同一个名字后来出现别的译法：仍按第一次的来，保证前后一致。"""

    store = TermStore(workdir / "terms.json")
    store.remember("Mychael", "米迦勒", NOW)

    store.remember("Mychael", "迈卡尔", NOW + timedelta(minutes=5))

    assert store.active() == {"Mychael": "米迦勒"}
    assert store.entries()[0].hits >= 1


def test_remember_rejects_junk(workdir: Path):
    store = TermStore(workdir / "terms.json")

    assert store.remember("", "米迦勒", NOW) is False
    assert store.remember("Mychael", "", NOW) is False
    assert store.remember("Mychael", "Mychael", NOW) is False      # 没翻出来
    assert len(store) == 0


def test_terms_expire_after_ttl(workdir: Path):
    """默认一天一清：超过 24 小时没再用到的字样自动消失。"""

    store = TermStore(workdir / "terms.json", ttl_hours=24)
    store.remember("Mychael", "米迦勒", NOW - timedelta(hours=25))   # 昨天的
    store.remember("POISON", "毒渊", NOW - timedelta(hours=2))       # 今天的

    dropped = store.prune(NOW)

    assert dropped == 1
    assert store.active() == {"POISON": "毒渊"}


def test_save_round_trip_and_file_disappears_when_empty(workdir: Path):
    path = workdir / "terms.json"
    store = TermStore(path)
    store.remember("Mychael", "米迦勒", NOW)
    store.save(NOW)

    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["entries"][0]["src"] == "Mychael"

    reopened = TermStore(path)
    assert reopened.load(NOW) == 0
    assert reopened.active() == {"Mychael": "米迦勒"}

    # 全过期以后落盘：文件直接删掉，不留占地方的空壳
    assert store.save(NOW + timedelta(hours=48)) == 1
    assert not path.exists()


def test_load_drops_expired_and_tolerates_corrupt_file(workdir: Path):
    path = workdir / "terms.json"
    # 手写一份"里面混着过期条目"的文件（save 自己会清过期，所以直接写盘）
    payload = {
        "version": 1,
        "entries": [
            {"src": "Mychael", "dst": "米迦勒", "at": (NOW - timedelta(hours=30)).isoformat()},
            {"src": "POISON", "dst": "毒渊", "at": NOW.isoformat()},
            {"src": "Alte", "dst": "阿尔特", "at": (NOW - timedelta(days=3)).isoformat()},
            {"src": "缺了译名"},
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    store = TermStore(path)
    assert store.load(NOW) == 2                            # Mychael 和 Alte 过期
    assert store.active() == {"POISON": "毒渊"}

    path.write_text("{ 这不是 json", encoding="utf-8")
    broken = TermStore(path)
    assert broken.load(NOW) == 0 and len(broken) == 0


def test_store_caps_entry_count(workdir: Path):
    store = TermStore(workdir / "terms.json", max_entries=3)
    for index in range(5):
        store.remember(f"Name{index}", f"名字{index}", NOW + timedelta(minutes=index))

    store.prune(NOW + timedelta(minutes=10))

    assert len(store) == 3
    assert "Name0" not in store.active()          # 留下最新记的几条
    assert "Name4" in store.active()


def test_merge_and_clear(workdir: Path):
    store = TermStore(workdir / "terms.json")
    assert store.merge([("A", "甲"), ("B", "乙"), ("A", "甲")], NOW) == 2

    assert store.clear() == 2
    assert len(store) == 0


def test_term_key_normalises_whitespace_and_case():
    assert term_key("  Mychael  ") == term_key("mychael")


# ---- 术语表按需注入 ----


def test_select_relevant_only_keeps_terms_in_the_batch():
    glossary = {"Redstone": "红石", "Netherite": "下界合金", "Mychael": "米迦勒"}

    chosen = select_relevant(glossary, ["Craft a Netherite Sword", "跟着 Mychael 走"])

    assert chosen == {"Netherite": "下界合金", "Mychael": "米迦勒"}


def test_select_relevant_tolerates_ocr_typos():
    """OCR 认错的写法（P0ISON / MychaeI）也要能命中术语。"""

    glossary = {"POISON": "毒渊", "Mychael": "米迦勒"}

    assert select_relevant(glossary, ["Welcome to P0ISON"]) == {"POISON": "毒渊"}
    assert select_relevant(glossary, ["Follow MychaeI"]) == {"Mychael": "米迦勒"}


def test_select_relevant_needs_all_words_of_a_multiword_term():
    glossary = {"Redstone Dust": "红石粉"}

    assert select_relevant(glossary, ["I need Redstone Dust"]) == {"Redstone Dust": "红石粉"}
    assert select_relevant(glossary, ["Only Redstone here"]) == {}


def test_select_relevant_handles_empty_input():
    assert select_relevant({}, ["anything"]) == {}
    assert select_relevant({"A": "甲"}, []) == {}
    assert select_relevant(None, ["A"]) == {}
    assert select_relevant({"  ": "甲"}, ["甲"]) == {}


def test_builtin_glossary_only_sends_what_appears():
    chosen = select_relevant(DEFAULT_GLOSSARY, ["Durability 1200 / 1200"])

    assert chosen == {"Durability": "耐久"}


# ---- 模型返回的 terms 字段 ----


def _translator(handler, **kwargs) -> OpenAICompatibleTranslator:
    return OpenAICompatibleTranslator(
        api_key="sk-test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        **kwargs,
    )


def _reply(lines: list[str], terms=None, paragraph: str = ""):
    payload: dict = {"lines": [{"i": i, "dst": f"【{text}】"} for i, text in enumerate(lines)]}
    if terms is not None:
        payload["terms"] = terms
    if paragraph:
        payload["paragraph"] = paragraph

    def handler(request: httpx.Request) -> httpx.Response:
        handler.last_request = request
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload)}}]})

    handler.last_request = None
    return handler


def test_terms_field_is_read_from_the_response():
    handler = _reply(
        ["Follow Mychael", "Welcome to POISON"],
        terms=[
            {"src": "Mychael", "dst": "米迦勒"},
            {"src": "POISON", "dst": "毒渊"},
        ],
    )
    translator = _translator(handler)

    translator.translate_lines(["Follow Mychael", "Welcome to POISON"])

    assert translator.last_terms == [("Mychael", "米迦勒"), ("POISON", "毒渊")]


def test_terms_that_are_not_in_the_batch_are_dropped():
    """模型可能瞎编：原文里根本没出现的"专有名词"不收。"""

    handler = _reply(
        ["Follow Mychael"],
        terms=[
            {"src": "Mychael", "dst": "米迦勒"},
            {"src": "Gandalf", "dst": "甘道夫"},        # 编的
            {"src": "Mychael", "dst": "米迦勒"},        # 重复
            {"src": "Mychael is here.", "dst": "米迦勒在这儿。"},  # 整句，不算术语
        ],
    )
    translator = _translator(handler)
    translator.glossary = {"Follow Mychael": "跟着米迦勒"}

    translator.translate_lines(["Follow Mychael"])

    assert translator.last_terms == [("Mychael", "米迦勒")]


def test_docorrupted_terms_field_is_ignored():
    handler = _reply(["Follow Mychael"], terms="不是数组")
    translator = _translator(handler)

    assert translator.translate_lines(["Follow Mychael"]) == ["【Follow Mychael】"]
    assert translator.last_terms == []


def test_extra_glossary_is_injected_and_user_glossary_wins():
    handler = _reply(["Follow Mychael"])
    translator = _translator(handler, glossary={"Mychael": "米迦勒（我自己定的）"})
    translator.extra_glossary = {"Mychael": "米迦勒", "POISON": "毒渊"}

    translator.translate_lines(["Follow Mychael"])

    prompt = json.loads(handler.last_request.content)["messages"][0]["content"]
    assert "Mychael=米迦勒（我自己定的）" in prompt     # 用户配置优先
    assert "POISON" not in prompt                       # 这批没出现 → 不注入


# ---- 缓存迁移 ----


def test_retag_keeps_user_corrections_across_prompt_versions(workdir: Path):
    """提示词改版不能让缓存（尤其手动修正过的译文）凭空失效。"""

    path = workdir / "cache.sqlite"
    cache = TranslationCache(path)
    cache.put("Steel Ingot", "钢锭（我改的）", "deepseek-chat", "v6")
    cache.put("Iron Nugget", "铁粒", "别的模型", "v6")

    moved = cache.retag_all("deepseek-chat", "v7")

    assert moved == 1
    assert cache.get("Steel Ingot", "deepseek-chat", "v7") == "钢锭（我改的）"
    assert cache.get("Steel Ingot", "deepseek-chat", "v6") is None
    assert cache.get("Iron Nugget", "别的模型", "v6") == "铁粒"      # 别的模型不动
    assert cache.count() == 2


# ---- 管线：把 terms 带回来 ----


class _TermsTranslator:
    name = "terms"

    def __init__(self) -> None:
        self.last_paragraph = ""
        self.last_terms = [("Mychael", "米迦勒")]
        self.seen_extra: list[dict[str, str]] = []

    def translate_lines(self, lines):
        self.seen_extra.append(dict(getattr(self, "extra_glossary", {}) or {}))
        return [f"【{text}】" for text in lines]


def test_pipeline_reports_terms():
    ocr = OcrResult(lines=[OcrLine("Follow Mychael")], elapsed_ms=1.0, backend="x")

    result = run_from_ocr(ocr, _TermsTranslator())

    assert result.terms == [("Mychael", "米迦勒")]


# ---- 控制器：记住并在下一批用上 ----


def _app(workdir: Path, translator=None) -> Application:
    path = save_config(Config(), workdir / "config.toml")
    config = load_config(path)
    app = Application(
        config,
        config_path=path,
        terms_path=workdir / "terms.json",
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=FakeOcr(),
        window=FakeWindow(),
    )
    app.translator = translator or DecodingTranslator()
    return app


def test_learned_terms_are_kept_out_of_the_user_glossary(workdir: Path):
    app = _app(workdir)

    added = app._learn_terms([("Mychael", "米迦勒"), ("POISON", "毒渊")])

    assert added == 2
    assert app.config.glossary == {}                    # 不污染用户配置
    assert app.terms.active() == {"Mychael": "米迦勒", "POISON": "毒渊"}
    assert (workdir / "terms.json").exists()


def test_worker_hands_learned_terms_to_the_next_request(workdir: Path):
    translator = _TermsTranslator()
    app = _app(workdir, translator)

    app.perform_translate()
    wait_for(app, "result")

    assert app.terms.active() == {"Mychael": "米迦勒"}
    # 这一批还不知道，下一批才会带上——这就是"前后译法一致"的实现方式
    assert translator.seen_extra[0] == {}
    app.perform_translate()
    wait_for(app, "result")
    assert translator.seen_extra[1] == {"Mychael": "米迦勒"}


def test_auto_learn_can_be_turned_off(workdir: Path):
    app = _app(workdir)
    app.config.terms.auto_learn = False

    assert app._learn_terms([("Mychael", "米迦勒")]) == 0
    assert len(app.terms) == 0


def test_clear_learned_terms(workdir: Path):
    app = _app(workdir)
    app._learn_terms([("Mychael", "米迦勒")])

    assert app.clear_learned_terms() == 1
    assert len(app.terms) == 0
    assert not (workdir / "terms.json").exists()


def test_terms_ttl_comes_from_config(workdir: Path):
    path = save_config(Config(), workdir / "config.toml")
    text = path.read_text(encoding="utf-8").replace("ttl_hours = 24.0", "ttl_hours = 1.0")
    path.write_text(text, encoding="utf-8")

    app = Application(
        load_config(path),
        config_path=path,
        terms_path=workdir / "terms.json",
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=FakeOcr(),
        window=FakeWindow(),
    )

    assert app.terms.ttl_hours == 1.0


def test_terms_config_round_trip(workdir: Path):
    config = Config()
    assert config.terms.auto_learn is True and config.terms.ttl_hours == 24.0

    path = save_config(config, workdir / "config.toml")
    text = path.read_text(encoding="utf-8")
    assert "[terms]" in text and "ttl_hours = 24.0" in text
    assert load_config(path).terms == config.terms


def test_terms_config_rejects_negative_ttl():
    from mchanhua.config import ConfigError, loads

    with pytest.raises(ConfigError):
        loads("[terms]\nttl_hours = -1\n")


def test_cache_key_includes_prompt_version():
    assert cache_key("a", "m", "v6") != cache_key("a", "m", "v7")


# ---- 设置窗口 ----


tk = pytest.importorskip("tkinter")


def test_settings_shows_and_clears_learned_terms(workdir: Path):
    from mchanhua.ui.settings_window import SettingsWindow

    store = TermStore(workdir / "terms.json")
    store.remember("Mychael", "米迦勒", NOW)
    cleared: list[int] = []

    try:
        window = SettingsWindow(
            Config(), terms=store, on_clear_terms=lambda: cleared.append(store.clear()) or len(cleared)
        )
    except tk.TclError as exc:  # pragma: no cover
        pytest.skip(f"没有可用的图形环境：{exc}")
    try:
        text = window._terms_label.cget("text")
        assert "自动术语表" in text and "1 条" in text and "24" in text
    finally:
        window.root.destroy()
        store.clear()
