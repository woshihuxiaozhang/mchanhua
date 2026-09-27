"""设置窗口的测试：热键录制、校验、保存。"""

import pytest

from mchanhua.config import Config, load_config, save_config
from mchanhua.hotkey import find_conflicts
from mchanhua.ui.hotkey_capture import describe_hotkey, hotkey_from_event, keysym_to_token

tk = pytest.importorskip("tkinter")


def test_hotkey_from_event_builds_expected_strings():
    assert hotkey_from_event("v", 0) == "v"
    assert hotkey_from_event("v", 0x0008) == "alt+v"
    assert hotkey_from_event("q", 0x0004 | 0x0008) == "ctrl+alt+q"
    assert hotkey_from_event("slash", 0x0008) == "alt+/"
    assert hotkey_from_event("F8", 0) == "f8"


def test_hotkey_from_event_ignores_bare_modifiers():
    assert hotkey_from_event("Control_L", 0x0004) is None
    assert hotkey_from_event("Alt_L", 0x0008) is None
    assert hotkey_from_event("Unknown", 0) is None


def test_keysym_to_token_maps_symbols():
    assert keysym_to_token("backslash") == "\\"
    assert keysym_to_token("bracketleft") == "["
    assert keysym_to_token("Tab") == "tab"
    assert keysym_to_token("Escape") == "esc"


def test_describe_hotkey_is_readable():
    assert describe_hotkey("ctrl+alt+q") == "Ctrl + Alt + Q"


def test_find_conflicts_detects_duplicates():
    problems = find_conflicts({"取词": "alt+v", "框选": "alt+v"})
    assert problems and "重复" in problems[0]


def test_find_conflicts_detects_prefix_overlap():
    problems = find_conflicts({"取词": "ctrl+alt", "退出": "ctrl+alt+x"})
    assert any("会先于" in problem for problem in problems)


def test_find_conflicts_reports_invalid_hotkey():
    problems = find_conflicts({"取词": "ctrl+"})
    assert problems and "不合法" in problems[0]


def _window(config: Config):
    from mchanhua.ui.settings_window import SettingsWindow

    try:
        return SettingsWindow(config)
    except tk.TclError as exc:  # pragma: no cover - 无图形环境
        pytest.skip(f"没有可用的图形环境：{exc}")


def test_settings_window_collects_and_saves(workdir):
    path = save_config(Config(), workdir / "config.toml")
    config = load_config(path)
    window = _window(config)
    try:
        window._vars["api_key"].set("sk-from-ui")
        window._vars["provider"].set("Ollama 本地模型（免 key）")
        window._apply_preset()
        assert window._vars["base_url"].get().startswith("http://localhost:11434")

        window._vars["hotkey.translate"].set("alt+q")
        window._vars["ui.result_font_size"].set("20")
        assert window.validate() == []

        collected = window.collect()
        assert collected.translate.api_key == "sk-from-ui"
        assert collected.hotkeys.translate == "alt+q"
        assert collected.ui.result_font_size == 20

        save_config(collected, path)
        assert "sk-from-ui" in path.read_text(encoding="utf-8")
    finally:
        window.root.destroy()


def test_settings_window_validation_reports_conflicts(workdir):
    window = _window(Config())
    try:
        window._vars["hotkey.translate"].set("alt+v")
        window._vars["hotkey.select_region"].set("alt+v")
        assert any("重复" in problem for problem in window.validate())
    finally:
        window.root.destroy()
