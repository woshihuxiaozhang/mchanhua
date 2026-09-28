"""「选择按键」对话框：按住一个或多个键，点确定写回热键。"""

import time

import pytest

tk = pytest.importorskip("tkinter")


def _picker(initial: str = "", parent=None):
    import tkinter as tk_module

    from mchanhua.ui.hotkey_picker import HotkeyPicker

    owns = parent is None
    root = parent or tk_module.Tk()
    root.withdraw()
    try:
        picker = HotkeyPicker(root, initial=initial)
    except tk.TclError as exc:  # pragma: no cover - 无图形环境
        root.destroy()
        pytest.skip(f"没有可用的图形环境：{exc}")
    _settle(picker)
    return picker, root, owns


def _settle(picker, timeout: float = 3.0) -> None:
    """等 customtkinter 把窗口 withdraw/deiconify 那一轮跑完，按键事件才送得进去。"""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        picker.root.update()
        if picker.root.winfo_ismapped():
            return
        time.sleep(0.02)


def _press(picker, *keysyms: str) -> None:
    for keysym in keysyms:
        picker.root.event_generate("<KeyPress>", keysym=keysym)
    picker.root.update()


def test_picker_returns_modifier_only_combo():
    picker, root, owns = _picker()
    try:
        _press(picker, "Control_L", "Alt_L")
        picker._accept()
        assert picker.result == "ctrl+alt"
    finally:
        if owns:
            root.destroy()


def test_picker_returns_three_key_combo():
    picker, root, owns = _picker()
    try:
        _press(picker, "Control_L", "Alt_L", "q")
        picker._accept()
        assert picker.result == "ctrl+alt+q"
    finally:
        if owns:
            root.destroy()


def test_picker_clear_returns_empty_string():
    picker, root, owns = _picker(initial="alt+s")
    try:
        picker._clear()
        assert picker.result == ""
    finally:
        if owns:
            root.destroy()


def test_picker_cancel_returns_none():
    picker, root, owns = _picker(initial="alt+s")
    try:
        picker._cancel()
        assert picker.result is None
    finally:
        if owns:
            root.destroy()


def test_picker_without_keys_keeps_initial_value():
    """没按任何键就点确定：保留原来的热键，而不是清掉。"""

    picker, root, owns = _picker(initial="alt+v")
    try:
        picker._accept()
        assert picker.result == "alt+v"
    finally:
        if owns:
            root.destroy()


def test_picker_pauses_and_resumes_hotkeys():
    """对话框打开期间暂停全局热键，关闭后恢复（哪怕中途报错）。"""

    calls: list[str] = []
    picker, root, owns = _picker()
    try:
        picker.on_pause = lambda: calls.append("pause")
        picker.on_resume = lambda: calls.append("resume")
        picker.root.after(50, picker._cancel)     # 模拟用户点「取消」
        assert picker.show() is None
        assert calls == ["pause", "resume"]
    finally:
        if owns:
            root.destroy()
