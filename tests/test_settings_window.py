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


# ---- 历史翻译页 ----


def test_settings_window_has_history_tab_showing_all_entries(monkeypatch):
    """设置里能看到全部历史（小窗只看最近 20 条）。"""

    from datetime import datetime

    from mchanhua.history import TranslationHistory
    from mchanhua.ui.settings_window import SettingsWindow

    history = TranslationHistory()
    for index in range(25):
        history.add([f"line {index}"], [f"第 {index} 行"], at=datetime(2026, 9, 28, 10, index % 60))

    try:
        window = SettingsWindow(Config(), history=history)
    except tk.TclError as exc:  # pragma: no cover
        pytest.skip(f"没有可用的图形环境：{exc}")
    try:
        assert "历史翻译" in window._pages
        text = window._history_text.get("1.0", "end")
        assert "line 0" in text and "line 24" in text     # 25 条全在（不止 20 条）
        assert "共 25 条" in window._history_count.cget("text")
    finally:
        window.root.destroy()


def test_settings_window_clear_history(monkeypatch):
    from datetime import datetime

    from mchanhua.history import TranslationHistory
    from mchanhua.ui.settings_window import SettingsWindow

    history = TranslationHistory()
    history.add(["Steel Ingot"], ["钢锭"], at=datetime(2026, 9, 28, 14, 35))
    cleared: list[str] = []

    try:
        window = SettingsWindow(Config(), history=history, on_history_cleared=lambda: cleared.append("ok"))
    except tk.TclError as exc:  # pragma: no cover
        pytest.skip(f"没有可用的图形环境：{exc}")
    try:
        monkeypatch.setattr("mchanhua.ui.settings_window.messagebox.askyesno", lambda *a, **k: True)
        window.clear_history()

        assert len(history) == 0
        assert cleared == ["ok"]
        assert "还没有翻译记录" in window._history_text.get("1.0", "end")
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


# ---- 页面滚动：内容比窗口高时要能滚 ----


def test_settings_pages_are_scrollable():
    """回归：设置窗口的页以前没有滚动条，界面外观页下半截根本看不到。"""

    import customtkinter as ctk

    window = _window(Config())
    try:
        for name in ("翻译服务", "热键", "界面外观", "历史翻译"):
            body = window._page_bodies[name]
            assert isinstance(body, ctk.CTkScrollableFrame)
            assert body._parent_frame.winfo_manager() == "pack"    # 外层容器在显示
            assert body._scrollbar.winfo_manager() == "grid"       # 右边挂了滚动条

        window._show_page("界面外观")
        window.root.update_idletasks()
        # 界面外观页的内容本来就比窗口可视区域高，必须靠滚动才能看全
        assert window._page_bodies["界面外观"].winfo_reqheight() > 400
    finally:
        window.root.destroy()


# ---- 背景图按钮 / 透明度滑块 ----


def test_settings_window_picks_background_image(workdir, monkeypatch):
    from PIL import Image

    from mchanhua.ui.settings_window import SettingsWindow

    path = workdir / "bg.png"
    Image.new("RGB", (640, 360), (10, 20, 30)).save(path)

    previews: list[str] = []
    try:
        window = SettingsWindow(Config(), preview_background=previews.append)
    except tk.TclError as exc:  # pragma: no cover
        pytest.skip(f"没有可用的图形环境：{exc}")
    try:
        monkeypatch.setattr(
            "mchanhua.ui.settings_window.filedialog.askopenfilename", lambda **k: str(path)
        )
        window.pick_background()

        assert window._background_path == str(path)
        assert previews == [str(path)]                     # 立即预览
        assert window.collect().ui.background_image == str(path)   # 保存时会写进配置

        window.clear_background()
        assert window._background_path == ""
        assert previews[-1] == ""
        assert window.collect().ui.background_image == ""
    finally:
        window.root.destroy()


def test_settings_window_rejects_broken_background(workdir, monkeypatch):
    from mchanhua.ui.settings_window import SettingsWindow

    broken = workdir / "broken.png"
    broken.write_text("not an image", encoding="utf-8")

    shown: list[tuple] = []
    monkeypatch.setattr(
        "mchanhua.ui.settings_window.messagebox.showerror",
        lambda title, text, **k: shown.append((title, text)),
    )
    try:
        window = SettingsWindow(Config())
    except tk.TclError as exc:  # pragma: no cover
        pytest.skip(f"没有可用的图形环境：{exc}")
    try:
        monkeypatch.setattr(
            "mchanhua.ui.settings_window.filedialog.askopenfilename", lambda **k: str(broken)
        )
        window.pick_background()

        assert window._background_path == ""               # 坏图不生效
        assert shown and "打不开" in shown[0][0]
    finally:
        window.root.destroy()


def test_settings_window_opacity_slider_updates_value_and_previews():
    from mchanhua.ui.settings_window import SettingsWindow

    seen: list[float] = []
    try:
        window = SettingsWindow(Config(), preview_opacity=seen.append)
    except tk.TclError as exc:  # pragma: no cover
        pytest.skip(f"没有可用的图形环境：{exc}")
    try:
        window._on_opacity_slide(0.55)

        assert window._vars["ui.opacity"].get() == "0.55"
        assert window._opacity_value.cget("text") == "0.55"
        assert seen == [0.55]
        assert abs(window.collect().ui.opacity - 0.55) < 1e-6
    finally:
        window.root.destroy()
