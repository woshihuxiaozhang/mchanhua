"""跨线程回归测试：每次取词都会新开工作线程，缓存与控制器必须扛得住。"""

import threading
import time

from mchanhua.app import Application
from mchanhua.config import Config
from mchanhua.geometry import Region
from mchanhua.translate.cache import TranslationCache
from mchanhua.ui.window import drain_queue
from tests.fakes import DecodingTranslator, FakeGrabber, FakeOcr, FakeWindow, wait_for


def test_cache_usable_from_multiple_threads(workdir):
    """曾经这里会报：SQLite objects created in a thread can only be used in that same thread."""

    cache = TranslationCache(workdir / "cache.sqlite")
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            for i in range(20):
                source = f"src-{index}-{i}"
                cache.put(source, f"dst-{index}-{i}", "deepseek-chat", "v2")
                assert cache.get(source, "deepseek-chat", "v2") == f"dst-{index}-{i}"
        except BaseException as exc:  # noqa: BLE001 - 测试里要把异常收集起来
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == [], f"多线程访问缓存出错：{errors}"
    assert cache.count() == 80
    cache.close()


def test_translator_created_once_is_reused_across_worker_threads(workdir):
    """连续两次取词会用到不同工作线程，第二次不应因缓存跨线程而失败。"""

    app = Application(
        Config(),
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=FakeOcr(),
        window=FakeWindow(),
        cache_path=workdir / "cache.sqlite",
    )
    app.translator = _ThreadRecordingTranslator()

    for _ in range(2):
        app.perform_translate(Region(0, 0, 20, 20))
        messages = wait_for(app, "result")
        assert any(message[0] == "result" for message in messages)
        assert not any(message[0] == "status" and "失败" in str(message[1]) for message in messages)

    assert len(app.translator.threads) == 2
    assert len(set(app.translator.threads)) == 2, "两次取词应发生在不同线程上（正是原 bug 的触发条件）"


class _ThreadRecordingTranslator:
    name = "recording"
    warnings: list[str] = []

    def __init__(self) -> None:
        self.threads: list[int] = []

    def translate_lines(self, lines):
        self.threads.append(threading.get_ident())
        return [f"[{text}]" for text in lines]


def test_second_request_while_busy_is_ignored():
    window = FakeWindow()
    app = Application(
        Config(),
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=FakeOcr(),
        window=window,
    )
    app._translate_lock.acquire()  # 模拟"上一次还在处理"
    try:
        app.perform_translate(Region(0, 0, 10, 10))
    finally:
        app._translate_lock.release()
    assert any("已记下这次请求" in text for text in window.statuses)
    assert app._pending_jobs == [("region", Region(0, 0, 10, 10))]


def test_pending_request_runs_after_current_finishes():
    window = FakeWindow()
    app = Application(
        Config(),
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=FakeOcr(),
        window=window,
    )
    app.translator = DecodingTranslator()

    app.perform_translate(Region(0, 0, 40, 40))     # 第一次开始跑
    app.perform_translate(Region(50, 50, 40, 40))   # 立刻再按一次 → 排队
    assert app._pending_jobs

    # 模拟界面轮询：把队列里的消息（包括排队的 "call" 任务）执行掉
    deadline = time.monotonic() + 20
    while len(window.results) < 2 and time.monotonic() < deadline:
        drain_queue(app.queue, window)
        time.sleep(0.05)

    assert len(window.results) == 2, "排队的那次也应该跑完"
    # 默认 screen 模式：整屏识别
    assert app.grabber.requests[-1].to_csv() == "0,0,2560,1440"
