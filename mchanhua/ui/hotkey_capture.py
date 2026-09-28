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


# ---- "按住一个或多个键"式录制（设置界面的「选择按键」按钮）----

# 输出顺序固定成 ctrl、alt、shift、windows，跟配置文件里的写法一致
MODIFIER_ORDER = ("ctrl", "alt", "shift", "windows")

MODIFIER_KEYSYM_TOKENS = {
    "control_l": "ctrl",
    "control_r": "ctrl",
    "alt_l": "alt",
    "alt_r": "alt",
    "shift_l": "shift",
    "shift_r": "shift",
    "win_l": "windows",
    "win_r": "windows",
    "super_l": "windows",
    "super_r": "windows",
}

# 这些键不参与录制：Caps 是开关键，Esc 留给"取消"
IGNORED_KEYSYMS = {"caps_lock", "escape"}


def keysym_to_press_token(keysym: str) -> str | None:
    """按下/松开事件里的按键名 → 配置里的 token（修饰键也会返回结果）。

    与 keysym_to_token 的区别：这里保留 Ctrl / Alt / Shift / Win，
    因为"只按修饰键"（ctrl+alt）也是合法的热键。
    """

    name = (keysym or "").strip().lower()
    if not name or name in IGNORED_KEYSYMS:
        return None
    token = MODIFIER_KEYSYM_TOKENS.get(name)
    if token is not None:
        return token
    return keysym_to_token(keysym)


def combo_from_pressed(pressed: list[str]) -> str | None:
    """把"当前按住的键（按按下顺序）"拼成热键串；一个都没有时返回 None。"""

    unique: list[str] = []
    for token in pressed:
        if token and token not in unique:
            unique.append(token)
    if not unique:
        return None
    modifiers = [name for name in MODIFIER_ORDER if name in unique]
    others = [token for token in unique if token not in MODIFIER_ORDER]
    return "+".join(modifiers + others) or None


class ComboTracker:
    """跟着按键事件记录"这一轮按住过的组合"。纯逻辑，方便测试。

    取"见过的最长组合"：先按住 ctrl+alt 再按 q，松开 q 之后仍然算 ctrl+alt+q，
    不会退回到 ctrl+alt；只按住 ctrl+alt（不按别的键）也能得到 ctrl+alt。
    """

    def __init__(self) -> None:
        self._pressed: list[str] = []
        self._best: str | None = None

    @property
    def pressed(self) -> list[str]:
        return list(self._pressed)

    @property
    def candidate(self) -> str | None:
        return self._best

    def press(self, keysym: str) -> str | None:
        token = keysym_to_press_token(keysym)
        if token is None:
            return self._best
        if token not in self._pressed:
            self._pressed.append(token)
        self._remember()
        return self._best

    def release(self, keysym: str) -> str | None:
        token = keysym_to_press_token(keysym)
        if token is not None and token in self._pressed:
            self._pressed.remove(token)
        return self._best

    def reset(self) -> None:
        self._pressed.clear()
        self._best = None

    def _remember(self) -> None:
        combo = combo_from_pressed(self._pressed)
        if combo is None:
            return
        if self._best is None or len(combo.split("+")) >= len(self._best.split("+")):
            self._best = combo
