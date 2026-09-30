"""区域类型（物品 / 字幕）与「每个区域绑自己的热键」。"""

from __future__ import annotations

from pathlib import Path

import pytest

from mchanhua.app import Application
from mchanhua.config import (
    AREA_KIND_GENERIC,
    AREA_KIND_ITEM,
    AREA_KIND_SUBTITLE,
    Config,
    ConfigError,
    dumps,
    load_config,
    loads,
    save_config,
)
from mchanhua.geometry import Region
from mchanhua.ocr.base import OcrLine, OcrResult
from mchanhua.pipeline import hint_for_kind, run_from_ocr
from mchanhua.translate.base import set_area_hint
from tests.fakes import FakeGrabber, FakeWindow, wait_for


def _result(texts: list[str]) -> OcrResult:
    return OcrResult(
        lines=[OcrLine(text) for text in texts], elapsed_ms=2.0, backend="fake"
    )


class HintedTranslator:
    """记录每次请求的原文和当次挂着的区域提示。"""

    name = "hinted"

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str]] = []
        self.last_paragraph = ""
        self.warnings: list[str] = []

    def translate_lines(self, lines):
        self.calls.append((list(lines), getattr(self, "area_hint", "")))
        self.last_paragraph = "整段：" + "".join(lines)
        self.warnings = []
        return [f"【{text}】" for text in lines]


# ---- 提示词分批 ----


def test_single_kind_uses_one_request_with_its_hint():
    translator = HintedTranslator()
    ocr = _result(["Steel Ingot", "Iron Nugget"])

    result = run_from_ocr(ocr, translator, line_kinds=[AREA_KIND_ITEM, AREA_KIND_ITEM])

    assert len(translator.calls) == 1
    assert translator.calls[0][0] == ["Steel Ingot", "Iron Nugget"]
    assert translator.calls[0][1] == hint_for_kind(AREA_KIND_ITEM)
    assert result.output_lines == ["【Steel Ingot】", "【Iron Nugget】"]


def test_mixed_kinds_are_translated_in_two_requests():
    """物品提示和剧情字幕混在一次取词里：分开问，各带各的提示词。"""

    translator = HintedTranslator()
    ocr = _result(["Steel Ingot", "Follow the light.", "Iron Nugget"])

    result = run_from_ocr(
        ocr,
        translator,
        line_kinds=[AREA_KIND_ITEM, AREA_KIND_SUBTITLE, AREA_KIND_ITEM],
    )

    by_lines = {tuple(lines): hint for lines, hint in translator.calls}
    assert by_lines[("Steel Ingot", "Iron Nugget")] == hint_for_kind(AREA_KIND_ITEM)
    assert by_lines[("Follow the light.",)] == hint_for_kind(AREA_KIND_SUBTITLE)
    # 行号要对上，不能因为分批就串行
    assert result.output_lines == ["【Steel Ingot】", "【Follow the light.】", "【Iron Nugget】"]
    assert result.line_areas == []


def test_item_group_never_becomes_a_paragraph():
    """物品清单被"整理成段"会变成一坨怪句子，直接不采纳。"""

    translator = HintedTranslator()
    result = run_from_ocr(
        _result(["Steel Ingot", "Follow the light."]),
        translator,
        line_kinds=[AREA_KIND_ITEM, AREA_KIND_SUBTITLE],
    )

    assert result.paragraph == "整段：Follow the light."


def test_no_kinds_means_no_hint_and_one_request():
    """没设类型（老配置）时行为和以前完全一样。"""

    translator = HintedTranslator()
    run_from_ocr(_result(["Steel Ingot"]), translator)

    assert len(translator.calls) == 1
    assert translator.calls[0][1] == ""


def test_area_hint_is_cleared_after_translating():
    translator = HintedTranslator()
    run_from_ocr(_result(["Steel Ingot"]), translator, line_kinds=[AREA_KIND_ITEM])

    assert getattr(translator, "area_hint", "") == ""


def test_set_area_hint_ignores_translators_without_attribute_support():
    class Locked:
        __slots__ = ()

    set_area_hint(Locked(), "随便什么")          # 不该抛异常


def test_kinds_are_truncated_with_fullscreen_line_cap():
    translator = HintedTranslator()
    ocr = _result(["Aaa", "Bbb", "Ccc"])

    run_from_ocr(
        ocr,
        translator,
        max_lines=2,
        line_kinds=[AREA_KIND_ITEM, AREA_KIND_SUBTITLE, AREA_KIND_SUBTITLE],
    )

    assert len(translator.calls) == 2            # 物品 1 批 + 字幕 1 批（第 3 行被截掉）
    lines = [line for call in translator.calls for line in call[0]]
    assert lines == ["Aaa", "Bbb"]


def test_area_hint_lands_in_the_real_prompt():
    """真的走到提示词里：物品区的提示词必须带上「物品」那段要求。"""

    import json

    import httpx

    from mchanhua.translate.deepseek import DeepSeekTranslator

    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        content = json.dumps({"lines": [{"i": 0, "dst": "钢锭"}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    translator = DeepSeekTranslator(
        api_key="sk-test", client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    run_from_ocr(_result(["Steel Ingot"]), translator, line_kinds=[AREA_KIND_ITEM])

    system_prompt = seen[0]["messages"][0]["content"]
    assert "【这一批文本的特点】" in system_prompt
    assert "物品" in system_prompt
    assert "通用" in system_prompt


# ---- 配置 ----


def test_area_kind_defaults_to_generic():
    config = Config()
    config.regions.add_area(Region(1, 2, 3, 4), name="区域1")

    assert config.regions.kind_of("区域1") == AREA_KIND_GENERIC
    assert config.regions.kind_of("不存在的区域") == AREA_KIND_GENERIC
    assert "区域1" not in config.regions.area_kinds     # 默认值不写进配置


def test_area_kind_and_hotkey_round_trip(workdir: Path):
    config = Config()
    config.regions.add_area(Region(100, 200, 300, 90), name="物品提示")
    config.regions.add_area(Region(400, 900, 800, 120), name="字幕区")
    config.regions.set_area_kind("物品提示", AREA_KIND_ITEM)
    config.regions.set_area_kind("字幕区", AREA_KIND_SUBTITLE)
    config.regions.set_area_hotkey("物品提示", "alt+1")

    path = save_config(config, workdir / "config.toml")
    text = path.read_text(encoding="utf-8")
    loaded = load_config(path)

    assert "[regions.hotkeys]" in text and "[regions.kinds]" in text
    assert loaded.regions.kind_of("物品提示") == AREA_KIND_ITEM
    assert loaded.regions.kind_of("字幕区") == AREA_KIND_SUBTITLE
    assert loaded.regions.hotkey_of("物品提示") == "alt+1"
    assert loaded.regions.hotkey_of("字幕区") == ""


def test_generic_kind_is_not_stored():
    config = Config()
    config.regions.add_area(Region(1, 2, 3, 4), name="区域1")

    config.regions.set_area_kind("区域1", AREA_KIND_ITEM)
    assert config.regions.area_kinds == {"区域1": AREA_KIND_ITEM}

    config.regions.set_area_kind("区域1", AREA_KIND_GENERIC)
    assert config.regions.area_kinds == {}


def test_remove_and_rename_carry_metadata():
    config = Config()
    config.regions.add_area(Region(1, 2, 3, 4), name="区域1")
    config.regions.add_area(Region(5, 6, 7, 8), name="区域2")
    config.regions.set_area_kind("区域1", AREA_KIND_SUBTITLE)
    config.regions.set_area_hotkey("区域1", "alt+1")

    config.regions.rename_area("区域1", "字幕区")
    assert config.regions.kind_of("字幕区") == AREA_KIND_SUBTITLE
    assert config.regions.hotkey_of("字幕区") == "alt+1"
    assert config.regions.area_kinds == {"字幕区": AREA_KIND_SUBTITLE}

    config.regions.remove_area("字幕区")
    assert config.regions.area_kinds == {}
    assert config.regions.area_hotkeys == {}


def test_unknown_kind_in_config_raises():
    with pytest.raises(ConfigError):
        loads('[regions.kinds]\n"区域1" = "怪物名"\n')


def test_kinds_table_must_be_a_table():
    with pytest.raises(ConfigError):
        loads("[regions]\nkinds = 3\n")


def test_dumps_without_area_metadata_stays_clean():
    text = dumps(Config())
    assert "[regions.hotkeys]" not in text
    assert "[regions.kinds]" not in text


# ---- 控制器 ----


class _OcrWithTwoAreas:
    name = "fake-ocr"

    def recognize(self, image):
        return OcrResult(
            lines=[
                OcrLine("Steel Ingot", Region(120, 130, 200, 24)),
                OcrLine("Follow the light.", Region(600, 900, 400, 26)),
            ],
            elapsed_ms=3.0,
            backend=self.name,
        )


class FakeHotkeys:
    def __init__(self) -> None:
        self.registered: dict[str, str] = {}

    def register(self, action, hotkey, callback) -> None:
        self.registered[action] = hotkey

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


def _app(workdir: Path, translator=None) -> Application:
    config_path = save_config(Config(), workdir / "config.toml")
    config = load_config(config_path)
    app = Application(
        config,
        config_path=config_path,
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=_OcrWithTwoAreas(),
        window=FakeWindow(),
    )
    app.translator = translator or HintedTranslator()
    return app


def test_per_area_hotkey_is_registered(workdir: Path):
    app = _app(workdir)
    app.config.regions.add_area(Region(100, 100, 400, 200), name="物品提示")
    app.config.regions.set_area_hotkey("物品提示", "alt+1")
    fake = FakeHotkeys()
    app.hotkeys = fake

    app._register_hotkeys()

    assert fake.registered["翻译区域「物品提示」"] == "alt+1"
    assert fake.registered["翻译自定义选区"] == "ctrl+alt"


def test_area_without_hotkey_is_not_registered(workdir: Path):
    app = _app(workdir)
    app.config.regions.add_area(Region(100, 100, 400, 200), name="物品提示")
    fake = FakeHotkeys()
    app.hotkeys = fake

    app._register_hotkeys()

    assert "翻译区域「物品提示」" not in fake.registered


def test_per_area_translate_only_grabs_that_area(workdir: Path):
    app = _app(workdir)
    app.config.regions.add_area(Region(100, 100, 400, 200), name="区域1")
    app.config.regions.add_area(Region(500, 800, 700, 300), name="区域2")

    app.perform_translate_area("区域2")
    messages = wait_for(app, "result")
    result = next(message[1] for message in messages if message[0] == "result")

    assert result.source_lines == ["Follow the light."]
    assert result.line_areas == ["区域2"]
    assert app.grabber.requests[-1].to_csv() == "0,0,2560,1440"   # 整屏抓一次再筛行


def test_per_area_translate_reports_missing_area(workdir: Path):
    app = _app(workdir)

    app.perform_translate_area("早就删掉的区域")

    assert any("已经不在了" in text for text in app.window.statuses)
    assert app.grabber.requests == []


def test_area_kind_reaches_the_translator(workdir: Path):
    translator = HintedTranslator()
    app = _app(workdir, translator)
    app.config.regions.add_area(Region(100, 100, 400, 200), name="物品提示")
    app.config.regions.add_area(Region(500, 800, 700, 300), name="字幕区")
    app.config.regions.set_area_kind("物品提示", AREA_KIND_ITEM)
    app.config.regions.set_area_kind("字幕区", AREA_KIND_SUBTITLE)

    app.perform_translate()
    wait_for(app, "result")

    hints = {tuple(lines): hint for lines, hint in translator.calls}
    assert hints[("Steel Ingot",)] == hint_for_kind(AREA_KIND_ITEM)
    assert hints[("Follow the light.",)] == hint_for_kind(AREA_KIND_SUBTITLE)


def test_framing_new_areas_reregisters_hotkeys(workdir: Path, monkeypatch):
    """Alt+V 框完（可能新增/删除了区域）要重新注册热键，删掉的区域不能还能按。"""

    import time

    app = _app(workdir)
    app.use_hotkeys = True
    fake = FakeHotkeys()
    app.hotkeys = fake
    app._new_hotkey_manager = lambda: fake      # 别去装真的全局键盘钩子

    def fake_pick(_monitor, _parent, existing=None, on_accept=None, on_remove=None,
                  on_remove_index=None):
        on_accept(Region(7, 8, 90, 100))
        return ["区域1"]

    monkeypatch.setattr("mchanhua.app.pick_region", fake_pick)

    app.perform_select_region()

    deadline = time.monotonic() + 5
    while not fake.registered and time.monotonic() < deadline:
        time.sleep(0.02)
    assert fake.registered["翻译自定义选区"] == "ctrl+alt"


# ---- 设置窗口 ----


tk = pytest.importorskip("tkinter")


def _settings(config: Config):
    from mchanhua.ui.settings_window import SettingsWindow

    last: Exception | None = None
    for _ in range(2):
        try:
            return SettingsWindow(config)
        except tk.TclError as exc:
            last = exc
    pytest.skip(f"没有可用的图形环境：{last}")  # pragma: no cover


def test_settings_area_rows_expose_kind_and_hotkey():
    config = Config()
    config.regions.add_area(Region(1, 2, 3, 4), name="物品提示")
    window = _settings(config)
    try:
        assert window._vars["hotkey.area:物品提示"].get() == ""

        window._vars["hotkey.area:物品提示"].set("alt+1")
        window._set_area_kind("物品提示", AREA_KIND_ITEM)
        collected = window.collect()

        assert collected.regions.hotkey_of("物品提示") == "alt+1"
        assert collected.regions.kind_of("物品提示") == AREA_KIND_ITEM
    finally:
        window.root.destroy()


def test_settings_rejects_area_hotkey_conflicts():
    config = Config()
    config.regions.add_area(Region(1, 2, 3, 4), name="物品提示")
    window = _settings(config)
    try:
        window._vars["hotkey.area:物品提示"].set("alt+/")     # 和「框选并翻译」撞了
        problems = window.validate()

        assert any("物品提示" in problem for problem in problems)
    finally:
        window.root.destroy()


def test_settings_rejects_invalid_area_hotkey():
    config = Config()
    config.regions.add_area(Region(1, 2, 3, 4), name="物品提示")
    window = _settings(config)
    try:
        window._vars["hotkey.area:物品提示"].set("ctrl+")
        problems = window.validate()

        assert any("物品提示" in problem for problem in problems)
    finally:
        window.root.destroy()


def test_settings_delete_area_clears_its_metadata():
    config = Config()
    config.regions.add_area(Region(1, 2, 3, 4), name="物品提示")
    config.regions.set_area_hotkey("物品提示", "alt+1")
    config.regions.set_area_kind("物品提示", AREA_KIND_ITEM)
    window = _settings(config)
    try:
        window._remove_area("物品提示")

        assert window.config.regions.area_hotkeys == {}
        assert window.config.regions.area_kinds == {}
        assert "hotkey.area:物品提示" not in window._vars
    finally:
        window.root.destroy()
