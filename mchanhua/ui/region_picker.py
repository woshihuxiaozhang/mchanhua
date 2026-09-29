"""全屏半透明遮罩，拖拽框选采集区域。

游戏（尤其《我的世界》这类第一人称）在前台全屏时会把鼠标"锁"住：
系统光标被固定在准心位置、移动全被游戏吃掉，遮罩上根本拖不动。
所以这里做两件事：
1. 弹出时用 Win32 抢前台 + 解除光标裁剪，游戏失焦后会把鼠标交还系统；
2. 仍然提供方向盘：方向键移动框、Ctrl+方向键缩放、Enter 确认、Esc 取消。
"""

from __future__ import annotations

import tkinter as tk

from mchanhua.geometry import Region, logical_to_physical, normalize_drag

KEY_STEP = 20          # 方向键每次移动多少逻辑像素
KEY_STEP_FINE = 4      # 按住 Shift 时的小步长
KEY_MIN_SIZE = 24      # 键盘框的最小边长
DEFAULT_BOX = (400, 240)   # 键盘框的初始尺寸


def take_foreground(window: tk.Misc) -> None:
    """把窗口顶到最前台，并解除游戏设置的光标裁剪区域。"""

    import sys

    if sys.platform != "win32":  # pragma: no cover - 目前只发布 Windows
        return
    try:
        import ctypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        hwnd = int(window.winfo_id())
        # Windows 只让"刚有输入"的进程抢前台：先喷一下 Alt 解锁
        VK_MENU, KEYEVENTF_KEYUP = 0x12, 0x0002
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        user32.ClipCursor(None)          # 游戏常把光标裁在窗口内，解除它
    except Exception:  # pragma: no cover - 失败也不影响后面的键盘框选
        pass


def pick_region(
    physical_screen: Region,
    parent: tk.Misc | None = None,
    on_ready=None,
) -> Region | None:
    """弹出遮罩让用户拖拽选择，返回物理像素区域；按 Esc / 右键 / 点击不拖拽都会取消。

    on_ready 只在测试里用（拿到遮罩窗口的引用去模拟按键），正常调用不用传。
    """

    owns_root = parent is None
    root = tk.Tk() if owns_root else tk.Toplevel(parent)
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    root.lift()                       # 盖在翻译小窗上面（小窗也是置顶的）
    try:
        root.attributes("-alpha", 0.35)
    except tk.TclError:  # pragma: no cover
        pass
    root.configure(bg="black")
    canvas = tk.Canvas(root, bg="black", highlightthickness=0, cursor="crosshair")
    canvas.pack(fill="both", expand=True)

    # 独占输入 + 抢键盘焦点：不然按 Esc 事件根本送不到遮罩上（以前就是这个问题）
    try:
        root.grab_set()
    except tk.TclError:  # pragma: no cover
        pass
    try:
        root.focus_force()
    except tk.TclError:  # pragma: no cover
        pass
    take_foreground(root)              # 让游戏失焦，把鼠标还给系统

    state = {"start": None, "rect": None, "result": None}
    keyboard = {"box": None}           # 键盘框（逻辑坐标 l, t, r, b）

    def screen_size() -> tuple[int, int]:
        width, height = root.winfo_width(), root.winfo_height()
        if width <= 1 or height <= 1:                     # 还没布局好
            return root.winfo_screenwidth(), root.winfo_screenheight()
        return width, height

    def draw_rect(rect) -> None:
        if state["rect"] is not None:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(*rect, outline="#5ac8fa", width=2)

    def accept(rect) -> None:
        """把逻辑框转成物理选区并收工。"""

        try:
            logical = normalize_drag(rect[0], rect[1], rect[2], rect[3])
        except ValueError:
            state["result"] = None
            root.destroy()
            return
        state["result"] = logical_to_physical(logical, screen_size(), physical_screen)
        root.destroy()

    def on_press(event) -> None:
        state["start"] = (event.x, event.y)
        if state["rect"] is not None:
            canvas.delete(state["rect"])
            state["rect"] = None

    def on_drag(event) -> None:
        if state["start"] is None:
            return
        x0, y0 = state["start"]
        draw_rect((x0, y0, event.x, event.y))

    def on_release(event) -> None:
        if state["start"] is None:
            state["result"] = None
            root.destroy()
            return
        x0, y0 = state["start"]
        accept((x0, y0, event.x, event.y))

    def on_cancel(event=None) -> None:
        state["result"] = None
        root.destroy()

    def on_key(event) -> str:
        """鼠标被游戏锁住时的备用方案：方向键移动框。"""

        key = event.keysym
        if key not in ("Up", "Down", "Left", "Right"):
            return ""
        if keyboard["box"] is None:
            width, height = screen_size()
            center_x, center_y = width // 2, height // 2
            half_w, half_h = DEFAULT_BOX[0] // 2, DEFAULT_BOX[1] // 2
            keyboard["box"] = [
                center_x - half_w, center_y - half_h, center_x + half_w, center_y + half_h
            ]
        left, top, right, bottom = keyboard["box"]
        step = KEY_STEP_FINE if event.state & 0x0001 else KEY_STEP     # Shift = 精细
        if event.state & 0x0004:                                       # Ctrl = 缩放
            if key == "Right":
                right += step
            elif key == "Left":
                right = max(left + KEY_MIN_SIZE, right - step)
            elif key == "Down":
                bottom += step
            else:
                bottom = max(top + KEY_MIN_SIZE, bottom - step)
        else:
            dx = -step if key == "Left" else step if key == "Right" else 0
            dy = -step if key == "Up" else step if key == "Down" else 0
            left += dx
            right += dx
            top += dy
            bottom += dy
        width, height = screen_size()
        left = min(max(0, left), width - KEY_MIN_SIZE)
        right = min(max(left + KEY_MIN_SIZE, right), width)
        top = min(max(0, top), height - KEY_MIN_SIZE)
        bottom = min(max(top + KEY_MIN_SIZE, bottom), height)
        keyboard["box"] = [left, top, right, bottom]
        draw_rect(keyboard["box"])
        return "break"

    def on_confirm(event=None) -> str:
        if keyboard["box"] is not None:
            accept(keyboard["box"])
        return "break"

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    canvas.bind("<ButtonPress-3>", on_cancel)      # 右键也能取消
    canvas.bind("<Escape>", on_cancel)             # 焦点在画布上时也要收得到
    root.bind("<Escape>", on_cancel)
    root.bind("<Key>", on_key)
    canvas.bind("<Key>", on_key)
    root.bind("<Return>", on_confirm)
    root.bind("<KP_Enter>", on_confirm)
    canvas.bind("<Return>", on_confirm)

    hint = canvas.create_text(
        10, 10, anchor="nw", fill="#e6e6e6", font=("Microsoft YaHei UI", 13),
        text="拖动框选 ｜ Enter 确认 ｜ Esc 取消\n"
             "鼠标被游戏锁住时：方向键移动框、Ctrl+方向键缩放、Enter 确认",
    )
    canvas.tag_raise(hint)

    root.update_idletasks()
    if on_ready is not None:                        # pragma: no cover - 测试用
        on_ready(root)
    if owns_root:
        root.mainloop()
    else:
        root.wait_window()
    return state["result"]
