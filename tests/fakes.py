"""测试用的假组件（被多个测试模块共用，放在这里避免重复导入测试模块）。"""

from __future__ import annotations

import queue
import time

from PIL import Image

from mchanhua.geometry import Region
from mchanhua.ocr.base import OcrLine, OcrResult


class FakeGrabber:
    name = "fake"

    def __init__(self) -> None:
        self.requests: list[Region | None] = []

    def monitors(self):
        return [Region(0, 0, 2560, 1440)]

    def primary_monitor(self):
        return Region(0, 0, 2560, 1440)

    def grab(self, region):
        self.requests.append(region)
        return Image.new("RGB", (region.width, region.height), (0, 0, 0))

    def close(self) -> None:
        return None


class FakeOcr:
    name = "fake-ocr"

    def recognize(self, image):
        return OcrResult(
            lines=[OcrLine(text="Steel Ingot"), OcrLine(text="磁石")],
            elapsed_ms=8.0,
            backend=self.name,
        )


class DecodingTranslator:
    name = "fake-translator"
    warnings: list[str] = []

    def translate_lines(self, lines):
        return [f"[{text[::-1]}]" for text in lines]


class FakeWindow:
    def __init__(self) -> None:
        self.statuses: list[str] = []
        self.results: list[object] = []
        self.sources: list[list[str]] = []
        self.root = FakeTkRoot()

    def set_status(self, text: str) -> None:
        self.statuses.append(text)

    def show_source(self, lines, elapsed_ms) -> None:
        self.sources.append(list(lines))

    def show_result(self, result) -> None:
        self.results.append(result)

    def poll(self, message_queue, interval_ms: int = 60) -> None:  # pragma: no cover
        pass

    def run(self) -> None:  # pragma: no cover
        pass


class FakeTkRoot:
    """最小化的 Tk root 替身：控制器会用到指针位置、屏幕尺寸与窗口显隐。"""

    def __init__(self) -> None:
        self.withdrawn = 0
        self.deiconified = 0
        self.destroyed = False

    def withdraw(self) -> None:
        self.withdrawn += 1

    def deiconify(self) -> None:
        self.deiconified += 1

    def update_idletasks(self) -> None:
        pass

    def after(self, _ms: int, func=None, *args):
        """测试里立即执行，等价于"稍后就开始抓图"。"""

        if func is not None:
            func(*args)
        return "after-id"

    def destroy(self) -> None:
        self.destroyed = True

    def winfo_pointerxy(self) -> tuple[int, int]:
        return (1024, 576)          # 逻辑坐标（对应物理 1280,720）

    def winfo_screenwidth(self) -> int:
        return 2048

    def winfo_screenheight(self) -> int:
        return 1152


def wait_for(app, kind: str, timeout: float = 10.0) -> list[tuple]:
    """等待指定类型的消息，返回期间收到的所有消息。"""

    collected: list[tuple] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            message = app.queue.get(timeout=0.1)
        except queue.Empty:
            continue
        collected.append(message)
        if message[0] == kind:
            return collected
    raise AssertionError(f"没等到 {kind} 消息，期间收到：{collected}")
