"""全屏遮罩框选。

游戏（尤其《我的世界》）在前台全屏时会锁住鼠标，而且**一旦失去前台就会弹出游戏菜单**，
正好把要框的字幕挡住。所以这里的遮罩：

1. **不抢前台、不抢焦点**：用 overrideredirect + topmost 只"贴"在画面上，
   游戏不会失焦、不会弹菜单、字幕一直看得见；
2. 输入不靠窗口焦点，而是走**全局键盘钩子** + **全局鼠标状态轮询**；
3. 方向键移动框、Ctrl+方向键缩放、Enter 确认、Backspace 取消
   （这几个键在《我的世界》里默认都没绑定，不会误操作游戏）；
4. 想用鼠标拖框按 M 打开（提示里会说明：会点到底下的窗口，桌面场景再用）。
"""

from __future__ import annotations

import queue
import sys
import time
import tkinter as tk

from mchanhua.geometry import (
    Region,
    logical_to_physical,
    normalize_drag,
    physical_to_logical,
)

KEY_STEP = 20          # 方向键每次移动多少逻辑像素
KEY_STEP_FINE = 4      # 按住 Shift 时的小步长
KEY_MIN_SIZE = 24      # 键盘框的最小边长
DEFAULT_BOX = (520, 260)   # 初始框尺寸（大致能罩住一行字幕）
# 按下鼠标前的这段时间里如果光标一直没动过，就认为鼠标被游戏锁住了
MOUSE_IDLE_LIMIT = 0.6
MOVE_KEYS = {"up": "up", "down": "down", "left": "left", "right": "right"}
CONFIRM_KEYS = {"enter", "return", "kp enter", "kp_enter"}
# 注意：Delete 不在这里——它在"连续框选"里是"撤掉上一个区域"
CANCEL_KEYS = {"backspace", "esc", "escape"}


def _window_size(root: tk.Misc) -> tuple[int, int]:
    width, height = root.winfo_width(), root.winfo_height()
    if width <= 1 or height <= 1:                     # 还没布局好
        return root.winfo_screenwidth(), root.winfo_screenheight()
    return width, height


class RegionPicker:
    """一次框选的完整过程；输入全部来自全局钩子/轮询，不依赖窗口焦点。

    传了 on_accept 就是"连续框选模式"：每次确认都把选区交出去、然后把框复位，
    遮罩不关，可以接着框下一个；Backspace/Esc 才结束。
    """

    def __init__(
        self,
        physical_screen: Region,
        parent: tk.Misc | None = None,
        existing: list[tuple[str, Region]] | None = None,
        on_accept=None,
        on_remove=None,
    ) -> None:
        self.physical_screen = physical_screen
        # 注意：这里必须**共享**同一个列表对象——框选过程中调用方会往里追加新区域，
        # 复制一份的话遮罩就永远看不到刚存的区域（黄线不显示就是这个原因）
        self.existing = existing if existing is not None else []
        self.on_accept = on_accept
        self.on_remove = on_remove
        self.accepted = 0
        self.result: Region | None = None
        self.box: list[int] | None = None              # 逻辑坐标 l, t, r, b
        self.mouse_enabled = True                      # 默认就能拖（和以前一样）
        self.mouse_blocked = False                     # 疑似被游戏锁住
        self._cursor: tuple[int, int] | None = None
        self._cursor_moved_at = time.monotonic()
        self._mouse_down = False
        self._mouse_start: tuple[int, int] | None = None
        self._pool: "queue.Queue[tuple[str, bool, bool]]" = queue.Queue()
        self._hook = None
        self._tick_id = None
        self._closed = False
        self._owned = parent is None
        self.root = tk.Tk() if self._owned else tk.Toplevel(parent)
        self._build()

    # ---- 界面 ----
    def _build(self) -> None:
        width, height = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.overrideredirect(True)               # 无边框、不激活：游戏不会失焦
        self.root.attributes("-topmost", True)
        try:
            self.root.attributes("-alpha", 0.35)
        except tk.TclError:  # pragma: no cover
            pass
        self.root.geometry(f"{width}x{height}+0+0")
        self.root.configure(bg="black")
        self.canvas = tk.Canvas(self.root, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self._hint = self.canvas.create_text(
            12, 10, anchor="nw", fill="#e8e8e8", font=("Microsoft YaHei UI", 13),
            text="",
            tags=("hint",),
        )
        self._set_hint()
        self._draw_existing()
        # 一开始就把框摆在屏幕中间，用户一按热键就能看到
        center_x, center_y = width // 2, height // 2
        half_w, half_h = DEFAULT_BOX[0] // 2, DEFAULT_BOX[1] // 2
        self.box = [center_x - half_w, center_y - half_h, center_x + half_w, center_y + half_h]
        self._draw_box()

    def _draw_box(self) -> None:
        self.canvas.delete("box")
        if self.box is None:
            return
        self.canvas.create_rectangle(*self.box, outline="#5ac8fa", width=3, tags=("box",))

    def _draw_existing(self) -> None:
        """把已经保存的区域画在遮罩上：浅色描边 + 名字，避免重复框。"""

        self.canvas.delete("existing")
        width, height = _window_size(self.root)
        for index, (name, region) in enumerate(self.existing, start=1):
            try:
                logical = physical_to_logical(region, (width, height), self.physical_screen)
            except ValueError:  # pragma: no cover - 越界区域
                continue
            self.canvas.create_rectangle(
                logical.x, logical.y, logical.right, logical.bottom,
                outline="#f2b544", width=2, dash=(6, 4), tags=("existing",),
            )
            self.canvas.create_text(
                logical.x + 4, logical.y + 4, anchor="nw", fill="#f2b544",
                font=("Microsoft YaHei UI", 12), text=f"{index}. {name}", tags=("existing",),
            )

    def _set_hint(self, extra: str = "") -> None:
        lines = [
            "拖动鼠标框选 ｜ 方向键移动框 ｜ Ctrl+方向键缩放 ｜ Enter 确认",
            "按 M 可关掉鼠标拖框（游戏里鼠标被锁时请用方向键）",
        ]
        if self.on_accept:
            lines.append("Backspace / Esc 结束框选")
            if self.on_remove is not None:
                lines.append("Delete 删掉最后一个区域（刚框的、以前的都行）")
        else:
            lines.append("Backspace / Esc 取消")
        if self.existing:
            lines.append(f"目前有 {len(self.existing)} 个区域（黄色虚线框）")
        if extra:
            lines.append(extra)
        self.canvas.itemconfigure(self._hint, text="\n".join(lines))

    # ---- 输入 ----
    def _install_hook(self) -> None:
        """装全局键盘钩子：遮罩没有焦点也能收到按键。"""

        try:
            import keyboard
        except ImportError:  # pragma: no cover - 缺少依赖时退回鼠标模式
            self.mouse_enabled = True
            return

        def on_event(event) -> None:
            if event.event_type != "down":
                return
            try:
                ctrl = bool(keyboard.is_pressed("ctrl"))
                shift = bool(keyboard.is_pressed("shift"))
            except Exception:  # pragma: no cover
                ctrl = shift = False
            self._pool.put((str(event.name).lower(), ctrl, shift))

        try:
            self._hook = keyboard.hook(on_event)
        except Exception:  # pragma: no cover
            self._hook = None

    def _uninstall_hook(self) -> None:
        if self._hook is None:
            return
        try:
            import keyboard

            keyboard.unhook(self._hook)
        except Exception:  # pragma: no cover
            pass
        self._hook = None

    def _tick(self) -> None:
        if self._closed:
            return
        while True:
            try:
                name, ctrl, shift = self._pool.get_nowait()
            except queue.Empty:
                break
            self.handle_key(name, ctrl, shift)
            if self._closed:
                return
        if self.mouse_enabled:
            self.poll_mouse()
        self._tick_id = self.root.after(30, self._tick)

    def handle_key(self, name: str, ctrl: bool = False, shift: bool = False) -> None:
        """处理一次按键（钩子线程排队进来，测试里可以直接调用）。"""

        if self._closed:
            return
        name = (name or "").lower()
        if name in CONFIRM_KEYS:
            self.confirm()
            return
        if name in CANCEL_KEYS:
            self.cancel()
            return
        if name == "m":
            self.mouse_enabled = not self.mouse_enabled
            self._set_hint(
                "鼠标拖框已关闭（只用键盘）" if not self.mouse_enabled else "鼠标拖框已打开"
            )
            return
        if name in ("delete", "kp delete") and self.on_remove is not None:
            self.on_remove()                  # 谁来删由调用方决定（还要同步配置文件）
            self._draw_existing()
            self._set_hint()
            return
        if name not in MOVE_KEYS:
            return
        self.move_box(name, ctrl=ctrl, shift=shift)

    def move_box(self, direction: str, ctrl: bool = False, shift: bool = False) -> None:
        if self.box is None:
            return
        left, top, right, bottom = self.box
        step = KEY_STEP_FINE if shift else KEY_STEP
        if ctrl:                                        # 缩放：动右/下边
            if direction == "right":
                right += step
            elif direction == "left":
                right = max(left + KEY_MIN_SIZE, right - step)
            elif direction == "down":
                bottom += step
            else:
                bottom = max(top + KEY_MIN_SIZE, bottom - step)
        else:
            dx = -step if direction == "left" else step if direction == "right" else 0
            dy = -step if direction == "up" else step if direction == "down" else 0
            left += dx
            right += dx
            top += dy
            bottom += dy
        width, height = _window_size(self.root)
        left = min(max(0, left), max(0, width - KEY_MIN_SIZE))
        right = min(max(left + KEY_MIN_SIZE, right), width)
        top = min(max(0, top), max(0, height - KEY_MIN_SIZE))
        bottom = min(max(top + KEY_MIN_SIZE, bottom), height)
        self.box = [left, top, right, bottom]
        self._draw_box()

    # ---- 鼠标（默认关闭：游戏里左键会打到游戏上）----
    def poll_mouse(self) -> None:
        if sys.platform != "win32":  # pragma: no cover
            return
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            point = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            down = bool(user32.GetAsyncKeyState(0x01) & 0x8000)
        except Exception:  # pragma: no cover
            return
        self.note_cursor(point.x, point.y)
        self.apply_mouse(point.x, point.y, down)

    def note_cursor(self, x: int, y: int) -> None:
        """记住光标位置；位置真的变了就记时间（判断鼠标有没有被游戏锁住）。"""

        if self._cursor != (x, y):
            self._cursor = (x, y)
            self._cursor_moved_at = time.monotonic()
            if self.mouse_blocked:                     # 光标又能动了
                self.mouse_blocked = False
                self._set_hint()

    def apply_mouse(self, x: int, y: int, down: bool) -> None:
        """鼠标状态机（抽出来方便测试）：按下→拖动→松开即确认。"""

        if down and not self._mouse_down:
            # 光标半天没动过 = 鼠标被游戏锁着（点击会打到游戏上），这次不接
            if time.monotonic() - self._cursor_moved_at > MOUSE_IDLE_LIMIT:
                self.mouse_blocked = True
                self._set_hint("鼠标像被游戏锁住了：请用方向键移动框，Enter 确认")
                return
            self._mouse_down = True
            self._mouse_start = (x, y)
            self.box = [x, y, x + 1, y + 1]
            self._draw_box()
            return
        if down and self._mouse_down and self._mouse_start is not None:
            start_x, start_y = self._mouse_start
            self.box = [start_x, start_y, x, y]
            self._draw_box()
            return
        if not down and self._mouse_down:
            self._mouse_down = False
            start = self._mouse_start
            self._mouse_start = None
            if start is None:
                return
            moved = abs(start[0] - x) + abs(start[1] - y)
            if moved < 8:                                # 只是点了一下：不算框
                return
            self.box = [start[0], start[1], x, y]
            self.confirm()

    # ---- 结果 ----
    def confirm(self) -> None:
        if self._closed or self.box is None:
            return
        try:
            logical = normalize_drag(self.box[0], self.box[1], self.box[2], self.box[3])
        except ValueError:
            self.result = None
            self.close()
            return
        region = logical_to_physical(logical, _window_size(self.root), self.physical_screen)
        if self.on_accept is not None:
            # 连续框选：交出去、复位框，遮罩留着继续用
            self.accepted += 1
            self.on_accept(region)
            self._reset_box()
            self._draw_existing()
            self._set_hint()
            return
        self.result = region
        self.close()

    def _reset_box(self) -> None:
        width, height = _window_size(self.root)
        center_x, center_y = width // 2, height // 2
        half_w, half_h = DEFAULT_BOX[0] // 2, DEFAULT_BOX[1] // 2
        self.box = [center_x - half_w, center_y - half_h, center_x + half_w, center_y + half_h]
        self._draw_box()

    def cancel(self) -> None:
        self.result = None
        self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._uninstall_hook()
        if self._tick_id is not None:
            try:
                self.root.after_cancel(self._tick_id)
            except Exception:  # pragma: no cover
                pass
            self._tick_id = None
        try:
            self.root.destroy()
        except Exception:  # pragma: no cover
            pass

    def run(self) -> Region | None:
        self._install_hook()
        self._tick_id = self.root.after(30, self._tick)
        self.root.update_idletasks()
        if self._owned:
            self.root.mainloop()
        else:
            self.root.wait_window()
        return self.result


def pick_region(
    physical_screen: Region,
    parent: tk.Misc | None = None,
    on_ready=None,
    existing: list[tuple[str, Region]] | None = None,
    on_accept=None,
    on_remove=None,
) -> Region | None:
    """弹出遮罩框选，返回物理像素区域。

    取消（Backspace / Esc / 右键）返回 None；on_ready 只在测试里用。
    existing 会把已保存的区域画在遮罩上；给了 on_accept 就是连续框选模式
    （每次确认回调一次、遮罩不关），此时返回值恒为 None。
    """

    picker = RegionPicker(
        physical_screen, parent, existing=existing, on_accept=on_accept, on_remove=on_remove
    )
    if on_ready is not None:                            # pragma: no cover - 测试用
        on_ready(picker)
    return picker.run()
