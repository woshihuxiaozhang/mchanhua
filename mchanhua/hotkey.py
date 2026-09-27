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
    """注册全局热键。

    所有热键都用自家匹配：库的匹配要求"当前按下的键集合恰好等于热键"，
    选区弹窗之类场景丢掉一次 key-up 就会残留按键，导致必须重按。
    自家判断只要求"组合里的键都按着"，并且按过一次后要等松开才会再次触发。
    """

    def __init__(self) -> None:
        self._registered: list[tuple[str, str]] = []
        self._watcher = ModifierComboWatcher()
        self._started = False

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
        self._watcher.register(action, normalized, callback)

    def start(self) -> None:
        """装上修饰键组合的监听（需要在注册之后调用）。"""

        if self._started or not self._watcher.bindings:
            return
        self._watcher.start()
        self._started = True

    @property
    def bindings(self) -> list[tuple[str, str]]:
        return list(self._registered)

    def stop(self) -> None:
        self._watcher.stop()
        self._started = False
        self._registered.clear()


class ModifierComboWatcher:
    """自己实现热键触发判断：只要组合里的键**都**按着就触发，松开后才允许再次触发。

    这样即使按键状态里残留了别的键（弹窗抢焦点时常见），也不会漏触发。
    """

    def __init__(self, is_pressed: Callable[[str], bool] | None = None) -> None:
        self._bindings: list[tuple[str, list[str], Callable[[], None]]] = []
        self._armed: dict[str, bool] = {}
        self._hook = None
        self._is_pressed = is_pressed or _default_is_pressed

    @property
    def bindings(self) -> list[tuple[str, list[str]]]:
        return [(action, keys) for action, keys, _ in self._bindings]

    def register(self, action: str, hotkey: str, callback: Callable[[], None]) -> None:
        keys = [part.strip().lower() for part in hotkey.split("+") if part.strip()]
        self._bindings.append((action, keys, callback))
        self._armed[action] = True

    def handle_event(self, name: str, event_type: str) -> bool:
        """处理一个按键事件；返回是否因此触发了某个热键。"""

        fired = False
        name = (name or "").lower()
        if event_type == "up":
            for action, keys, _ in self._bindings:
                if name in keys:
                    self._armed[action] = True
            return False

        for action, keys, callback in self._bindings:
            if not self._armed.get(action, True):
                continue
            if all(self._is_pressed(key) for key in keys):
                self._armed[action] = False
                get_logger().info("修饰键组合触发：%s", action)
                callback()
                fired = True
        return fired

    def start(self) -> None:
        try:
            import keyboard
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("缺少 keyboard 库，无法注册全局热键") from exc
        self._hook = keyboard.hook(lambda event: self.handle_event(event.name, event.event_type))

    def stop(self) -> None:
        if self._hook is None:
            return
        try:
            import keyboard

            keyboard.unhook(self._hook)
        except Exception:  # pragma: no cover
            pass
        self._hook = None


def _default_is_pressed(key: str) -> bool:
    try:
        import keyboard

        return bool(keyboard.is_pressed(key))
    except Exception:  # pragma: no cover
        return False
