"""结果小窗：紧凑工具条 + 可展开面板（简约 / 暖单色）。

默认只有一条细横条：左边标记、中间一行译文、右边耗时与展开箭头。
展开后是一张卡片：译文（大字）→ 分隔线 → 原文（次级灰），底部是固定/复制/设置。
所有颜色、字号、行高都来自配置里的主题；折叠即收起面板。
"""

from __future__ import annotations

import queue
import tkinter as tk
from dataclasses import dataclass
from typing import Callable

import customtkinter as ctk

from mchanhua.config import Config
from mchanhua.pipeline import PipelineResult
from mchanhua.ui.theme import Theme

FONT_STEPS = (11, 13, 15, 19)


def snap_font_size(size: int) -> int:
    """字号归到最近的阶梯（排版规范要求成体系）。"""

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
    """把队列里的消息交给 sink；"call" 消息是在界面线程执行的一次性任务。"""

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
    value = (color or "").lstrip("#")
    if len(value) != 6:
        return False
    try:
        red, green, blue = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return False
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
        self.root.minsize(320, 96)

        family = theme.font_family or "Microsoft YaHei UI"
        mono = "Consolas"
        self.strip_font = ctk.CTkFont(family=family, size=snap_font_size(theme.font_size))
        self.meta_font = ctk.CTkFont(family=mono, size=FONT_STEPS[0])
        self.tiny_font = ctk.CTkFont(family=family, size=FONT_STEPS[0])
        self.result_font = ctk.CTkFont(family=family, size=snap_font_size(theme.result_font_size))
        self.source_font = ctk.CTkFont(family=family, size=snap_font_size(theme.source_font_size))
        self.line_px = max(0, round((theme.line_height - 1.0) * snap_font_size(theme.result_font_size)))

        self.action_bars: list = []
        self.collapsed = False
        self.compare_mode = False
        self.source_visible = True
        self._last_result: PipelineResult | None = None

        self._build_strip()
        self._build_panel()
        self._build_status()
        self._drag_origin: tuple[int, int] | None = None

    # ---- 外观 ----
    def _apply_alpha(self) -> None:
        if self.theme.opacity >= 0.999:
            return
        try:
            self.root.attributes("-alpha", float(self.theme.opacity))
        except tk.TclError:  # pragma: no cover
            pass

    def _build_strip(self) -> None:
        theme = self.theme
        strip = ctk.CTkFrame(
            self.root, corner_radius=8, fg_color=theme.panel,
            border_width=1, border_color=theme.border, height=40,
        )
        strip.pack(fill="x", padx=theme.padding, pady=(theme.padding, 4))

        mark = ctk.CTkLabel(
            strip, text="译", width=26, height=22, corner_radius=4,
            fg_color=theme.accent_soft, text_color=theme.accent, font=self.tiny_font,
        )
        mark.pack(side="left", padx=(8, 8), pady=8)

        self.inline = ctk.CTkLabel(
            strip, text="待取词：移到物品上按热键", anchor="w",
            font=self.strip_font, text_color=theme.text_dim,
        )
        self.inline.pack(side="left", fill="x", expand=True)

        self.chip = ctk.CTkLabel(
            strip, text="", height=20, corner_radius=4, padx=6,
            fg_color=theme.accent_soft, text_color=theme.accent, font=self.meta_font,
        )
        self.chip.pack(side="right", padx=(6, 4))

        self.collapse_button = ctk.CTkButton(
            strip, text="展开", width=44, height=24, corner_radius=6, font=self.tiny_font,
            fg_color="transparent", hover_color=theme.border,
            text_color=theme.text_dim, command=self.toggle_collapsed,
        )
        self.collapse_button.pack(side="right", padx=(0, 6))

        for widget in (strip, mark, self.inline):
            widget.bind("<Button-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag)
        self.strip = strip

    def _build_panel(self) -> None:
        theme = self.theme
        self.panel = ctk.CTkFrame(
            self.root, corner_radius=8, fg_color=theme.panel,
            border_width=1, border_color=theme.border,
        )
        self.panel.pack(fill="both", expand=True, padx=theme.padding, pady=(0, 4))

        self.target = ctk.CTkTextbox(
            self.panel, wrap="word", font=self.result_font, height=62,
            fg_color="transparent", text_color=theme.text, corner_radius=0, border_width=0,
        )
        self.target.pack(fill="both", expand=True, padx=8, pady=(8, 2))
        self._apply_line_spacing(self.target)

        divider = ctk.CTkFrame(self.panel, height=1, fg_color=theme.border, corner_radius=0)
        divider.pack(fill="x", padx=8, pady=2)

        self.source_area = ctk.CTkFrame(self.panel, corner_radius=0, fg_color="transparent")
        self.source_area.pack(fill="x", padx=8, pady=(2, 0))
        self.source = ctk.CTkTextbox(
            self.source_area, height=44, wrap="word", font=self.source_font,
            fg_color="transparent", text_color=theme.text_dim, corner_radius=0, border_width=0,
        )
        self.source.pack(fill="x")
        self._apply_line_spacing(self.source, scale=0.7)

        bar = ctk.CTkFrame(self.panel, corner_radius=0, fg_color="transparent")
        bar.pack(fill="x", padx=8, pady=(4, 8))
        self.action_bars.append(bar)
        for text, command, primary in (
            ("固定", self._toggle_pin, False),
            ("复制", self._copy_result, False),
            ("翻译选区", self._translate, True),
            ("设置", self._open_settings, False),
        ):
            ctk.CTkButton(
                bar, text=text, height=26, corner_radius=6, font=self.tiny_font,
                fg_color=theme.button_primary if primary else theme.button_background,
                hover_color=theme.button_primary if primary else theme.border,
                text_color=theme.button_primary_text if primary else theme.button_text,
                border_width=0 if primary else 1, border_color=theme.border,
                command=command,
            ).pack(side="left", padx=(0, 6))

    def _build_status(self) -> None:
        self.status = ctk.CTkLabel(
            self.root, text="就绪：Alt+V 框选一次，之后按 Ctrl+Alt 翻译",
            anchor="w", justify="left", font=self.tiny_font, text_color=self.theme.text_dim,
        )
        self.status.pack(fill="x", padx=self.theme.padding + 2, pady=(0, self.theme.padding))

    def _apply_line_spacing(self, textbox, scale: float = 1.0) -> None:
        inner = getattr(textbox, "_textbox", None)
        if inner is None:
            return
        spacing = max(0, round(self.line_px * scale))
        try:
            inner.configure(spacing2=spacing, spacing3=spacing)
        except tk.TclError:  # pragma: no cover
            pass

    # ---- 交互 ----
    def _start_drag(self, event) -> None:
        self._drag_origin = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _drag(self, event) -> None:
        if self._drag_origin is None:
            return
        self.root.geometry(f"+{event.x_root - self._drag_origin[0]}+{event.y_root - self._drag_origin[1]}")

    def toggle_collapsed(self) -> None:
        """折叠 / 展开：折叠只留一条横条，展开显示译文与原文。"""

        self.collapsed = not self.collapsed
        self.compare_mode = not self.collapsed
        if self.collapsed:
            self.panel.pack_forget()
            self.collapse_button.configure(text="展开")
            self.set_status("已折叠：只保留这条横条（点「展开」看原文）")
        else:
            self.panel.pack(fill="both", expand=True, padx=self.theme.padding, pady=(0, 4))
            self.collapse_button.configure(text="收起")
            self.set_status("已展开：译文在上，原文在下")

    def set_compare_mode(self, enabled: bool) -> None:
        """展开/收起面板（保留旧接口语义）。"""

        if bool(enabled) == (not self.collapsed):
            return
        self.toggle_collapsed()

    def _toggle_pin(self) -> None:
        current = bool(self.root.attributes("-topmost"))
        self.root.attributes("-topmost", not current)
        self.set_status("已取消置顶" if current else "已置顶")

    def _copy_result(self) -> None:
        text = self.target.get("1.0", "end").strip()
        if not text:
            self.set_status("没有可复制的译文")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.set_status("译文已复制到剪贴板")

    def _toggle_source(self) -> None:
        self.source_visible = not self.source_visible
        if self.source_visible:
            self.source.pack(fill="x")
        else:
            self.source.pack_forget()

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
        self.inline.configure(text="待取词：移到物品上按热键", text_color=self.theme.text_dim)
        self.chip.configure(text="")

    # ---- 显示 ----
    def set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def status_text(self) -> str:
        return str(self.status.cget("text"))

    def show_source(self, lines: list[str], elapsed_ms: float) -> None:
        self.source.delete("1.0", "end")
        self.source.insert("1.0", "\n".join(lines))
        joined = " ".join(part.strip() for part in lines if part.strip())
        self.inline.configure(text=joined[:28] + ("…" if len(joined) > 28 else ""), text_color=self.theme.text)
        self.chip.configure(text=f"{elapsed_ms / 1000:.1f}s")
        self.set_status(f"OCR 完成（{elapsed_ms:.0f} ms），正在翻译…")

    def show_result(self, result: PipelineResult) -> None:
        self._last_result = result
        self.source.delete("1.0", "end")
        self.source.insert("1.0", "\n".join(result.source_lines))
        self.target.delete("1.0", "end")
        self.target.insert("1.0", "\n".join(result.output_lines))

        first = next((line.strip() for line in result.output_lines if line.strip()), "")
        self.inline.configure(
            text=first[:28] + ("…" if len(first) > 28 else "") or "（没有译文）",
            text_color=self.theme.text,
        )
        total_ms = result.ocr_ms + result.translate_ms
        self.chip.configure(text=f"{total_ms / 1000:.1f}s")

        # 多行结果自动展开（需要看原文），单行则保持紧凑
        if len(result.source_lines) >= 3:
            if self.collapsed:
                self.toggle_collapsed()
            else:
                self.compare_mode = True

        parts = [
            f"OCR {result.ocr_ms:.0f} ms",
            f"翻译 {result.translate_ms:.0f} ms",
            f"已翻 {result.translated_count} 行",
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
