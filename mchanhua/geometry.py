"""屏幕坐标与区域模型。

坐标约定：程序内部一律使用**物理像素**。Windows 在 125% 缩放下逻辑坐标与物理
坐标不一致（本机 2560x1440 物理屏会被报告成 2048x1152），采集、框选、OCR 区域
必须统一到物理像素，否则会出现 25% 的整体偏移。
"""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class Region:
    """一个矩形区域，单位是物理像素。"""

    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        for name in ("x", "y", "width", "height"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{name} 必须是整数，当前为 {value!r}")
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"区域宽高必须为正数：{self}")

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)

    def to_csv(self) -> str:
        return f"{self.x},{self.y},{self.width},{self.height}"

    def to_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)

    def to_mss(self) -> dict[str, int]:
        """转成 mss 需要的字典形式。"""

        return {"left": self.x, "top": self.y, "width": self.width, "height": self.height}

    def moved(self, dx: int, dy: int) -> "Region":
        return Region(self.x + dx, self.y + dy, self.width, self.height)

    def scaled(self, factor: float) -> "Region":
        """按比例缩放（用于图像放大后的坐标映射）。"""

        if factor <= 0:
            raise ValueError(f"缩放系数必须为正数：{factor}")
        return Region(
            round(self.x * factor),
            round(self.y * factor),
            max(1, round(self.width * factor)),
            max(1, round(self.height * factor)),
        )

    def intersect(self, other: "Region") -> "Region | None":
        """与另一个区域求交集，没有重叠时返回 None。"""

        left = max(self.x, other.x)
        top = max(self.y, other.y)
        right = min(self.right, other.right)
        bottom = min(self.bottom, other.bottom)
        if right <= left or bottom <= top:
            return None
        return Region(left, top, right - left, bottom - top)

    def clamp(self, bounds: "Region") -> "Region":
        """裁剪到 bounds 范围内，完全不重叠时抛 ValueError。"""

        clipped = self.intersect(bounds)
        if clipped is None:
            raise ValueError(f"区域 {self} 完全落在边界 {bounds} 之外")
        return clipped

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.right and self.y <= y < self.bottom

    @classmethod
    def parse(cls, text: str | Sequence[int]) -> "Region":
        """解析 "x,y,w,h"，也接受四元素序列。"""

        if isinstance(text, str):
            parts = [p.strip() for p in text.replace("，", ",").split(",")]
            if len(parts) != 4 or "" in parts:
                raise ValueError(f"区域格式应为 x,y,w,h，当前为 {text!r}")
            try:
                values = [int(p) for p in parts]
            except ValueError as exc:
                raise ValueError(f"区域必须是整数：{text!r}") from exc
        else:
            values = list(text)
            if len(values) != 4:
                raise ValueError(f"区域需要 4 个数值，当前为 {values!r}")
            values = [int(v) for v in values]
        return cls(*values)

    def __str__(self) -> str:  # pragma: no cover - 便于调试
        return self.to_csv()


def enable_dpi_awareness() -> str:
    """声明本进程 DPI 感知，返回实际生效的模式。

    必须在创建任何窗口或读取屏幕坐标之前调用。
    """

    if sys.platform != "win32":
        return "not-windows"

    user32 = ctypes.windll.user32
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return "per-monitor-v2"
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return "per-monitor"
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
        return "system"
    except Exception:
        pass
    return "unchanged"

