import pytest

from mchanhua.hotkey import normalize_hotkey
from mchanhua.hotkey import is_modifier_only


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
