"""设置窗口的测试：热键录制、校验、保存。"""

import time

import pytest

from mchanhua.config import Config, load_config, save_config
from mchanhua.hotkey import find_conflicts
from mchanhua.ui.hotkey_capture import (
    ComboTracker,
    combo_from_pressed,
    describe_hotkey,
    hotkey_from_event,
    keysym_to_press_token,
    keysym_to_token,
)

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

    last: Exception | None = None
    for _ in range(2):      # 这台机器上 Tk 初始化偶尔读不到 ttk 脚本，重试一次更稳
        try:
            return SettingsWindow(config)
        except tk.TclError as exc:
            last = exc
            time.sleep(0.2)
    pytest.skip(f"没有可用的图形环境：{last}")  # pragma: no cover


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


# ---- 「选择按键」：按住一个或多个键选出组合 ----


def test_keysym_to_press_token_keeps_modifiers():
    assert keysym_to_press_token("Control_L") == "ctrl"
    assert keysym_to_press_token("Alt_R") == "alt"
    assert keysym_to_press_token("Shift_L") == "shift"
    assert keysym_to_press_token("Super_L") == "windows"
    assert keysym_to_press_token("Caps_Lock") is None
    assert keysym_to_press_token("Escape") is None      # 留给"取消"
    assert keysym_to_press_token("slash") == "/"


def test_combo_from_pressed_orders_modifiers_first():
    assert combo_from_pressed(["q", "alt", "ctrl"]) == "ctrl+alt+q"
    assert combo_from_pressed(["alt"]) == "alt"
    assert combo_from_pressed([]) is None
    assert combo_from_pressed(["alt", "alt"]) == "alt"


def test_tracker_accepts_modifier_only_combo():
    """只按住 Ctrl+Alt 也必须能选出来（在输入框里直接按是选不出来的）。"""

    tracker = ComboTracker()
    tracker.press("Control_L")
    tracker.press("Alt_L")
    assert tracker.candidate == "ctrl+alt"
    tracker.release("Alt_L")
    tracker.release("Control_L")
    assert tracker.candidate == "ctrl+alt"


def test_tracker_keeps_longest_combo_of_one_gesture():
    tracker = ComboTracker()
    for keysym in ("Control_L", "Alt_L", "q"):
        tracker.press(keysym)
    tracker.release("q")
    tracker.release("Alt_L")
    tracker.release("Control_L")
    assert tracker.candidate == "ctrl+alt+q"


def test_tracker_single_key_and_reset():
    tracker = ComboTracker()
    tracker.press("F8")
    tracker.release("F8")
    assert tracker.candidate == "f8"
    tracker.reset()
    assert tracker.candidate is None
    assert tracker.pressed == []


def test_tracker_ignores_unknown_keys():
    tracker = ComboTracker()
    tracker.press("Num_Lock")            # 不认识
    assert tracker.candidate is None
    tracker.press("m")
    assert tracker.candidate == "m"


def _patch_picker(monkeypatch, result: str | None, record: dict):
    """把选择对话框换成假的，只测设置窗口这边接得对不对。"""

    import mchanhua.ui.settings_window as settings

    def fake(parent, title="", initial="", on_pause=None, on_resume=None):
        record["title"] = title
        record["initial"] = initial
        record["pause"] = on_pause
        record["resume"] = on_resume
        return result

    monkeypatch.setattr(settings, "pick_hotkey", fake)


def test_settings_window_uses_picked_hotkey(monkeypatch):
    record: dict = {}
    _patch_picker(monkeypatch, "ctrl+alt+shift+q", record)
    window = _window(Config())
    try:
        window._pick_hotkey("translate")
        assert window._vars["hotkey.translate"].get() == "ctrl+alt+shift+q"
        assert "翻译自定义选区" in record["title"]
        assert window.validate() == []
    finally:
        window.root.destroy()


def test_settings_window_can_clear_hotkey(monkeypatch):
    _patch_picker(monkeypatch, "", {})
    window = _window(Config())
    try:
        window._pick_hotkey("quit")
        assert window._vars["hotkey.quit"].get() == ""
    finally:
        window.root.destroy()


def test_settings_window_keeps_value_when_cancelled(monkeypatch):
    _patch_picker(monkeypatch, None, {})
    window = _window(Config())
    try:
        before = window._vars["hotkey.translate"].get()
        window._pick_hotkey("translate")
        assert window._vars["hotkey.translate"].get() == before
    finally:
        window.root.destroy()


def test_settings_window_passes_pause_callbacks(monkeypatch):
    """录制期间要能通知外面暂停/恢复全局热键。"""

    record: dict = {}
    _patch_picker(monkeypatch, "alt+t", record)
    paused: list[str] = []

    def pause() -> None:
        paused.append("pause")

    def resume() -> None:
        paused.append("resume")

    from mchanhua.ui.settings_window import SettingsWindow

    try:
        window = SettingsWindow(Config(), pause_hotkeys=pause, resume_hotkeys=resume)
    except tk.TclError as exc:  # pragma: no cover
        pytest.skip(f"没有可用的图形环境：{exc}")
    try:
        window._pick_hotkey("translate")
        assert record["pause"] is pause and record["resume"] is resume
    finally:
        window.root.destroy()


class _FakeKeyEvent:
    def __init__(self, keysym: str) -> None:
        self.keysym = keysym
        self.state = 0


def test_entry_capture_records_modifier_only_combo():
    """在输入框里直接按键：只按 Ctrl+Alt 也要录得出来（以前这种情况下什么都不记）。"""

    paused: list[str] = []
    window = _window(Config())
    try:
        window.pause_hotkeys = lambda: paused.append("pause")
        window.resume_hotkeys = lambda: paused.append("resume")

        window._capture_focus_in("translate")
        assert window._vars["hotkey.translate"].get() == ""
        window._capture_press(_FakeKeyEvent("Control_L"), "translate")
        window._capture_press(_FakeKeyEvent("Alt_L"), "translate")
        assert window._vars["hotkey.translate"].get() == "ctrl+alt"
        window._capture_release(_FakeKeyEvent("Alt_L"), "translate")
        window._capture_release(_FakeKeyEvent("Control_L"), "translate")
        assert window._vars["hotkey.translate"].get() == "ctrl+alt"

        window._capture_focus_out("translate")
        assert paused == ["pause", "resume"]
    finally:
        window.root.destroy()


def test_entry_capture_keeps_longest_combo():
    window = _window(Config())
    try:
        window._capture_focus_in("translate_clipboard")
        for keysym in ("Control_L", "Shift_L", "s"):
            window._capture_press(_FakeKeyEvent(keysym), "translate_clipboard")
        for keysym in ("s", "Shift_L", "Control_L"):
            window._capture_release(_FakeKeyEvent(keysym), "translate_clipboard")
        assert window._vars["hotkey.translate_clipboard"].get() == "ctrl+shift+s"
    finally:
        window.root.destroy()


def test_entry_capture_restores_value_when_nothing_pressed():
    """点进输入框又点走、什么都没按：不能把原来的热键悄悄清掉。"""

    window = _window(Config())
    try:
        before = window._vars["hotkey.select_region"].get()
        window._capture_focus_in("select_region")
        assert window._vars["hotkey.select_region"].get() == ""
        window._capture_focus_out("select_region")
        assert window._vars["hotkey.select_region"].get() == before
    finally:
        window.root.destroy()


def test_entry_capture_can_be_turned_off_for_manual_typing():
    """关掉录制后，输入框恢复成普通输入框，可以手输。"""

    window = _window(Config())
    try:
        window._vars["capture_in_entry"].set(False)
        assert window._capture_press(_FakeKeyEvent("Control_L"), "translate") == ""
        window._vars["hotkey.translate"].set("alt+t")
        assert window._vars["hotkey.translate"].get() == "alt+t"
    finally:
        window.root.destroy()
