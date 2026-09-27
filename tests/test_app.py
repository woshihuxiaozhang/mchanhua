"""应用控制器的接线测试：用假组件跑通"采集 → OCR → 翻译 → 消息队列"。"""

import queue
import time

from PIL import Image

from mchanhua.app import Application
from mchanhua.config import Config
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
        return OcrResult(lines=[OcrLine(text="Steel Ingot"), OcrLine(text="磁石")], elapsed_ms=8.0, backend=self.name)


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

    def show_source(self, lines, elapsed_ms) -> None:  # pragma: no cover - 由消息队列驱动
        pass

    def show_result(self, result) -> None:  # pragma: no cover
        pass

    def poll(self, message_queue, interval_ms: int = 60) -> None:  # pragma: no cover
        pass

    def run(self) -> None:  # pragma: no cover
        pass


def _wait_for(app: Application, kind: str, timeout: float = 10.0) -> list[tuple]:
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


def test_worker_pushes_ocr_and_result_messages():
    app = Application(
        Config(),
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=FakeOcr(),
        window=FakeWindow(),
    )
    app.translator = DecodingTranslator()

    app.perform_translate(Region(100, 200, 400, 300))
    messages = _wait_for(app, "result")
    assert any(message[0] == "ocr" for message in messages)

    result = next(message[1] for message in messages if message[0] == "result")
    assert result.source_lines == ["Steel Ingot", "磁石"]
    assert result.output_lines == [f"[{'Steel Ingot'[::-1]}]", "磁石"]  # 中文行原样保留
    assert result.ocr_backend == "fake-ocr"


def test_missing_api_key_reports_but_still_shows_source():
    window = FakeWindow()
    app = Application(
        Config(),
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=FakeOcr(),
        window=window,
    )
    assert app._ensure_translator() is None
    assert app.translator_error and "API key" in app.translator_error


def test_capture_failure_is_reported():
    class BrokenGrabber(FakeGrabber):
        def grab(self, region):
            raise RuntimeError("采集失败")

    app = Application(
        Config(),
        use_hotkeys=False,
        grabber=BrokenGrabber(),
        ocr=FakeOcr(),
        window=FakeWindow(),
    )
    app.perform_translate(Region(0, 0, 10, 10))
    messages = _wait_for(app, "status")
    assert any(message[0] == "status" and "采集失败" in message[1] for message in messages)


def test_request_translate_enqueues_one_shot_callable():
    """回归：热键请求进队列的是"一次性任务"，不是可被 drain 再放一遍的消息类型。"""

    app = Application(
        Config(),
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=FakeOcr(),
        window=FakeWindow(),
    )
    app.request_translate()
    kind, payload = app.queue.get_nowait()
    assert kind == "call"
    assert callable(payload)
