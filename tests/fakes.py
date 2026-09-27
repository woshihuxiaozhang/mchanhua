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

    def set_status(self, text: str) -> None:
        self.statuses.append(text)

    def show_source(self, lines, elapsed_ms) -> None:  # pragma: no cover - 由队列驱动
        pass

    def show_result(self, result) -> None:  # pragma: no cover
        pass

    def poll(self, message_queue, interval_ms: int = 60) -> None:  # pragma: no cover
        pass

    def run(self) -> None:  # pragma: no cover
        pass


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
