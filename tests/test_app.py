"""应用控制器的接线测试：用假组件跑通"采集 → OCR → 翻译 → 消息队列"。"""

from mchanhua.app import Application
from mchanhua.config import Config
from mchanhua.geometry import Region
from mchanhua.ocr.base import OcrLine, OcrResult
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


# ---- 抓屏时先藏起自己的窗口 ----


def test_capture_hides_window_then_shows_it_again():
    """全屏翻译前窗口必须先藏起来，抓完再放回来（否则会把自己界面也翻译进去）。"""

    window = FakeWindow()
    app = Application(
        Config(),
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=FakeOcr(),
        window=window,
    )
    app.translator = DecodingTranslator()

    app.perform_translate_fullscreen()
    messages = wait_for(app, "call")      # 等"把窗口放回来"的回调入队
    calls = [message[1] for message in messages if message[0] == "call"]
    for call in calls:                    # 界面没跑主循环，手动把排队的回调执行掉
        call()

    assert window.root.withdrawn >= 1     # 抓图时藏起来了
    assert window.root.deiconified >= 1   # 抓完放回来了
    assert app._hidden_for_capture is False


def test_selection_outside_window_does_not_hide_it():
    """选区离窗口很远时不要藏窗口——不然每按一次热键窗口都闪一下。"""

    window = FakeWindow()
    app = Application(
        Config(),
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=FakeOcr(),
        window=window,
    )
    app.translator = DecodingTranslator()

    # FakeTkRoot 的窗口坐标是 (0,0,200,200)，选它右边的区域
    app.perform_translate(Region(1200, 600, 300, 200))
    messages = wait_for(app, "result")
    for call in [message[1] for message in messages if message[0] == "call"]:
        call()

    assert window.root.withdrawn == 0
    assert window.root.deiconified == 0


def test_selection_covering_window_hides_it():
    """选区把窗口框进去时必须藏窗口，否则会把界面一起翻译。"""

    window = FakeWindow()
    app = Application(
        Config(),
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=FakeOcr(),
        window=window,
    )
    app.translator = DecodingTranslator()

    app.perform_translate(Region(0, 0, 400, 300))     # 盖上窗口
    messages = wait_for(app, "call")
    for call in [message[1] for message in messages if message[0] == "call"]:
        call()

    assert window.root.withdrawn >= 1
    assert window.root.deiconified >= 1


def test_window_comes_back_before_ocr_and_translation(workdir):
    """窗口要在"抓完图"就放回来，不能等 OCR/翻译跑完（否则像卡住了）。"""

    window = FakeWindow()

    class _SlowOcr:
        name = "fake-ocr"

        def recognize(self, image):
            return OcrResult(lines=[OcrLine(text="Steel Ingot")], elapsed_ms=1.0, backend=self.name)

    app = Application(
        Config(),
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=_SlowOcr(),
        window=window,
    )

    class _RecordingTranslator:
        name = "fake"
        warnings: list[str] = []

        def translate_lines(self, lines):
            return [f"[{text}]" for text in lines]

    app.translator = _RecordingTranslator()

    app.perform_translate_fullscreen()
    messages = wait_for(app, "result")

    # 队列是先进先出："恢复窗口"必须排在结果之前入队，
    # 界面主循环按顺序处理，所以窗口一定在显示结果之前就回来了。
    show_index = next(
        index for index, message in enumerate(messages)
        if message[0] == "call" and getattr(message[1], "__name__", "") == "_show_after_capture"
    )
    result_index = next(
        index for index, message in enumerate(messages) if message[0] == "result"
    )
    assert show_index < result_index


# ---- 框选（Alt+V / Alt+/）：框的时候窗口得先让开 ----


def _app_with_fake_pick(monkeypatch, region):
    window = FakeWindow()
    app = Application(
        Config(),
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=FakeOcr(),
        window=window,
    )
    app.translator = DecodingTranslator()
    seen: list[int] = []

    def fake_pick(_monitor, _parent):
        seen.append(window.root.withdrawn)      # 框选那一刻窗口藏了没
        return region

    monkeypatch.setattr("mchanhua.app.pick_region", fake_pick)
    return app, window, seen


def test_select_and_translate_hides_window_while_picking(monkeypatch):
    """Alt+/：框选时窗口要藏起来（否则挡住字幕框不到），抓完再放回来。"""

    app, window, seen = _app_with_fake_pick(monkeypatch, Region(100, 200, 400, 300))

    app.perform_select_and_translate()
    messages = wait_for(app, "result")
    for call in [message[1] for message in messages if message[0] == "call"]:
        call()

    assert seen == [1]                     # 框选时窗口已经藏好
    assert window.root.deiconified >= 1    # 抓完图放回来
    assert app._hidden_for_capture is False


def test_select_and_translate_keeps_window_hidden_until_captured(monkeypatch):
    """抓图还没开始前不能把窗口又露出来，否则会被拍进画面。"""

    app, window, _seen = _app_with_fake_pick(monkeypatch, Region(100, 200, 400, 300))
    app.config.ocr.settle_frames = 1          # 只抓一帧，方便数抓图次数

    captured: list[str] = []

    def fake_grab(region):
        captured.append("grabbed")
        # 抓图这一刻窗口必须是藏着的
        assert window.root.deiconified == 0
        return FakeGrabber().grab(region or Region(0, 0, 10, 10))

    app.grabber.grab = fake_grab
    app.perform_select_and_translate()
    wait_for(app, "call")

    assert captured == ["grabbed"]


def test_select_and_translate_cancel_restores_window(monkeypatch):
    """Alt+/ 框选取消：不翻译，窗口也要放回来。"""

    app, window, seen = _app_with_fake_pick(monkeypatch, None)

    app.perform_select_and_translate()

    assert seen == [1]
    assert window.root.deiconified >= 1


def test_select_region_restores_window(monkeypatch):
    """Alt+V：只框选不翻译，框完立刻把窗口放回来。"""

    app, window, seen = _app_with_fake_pick(monkeypatch, Region(100, 200, 400, 300))

    app.perform_select_region()

    assert seen == [1]
    assert window.root.deiconified >= 1
    assert app.config.regions.custom_region() is not None
