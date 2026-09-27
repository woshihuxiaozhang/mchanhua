import pytest

from mchanhua.hotkey import normalize_hotkey


def test_normalize_hotkey_lowercases_and_trims():
    assert normalize_hotkey("Ctrl+Alt+Q") == "ctrl+alt+q"
    assert normalize_hotkey(" ctrl + shift + f8 ") == "ctrl+shift+f8"


def test_normalize_hotkey_rejects_bad_input():
    for bad in ("", "ctrl+", "+q", "ctrl+alt+unknown", "ctrl+alt"):
        with pytest.raises(ValueError):
            normalize_hotkey(bad)

