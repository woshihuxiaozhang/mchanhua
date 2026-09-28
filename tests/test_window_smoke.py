"""界面冒烟测试：确认 Tk 窗口能创建、更新、销毁（无图形环境时跳过）。"""

import time

import pytest

from mchanhua.config import Config
from mchanhua.pipeline import PipelineResult
from mchanhua.ui.window import drain_queue, resolve_position

tk = pytest.importorskip("tkinter")


def _window():
    from mchanhua.ui.window import ResultWindow

    last: Exception | None = None
    for _ in range(2):      # 这台机器上 Tk 初始化偶尔读不到 ttk 脚本，重试一次更稳
        try:
            return ResultWindow(Config())
        except tk.TclError as exc:
            last = exc
            time.sleep(0.2)
    pytest.skip(f"没有可用的图形环境：{last}")  # pragma: no cover


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
        from customtkinter import ScalingTracker

        scaling = float(ScalingTracker.get_window_dpi_scaling(window.root)) or 1.0
        # 布局自己需要的宽度（换算回逻辑像素）不能超过配置宽度，否则窗口会被撑到屏幕外
        assert window.root.winfo_reqwidth() / scaling <= ui.width
        width, height = window._place_window()
        screen_w = window.root.winfo_screenwidth()
        screen_h = window.root.winfo_screenheight()
        x, y = resolve_position(ui, (screen_w, screen_h), (width, height))
        assert x + width <= screen_w
        assert y + height <= screen_h
    finally:
        window.root.destroy()


def test_window_height_hugs_content():
    """回归测试：小窗底部不该留空白——高度按内容算（配置里的高度只当下限）。"""

    window = _window()
    try:
        window.root.update_idletasks()
        from customtkinter import ScalingTracker

        scaling = float(ScalingTracker.get_window_dpi_scaling(window.root)) or 1.0
        needed = int(window.root.winfo_reqheight() / scaling + 0.5)
        width, height = window._place_window()
        # 高度只允许比内容多出"配置下限"那一部分，且不能凭空多出一大截
        assert height / scaling <= max(needed, window.config.ui.height) + 1
        # 内容比配置下限高时，窗口就贴内容
        assert window.card.cget("border_width") == 0        # 白卡片不再画外框
    finally:
        window.root.destroy()


def test_collapsing_shrinks_window():
    """折叠后窗口要跟着变矮（以前会留着原来那块空白）。"""

    window = _window()
    try:
        window.root.update_idletasks()
        before = window._place_window()[1]
        window.toggle_collapsed()
        window.root.update_idletasks()
        after = window._place_window()[1]
        assert after < before
    finally:
        window.root.destroy()


def test_card_has_square_corners_and_no_extra_buttons():
    """内框改成直角；最小化和关闭不再重复放在卡片里（标题栏已经有了）。"""

    window = _window()
    try:
        window.root.update_idletasks()
        assert int(window.card.cget("corner_radius")) == 0
        title_row = window.card.winfo_children()[0]
        texts = [child.cget("text") for child in title_row.winfo_children()]
        assert texts == ["文", "取词翻译", window._provider_label()]
        assert "✕" not in texts and "—" not in texts
    finally:
        window.root.destroy()


def test_window_is_compact():
    """窗口高度要贴着内容（曾经多出一大块空白）。"""

    window = _window()
    try:
        window.root.update_idletasks()
        width, height = window._place_window()
        assert height <= 240          # 物理像素；改之前是 268 起步
    finally:
        window.root.destroy()


def test_light_title_bar_helper_does_not_raise():
    from mchanhua.ui.titlebar import use_light_title_bar

    window = _window()
    try:
        assert use_light_title_bar(window.root) in (True, False)   # 非 Windows 返回 False
    finally:
        window.root.destroy()


def test_text_area_grows_with_result_and_shrinks_on_clear():
    """译文/原文区跟着内容长高：没结果时收成一行，窗口不留大片空白。"""

    window = _window()
    try:
        window.root.update_idletasks()
        idle = window._place_window()[1]

        window.show_result(
            PipelineResult(source_lines=["a", "b", "c"], output_lines=["甲", "乙", "丙"])
        )
        window.root.update_idletasks()
        grown = window._place_window()[1]
        assert grown > idle

        window._clear()
        window.root.update_idletasks()
        assert window._place_window()[1] <= idle + 1
    finally:
        window.root.destroy()
