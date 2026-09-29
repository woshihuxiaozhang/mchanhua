"""全屏半透明遮罩，拖拽框选采集区域。"""

from __future__ import annotations

import tkinter as tk

from mchanhua.geometry import Region, logical_to_physical, normalize_drag


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

    state = {"start": None, "rect": None, "result": None}

    def on_press(event) -> None:
        state["start"] = (event.x, event.y)
        if state["rect"] is not None:
            canvas.delete(state["rect"])
            state["rect"] = None

    def on_drag(event) -> None:
        if state["start"] is None:
            return
        if state["rect"] is not None:
            canvas.delete(state["rect"])
        x0, y0 = state["start"]
        state["rect"] = canvas.create_rectangle(x0, y0, event.x, event.y, outline="#5ac8fa", width=2)

    def on_release(event) -> None:
        if state["start"] is None:
            state["result"] = None
            root.destroy()
            return
        x0, y0 = state["start"]
        try:
            logical = normalize_drag(x0, y0, event.x, event.y)
        except ValueError:
            state["result"] = None
            root.destroy()
            return
        state["result"] = logical_to_physical(
            logical,
            (root.winfo_width(), root.winfo_height()),
            physical_screen,
        )
        root.destroy()

    def on_cancel(event=None) -> None:
        state["result"] = None
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    canvas.bind("<ButtonPress-3>", on_cancel)      # 右键也能取消
    canvas.bind("<Escape>", on_cancel)             # 焦点在画布上时也要收得到
    root.bind("<Escape>", on_cancel)

    root.update_idletasks()
    if on_ready is not None:                        # pragma: no cover - 测试用
        on_ready(root)
    if owns_root:
        root.mainloop()
    else:
        root.wait_window()
    return state["result"]
