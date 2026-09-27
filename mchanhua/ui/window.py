"""结果小窗（浮层卡片风格）。

设计要点：译文当主角、原文退到次级、耗时信息归到状态行；多行结果（如全屏翻译）
自动切成"原文 | 译文"双栏对照。所有颜色/字号/内边距都来自配置里的主题。
"""

from __future__ import annotations

import queue
import tkinter as tk
from dataclasses import dataclass
from typing import Callable

import customtkinter as ctk

from mchanhua.config import Config
from mchanhua.ui.contrast import text_on
from mchanhua.pipeline import PipelineResult
from mchanhua.ui.theme import Theme

# 字号阶梯（排版规范要求成体系，而不是随手取值）
FONT_STEPS = (11, 13, 15, 19)


def snap_font_size(size: int) -> int:
    """把字号归到最近的阶梯上。"""

    return min(FONT_STEPS, key=lambda step: abs(step - size))


def resolve_position(config, screen_size: tuple[int, int]) -> tuple[int, int]:
    """根据配置算出窗口左上角坐标（逻辑坐标）。"""

    screen_w, screen_h = screen_size
    margin = 24
    if config.position == "left":
        return (margin, margin)
    if config.position == "right":
        return (max(0, screen_w - config.width - margin), margin)
    if config.position == "bottom-right":
        return (max(0, screen_w - config.width - margin), max(0, screen_h - config.height - margin))
    if config.position == "bottom-left":
        return (margin, max(0, screen_h - config.height - margin))
    return (margin, margin)


@dataclass
class WindowCallbacks:
    on_translate: Callable[[], None] | None = None
    on_open_settings: Callable[[], None] | None = None
    on_select_and_translate: Callable[[], None] | None = None
    on_translate_fullscreen: Callable[[], None] | None = None
    on_open_image: Callable[[], None] | None = None
    on_select_region: Callable[[], None] | None = None
    on_quit: Callable[[], None] | None = None


def drain_queue(message_queue: "queue.Queue[tuple]", sink, max_messages: int = 50) -> int:
    """把队列里的消息交给 sink 处理；"call" 消息是在界面线程执行的一次性任务。"""

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


def _is_dark(color: str) -> bool:
    """判断颜色是不是深色（用来决定界面走深色还是浅色外观）。"""

    value = (color or "").lstrip("#")
    if len(value) != 6:
        return True
    try:
        red, green, blue = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return True
    return (red * 299 + green * 587 + blue * 114) / 1000 < 140


class ResultWindow:
    def __init__(self, config: Config, callbacks: WindowCallbacks | None = None) -> None:
        self.config = config
        self.callbacks = callbacks or WindowCallbacks()
        self.heartbeat = None
        self.theme = Theme.from_config(config.ui)
        theme = self.theme

        ctk.set_appearance_mode("dark" if _is_dark(theme.background) else "light")
        self.root = ctk.CTk(fg_color=theme.background)
        self.root.title("mchanhua 取词翻译")
        self.root.attributes("-topmost", bool(theme.always_on_top))
        self.root.after(200, self._apply_alpha)

        x, y = resolve_position(
            config.ui, (self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        )
        self.root.geometry(f"{theme.width}x{theme.height}+{x}+{y}")
        self.root.minsize(360, 260)

        family = theme.font_family or "Microsoft YaHei UI"
        self.title_font = ctk.CTkFont(family=family, size=snap_font_size(theme.font_size))
        self.meta_font = ctk.CTkFont(family=family, size=FONT_STEPS[0])
        self.result_font = ctk.CTkFont(family=family, size=snap_font_size(theme.result_font_size))
        self.source_font = ctk.CTkFont(family=family, size=snap_font_size(theme.source_font_size))
        # 行高：把倍数换算成像素，加到每行之后，长句更好读
        self.line_px = max(0, round((theme.line_height - 1.0) * snap_font_size(theme.result_font_size)))

        self._build_chrome()
        self._build_body()
        self.action_bars: list = []
        self.collapsed = False
        self._expanded_geometry = f"{theme.width}x{theme.height}"
        self._build_actions()
        self._drag_origin: tuple[int, int] | None = None
        self.compare_mode = False

    # ---- 外观 ----
    def _apply_alpha(self) -> None:
        if self.theme.opacity >= 0.999:
            return          # 1.0 时不设置 alpha，避免半透明带来的透视与残影
        try:
            self.root.attributes("-alpha", float(self.theme.opacity))
        except tk.TclError:  # pragma: no cover
            pass

    def _build_chrome(self) -> None:
        theme = self.theme
        bar = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        bar.pack(fill="x", padx=theme.padding, pady=(theme.padding, 0))

        mark = ctk.CTkLabel(bar, text="译", width=24, height=24, corner_radius=6,
                            fg_color=theme.accent, text_color=theme.background,
                            font=self.meta_font)
        mark.pack(side="left", padx=(0, 8))
        title = ctk.CTkLabel(bar, text="取词翻译", font=self.title_font, text_color=theme.text)
        title.pack(side="left")
        self.provider_chip = ctk.CTkLabel(
            bar, text=self._provider_label(), font=self.meta_font,
            text_color=theme.accent, fg_color="transparent",
        )
        self.provider_chip.pack(side="left", padx=8)

        for text, command in (("✕", self._quit), ("—", self._minimize)):
            ctk.CTkButton(
                bar, text=text, width=28, height=24, corner_radius=6,
                fg_color="transparent", hover_color=theme.panel,
                text_color=theme.text_dim, font=self.meta_font, command=command,
            ).pack(side="right", padx=2)
        self.collapse_button = ctk.CTkButton(
            bar, text="折叠", width=44, height=24, corner_radius=6, font=self.meta_font,
            fg_color="transparent", hover_color=self.theme.panel,
            text_color=self.theme.text_dim, command=self.toggle_collapsed,
        )
        self.collapse_button.pack(side="right", padx=2)
        for widget in (bar, mark, title):
            widget.bind("<Button-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag)

        self.status = ctk.CTkLabel(
            self.root, text="就绪：Alt+V 框选一次，之后按 Ctrl+Alt 翻译",
            anchor="w", justify="left", font=self.meta_font, text_color=theme.text_dim,
        )
        self.status.pack(fill="x", padx=theme.padding + 4, pady=(2, 6))

    def _build_body(self) -> None:
        theme = self.theme
        self.body = ctk.CTkFrame(self.root, corner_radius=8, fg_color=theme.panel)
        self.body.pack(fill="both", expand=True, padx=theme.padding, pady=(0, 6))

        self.result_area = ctk.CTkFrame(self.body, corner_radius=0, fg_color="transparent")
        self.result_area.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        self.target = ctk.CTkTextbox(
            self.result_area, wrap="word", font=self.result_font,
            fg_color="transparent", text_color=theme.text, corner_radius=6, border_width=0,
        )
        self.target.pack(fill="both", expand=True)
        self._apply_line_spacing(self.target)

        self.source_area = ctk.CTkFrame(self.body, corner_radius=0, fg_color="transparent")
        self.source_area.pack(fill="x", padx=6, pady=(0, 6))
        header = ctk.CTkFrame(self.source_area, corner_radius=0, fg_color="transparent")
        header.pack(fill="x")
        self.source_label = ctk.CTkLabel(
            header, text="原文", anchor="w", font=self.meta_font, text_color=theme.text_dim
        )
        self.source_label.pack(side="left")
        self.source_toggle = ctk.CTkButton(
            header, text="收起", width=44, height=20, corner_radius=6, font=self.meta_font,
            fg_color="transparent", hover_color=theme.button_background,
            text_color=theme.text_dim, command=self._toggle_source,
        )
        self.source_toggle.pack(side="right")
        self.source = ctk.CTkTextbox(
            self.source_area, height=64, wrap="word", font=self.source_font,
            fg_color="transparent", text_color=theme.text_dim, corner_radius=6, border_width=0,
        )
        self.source.pack(fill="x")
        self._apply_line_spacing(self.source, scale=0.8)
        self.source_visible = True

    def _apply_line_spacing(self, textbox, scale: float = 1.0) -> None:
        """给 Tk 文本框加行距（CTkTextbox 内部是 tkinter.Text）。"""

        inner = getattr(textbox, "_textbox", None)
        if inner is None:
            return
        spacing = max(0, round(self.line_px * scale))
        try:
            inner.configure(spacing2=spacing, spacing3=spacing)
        except tk.TclError:  # pragma: no cover
            pass

    def _build_actions(self) -> None:
        theme = self.theme
        rows = (
            (
                ("翻译选区", self._translate, True),
                ("框选并翻译", self._select_and_translate, False),
                ("全屏翻译", self._translate_fullscreen, False),
                ("双栏对照", self._toggle_layout, False),
            ),
            (
                ("打开图片", self._open_image, False),
                ("只框选", self._select_region, False),
                ("清空", self._clear, False),
                ("设置", self._open_settings, False),
                ("退出", self._quit, False),
            ),
        )
        for row in rows:
            bar = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
            bar.pack(fill="x", padx=theme.padding, pady=(0, 6))
            self.action_bars.append(bar)
            for text, command, primary in row:
                ctk.CTkButton(
                    bar, text=text, height=28, corner_radius=6, font=self.meta_font,
                    fg_color=theme.accent if primary else theme.button_background,
                    hover_color=theme.accent if primary else theme.panel,
                    text_color=theme.background if primary else theme.button_text,
                    command=command,
                ).pack(side="left", padx=(0, 6))

    def _provider_label(self) -> str:
        from mchanhua.translate.providers import find_preset

        preset = find_preset(self.config.translate.provider)
        return preset.label.split("（")[0] if preset else self.config.translate.provider

    # ---- 拖动 / 窗口按钮 ----
    def _start_drag(self, event) -> None:
        self._drag_origin = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _drag(self, event) -> None:
        if self._drag_origin is None:
            return
        self.root.geometry(f"+{event.x_root - self._drag_origin[0]}+{event.y_root - self._drag_origin[1]}")

    def _minimize(self) -> None:
        self.root.iconify()

    def toggle_collapsed(self) -> None:
        """折叠：只保留标题栏与译文（隐藏原文与按钮），再点展开。"""

        self.collapsed = not self.collapsed
        if self.collapsed:
            self.source_area.pack_forget()
            for bar in self.action_bars:
                bar.pack_forget()
            self.root.geometry(f"{self.theme.width}x118")
            self.collapse_button.configure(text="展开")
            self.set_status("已折叠（只显示译文）")
        else:
            self.source_area.pack(fill="x", padx=6, pady=(0, 6))
            for bar in self.action_bars:
                bar.pack(fill="x", padx=self.theme.padding, pady=(0, 6))
            self.root.geometry(self._expanded_geometry)
            self.collapse_button.configure(text="折叠")
            self.set_status("已展开（译文在上、原文在下）")

    # ---- 按钮回调 ----
    def _call(self, name: str) -> None:
        callback = getattr(self.callbacks, name, None)
        if callback:
            callback()

    def _translate(self) -> None:
        self._call("on_translate")

    def _select_and_translate(self) -> None:
        self._call("on_select_and_translate")

    def _translate_fullscreen(self) -> None:
        self._call("on_translate_fullscreen")

    def _open_image(self) -> None:
        self._call("on_open_image")

    def _select_region(self) -> None:
        self._call("on_select_region")

    def _open_settings(self) -> None:
        self._call("on_open_settings")

    def _quit(self) -> None:
        self._call("on_quit")

    def _clear(self) -> None:
        self.target.delete("1.0", "end")
        self.source.delete("1.0", "end")

    def _toggle_layout(self) -> None:
        self.set_compare_mode(not self.compare_mode)

    def _toggle_source(self) -> None:
        """译文为主：原文可以收起，需要核对时再展开。"""

        self.source_visible = not self.source_visible
        if self.source_visible:
            self.source.pack(fill="x")
            self.source_toggle.configure(text="收起")
        else:
            self.source.pack_forget()
            self.source_toggle.configure(text="展开")
        self.set_status("已展开原文" if self.source_visible else "已收起原文（点「展开」可恢复）")

    def set_compare_mode(self, enabled: bool) -> None:
        """切换"对话式"与"原文 | 译文"双栏对照。"""

        self.compare_mode = bool(enabled)
        if self.compare_mode:
            self.source_label.configure(text="原文（与译文逐行对应）")
        else:
            self.source_label.configure(text="原文")
        self.set_status("已切换到双栏对照" if self.compare_mode else "已切换到对话式")

    # ---- 显示 ----
    def set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def status_text(self) -> str:
        return str(self.status.cget("text"))

    def show_source(self, lines: list[str], elapsed_ms: float) -> None:
        self.source.delete("1.0", "end")
        self.source.insert("1.0", "\n".join(lines))
        self.set_status(f"OCR 完成（{elapsed_ms:.0f} ms），正在翻译…")

    def show_result(self, result: PipelineResult) -> None:
        self.source.delete("1.0", "end")
        self.source.insert("1.0", "\n".join(result.source_lines))
        self.target.delete("1.0", "end")
        self.target.insert("1.0", "\n".join(result.output_lines))

        # 多行结果（通常是全屏翻译）自动切成双栏对照
        if len(result.source_lines) >= 4 and not self.compare_mode:
            self.compare_mode = True
            self.source_label.configure(text="原文（与译文逐行对应）")

        parts = [
            f"OCR {result.ocr_ms:.0f} ms",
            f"翻译 {result.translate_ms:.0f} ms",
            f"已翻 {result.translated_count} 行",
            self._provider_label(),
        ]
        if result.warnings:
            parts.append(f"提示：{result.warnings[0]}")
        self.set_status(" · ".join(parts))

    def on_poll(self) -> None:
        if self.heartbeat is not None:
            self.heartbeat()

    def drain(self, message_queue: "queue.Queue[tuple]", max_messages: int = 50) -> int:
        return drain_queue(message_queue, self, max_messages)

    def poll(self, message_queue: "queue.Queue[tuple]", interval_ms: int = 60) -> None:
        self.on_poll()
        self.drain(message_queue)
        self.root.after(interval_ms, lambda: self.poll(message_queue, interval_ms))

    def run(self) -> None:
        self.root.mainloop()
