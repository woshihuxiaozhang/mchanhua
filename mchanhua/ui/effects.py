"""按钮反馈与加载动画的小工具。

参考了 GitHub 上 CamusFSY/memphis-python-gui-skill 里对 Tkinter/CustomTkinter 的几条做法：
- 按钮要有"按下"的即时反馈（那里用的是按下时把前景往阴影方向挪几像素；
  我们的按钮是圆角浅色块，改用更稳的做法：按下时颜色加深、松开回弹）；
- 悬停不要是硬切换，要有一小段过渡（自己插值颜色，因为 customtkinter 的
  hover_color 是瞬间生效的）；
- 阻塞性的工作要在独立的状态区里显示进度，别让界面看起来死了。

动画一律用 root.after 的**有限步数**（不自我递归），所以在测试里用"立即执行"的
假 root 也不会失控。
"""

from __future__ import annotations

from typing import Callable, Iterable

import customtkinter as ctk

# 加载转圈用的字符：Segoe UI Symbol 里都有，转起来比较顺
SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

_HEX = "0123456789abcdefABCDEF"


def parse_color(value) -> tuple[int, int, int] | None:
    """把 '#rrggbb' 拆成三元组；不是颜色就返回 None（比如 'transparent'）。"""

    if not isinstance(value, str):
        return None
    text = value.strip()
    if len(text) == 7 and text.startswith("#") and all(ch in _HEX for ch in text[1:]):
        return int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16)
    return None


def mix(first: str, second: str, ratio: float) -> str:
    """两色按比例混合（ratio=0 → first，1 → second）。"""

    ratio = max(0.0, min(1.0, float(ratio)))
    if ratio <= 0:                     # 端点原样返回：保留原来的大小写写法
        return first
    if ratio >= 1:
        return second
    left = parse_color(first)
    right = parse_color(second)
    if left is None or right is None:
        return second if ratio >= 0.5 else first
    parts = (round(a + (b - a) * ratio) for a, b in zip(left, right))
    return "#{:02x}{:02x}{:02x}".format(*parts)


def shade(color: str, factor: float) -> str:
    """调亮/调暗：factor<1 变暗、>1 变亮（对 'transparent' 原样返回）。"""

    rgb = parse_color(color)
    if rgb is None:
        return color
    parts = (max(0, min(255, round(channel * factor))) for channel in rgb)
    return "#{:02x}{:02x}{:02x}".format(*parts)


def animate_color(
    widget,
    option: str,
    start: str,
    end: str,
    *,
    steps: int = 4,
    delay: int = 25,
    done: Callable[[], None] | None = None,
) -> None:
    """把某个颜色属性从 start 平滑过渡到 end（步数固定，跑完就停）。"""

    if parse_color(start) is None or parse_color(end) is None:
        _safe_configure(widget, **{option: end})
        if done is not None:
            done()
        return
    total = max(1, int(steps))
    root = getattr(widget, "_root", None) or getattr(getattr(widget, "master", None), "_root", None)

    def step(index: int) -> None:
        ratio = index / total
        _safe_configure(widget, **{option: mix(start, end, ratio)})
        if index >= total:
            if done is not None:
                done()
            return
        if root is not None and hasattr(root, "after"):
            root.after(max(1, delay), lambda: step(index + 1))
        else:  # pragma: no cover - 没有 root 就直接跳到位
            step(total)

    step(0)


def _safe_configure(widget, **options) -> None:
    try:
        widget.configure(**options)
    except Exception:  # pragma: no cover - 窗口销毁/属性不支持
        pass


class ButtonFeedback:
    """给一个 CTkButton 挂上悬停/按下的过渡反馈。

    状态：常态 → 悬停（CTk 自己也会改 hover_color，我们把它接过来做插值）→ 按下（加深）。
    """

    def __init__(self, button: ctk.CTkButton, *, accent: bool = False) -> None:
        self.button = button
        self.base = _color_option(button, "fg_color") or "transparent"
        self.hover = _color_option(button, "hover_color") or shade(
            self.base if parse_color(self.base) else "#FFFFFF", 0.94
        )
        self.pressed = shade(self.base, 0.88) if parse_color(self.base) else "#E8EAED"
        self.inside = False
        self._busy = False
        button.bind("<Enter>", self._on_enter, add="+")
        button.bind("<Leave>", self._on_leave, add="+")
        button.bind("<ButtonPress-1>", self._on_press, add="+")
        button.bind("<ButtonRelease-1>", self._on_release, add="+")

    def refresh_base(self) -> None:
        """按钮换了配色（例如「实时」开关点亮）后重新记住常态色。"""

        self.base = _color_option(self.button, "fg_color") or "transparent"
        self.hover = _color_option(self.button, "hover_color") or self.hover
        self.pressed = shade(self.base, 0.88) if parse_color(self.base) else self.pressed

    def _to(self, target: str, steps: int = 4, delay: int = 25) -> None:
        current = _color_option(self.button, "fg_color") or self.base
        animate_color(self.button, "fg_color", current, target, steps=steps, delay=delay)

    def _on_enter(self, _event=None) -> None:
        self.inside = True
        self._to(self.hover)

    def _on_leave(self, _event=None) -> None:
        self.inside = False
        self._to(self.base)

    def _on_press(self, _event=None) -> None:
        self._to(self.pressed, steps=2, delay=15)

    def _on_release(self, _event=None) -> None:
        self._to(self.hover if self.inside else self.base, steps=3, delay=20)


def _color_option(widget, option: str):
    try:
        return widget.cget(option)
    except Exception:  # pragma: no cover - 个别控件没有这个属性
        return None


def attach_feedback(button: ctk.CTkButton, *, accent: bool = False) -> ButtonFeedback:
    """给按钮挂反馈并返回句柄（后面改配色时调 refresh_base）。"""

    return ButtonFeedback(button, accent=accent)


class Spinner:
    """加载转圈：每次 poll 走一帧，不自己排定时器。"""

    def __init__(self, frames: Iterable[str] = SPINNER_FRAMES) -> None:
        self.frames = tuple(frames) or ("…",)
        self.index = 0

    def frame(self) -> str:
        return self.frames[self.index % len(self.frames)]

    def advance(self) -> str:
        self.index += 1
        return self.frame()

    def reset(self) -> None:
        self.index = 0
