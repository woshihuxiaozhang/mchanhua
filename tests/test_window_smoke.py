"""界面冒烟测试：确认 Tk 窗口能创建、更新、销毁（无图形环境时跳过）。"""

import pytest

from mchanhua.config import Config
from mchanhua.pipeline import PipelineResult
from mchanhua.ui.window import drain_queue, resolve_position

tk = pytest.importorskip("tkinter")


def _window():
    from mchanhua.ui.window import ResultWindow

    try:
        return ResultWindow(Config())
    except tk.TclError as exc:  # pragma: no cover - 无显示环境
        pytest.skip(f"没有可用的图形环境：{exc}")


def test_window_renders_results_and_dispatches_queue_messages():
    """一个用例里只创建一次 Tk 根窗口：同一进程反复 Tk()/destroy() 在部分环境会报 TclError。"""

    import queue

    window = _window()
    try:
        window.set_status("测试状态")
        window.show_source(["Steel Ingot"], 12.0)
        window.show_result(
            PipelineResult(
                source_lines=["Steel Ingot"],
                output_lines=["钢锭"],
                ocr_ms=12.0,
                translate_ms=345.0,
                ocr_backend="fake",
            )
        )
        window.root.update()
        assert window.target.get("1.0", "end").strip() == "钢锭"
        assert "钢锭" in window.status.cget("text") or "OCR" in window.status.cget("text")
        window._clear()
        assert window.target.get("1.0", "end").strip() == ""
        messages: queue.Queue[tuple] = queue.Queue()
        messages.put(("status", "来自队列"))
        messages.put(("result", PipelineResult(source_lines=["a"], output_lines=["b"])))
        window.drain(messages)
        window.root.update()
        assert window.target.get("1.0", "end").strip() == "b"
        # 结果消息会覆盖状态栏，最终显示的是耗时摘要
        assert "OCR" in window.status.cget("text")
    finally:
        window.root.destroy()


class _RecordingSink:
    def __init__(self) -> None:
        self.statuses: list[str] = []
        self.sources: list[list[str]] = []
        self.results: list[PipelineResult] = []

    def set_status(self, text: str) -> None:
        self.statuses.append(text)

    def show_source(self, lines, elapsed_ms) -> None:
        self.sources.append(list(lines))

    def show_result(self, result: PipelineResult) -> None:
        self.results.append(result)


def test_drain_queue_executes_callables_and_is_bounded():
    """回归测试：任务如果又往队列里补消息，drain 也必须返回（不能无限自喂）。"""

    import queue

    messages: queue.Queue[tuple] = queue.Queue()
    sink = _RecordingSink()
    executions: list[int] = []

    def re_enqueue() -> None:
        executions.append(1)
        messages.put(("call", re_enqueue))  # 故意制造"自己喂自己"

    messages.put(("status", "开始"))
    messages.put(("call", re_enqueue))

    handled = drain_queue(messages, sink, max_messages=10)

    assert handled == 10          # 有上限，不会卡死
    assert sink.statuses == ["开始"]
    assert len(executions) == 9   # 其余配额被"自喂"的消息吃掉


def test_multiline_result_switches_to_compare_mode():
    """全屏/多行结果自动切成双栏对照。"""

    window = _window()
    try:
        assert window.compare_mode is False
        window.show_result(
            PipelineResult(
                source_lines=["a", "b", "c", "d"],
                output_lines=["甲", "乙", "丙", "丁"],
            )
        )
        assert window.compare_mode is True
        window.set_compare_mode(False)
        assert window.compare_mode is False
    finally:
        window.root.destroy()


def test_window_stays_on_screen_and_buttons_fit():
    """回归测试：按钮把窗口顶宽后会跑到屏幕外，右边按钮被切掉。"""

    window = _window()
    try:
        # 只刷新布局，不跑 after 回调（上一个用例销毁窗口后仍有待执行的回调）
        window.root.update_idletasks()
        ui = window.config.ui
        # 布局自己需要的宽度不能超过配置宽度，否则窗口会被撑到屏幕外
        assert window.root.winfo_reqwidth() <= ui.width
        width, height = window._place_window()
        screen_w = window.root.winfo_screenwidth()
        screen_h = window.root.winfo_screenheight()
        x, y = resolve_position(ui, (screen_w, screen_h), (width, height))
        assert x + width <= screen_w
        assert y + height <= screen_h
    finally:
        window.root.destroy()
