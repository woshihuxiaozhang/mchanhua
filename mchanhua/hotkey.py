"""全局热键封装。"""

from __future__ import annotations

import re
from typing import Callable

from mchanhua.logging_setup import get_logger

# 符号键（/ \ ; ' , . [ ] = - `）逐一转义后放进字符类，
# 避免 "-" 在类里意外形成范围（曾导致 alt+/ 被判为非法按键）
SYMBOL_KEYS = "/\\;',.[]=-`"
_SYMBOL_CLASS = "".join(re.escape(char) for char in SYMBOL_KEYS)
TOKEN_PATTERN = re.compile(
    rf"^(ctrl|alt|shift|windows|cmd|tab|space|enter|esc|[a-z0-9]|f\d{{1,2}}|[{_SYMBOL_CLASS}])$"
)
MODIFIERS = {"ctrl", "alt", "shift", "windows", "cmd"}


def normalize_hotkey(text: str) -> str:
    """把热键串标准化成 keyboard 库接受的写法。"""

    parts = [part.strip().lower() for part in text.split("+")]
    if not parts or any(not part for part in parts):
        raise ValueError(f"热键格式不合法：{text!r}")
    for part in parts:
        if not TOKEN_PATTERN.match(part):
            raise ValueError(f"热键包含不支持的按键：{part!r}")
    return "+".join(parts)


def is_modifier_only(hotkey: str) -> bool:
    """判断热键是否只由修饰键组成（例如 ctrl+alt）。"""

    parts = [part.strip().lower() for part in hotkey.split("+") if part.strip()]
    return bool(parts) and all(part in MODIFIERS for part in parts)


def reset_pressed_state() -> int:
    """清掉 keyboard 库记录的"当前按下的键"，返回清掉的个数。

    该库用「当前按下的键的精确集合」匹配热键（`tuple(sorted(_pressed_events))`）。
    弹窗抢焦点、窗口切换时容易丢掉某个键的 key-up，集合里就会残留一个键，
    于是 Ctrl+Alt 这类组合再也匹配不上，必须松开重按——这就是"要按两次"的原因。
    """

    try:
        import keyboard
    except ImportError:  # pragma: no cover - 依赖缺失时才走到
        return 0

    pressed = getattr(keyboard, "_pressed_events", None)
    lock = getattr(keyboard, "_pressed_events_lock", None)
    if pressed is None:
        return 0
    count = len(pressed)
    if lock is not None:
        with lock:
            pressed.clear()
    else:  # pragma: no cover
        pressed.clear()
    return count


class HotkeyManager:
    """注册全局热键；keyboard 库缺失或注册失败时给出可读的错误。"""

    def __init__(self) -> None:
        self._registered: list[tuple[str, str]] = []

    def register(self, action: str, hotkey: str, callback: Callable[[], None]) -> None:
        normalized = normalize_hotkey(hotkey)
        if is_modifier_only(normalized):
            get_logger().warning(
                "热键 %s 只由修饰键组成：按下这几个键就会立即触发，"
                "并且会和其他以它为前缀的快捷键（如 %s+某键）冲突",
                normalized,
                normalized,
            )
        self._registered.append((action, normalized))
        try:
            import keyboard
        except ImportError as exc:  # pragma: no cover - 依赖缺失时才走到
            raise RuntimeError("缺少 keyboard 库，无法注册全局热键：python -m pip install keyboard") from exc
        try:
            keyboard.add_hotkey(normalized, callback)
        except Exception as exc:
            raise RuntimeError(f"注册热键 {normalized} 失败：{exc}") from exc

    @property
    def bindings(self) -> list[tuple[str, str]]:
        return list(self._registered)

    def stop(self) -> None:
        try:
            import keyboard

            for _, hotkey in self._registered:
                try:
                    keyboard.remove_hotkey(hotkey)
                except (KeyError, ValueError):
                    pass
        except ImportError:  # pragma: no cover
            pass
        self._registered.clear()
