"""把一次按键事件转换成热键字符串（设置界面里"录制热键"用）。

这些是纯函数，方便测试；Tk 事件里 keysym 是按键名、state 是按住的修饰键位。
"""

from __future__ import annotations

# Windows 上 Tk 的修饰键状态位
MODIFIER_BITS: tuple[tuple[str, int], ...] = (
    ("ctrl", 0x0004),
    ("alt", 0x0008),
    ("shift", 0x0001),
)

KEYSYM_MAP = {
    "slash": "/",
    "backslash": "\\",
    "semicolon": ";",
    "apostrophe": "'",
    "comma": ",",
    "period": ".",
    "bracketleft": "[",
    "bracketright": "]",
    "minus": "-",
    "equal": "=",
    "grave": "`",
    "space": "space",
    "tab": "tab",
    "escape": "esc",
    "return": "enter",
}

MODIFIER_KEYSYMS = {
    "control_l",
    "control_r",
    "alt_l",
    "alt_r",
    "shift_l",
    "shift_r",
    "win_l",
    "win_r",
    "super_l",
    "super_r",
    "caps_lock",
}


def keysym_to_token(keysym: str) -> str | None:
    """把 Tk 的 keysym 转成配置里的按键名；不认识返回 None。"""

    name = (keysym or "").strip()
    if not name:
        return None
    lowered = name.lower()
    if lowered in MODIFIER_KEYSYMS:
        return None
    if len(name) == 1:
        return lowered
    if lowered.startswith("f") and lowered[1:].isdigit():
        return lowered
    return KEYSYM_MAP.get(lowered)


def hotkey_from_event(keysym: str, state: int) -> str | None:
    """把"按下的键 + 按住的修饰键"拼成热键串，例如 alt+v、ctrl+alt+q、alt+/。"""

    token = keysym_to_token(keysym)
    if token is None:
        return None
    if token in {name for name, _ in MODIFIER_BITS}:
        return None
    parts = [name for name, bit in MODIFIER_BITS if state & bit]
    parts.append(token)
    return "+".join(parts)


def describe_hotkey(hotkey: str) -> str:
    """给人看的中文说明。"""

    names = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "esc": "Esc"}
    return " + ".join(names.get(part, part.upper()) for part in hotkey.split("+") if part)
