"""界面冒烟测试：确认 Tk 窗口能创建、更新、销毁（无图形环境时跳过）。"""

import pytest

from mchanhua.config import Config
from mchanhua.pipeline import PipelineResult

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
