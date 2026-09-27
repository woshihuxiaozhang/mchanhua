"""全局热键封装。"""

from __future__ import annotations

import re
from typing import Callable

from mchanhua.logging_setup import get_logger

TOKEN_PATTERN = re.compile(r"^(ctrl|alt|shift|windows|cmd|tab|space|enter|esc|[a-z0-9]|f\d{1,2})$")
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
