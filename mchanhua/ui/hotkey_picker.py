"""「选择按键」对话框：按住键盘上的一个或多个键，取这一轮按过的最长组合。

比"在输入框里直接按"更靠得住：
- 只按修饰键（Ctrl+Alt）也能选出来，而按键事件里修饰键本身是不会有别的键的；
- 界面实时显示按住了哪些键，按全了没有一眼就看得出来；
- 录制的这段时间会把全局热键暂停，免得一边录一边把翻译触发了。
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

import customtkinter as ctk

from mchanhua.ui.hotkey_capture import ComboTracker, describe_hotkey

CARD = "#FFFFFF"
FIELD = "#F5F5F5"
LINE = "#E8E8E8"
TEXT = "#1B1B1B"
LABEL = "#8A8A8A"
BLUE = "#1A73E8"
BLUE_SOFT = "#E8F0FE"


class HotkeyPicker:
    """模态小窗：确定返回热键串，清空返回空字符串，取消返回 None。"""

    def __init__(
        self,
        parent: tk.Misc,
        title: str = "选择热键",
        initial: str = "",
        on_pause: Callable[[], None] | None = None,
        on_resume: Callable[[], None] | None = None,
    ) -> None:
        self.tracker = ComboTracker()
        self.initial = (initial or "").strip()
        self.result: str | None = None
        self._closed = False
        self.on_pause = on_pause
        self.on_resume = on_resume

        family = "Microsoft YaHei UI"
        self.f_label = ctk.CTkFont(family=family, size=13)
        self.f_big = ctk.CTkFont(family=family, size=22)
        self.f_small = ctk.CTkFont(family=family, size=11)

        self.root = ctk.CTkToplevel(parent)
        self.root.title(title)
        self.root.geometry("440x260")
        self.root.resizable(False, False)
        self.root.configure(fg_color="#F7F7F7")
        card = ctk.CTkFrame(self.root, corner_radius=12, fg_color=CARD,
                            border_width=1, border_color=LINE)
        card.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(card, text="按住你想用的按键组合喵", font=self.f_label,
                     text_color=TEXT).pack(anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(
            card,
            text="只按修饰键（如 Ctrl+Alt）也可以，再加别的键（如 Ctrl+Alt+Q）也行喵～"
                 "松开后点「确定」就好，Esc 取消。",
            font=self.f_small, text_color=LABEL, justify="left", wraplength=380,
        ).pack(anchor="w", padx=16)

        holder = ctk.CTkFrame(card, corner_radius=8, fg_color=FIELD,
                              border_width=1, border_color=LINE)
        holder.pack(fill="x", padx=16, pady=(12, 6))
        self.display = ctk.CTkLabel(holder, text=describe_hotkey(self.initial) or "（还没按到键喵）",
                                    font=self.f_big, text_color=TEXT)
        self.display.pack(pady=14)

        self.hint = ctk.CTkLabel(card, text="", font=self.f_small, text_color=LABEL)
        self.hint.pack(anchor="w", padx=16)

        row = ctk.CTkFrame(card, corner_radius=0, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(10, 14))
        self._button(row, "确定", self._accept, primary=True, width=90).pack(side="left")
        self._button(row, "重来", self._reset, width=70).pack(side="left", padx=8)
        self._button(row, "清空（不注册）", self._clear, width=120).pack(side="left")
        self._button(row, "取消", self._cancel, width=70).pack(side="right")

        self.root.bind("<KeyPress>", self._on_press)
        self.root.bind("<KeyRelease>", self._on_release)
        self.root.bind("<Escape>", lambda _event: self._cancel())
        self.root.bind("<Return>", lambda _event: self._accept())
        self.root.protocol("WM_DELETE_WINDOW", self._cancel)
        self.root.transient(parent)
        self.root.grab_set()
        self.root.after(60, self._focus)

    # ---- 小部件 ----
    def _button(self, parent, text: str, command, primary: bool = False, width: int = 80):
        return ctk.CTkButton(
            parent, text=text, command=command, height=34, corner_radius=6,
            font=self.f_label, width=width,
            fg_color=BLUE_SOFT if primary else CARD,
            hover_color="#DCE7FB" if primary else FIELD,
            text_color=BLUE if primary else "#3C4043",
            border_width=0 if primary else 1, border_color="#E0E0E0",
        )

    def _focus(self) -> None:
        try:
            self.root.focus_force()
        except tk.TclError:  # pragma: no cover - 窗口已销毁
            pass

    # ---- 按键 ----
    def _on_press(self, event) -> str:
        if (event.keysym or "").lower() == "escape":
            return "break"                     # 交给 Esc 绑定处理
        self.tracker.press(event.keysym)
        self._refresh()
        return "break"                          # 别让按键跑进输入框

    def _on_release(self, event) -> str:
        self.tracker.release(event.keysym)
        self._refresh()
        return "break"

    def _refresh(self) -> None:
        candidate = self.tracker.candidate
        pressed = self.tracker.pressed
        if candidate:
            self.display.configure(text=describe_hotkey(candidate))
        else:
            self.display.configure(text="（还没按到键喵）")
        if pressed:
            self.hint.configure(text="按着呐：" + describe_hotkey("+".join(pressed)))
        elif candidate:
            self.hint.configure(text="松开后点「确定」就好喵")
        else:
            self.hint.configure(text="")

    def _reset(self) -> None:
        self.tracker.reset()
        self._refresh()

    # ---- 结果 ----
    def _accept(self) -> None:
        value = self.tracker.candidate or self.initial
        if not value:
            self.hint.configure(text="还没按到任何键喵～按住想用的按键组合")
            return
        self.result = value
        self._close()

    def _clear(self) -> None:
        self.result = ""
        self._close()

    def _cancel(self) -> None:
        self.result = None
        self._close()

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.root.grab_release()
        except tk.TclError:  # pragma: no cover
            pass
        self.root.destroy()

    def show(self) -> str | None:
        """弹出对话框并等它关闭，返回热键串（空串 = 不注册）/ None = 没改。"""

        if self.on_pause is not None:
            try:
                self.on_pause()
            except Exception:  # pragma: no cover - 暂停失败不该拦住录制
                pass
        try:
            if not self._closed:        # 已经关掉的窗口不能再 wait_window（会一直等）
                self.root.wait_window()
        finally:
            if self.on_resume is not None:
                try:
                    self.on_resume()
                except Exception:  # pragma: no cover
                    pass
        return self.result


def pick_hotkey(
    parent: tk.Misc,
    title: str = "选择热键",
    initial: str = "",
    on_pause: Callable[[], None] | None = None,
    on_resume: Callable[[], None] | None = None,
) -> str | None:
    picker = HotkeyPicker(parent, title=title, initial=initial, on_pause=on_pause, on_resume=on_resume)
    return picker.show()
