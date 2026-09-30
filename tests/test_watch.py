"""连续翻译模式（守护选区）：判定逻辑、配置、控制器接线。"""

from __future__ import annotations

import queue
import time

import pytest

from mchanhua.app import Application
from mchanhua.config import (
    Config,
    ConfigError,
    WatchConfig,
    dumps,
    load_config,
    loads,
    save_config,
)
from mchanhua.geometry import Region
from mchanhua.ocr.base import OcrLine, OcrResult
from mchanhua.watch import is_changed, normalize_text, should_request, similarity
from tests.fakes import DecodingTranslator, FakeGrabber, FakeTkRoot, FakeWindow


# ---- 纯逻辑：怎么算"文字变了" ----


def test_normalize_text_drops_whitespace_and_case():
    assert normalize_text(" Steel   Ingot ") == "steelingot"
    assert normalize_text("") == ""
    assert normalize_text(None) == ""


def test_similarity_handles_empty_sides():
    assert similarity("", "") == 1.0
    assert similarity("abc", "") == 0.0
    assert similarity("abc", "abc") == 1.0
    assert 0 < similarity("Steel Ingot", "Steel Ingot!") < 1


def test_is_changed_treats_empty_current_as_no_change():
    assert is_changed("something", "") is False      # 没识别到文字：不算变化
    assert is_changed("", "something") is True       # 第一次拿到内容
    assert is_changed("", "") is False


def test_is_changed_tolerates_ocr_jitter():
    """识别出的字符每次有一点点抖动，不能每次都当成「字幕变了」去发请求。"""

    assert is_changed("Steel Ingot", "Steel lngot", threshold=0.9) is False
    assert is_changed("Steel Ingot", "Iron Nugget", threshold=0.9) is True


def test_should_request_respects_min_interval():
    """内容变了但离上一次请求太近，先攒一攒。"""

    assert should_request("", "hello", seconds_since_last=0.0, min_interval=3.0) is True
    assert should_request("hello", "hello world", seconds_since_last=1.0, min_interval=3.0) is False
    assert should_request("hello", "hello world", seconds_since_last=3.5, min_interval=3.0) is True
    assert should_request("hello", "hello", seconds_since_last=99.0, min_interval=3.0) is False
    assert should_request("hello", "", seconds_since_last=99.0, min_interval=3.0) is False


# ---- 配置 ----


def test_watch_config_round_trip(workdir):
    config = Config()
    config.watch = WatchConfig(
        interval=0.8, min_request_interval=2.5, similarity=0.75, idle_slowdown_after=12
    )

    path = save_config(config, workdir / "config.toml")
    loaded = load_config(path)

    assert loaded.watch == config.watch


def test_watch_section_is_written_and_readable():
    text = dumps(Config())
    assert "[watch]" in text
    assert loads(text).watch == Config().watch
    assert loads("[watch]\ninterval = 2.0\nsimilarity = 0.5\n").watch.interval == 2.0


@pytest.mark.parametrize(
    "text",
    (
        "[watch]\ninterval = 0\n",
        "[watch]\ninterval = -1\n",
        "[watch]\nsimilarity = 1.5\n",
        "[watch]\nmin_request_interval = -0.5\n",
        "[watch]\nidle_slowdown_after = 0\n",
    ),
)
def test_invalid_watch_values_raise(text):
    with pytest.raises(ConfigError):
        loads(text)


def test_watch_hotkey_default_and_overridable():
    assert Config().hotkeys.watch == "alt+c"
    assert loads('[hotkeys]\nwatch = "ctrl+alt+w"\n').hotkeys.watch == "ctrl+alt+w"


# ---- 控制器接线 ----


class DeferredRoot(FakeTkRoot):
    """after 只登记不立刻执行：守护循环的定时器由测试自己驱动，避免递归。"""

    def __init__(self) -> None:
        super().__init__()
        self.scheduled: dict[str, tuple] = {}
        self.cancelled: list[str] = []
        self._next_token = 1

    def after(self, ms: int, func=None, *args):
        if func is None:
            return "after-id"
        token = f"after-{self._next_token}"
        self._next_token += 1
        self.scheduled[token] = (ms, func)
        return token

    def after_cancel(self, token) -> None:
        self.cancelled.append(token)
        self.scheduled.pop(token, None)

    def run_due(self) -> int:
        pending = list(self.scheduled.values())
        self.scheduled.clear()
        for _ms, func in pending:
            func()
        return len(pending)


class MutableOcr:
    """识别结果可以随时改：用来模拟「字幕变了」。"""

    name = "mutable-ocr"

    def __init__(self, lines: list[str]) -> None:
        self.lines = list(lines)
        self.calls = 0

    def recognize(self, image):
        self.calls += 1
        return OcrResult(
            lines=[OcrLine(text=text) for text in self.lines],
            elapsed_ms=3.0,
            backend=self.name,
        )


class FakeHotkeys:
    def __init__(self) -> None:
        self.registered: dict[str, str] = {}
        self.started = 0

    def register(self, action, hotkey, callback) -> None:
        self.registered[action] = hotkey

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        pass


class WatchWindow(FakeWindow):
    """窗口替身 + 能自己跑的 after 定时器。"""

    def __init__(self) -> None:
        super().__init__()
        self.root = DeferredRoot()


def make_app(ocr, *, regions: bool = True) -> Application:
    config = Config()
    # 退出清空区域是给"真人用"的；测试里要留住区域，否则一构造就被清掉了
    config.regions.clear_on_exit = False
    if regions:
        config.regions.set_custom_region(Region(100, 200, 400, 300))
    else:
        config.regions.follow_cursor = None
    app = Application(
        config,
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=ocr,
        window=WatchWindow(),
    )
    app.translator = DecodingTranslator()
    return app


def push_through_window(app, message) -> None:
    """把一条队列消息交给窗口处理（模拟界面 drain 一次）。"""

    box: queue.Queue[tuple] = queue.Queue()
    box.put(message)
    drain = getattr(app.window, "drain", None)
    if drain is not None:
        drain(box)
        return
    from mchanhua.ui.window import drain_queue

    drain_queue(box, app.window)


def probe_once(app) -> None:
    """跑一拍「抓图 + 识别」，并把主线程该做的那部分接着做完。"""

    app._watch_probe()
    from mchanhua.ui.window import drain_queue

    drain_queue(app.queue, app.window)


def wait_result(app, timeout: float = 10.0):
    """等一条 result 消息（顺手把期间的消息交给窗口）。"""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            message = app.queue.get(timeout=0.05)
        except queue.Empty:
            continue
        push_through_window(app, message)
        if message[0] == "result":
            return message[1]
    raise AssertionError("没等到 result 消息")


def wait_for_lock(app, timeout: float = 5.0) -> bool:
    """等上一次翻译把锁放掉（结果消息先到、finally 后跑，中间有个小窗口）。"""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if app._translate_lock.acquire(blocking=False):
            app._translate_lock.release()
            return True
        time.sleep(0.02)
    return False


def settle(app, seconds: float = 0.2) -> None:
    """等一下可能还在跑的翻译线程，再把消息清干净。"""

    time.sleep(seconds)
    from mchanhua.ui.window import drain_queue

    drain_queue(app.queue, app.window)


def test_start_watch_without_any_region_is_refused():
    app = make_app(MutableOcr(["Steel Ingot"]), regions=False)

    assert app.start_watch() is False
    assert app._watch_active is False
    assert any("还没有选区" in text for text in app.window.statuses)
    assert app.grabber.requests == []          # 什么都没抓


def test_start_watch_uses_saved_area_and_lights_up_the_button():
    app = make_app(MutableOcr(["Steel Ingot"]))

    assert app.start_watch() is True

    assert app._watch_active is True
    assert [name for name, _box in app._watch_areas] == ["区域1"]
    assert app.window.watch_states == [True]
    assert any("连续翻译中" in text for text in app.window.statuses)
    assert len(app.window.root.scheduled) == 1        # 已经排好下一拍
    app.stop_watch()


def test_same_text_twice_only_translates_once():
    ocr = MutableOcr(["Steel Ingot"])
    app = make_app(ocr)
    app.start_watch()

    probe_once(app)
    wait_result(app)
    assert wait_for_lock(app)
    first_grabs = len(app.grabber.requests)
    assert first_grabs >= 1
    assert len(app.window.results) == 1

    probe_once(app)                     # 内容完全没变
    settle(app)

    assert ocr.calls == 2               # 该抓还是抓、该识别还是识别
    assert len(app.grabber.requests) > first_grabs
    assert len(app.window.results) == 1  # 但没有再发翻译请求
    assert app._watch_idle_ticks == 1
    app.stop_watch()


def test_changed_text_triggers_another_translation():
    ocr = MutableOcr(["Steel Ingot"])
    app = make_app(ocr)
    app.config.watch.min_request_interval = 0.0        # 去掉限流，只测「变了就翻」
    app.start_watch()

    probe_once(app)
    wait_result(app)
    assert wait_for_lock(app)

    ocr.lines = ["Iron Nugget"]
    probe_once(app)
    wait_result(app)
    assert wait_for_lock(app)

    assert len(app.window.results) == 2
    assert app.window.results[-1].source_lines == ["Iron Nugget"]
    app.stop_watch()


def test_min_interval_throttles_quick_changes():
    """文字变得太快时先攒着：默认最短间隔 3 秒内不重复发请求。"""

    ocr = MutableOcr(["Steel Ingot"])
    app = make_app(ocr)
    app.start_watch()

    probe_once(app)
    wait_result(app)
    assert wait_for_lock(app)

    ocr.lines = ["Iron Nugget"]
    probe_once(app)
    settle(app)

    assert len(app.window.results) == 1
    app.stop_watch()


def test_empty_ocr_result_is_not_a_change():
    ocr = MutableOcr([])
    app = make_app(ocr)
    app.start_watch()

    probe_once(app)
    probe_once(app)
    settle(app)

    assert app.window.results == []
    assert app._watch_last_text == ""
    app.stop_watch()


def test_stop_watch_stops_grabbing_and_cancels_timer():
    app = make_app(MutableOcr(["Steel Ingot"]))
    app.start_watch()
    token = app._watch_after_id
    assert token is not None

    app.stop_watch()

    assert app._watch_active is False
    assert app.window.watch_states == [True, False]
    assert token in app.window.root.cancelled
    assert any("已停止" in text for text in app.window.statuses)

    before = len(app.grabber.requests)
    assert app.window.root.run_due() == 0        # 定时器已取消，没有待跑的回调
    app._watch_tick()                            # 就算被叫到也什么都不做
    assert len(app.grabber.requests) == before


def test_toggle_watch_switches_on_and_off():
    app = make_app(MutableOcr(["Steel Ingot"]))

    app.toggle_watch()
    assert app._watch_active is True

    app.toggle_watch()
    assert app._watch_active is False


def test_watch_tick_skips_when_busy_or_picking():
    app = make_app(MutableOcr(["Steel Ingot"]))
    app.start_watch()
    probes: list[str] = []
    app._watch_probe = lambda: probes.append("probe")

    app._watch_tick()
    assert app._watch_busy is True              # 这一拍还没回来
    deadline = time.monotonic() + 3
    while not probes and time.monotonic() < deadline:
        time.sleep(0.01)
    assert probes == ["probe"]

    app._watch_tick()
    time.sleep(0.1)
    assert probes == ["probe"]                  # 忙的时候不再派活

    app._watch_busy = False
    app._picking = True
    app._watch_tick()
    time.sleep(0.1)
    assert probes == ["probe"]                  # 框选时不掺和
    app._picking = False

    assert app.window.root.scheduled              # 每一拍都会排下一拍
    app.stop_watch()


def test_watch_tick_doubles_interval_after_long_idle():
    app = make_app(MutableOcr(["Steel Ingot"]))
    app.start_watch()
    app.config.watch.interval = 1.0
    app.config.watch.idle_slowdown_after = 3

    app._watch_idle_ticks = 0
    assert app._watch_interval_ms() == 1000
    app._watch_idle_ticks = 3
    assert app._watch_interval_ms() == 2000     # 长时间没变化就降频
    app.stop_watch()


def test_watch_ignores_tiny_ocr_jitter():
    app = make_app(MutableOcr(["Steel Ingot"]))
    app.start_watch()
    probe_once(app)
    wait_result(app)
    assert wait_for_lock(app)

    # 文本只差一个字符：相似度足够高，不算变化
    app._watch_checked(
        "Steel lngot",
        OcrResult(lines=[OcrLine(text="Steel lngot")], elapsed_ms=1.0, backend="x"),
        [],
    )

    assert len(app.window.results) == 1
    assert app._watch_idle_ticks == 1
    app.stop_watch()


def test_watch_probe_failure_does_not_kill_the_loop():
    class BrokenGrabber(FakeGrabber):
        def grab(self, region):
            raise RuntimeError("采集失败")

    app = make_app(MutableOcr(["Steel Ingot"]))
    app.grabber = BrokenGrabber()
    app.start_watch()

    probe_once(app)          # 不该抛异常
    settle(app)

    assert app._watch_active is True
    assert app._watch_busy is False
    assert app.window.results == []
    app.stop_watch()


def test_watch_remembers_last_text_for_next_comparison():
    app = make_app(MutableOcr(["Steel Ingot"]))
    app.config.watch.min_request_interval = 0.0
    app.start_watch()
    probe_once(app)
    wait_result(app)
    assert wait_for_lock(app)

    assert app._watch_last_text == "Steel Ingot"
    assert app._watch_last_request > 0
    app.stop_watch()


def test_watch_hotkey_is_registered():
    app = make_app(MutableOcr(["Steel Ingot"]))
    app.config.hotkeys.watch = "alt+c"
    app.config.hotkeys.quit = ""
    fake = FakeHotkeys()
    app.hotkeys = fake

    app._register_hotkeys()

    assert fake.registered["连续翻译模式"] == "alt+c"
    assert fake.started == 1


def test_request_toggle_watch_enqueues_one_shot_callable():
    app = make_app(MutableOcr(["Steel Ingot"]))

    app.request_toggle_watch()

    kind, payload = app.queue.get_nowait()
    assert kind == "call"
    assert callable(payload)


# ---- 设置窗口 ----


tk = pytest.importorskip("tkinter")


def _settings(config: Config):
    from mchanhua.ui.settings_window import SettingsWindow

    last: Exception | None = None
    for _ in range(2):
        try:
            return SettingsWindow(config)
        except tk.TclError as exc:
            last = exc
            time.sleep(0.2)
    pytest.skip(f"没有可用的图形环境：{last}")  # pragma: no cover


def test_settings_has_watch_hotkey_row():
    from mchanhua.ui.settings_window import HOTKEY_LABELS

    assert ("watch", "连续翻译模式") in HOTKEY_LABELS


def test_settings_watch_page_collects_values():
    window = _settings(Config())
    try:
        assert "连续翻译" in window._pages
        window._vars["watch.interval"].set("0.9")
        window._vars["watch.min_request_interval"].set("2")
        window._vars["watch.similarity"].set("0.8")
        window._vars["watch.idle_slowdown_after"].set("10")
        assert window.validate() == []

        collected = window.collect()
        assert collected.watch.interval == 0.9
        assert collected.watch.min_request_interval == 2.0
        assert collected.watch.similarity == 0.8
        assert collected.watch.idle_slowdown_after == 10
    finally:
        window.root.destroy()


def test_settings_watch_page_rejects_bad_values():
    window = _settings(Config())
    try:
        window._vars["watch.interval"].set("0")
        window._vars["watch.similarity"].set("2")
        window._vars["watch.min_request_interval"].set("abc")
        problems = window.validate()

        assert any("检查间隔" in problem for problem in problems)
        assert any("相似度" in problem for problem in problems)
        assert any("最短翻译间隔" in problem for problem in problems)
    finally:
        window.root.destroy()


def test_settings_watch_values_survive_save(workdir):
    path = save_config(Config(), workdir / "config.toml")
    config = load_config(path)
    window = _settings(config)
    try:
        window._vars["watch.interval"].set("1.5")
        save_config(window.collect(), path)
        assert load_config(path).watch.interval == 1.5
    finally:
        window.root.destroy()
