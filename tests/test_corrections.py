"""手动修正译文 → 写回缓存 / 术语表。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from mchanhua.app import Application, glossary_term
from mchanhua.config import Config, load_config, save_config
from mchanhua.history import TranslationHistory
from mchanhua.pipeline import PipelineResult
from mchanhua.translate import CachingTranslator
from mchanhua.translate.cache import TranslationCache
from tests.fakes import FakeGrabber, FakeOcr, FakeWindow


# ---- 什么算术语 ----


def test_glossary_term_accepts_short_nouns():
    assert glossary_term("Steel Ingot", "钢锭") == "Steel Ingot"
    assert glossary_term("  Iron   Nugget ", "铁粒") == "Iron Nugget"
    assert glossary_term("Netherite", "下界合金") == "Netherite"


def test_glossary_term_rejects_sentences_and_junk():
    assert glossary_term("You should not be here.", "你不该来这里。") is None
    assert glossary_term("Follow the light!", "跟着光走！") is None
    assert glossary_term("", "钢锭") is None
    assert glossary_term("Steel Ingot", "") is None
    # 太长的（多半是整句）和太长的译文都不收
    assert glossary_term("a b c d e", "一二三四五") is None
    assert glossary_term("Steel Ingot", "钢锭" * 20) is None
    assert glossary_term("x" * 41, "钢锭") is None


# ---- 历史 ----


def test_history_amend_last_rewrites_targets():
    history = TranslationHistory()
    history.add(["Steel Ingot", "Iron Nugget"], ["钢铁锭", "铁粒"],
                at=datetime(2026, 9, 30, 12, 0))

    assert history.amend_last([("Steel Ingot", "钢锭")]) is True

    entry = history.all()[-1]
    assert entry.target == ("钢锭", "铁粒")
    assert entry.source == ("Steel Ingot", "Iron Nugget")
    assert entry.clock == "12:00"          # 时间不变


def test_history_amend_last_is_a_noop_when_nothing_changes():
    history = TranslationHistory()
    history.add(["Steel Ingot"], ["钢锭"])

    assert history.amend_last([("Steel Ingot", "钢锭")]) is False
    assert history.amend_last([]) is False


def test_history_amend_last_without_entries_is_safe():
    assert TranslationHistory().amend_last([("Steel Ingot", "钢锭")]) is False


# ---- 缓存 ----


class RecordingInner:
    name = "recording"

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.last_paragraph = ""

    def translate_lines(self, lines):
        self.calls.append(list(lines))
        return [f"模型译：{text}" for text in lines]


def test_remembered_correction_short_circuits_the_model(workdir: Path):
    inner = RecordingInner()
    cache = TranslationCache(workdir / "cache.sqlite")
    translator = CachingTranslator(inner, cache, "deepseek-chat", "v9")

    translator.remember("Steel Ingot", "钢锭")
    result = translator.translate_lines(["Steel Ingot", "Iron Nugget"])

    assert result == ["钢锭", "模型译：Iron Nugget"]
    assert inner.calls == [["Iron Nugget"]]      # 改过的那句没再问模型


# ---- 小窗：改译文 ----


tk = pytest.importorskip("tkinter")


def _window(callbacks=None):
    from mchanhua.ui.window import ResultWindow

    last: Exception | None = None
    for _ in range(2):
        try:
            window = ResultWindow(Config(), callbacks)
            window.root.update_idletasks()
            return window
        except tk.TclError as exc:
            last = exc
    pytest.skip(f"没有可用的图形环境：{last}")  # pragma: no cover


def test_save_button_only_shows_up_after_editing():
    window = _window()
    try:
        window.show_result(PipelineResult(source_lines=["Steel Ingot"], output_lines=["钢铁锭"]))
        assert window.correction_button.winfo_manager() == ""     # 没改之前不露

        window.target.delete("1.0", "end")
        window.target.insert("1.0", "钢锭")
        window.root.update()

        assert window.correction_button.winfo_manager() == "pack"
        assert window.correction_pairs() == [("Steel Ingot", "钢锭")]
    finally:
        window.root.destroy()


def test_programmatic_result_write_is_not_treated_as_an_edit():
    window = _window()
    try:
        window.show_result(PipelineResult(source_lines=["Steel Ingot"], output_lines=["钢铁锭"]))
        window.show_result(PipelineResult(source_lines=["Iron Nugget"], output_lines=["铁粒"]))
        window.root.update()

        assert window.correction_button.winfo_manager() == ""
        assert window.correction_pairs() == []
    finally:
        window.root.destroy()


def test_clear_hides_the_save_button():
    window = _window()
    try:
        window.show_result(PipelineResult(source_lines=["Steel Ingot"], output_lines=["钢铁锭"]))
        window.target.delete("1.0", "end")
        window.target.insert("1.0", "钢锭")
        window.root.update()
        assert window.correction_button.winfo_manager() == "pack"

        window.show_notice("没有识别到文字")

        assert window.correction_button.winfo_manager() == ""
        assert window.save_corrections() is None      # 没结果时点保存也不能炸
        assert "还没有译文可以修正" in window.status_text()
    finally:
        window.root.destroy()


def test_correction_pairs_align_with_area_labels_and_paragraph():
    """多区域 + 整段整理时，［区域1］这种标题行不能被当成译文。"""

    window = _window()
    try:
        window.show_result(
            PipelineResult(
                source_lines=["Steel Ingot", "Follow the light."],
                output_lines=["钢铁锭", "跟着光走。"],
                line_areas=["区域1", "区域2"],
                paragraph="钢铁锭；跟着光走。",
            )
        )
        assert window._target_map[0] is None and window._target_map[1] is None

        window.target.delete("1.0", "end")
        window.target.insert("1.0", "钢铁锭；跟着光走。\n\n［区域1］\n钢锭\n［区域2］\n跟着光走")
        window.root.update()

        assert window.correction_pairs() == [
            ("Steel Ingot", "钢锭"),
            ("Follow the light.", "跟着光走"),
        ]
    finally:
        window.root.destroy()


def test_save_corrections_hands_pairs_to_the_controller():
    from mchanhua.ui.window import WindowCallbacks

    seen: list[list] = []
    window = _window(WindowCallbacks(on_save_corrections=seen.append))
    try:
        window.show_result(PipelineResult(source_lines=["Steel Ingot"], output_lines=["钢铁锭"]))
        window.target.delete("1.0", "end")
        window.target.insert("1.0", "钢锭")
        window.root.update()

        window.save_corrections()

        assert seen == [[("Steel Ingot", "钢锭")]]
        assert window.correction_button.winfo_manager() == ""      # 存完收起来
        assert window.correction_pairs() == []                     # 再点不会重复提交
    finally:
        window.root.destroy()


def test_save_corrections_refuses_when_line_count_changed():
    seen: list[list] = []
    from mchanhua.ui.window import WindowCallbacks

    window = _window(WindowCallbacks(on_save_corrections=seen.append))
    try:
        window.show_result(PipelineResult(source_lines=["Steel Ingot"], output_lines=["钢铁锭"]))
        window.target.delete("1.0", "end")
        window.target.insert("1.0", "钢锭\n多出来的一行")
        window.root.update()

        window.save_corrections()

        assert seen == []
        assert "行数对不上" in window.status_text()
    finally:
        window.root.destroy()


# ---- 控制器：写回缓存与术语表 ----


def _app(workdir: Path, translator=None) -> Application:
    path = save_config(Config(), workdir / "config.toml")
    config = load_config(path)
    app = Application(
        config,
        config_path=path,
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=FakeOcr(),
        window=FakeWindow(),
    )
    if translator is not None:
        app.translator = translator
    return app


def test_apply_corrections_writes_cache_glossary_and_history(workdir: Path):
    inner = RecordingInner()
    caching = CachingTranslator(inner, TranslationCache(workdir / "cache.sqlite"), "m", "v")
    app = _app(workdir, caching)
    app.history.add(["Steel Ingot"], ["钢铁锭"])

    app.apply_corrections([("Steel Ingot", "钢锭")])

    # 术语表：短名词才记，并且立刻落盘
    assert app.config.glossary["Steel Ingot"] == "钢锭"
    assert load_config(Path(app.config_path)).glossary["Steel Ingot"] == "钢锭"
    # 缓存：同一句以后不再问模型
    assert caching.translate_lines(["Steel Ingot"]) == ["钢锭"]
    assert inner.calls == []
    # 历史里的译文跟着改掉（只改内存）
    assert app.history.all()[-1].target == ("钢锭",)
    assert any("已保存修正 1 行" in text for text in app.window.statuses)


def test_apply_corrections_keeps_sentences_out_of_the_glossary(workdir: Path):
    inner = RecordingInner()
    caching = CachingTranslator(inner, TranslationCache(workdir / "cache.sqlite"), "m", "v")
    app = _app(workdir, caching)

    app.apply_corrections([("You should not be here.", "你不该来这里。")])

    assert app.config.glossary == {}
    assert caching.translate_lines(["You should not be here."]) == ["你不该来这里。"]
    assert inner.calls == []


def test_apply_corrections_rebuilds_translator_after_glossary_change(workdir: Path):
    app = _app(workdir)
    app.translator = object()      # 假装已经建好了翻译器

    app.apply_corrections([("Steel Ingot", "钢锭")])

    # 术语表变了 → 下次请求要用新提示词重建翻译器
    assert app.translator is None


def test_apply_corrections_without_translator_still_records_glossary(workdir: Path):
    app = _app(workdir)                    # 没配 api key，翻译器建不出来

    app.apply_corrections([("Steel Ingot", "钢锭")])

    assert app.config.glossary["Steel Ingot"] == "钢锭"
    assert any("没有可用的翻译服务" in text for text in app.window.statuses)


def test_glossary_correction_shows_up_in_the_next_prompt(workdir: Path):
    """改过之后，术语表里的译法要真的进到提示词里。"""

    from mchanhua.translate.deepseek import build_system_prompt

    app = _app(workdir)
    app.apply_corrections([("Steel Ingot", "钢锭")])

    prompt = build_system_prompt(app.config.glossary)
    assert "Steel Ingot=钢锭" in prompt
