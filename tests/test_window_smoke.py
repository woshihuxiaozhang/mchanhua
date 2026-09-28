"""界面冒烟测试：确认 Tk 窗口能创建、更新、销毁（无图形环境时跳过）。"""

import time
from datetime import datetime

import pytest

from mchanhua.config import Config
from mchanhua.history import TranslationHistory
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
    """内框改成直角；标题行只留「文 / 取词翻译 / 服务 / 时钟」，没有重复的关闭按钮。"""

    window = _window()
    try:
        window.root.update_idletasks()
        assert int(window.card.cget("corner_radius")) == 0
        title_row = window.card.winfo_children()[0]
        texts = [child.cget("text") for child in title_row.winfo_children()]
        assert texts == ["文", "取词翻译", window._provider_label(), "🕘"]
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


def test_notice_clears_previous_result_and_shows_hint():
    """提示消息（例如"选区内没有识别到文字"）要清掉上次的译文，别让人误会。"""

    window = _window()
    try:
        window.show_result(
            PipelineResult(source_lines=["Steel Ingot"], output_lines=["钢锭"])
        )
        window.root.update_idletasks()
        assert window.target.get("1.0", "end").strip() == "钢锭"

        window.show_notice("选区内没有识别到文字")
        window.root.update_idletasks()

        assert window.target.get("1.0", "end").strip() == ""
        assert window.source.get("1.0", "end").strip() == ""
        assert window.status_text() == "选区内没有识别到文字"
    finally:
        window.root.destroy()


def test_poll_arms_next_tick_before_doing_the_work():
    """回归：弹框选遮罩时 drain 会阻塞，心跳必须在此之前就排好下一次。"""

    import queue as queue_module

    from mchanhua.ui.window import ResultWindow

    order: list[str] = []

    class _FakeRoot:
        def after(self, _ms, _fn) -> None:
            order.append("after")

    class _FakeSink:
        root = _FakeRoot()

        def on_poll(self) -> None:
            order.append("beat")

        def drain(self, _queue, _max_messages=50) -> int:
            order.append("drain")
            return 0

        poll = ResultWindow.poll

    _FakeSink().poll(queue_module.Queue(), 60)

    assert order == ["after", "beat", "drain"]


# ---- 历史翻译（时钟按钮 + 窗内折叠面板）----


def test_history_button_is_a_clock_icon():
    window = _window()
    try:
        assert window.history_button.cget("text") == "🕘"
    finally:
        window.root.destroy()


def test_clock_button_expands_history_inside_the_same_window():
    """点时钟：在当前窗口里展开历史面板，不另开窗口。"""

    history = TranslationHistory()
    history.add(["Steel Ingot"], ["钢锭"], at=datetime(2026, 9, 28, 14, 35))
    window = _window()
    try:
        window.history_provider = history.recent
        window.root.update_idletasks()
        before = window._place_window()[1]
        idle_status = window.status_text()                   # 打开前的状态（"待取词…"）
        assert window.history_open is False
        assert window.history_panel.winfo_manager() == ""    # 初始不占位置

        window.toggle_history()
        window.root.update_idletasks()

        assert window.history_open is True
        assert window.history_panel.winfo_manager() == "pack"
        assert window.target.winfo_manager() == ""           # 译文区让位给历史
        # 面板就是窗口内容的一部分：铺满、没有自己的边框和底色
        pack_info = window.history_panel.pack_info()
        assert pack_info["fill"] == "both"
        assert int(window.history_panel.cget("border_width")) == 0
        assert int(window.history_panel.cget("corner_radius")) == 0
        text = window.history_text.get("1.0", "end")
        assert "[14:35]" in text and "钢锭" in text and "Steel Ingot" in text
        assert window._place_window()[1] >= before          # 窗口够高放得下面板
        assert len(window.root.winfo_children()) >= 1       # 没有另开窗口

        window.toggle_history()
        window.root.update_idletasks()
        assert window.history_open is False
        assert window.history_panel.winfo_manager() == ""
        assert window.target.winfo_manager() == "pack"
        assert window.status_text() == idle_status           # 状态栏不残留历史提示
    finally:
        window.root.destroy()


def test_new_result_closes_history_panel():
    window = _window()
    try:
        window.toggle_history()
        assert window.history_open is True

        window.show_result(PipelineResult(source_lines=["a"], output_lines=["甲"]))

        assert window.history_open is False
        assert window.target.get("1.0", "end").strip() == "甲"
    finally:
        window.root.destroy()


def test_history_message_updates_the_panel():
    import queue as queue_module

    history = TranslationHistory()
    history.add(["Redstone"], ["红石"], at=datetime(2026, 9, 28, 8, 3))
    window = _window()
    try:
        messages: queue_module.Queue = queue_module.Queue()
        messages.put(("history", history.recent()))
        window.drain(messages)
        window.root.update_idletasks()
        text = window.history_text.get("1.0", "end")
        assert "[08:03]" in text and "红石" in text
    finally:
        window.root.destroy()
