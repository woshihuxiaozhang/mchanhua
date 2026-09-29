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


def follow_cursor_region(offset: Region, cursor: tuple[int, int], bounds: Region) -> Region:
    """按"跟随光标"的相对区域算出实际采集区域。

    offset 的 x/y 是相对光标的偏移（可为负），宽高是区域大小。
    """

    region = Region(cursor[0] + offset.x, cursor[1] + offset.y, offset.width, offset.height)
    return region.clamp(bounds)


def logical_to_physical(logical: Region, logical_size: tuple[int, int], physical: Region) -> Region:
    """把逻辑坐标（Tk 窗口坐标）换算成物理像素坐标。

    125% 缩放下两者相差 1.25 倍，框选必须做这个换算，否则采集区域会整体偏移。
    """

    if logical_size[0] <= 0 or logical_size[1] <= 0:
        raise ValueError(f"逻辑尺寸非法：{logical_size}")
    scale_x = physical.width / logical_size[0]
    scale_y = physical.height / logical_size[1]
    result = Region(
        physical.x + round(logical.x * scale_x),
        physical.y + round(logical.y * scale_y),
        max(1, round(logical.width * scale_x)),
        max(1, round(logical.height * scale_y)),
    )
    return result.clamp(physical)


def physical_to_logical(
    region: Region, logical_size: tuple[int, int], physical: Region
) -> Region:
    """物理像素 → 窗口逻辑坐标（logical_to_physical 的反向，用来把已保存区域画到遮罩上）。"""

    if physical.width <= 0 or physical.height <= 0:
        raise ValueError(f"物理尺寸非法：{physical}")
    scale_x = logical_size[0] / physical.width
    scale_y = logical_size[1] / physical.height
    return Region(
        round((region.x - physical.x) * scale_x),
        round((region.y - physical.y) * scale_y),
        max(1, round(region.width * scale_x)),
        max(1, round(region.height * scale_y)),
    )


def normalize_drag(x0: int, y0: int, x1: int, y1: int) -> Region:
    """把拖拽起止点转成区域，支持从任意方向拖。"""

    left, right = sorted((x0, x1))
    top, bottom = sorted((y0, y1))
    if right == left or bottom == top:
        raise ValueError("拖拽区域太小")
    return Region(left, top, right - left, bottom - top)
