"""结果显示小窗。

设计目标：不覆盖游戏画面，只在旁边显示译文；置顶、半透明、可拖动。
"""

from __future__ import annotations

import queue
import tkinter as tk
from dataclasses import dataclass
from tkinter import font as tkfont
from typing import Callable

from mchanhua.config import Config
from mchanhua.pipeline import PipelineResult
from mchanhua.ui.theme import Theme


def resolve_position(config, screen_size: tuple[int, int]) -> tuple[int, int]:
    """根据配置算出窗口左上角坐标（逻辑坐标）。"""

    screen_w, screen_h = screen_size
    margin = 24
    if config.position == "left":
        return (margin, margin)
    if config.position == "right":
        return (max(0, screen_w - config.width - margin), margin)
    if config.position == "bottom-right":
        return (
            max(0, screen_w - config.width - margin),
            max(0, screen_h - config.height - margin),
        )
    if config.position == "bottom-left":
        return (margin, max(0, screen_h - config.height - margin))
    return (margin, margin)


@dataclass
class WindowCallbacks:
    on_translate: Callable[[], None] | None = None
    on_select_and_translate: Callable[[], None] | None = None
    on_translate_fullscreen: Callable[[], None] | None = None
    on_open_image: Callable[[], None] | None = None
    on_select_region: Callable[[], None] | None = None
    on_quit: Callable[[], None] | None = None


def drain_queue(message_queue: "queue.Queue[tuple]", sink, max_messages: int = 50) -> int:
    """把队列里的消息交给 sink 处理，返回处理条数。

    sink 需要实现 set_status / show_source / show_result；
    带 "call" 的消息是"在界面线程执行一次的任务"。

    这里刻意加上 max_messages 上限：万一某个任务又往队列里补消息，
    drain 也不会陷进去出不来（曾经就是因为这个把 Tk 主线程卡死过）。
    """

    handled = 0
    for _ in range(max_messages):
        try:
            message = message_queue.get_nowait()
        except queue.Empty:
            break
        handled += 1
        kind = message[0]
        if kind == "status":
            sink.set_status(message[1])
        elif kind == "ocr":
            sink.show_source(message[1], message[2])
        elif kind == "result":
            sink.show_result(message[1])
        elif kind == "call":
            message[1]()
    return handled


class ResultWindow:
    def __init__(self, config: Config, callbacks: WindowCallbacks | None = None) -> None:
        self.config = config
        self.callbacks = callbacks or WindowCallbacks()
        self.heartbeat = None
        self.theme = Theme.from_config(config.ui)
        theme = self.theme
        self.root = tk.Tk()
        self.root.title("mchanhua 取词翻译")
        self.root.attributes("-topmost", bool(theme.always_on_top))
        # 透明度放到窗口映射之后再设：映射前设置分层窗口属性，在部分环境下会导致窗口不重绘
        self.root.after(200, self._apply_alpha)

        width, height = theme.width, theme.height
        x, y = resolve_position(config.ui, (self.root.winfo_screenwidth(), self.root.winfo_screenheight()))
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(320, 220)
        self.root.configure(bg=theme.background)

        family = theme.font_family
        if family not in tkfont.families():
            family = "Microsoft YaHei"
        self.target_font = tkfont.Font(family=family, size=theme.result_font_size)
        self.source_font = tkfont.Font(family=family, size=theme.source_font_size)

        self.status = tk.Label(
            self.root,
            text="就绪：把鼠标移到物品上，按热键取词",
            anchor="w",
            bg=theme.background,
            fg=theme.accent,
            font=self.source_font,
            padx=theme.padding,
            pady=4,
        )
        self.status.pack(fill="x")

        body = tk.Frame(self.root, bg=theme.background)
        body.pack(fill="both", expand=True, padx=theme.padding, pady=(0, 4))

        target_area = tk.Frame(body, bg=theme.background)
        target_area.pack(fill="both", expand=True)

        self.target = tk.Text(
            target_area,
            wrap="word",
            font=self.target_font,
            bg=theme.panel,
            fg=theme.text,
            insertbackground=theme.text,
            relief="flat",
            padx=theme.padding,
            pady=6,
        )
        scrollbar = tk.Scrollbar(target_area, command=self.target.yview)
        self.target.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.target.pack(side="left", fill="both", expand=True)

        self.source = tk.Text(
            body,
            height=4,
            wrap="word",
            font=self.source_font,
            bg=theme.panel,
            fg=theme.text_dim,
            relief="flat",
            padx=theme.padding,
            pady=4,
        )
        self.source.pack(fill="x", pady=(6, 0))

        button_rows = (
            (("翻译选区", self._translate), ("框选并翻译", self._select_and_translate), ("全屏翻译", self._translate_fullscreen)),
            (("只框选", self._select_region), ("打开图片", self._open_image), ("清空", self._clear), ("退出", self._quit)),
        )
        for row in button_rows:
            bar = tk.Frame(self.root, bg=theme.background)
            bar.pack(fill="x", padx=theme.padding, pady=(0, 6))
            for text, command in row:
                tk.Button(
                    bar,
                    text=text,
                    command=command,
                    font=self.source_font,
                    bg=theme.button_background,
                    fg=theme.button_text,
                    activebackground=theme.accent,
                    activeforeground=theme.panel,
                    relief="flat",
                ).pack(side="left", padx=(0, 6))

        for widget in (self.status, body):
            widget.bind("<Button-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag)
        self._drag_origin: tuple[int, int] | None = None

    def _apply_alpha(self) -> None:
        try:
            self.root.attributes("-alpha", float(self.theme.opacity))
        except tk.TclError:  # pragma: no cover - 少数平台不支持
            pass

    # ---- 拖动窗口 ----
    def _start_drag(self, event) -> None:
        self._drag_origin = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _drag(self, event) -> None:
        if self._drag_origin is None:
            return
        self.root.geometry(f"+{event.x_root - self._drag_origin[0]}+{event.y_root - self._drag_origin[1]}")

    # ---- 按钮 ----
    def _translate(self) -> None:
        if self.callbacks.on_translate:
            self.callbacks.on_translate()

    def _select_region(self) -> None:
        if self.callbacks.on_select_region:
            self.callbacks.on_select_region()

    def _translate_fullscreen(self) -> None:
        if self.callbacks.on_translate_fullscreen:
            self.callbacks.on_translate_fullscreen()

    def _select_and_translate(self) -> None:
        if self.callbacks.on_select_and_translate:
            self.callbacks.on_select_and_translate()

    def _open_image(self) -> None:
        if self.callbacks.on_open_image:
            self.callbacks.on_open_image()

    def _clear(self) -> None:
        self.target.delete("1.0", "end")
        self.source.delete("1.0", "end")

    def _quit(self) -> None:
        if self.callbacks.on_quit:
            self.callbacks.on_quit()

    # ---- 显示 ----
    def set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def show_source(self, lines: list[str], elapsed_ms: float) -> None:
        self.source.delete("1.0", "end")
        self.source.insert("1.0", "\n".join(lines))
        self.set_status(f"OCR 完成（{elapsed_ms:.0f} ms），正在翻译…")

    def show_result(self, result: PipelineResult) -> None:
        self.source.delete("1.0", "end")
        self.source.insert("1.0", "\n".join(result.source_lines))
        self.target.delete("1.0", "end")
        self.target.insert("1.0", "\n".join(result.output_lines))
        parts = [
            f"OCR {result.ocr_ms:.0f} ms",
            f"翻译 {result.translate_ms:.0f} ms",
            f"已翻 {result.translated_count} 行",
        ]
        if result.warnings:
            parts.append(f"提示：{result.warnings[0]}")
        self.set_status(" | ".join(parts))

    def drain(self, message_queue: "queue.Queue[tuple]", max_messages: int = 50) -> int:
        """在主线程里消费后台线程的消息。

        注意：这里只**执行**消息里的任务，绝不能再往同一个队列里补消息，
        否则 drain 会自己喂自己、无限循环，把 Tk 主线程卡死。
        max_messages 是额外的保险。
        """

        return drain_queue(message_queue, self, max_messages)

    def poll(self, message_queue: "queue.Queue[tuple]", interval_ms: int = 60) -> None:
        if self.heartbeat is not None:
            self.heartbeat()
        self.drain(message_queue)
        self.root.after(interval_ms, lambda: self.poll(message_queue, interval_ms))

    def run(self) -> None:
        self.root.mainloop()
