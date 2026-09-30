"""界面动效：图标、按钮反馈、加载转圈、历史浮层滑动。"""

from __future__ import annotations

import pytest

from mchanhua.config import Config
from mchanhua.ui import icons
from mchanhua.ui.effects import Spinner, attach_feedback, mix, parse_color, shade


# ---- 颜色小工具 ----


def test_parse_and_mix_colors():
    assert parse_color("#1a73e8") == (26, 115, 232)
    assert parse_color("transparent") is None
    assert parse_color("#12345") is None

    assert mix("#000000", "#ffffff", 0.0) == "#000000"
    assert mix("#000000", "#ffffff", 1.0) == "#ffffff"
    assert mix("#000000", "#ffffff", 0.5) == "#808080"
    assert mix("transparent", "#ffffff", 0.2) == "transparent"


def test_shade_lightens_and_darkens():
    assert shade("#ffffff", 0.5) == "#808080"
    assert shade("#808080", 2.0) == "#ffffff"
    assert shade("transparent", 0.5) == "transparent"


def test_spinner_advances_and_wraps():
    spinner = Spinner(("a", "b", "c"))

    assert spinner.frame() == "a"
    assert spinner.advance() == "b"
    assert spinner.advance() == "c"
    assert spinner.advance() == "a"

    spinner.reset()
    assert spinner.frame() == "a"


# ---- 图标 ----


def test_icon_files_are_bundled():
    """按钮上用的图标都要在 assets/icons 里（缺了就退回纯文字，不好看）。"""

    needed = (
        "scan", "crop", "monitor", "sliders", "clock", "check", "bolt",
        "folder", "doc", "trash", "plus", "eye", "pulse", "refresh",
    )
    missing = [name for name in needed if not icons.icon_path(name).exists()]
    assert not missing, f"缺图标文件：{missing}（跑一下 tools/make_icons.py）"
    assert icons.icon_path("scan", accent=True).exists()


def test_icon_returns_none_when_file_missing():
    assert icons.icon("这个图标不存在") is None


def test_icon_kwargs_are_omitted_without_an_icon():
    """回归：customtkinter 里 image=None + compound 会把按钮文字吞掉（按钮变空白框）。"""

    assert icons.icon_kwargs(None) == {}
    assert icons.icon_kwargs("这个图标不存在") == {}
    assert set(icons.icon_kwargs("check")) == {"image", "compound"}


tk = pytest.importorskip("tkinter")


def _window():
    from mchanhua.ui.window import ResultWindow

    last: Exception | None = None
    for _ in range(2):
        try:
            window = ResultWindow(Config())
            window.root.update_idletasks()
            return window
        except tk.TclError as exc:
            last = exc
    pytest.skip(f"没有可用的图形环境：{last}")  # pragma: no cover


def test_buttons_have_icons_and_feedback():
    window = _window()
    try:
        assert window.feedback, "按钮应当挂上反馈"
        assert window.watch_button.cget("image") is not None
        assert window.correction_button.cget("image") is not None

        bar = window.action_bars[0]
        buttons = [child for child in bar.winfo_children()]
        assert len(buttons) == 4
        assert all(button.cget("image") is not None for button in buttons)
    finally:
        window.root.destroy()


def test_settings_buttons_keep_their_text():
    """回归：设置窗口底部「取消」曾经因为 image=None + compound 变成空白按钮。"""

    from mchanhua.ui.settings_window import SettingsWindow

    try:
        settings = SettingsWindow(Config())
    except tk.TclError as exc:  # pragma: no cover
        pytest.skip(f"没有可用的图形环境：{exc}")
    try:
        settings.root.update_idletasks()
        texts = _all_button_texts(settings.card)
        for expected in ("保存并应用", "取消", "打开配置目录", "打开日志目录", "测试连接"):
            assert expected in texts, f"按钮文字不见了：{expected}（现有 {texts}）"
        # 带图标的按钮要真的挂上了图
        with_icon = [button for button in _all_buttons(settings.card)
                     if button.cget("image") is not None]
        assert len(with_icon) >= 5
    finally:
        settings.root.destroy()


def _all_buttons(widget) -> list:
    import customtkinter as ctk

    found = []
    for child in widget.winfo_children():
        if isinstance(child, ctk.CTkButton):
            found.append(child)
        found.extend(_all_buttons(child))
    return found


def _all_button_texts(widget) -> list[str]:
    texts = []
    for button in _all_buttons(widget):
        try:
            texts.append(str(button.cget("text")))
        except Exception:  # pragma: no cover
            continue
    return texts


def test_hover_and_press_animate_button_color():
    """悬停/按下要有过渡：颜色是渐变的，而且最后落在正确颜色上。"""

    from PIL import Image

    import customtkinter as ctk

    window = _window()
    try:
        button = ctk.CTkButton(
            window.card, text="测试", fg_color="#FFFFFF", hover_color="#DCE7FB",
            command=lambda: None,
        )
        feedback = attach_feedback(button)

        feedback._on_enter()
        assert button.cget("fg_color") == feedback.hover        # 即时执行 → 一步到位
        feedback._on_press()
        assert button.cget("fg_color") == feedback.pressed
        feedback._on_release()
        assert button.cget("fg_color") == feedback.hover
        feedback._on_leave()
        assert button.cget("fg_color") == feedback.base
    finally:
        window.root.destroy()


def test_busy_shows_spinner_and_progress_bar():
    window = _window()
    try:
        window.set_status("正在采集识别喵…")
        assert window.progress.winfo_manager() == ""            # 空闲时不占地方
        assert window.status_text() == "正在采集识别喵…"

        window.set_busy(True)
        assert window.progress.winfo_manager() == "pack"
        assert window.status.cget("text").startswith(window.spinner.frame())
        assert window.status_text() == "正在采集识别喵…"         # 原文案不变，方便测试/排查

        first = window.spinner.frame()
        window.on_poll()                                        # 每次 poll 走一帧
        assert window.spinner.frame() != first

        window.set_busy(False)
        assert window.progress.winfo_manager() == ""
        assert window.status.cget("text") == "正在采集识别喵…"
    finally:
        window.root.destroy()


def test_busy_message_from_queue_reaches_the_window():
    """控制器用 ("busy", True/False) 消息控制转圈，不用直接碰 Tk。"""

    import queue as queue_module

    from mchanhua.ui.window import drain_queue

    window = _window()
    try:
        box: queue_module.Queue[tuple] = queue_module.Queue()
        box.put(("busy", True))
        drain_queue(box, window)
        assert window.busy is True and window.progress.winfo_manager() == "pack"

        box.put(("busy", False))
        drain_queue(box, window)
        assert window.busy is False and window.progress.winfo_manager() == ""
    finally:
        window.root.destroy()


def test_history_panel_slides_in_to_the_final_position():
    window = _window()
    try:
        import time

        from customtkinter import ScalingTracker

        from mchanhua.ui.window import HISTORY_PANEL_RIGHT

        window.toggle_history()
        assert window.history_panel.winfo_manager() == "place"

        # 滑动是几步 after 回调：跑几轮事件循环让它走完
        deadline = time.monotonic() + 2.0
        scaling = float(ScalingTracker.get_window_dpi_scaling(window.root)) or 1.0
        gap = None
        while time.monotonic() < deadline:
            window.root.update()
            panel_right = window.history_panel.winfo_x() + window.history_panel.winfo_width()
            gap = window.root.winfo_width() - panel_right
            if abs(gap - round(HISTORY_PANEL_RIGHT * scaling)) <= 2:
                break
            time.sleep(0.02)

        # 滑完停在离窗口右边 10 逻辑像素的位置（原来是直接"闪现"出来的）
        assert gap is not None and abs(gap - round(HISTORY_PANEL_RIGHT * scaling)) <= 2
    finally:
        window.root.destroy()
