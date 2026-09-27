"""屏幕采集。

热键触发一次、抓一帧，所以不需要 dxcam 那种高帧率能力，
mss（纯 Python）足够快也更省事；出问题时还能退回 Pillow 的 ImageGrab。
"""

from __future__ import annotations

from typing import Protocol

from PIL import Image

from mchanhua.geometry import Region


class Grabber(Protocol):
    name: str

    def monitors(self) -> list[Region]: ...

    def primary_monitor(self) -> Region: ...

    def grab(self, region: Region) -> Image.Image: ...

    def close(self) -> None: ...


class MssGrabber:
    name = "mss"

    def __init__(self, monitor: int = 1) -> None:
        self._monitor = monitor
        self._sct = None

    def _session(self):
        if self._sct is None:
            import mss

            self._sct = mss.mss()
        return self._sct

    def monitors(self) -> list[Region]:
        session = self._session()
        regions = []
        for mon in session.monitors:
            regions.append(Region(int(mon["left"]), int(mon["top"]), int(mon["width"]), int(mon["height"])))
        return regions

    def primary_monitor(self) -> Region:
        monitors = self.monitors()
        index = min(max(self._monitor, 0), len(monitors) - 1)
        return monitors[index]

    def grab(self, region: Region) -> Image.Image:
        shot = self._session().grab(region.to_mss())
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    def close(self) -> None:
        if self._sct is not None:
            self._sct.close()
            self._sct = None


class PillowGrabber:
    name = "pillow"

    def __init__(self, monitor: int = 1) -> None:
        self._monitor = monitor

    def monitors(self) -> list[Region]:
        from PIL import ImageGrab

        image = ImageGrab.grab()
        if self._monitor > 1:
            raise RuntimeError("Pillow 后端只支持主显示器")
        return [Region(0, 0, image.width, image.height)]

    def primary_monitor(self) -> Region:
        return self.monitors()[0]

    def grab(self, region: Region) -> Image.Image:
        from PIL import ImageGrab

        box = (region.x, region.y, region.right, region.bottom)
        return ImageGrab.grab(bbox=box, all_screens=True).convert("RGB")

    def close(self) -> None:  # pragma: no cover - 无资源需要释放
        return None


def create_grabber(backend: str = "auto", monitor: int = 1) -> Grabber:
    if backend == "mss":
        return MssGrabber(monitor)
    if backend == "pillow":
        return PillowGrabber(monitor)
    try:
        return MssGrabber(monitor)
    except Exception:
        return PillowGrabber(monitor)


def resolve_region(region: Region | None, monitor: Region) -> Region:
    """确定实际要采集的区域：None 表示整屏，否则裁剪到屏幕范围内。"""

    if region is None:
        return monitor
    return region.clamp(monitor)


def grab_screen(
    grabber: Grabber,
    region: Region | None = None,
) -> Image.Image:
    target = resolve_region(region, grabber.primary_monitor())
    image = grabber.grab(target)
    if image.size != (target.width, target.height):
        raise RuntimeError(
            f"采集尺寸不符：期望 {target.width}x{target.height}，实际 {image.width}x{image.height}"
        )
    return image
