import pytest

from mchanhua.hotkey import HotkeyManager, ModifierComboWatcher, is_modifier_only, normalize_hotkey


def test_normalize_hotkey_lowercases_and_trims():
    assert normalize_hotkey("Ctrl+Alt+Q") == "ctrl+alt+q"
    assert normalize_hotkey(" ctrl + shift + f8 ") == "ctrl+shift+f8"


def test_normalize_hotkey_rejects_bad_input():
    for bad in ("", "ctrl+", "+q", "ctrl+alt+unknown"):
        with pytest.raises(ValueError):
            normalize_hotkey(bad)


def test_modifier_only_hotkey_is_allowed_and_flagged():
    assert normalize_hotkey("Ctrl+Alt") == "ctrl+alt"
    assert is_modifier_only("ctrl+alt")
    assert not is_modifier_only("ctrl+alt+q")
    assert not is_modifier_only("f8")


def test_symbol_keys_are_accepted():
    for good in ("alt+/", "alt+m", "ctrl+shift+/", "alt+\\", "ctrl+alt+.", "alt+-"):
        assert normalize_hotkey(good) == good


class _FakeKeys:
    """模拟"当前按下的键"，可以故意塞入残留键。"""

    def __init__(self) -> None:
        self.down: set[str] = set()

    def press(self, *names: str) -> None:
        self.down.update(names)

    def release(self, *names: str) -> None:
        self.down.difference_update(names)

    def __call__(self, name: str) -> bool:
        return name in self.down


def test_modifier_combo_fires_when_all_keys_are_down():
    keys = _FakeKeys()
    fired: list[str] = []
    watcher = ModifierComboWatcher(is_pressed=keys)
    watcher.register("翻译", "ctrl+alt", lambda: fired.append("hit"))

    keys.press("ctrl")
    assert watcher.handle_event("ctrl", "down") is False
    keys.press("alt")
    assert watcher.handle_event("alt", "down") is True
    assert fired == ["hit"]


def test_modifier_combo_fires_even_with_stale_extra_key():
    """回归：库里要求按键集合"恰好相等"，残留一个键就再也触发不了；自家判断不受影响。"""

    keys = _FakeKeys()
    fired: list[str] = []
    watcher = ModifierComboWatcher(is_pressed=keys)
    watcher.register("翻译", "ctrl+alt", lambda: fired.append("hit"))

    keys.press("v")                 # Alt+V 之后残留的键
    keys.press("alt")
    watcher.handle_event("alt", "down")
    keys.press("ctrl")
    assert watcher.handle_event("ctrl", "down") is True
    assert fired == ["hit"]


def test_modifier_combo_does_not_repeat_until_released():
    keys = _FakeKeys()
    fired: list[str] = []
    watcher = ModifierComboWatcher(is_pressed=keys)
    watcher.register("翻译", "ctrl+alt", lambda: fired.append("hit"))

    keys.press("ctrl", "alt")
    assert watcher.handle_event("alt", "down") is True
    assert watcher.handle_event("alt", "down") is False       # 按住不放不重复触发
    keys.release("alt")
    watcher.handle_event("alt", "up")                          # 松开后重新武装
    keys.press("alt")
    assert watcher.handle_event("alt", "down") is True
    assert fired == ["hit", "hit"]


def test_hotkey_manager_routes_modifier_only_to_watcher():
    manager = HotkeyManager()
    manager.register("翻译", "ctrl+alt", lambda: None)

    assert manager._watcher.bindings == [("翻译", ["ctrl", "alt"])]
    assert manager.bindings == [("翻译", "ctrl+alt")]


def test_hotkey_manager_routes_plain_combo_to_watcher_too():
    """普通组合键也走自家匹配，避免库里"精确集合"带来的漏触发。"""

    manager = HotkeyManager()
    manager.register("框选", "alt+v", lambda: None)

    assert manager._watcher.bindings == [("框选", ["alt", "v"])]
