"""应用控制器的接线测试：用假组件跑通"采集 → OCR → 翻译 → 消息队列"。"""

from mchanhua.app import Application
from mchanhua.config import Config
from mchanhua.geometry import Region
from tests.fakes import DecodingTranslator, FakeGrabber, FakeOcr, FakeWindow, wait_for


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
    messages = wait_for(app, "result")
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
    messages = wait_for(app, "status")
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


class _RecordingHotkeys:
    """记录 stop/start 的假热键管理器。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def stop(self) -> None:
        self.calls.append("stop")

    def start(self) -> None:
        self.calls.append("start")


def test_recording_hotkeys_pauses_and_resumes_global_hotkeys():
    """录制新热键时要先卸掉全局热键，否则按 Ctrl+Alt 会顺手触发翻译。"""

    app = Application(
        Config(),
        use_hotkeys=True,
        grabber=FakeGrabber(),
        ocr=FakeOcr(),
        window=FakeWindow(),
    )
    manager = _RecordingHotkeys()
    app.hotkeys = manager

    app.suspend_hotkeys()
    app.resume_hotkeys()

    assert manager.calls == ["stop", "start"]


def test_resume_hotkeys_does_nothing_when_hotkeys_disabled():
    app = Application(
        Config(),
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=FakeOcr(),
        window=FakeWindow(),
    )
    manager = _RecordingHotkeys()
    app.hotkeys = manager

    app.resume_hotkeys()

    assert manager.calls == []


def test_finished_translation_goes_into_history():
    """翻译完成后要记进内存历史，并把最近记录推给界面（含本次）。"""

    app = Application(
        Config(),
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=FakeOcr(),
        window=FakeWindow(),
    )
    app.translator = DecodingTranslator()

    app.perform_translate(Region(100, 200, 400, 300))
    messages = wait_for(app, "result")

    entries = app.history.all()
    assert len(entries) == 1
    assert entries[0].pairs() == [("Steel Ingot", "[tognI leetS]"), ("磁石", "磁石")]

    pushed = [message for message in messages if message[0] == "history"]
    assert pushed and pushed[-1][1] == entries           # 界面拿到的是最新历史


def test_empty_selection_does_not_go_into_history():
    """选区内没文字时只是提示，不该记一条空历史。"""

    class _BlindOcr:
        name = "fake-ocr"

        def recognize(self, image):  # noqa: ARG002 - 接口要求
            from mchanhua.ocr.base import OcrResult

            return OcrResult(lines=[], elapsed_ms=1.0, backend=self.name)

    app = Application(
        Config(),
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=_BlindOcr(),
        window=FakeWindow(),
    )
    app.translator = DecodingTranslator()

    app.perform_translate(Region(100, 200, 400, 300))
    wait_for(app, "notice")

    assert app.history.all() == []
