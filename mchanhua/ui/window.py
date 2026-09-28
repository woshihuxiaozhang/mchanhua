"""取词小窗：按参考图实现——白卡片 + 透明背景。

布局（自上而下）：标题行（标记 · 取词翻译 · 服务标签 · 最小化/关闭）
→ 译文（大字）→ 原文（灰字，在译文下方）→ 元信息行 → 四个圆角按钮。
窗口背景透明，只有白卡片可见；卡片可拖动，双击标题行折叠。
"""

from __future__ import annotations

import queue
import tkinter as tk
from dataclasses import dataclass
from typing import Callable

import customtkinter as ctk
from customtkinter import ScalingTracker

from mchanhua.config import Config
from mchanhua.pipeline import PipelineResult
from mchanhua.ui.titlebar import use_light_title_bar

FONT_STEPS = (11, 13, 15, 19)
TRANSPARENT = "#010203"          # 只用来做透明键，不参与主题


def snap_font_size(size: int) -> int:
    return min(FONT_STEPS, key=lambda step: abs(step - size))


def resolve_position(
    config, screen_size: tuple[int, int], size: tuple[int, int] | None = None
) -> tuple[int, int]:
    """算出小窗左上角坐标。size 用于传入"布局需要的最小尺寸"（可能比配置大）。"""

    width, height = size or (config.width, config.height)
    screen_w, screen_h = screen_size
    margin = 24
    if config.position == "left":
        return (margin, margin)
    if config.position == "right":
        return (max(0, screen_w - width - margin), margin)
    if config.position == "bottom-right":
        return (max(0, screen_w - width - margin), max(0, screen_h - height - margin))
    if config.position == "bottom-left":
        return (margin, max(0, screen_h - height - margin))
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
        ui = config.ui

        ctk.set_appearance_mode("dark" if _is_dark(ui.background) else "light")
        self.root = ctk.CTk(fg_color=TRANSPARENT)
        self.root.title("mchanhua 取词翻译")
        self.root.attributes("-topmost", bool(ui.always_on_top))
        # 背景透明：把透明键色之外的部分留给白卡片
        try:
            self.root.attributes("-transparentcolor", TRANSPARENT)
        except tk.TclError:  # pragma: no cover - 少数平台不支持
            pass
        self._apply_light_title_bar()
        self.root.after(200, self._apply_alpha)

        self.root.geometry(f"{ui.width}x{ui.height}")
        self.root.minsize(400, 190)

        family = ui.font_family or "Microsoft YaHei UI"
        self.f_title = ctk.CTkFont(family=family, size=snap_font_size(ui.font_size))
        self.f_result = ctk.CTkFont(family=family, size=snap_font_size(ui.result_font_size))
        self.f_source = ctk.CTkFont(family=family, size=snap_font_size(ui.source_font_size))
        self.f_meta = ctk.CTkFont(family=family, size=FONT_STEPS[0])

        self.card = ctk.CTkFrame(
            self.root, corner_radius=0, fg_color="#FFFFFF", border_width=0   # 直角内框
        )
        self.card.pack(fill="both", expand=True)      # 白卡片直接铺满窗口：没有外框、没有留白

        self.collapsed = False
        self.compare_mode = False
        self.source_visible = True
        self.action_bars: list = []
        self._drag_origin = None

        self._build_title()
        self._build_text()
        self._build_meta()
        self.set_status("待取词：把鼠标移到物品上按热键")
        self._build_buttons()
        self._place_window()
        # customtkinter 的尺寸换算在窗口映射之后才生效，等它稳定再摆一次，
        # 否则高度是按"还没定型的请求尺寸"算的，底下会多出一块空白。
        self.root.after(250, self._place_window)

    def _place_window(self):
        """按内容的实际尺寸摆好窗口：不留多余空白，也不会顶出屏幕（按钮被切掉）。

        customtkinter 会把 geometry 里的宽高乘上 DPI 缩放，而坐标不加缩放，
        所以尺寸按"逻辑像素"（配置单位）给、位置按物理像素算，
        否则高分屏上窗口会顶出屏幕右边、最右边的按钮被切掉。
        config.ui.width / height 现在只当"下限"：内容更小就贴内容，绝不留空。
        """

        ui = self.config.ui
        self.root.update_idletasks()
        scaling = float(ScalingTracker.get_window_dpi_scaling(self.root)) or 1.0
        screen_w = self.root.winfo_screenwidth()      # 物理像素
        screen_h = self.root.winfo_screenheight()
        # winfo_req* 是物理像素，先换回逻辑像素跟配置取大，再换回物理算位置
        needed_w = int(self.root.winfo_reqwidth() / scaling + 0.5)
        needed_h = int(self.root.winfo_reqheight() / scaling + 0.5)
        logical_w = max(int(ui.width), needed_w)
        logical_h = max(needed_h, int(ui.height))     # 高度贴内容，配置值只当下限
        physical_w = int(round(logical_w * scaling))
        physical_h = int(round(logical_h * scaling))
        x, y = resolve_position(ui, (screen_w, screen_h), (physical_w, physical_h))
        self.root.geometry(f"{logical_w}x{logical_h}+{x}+{y}")
        return physical_w, physical_h

    # ---- 顶部标题行 ----
    def _build_title(self) -> None:
        row = ctk.CTkFrame(self.card, corner_radius=0, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(10, 0))
        ctk.CTkLabel(row, text="文", width=20, height=20, corner_radius=4,
                     fg_color="#E8F0FE", text_color="#1A73E8", font=self.f_meta).pack(side="left")
        ctk.CTkLabel(row, text="取词翻译", font=self.f_title, text_color="#1B1B1B").pack(
            side="left", padx=(6, 8)
        )
        self.provider_chip = ctk.CTkLabel(
            row, text=self._provider_label(), height=20, corner_radius=10, padx=8,
            fg_color="#E8F0FE", text_color="#1A73E8", font=self.f_meta,
        )
        self.provider_chip.pack(side="left")
        # 最小化 / 关闭交给外框的标题栏按钮，这里不再重复放一份
        for widget in (row, self.card):
            widget.bind("<Button-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag)
            widget.bind("<Double-Button-1>", lambda _event: self.toggle_collapsed())

    # ---- 译文 / 原文 ----
    def _build_text(self) -> None:
        self.target = ctk.CTkTextbox(
            self.card, wrap="word", font=self.f_result, fg_color="transparent",
            text_color="#111111", corner_radius=0, border_width=0, height=44,
        )
        self.target.pack(fill="x", padx=12, pady=(6, 0))
        self.source_area = ctk.CTkFrame(self.card, corner_radius=0, fg_color="transparent")
        self.source_area.pack(fill="x", padx=12)
        self.source = ctk.CTkTextbox(
            self.source_area, wrap="word", font=self.f_source, fg_color="transparent",
            text_color="#8A8A8A", corner_radius=0, border_width=0, height=30,
        )
        self.source.pack(fill="x")

    def _build_meta(self) -> None:
        self.status = ctk.CTkLabel(
            self.card, text="", anchor="w", justify="left",
            font=self.f_meta, text_color="#9A9A9A",
        )
        self.status.pack(fill="x", padx=16)

    # ---- 底部按钮 ----
    def _build_buttons(self) -> None:
        bar = ctk.CTkFrame(self.card, corner_radius=0, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=(8, 8))
        self.action_bars.append(bar)
        specs = (
            ("翻译选区", self._translate, True, "scan-text"),
            ("框选并翻译", self._select_and_translate, False, "crop"),
            ("全屏翻译", self._translate_fullscreen, False, "monitor"),
            ("设置", self._open_settings, False, "settings"),
        )
        for column in range(len(specs)):
            # 四等分：按钮永远不会把窗口顶宽，也就不会顶出屏幕
            bar.grid_columnconfigure(column, weight=1, uniform="action")
        for column, (text, command, primary, _icon) in enumerate(specs):
            ctk.CTkButton(
                bar, text=text, width=1, height=34, corner_radius=6, font=self.f_source,
                fg_color="#E8F0FE" if primary else "#FFFFFF",
                hover_color="#DCE7FB" if primary else "#F1F1F1",
                text_color="#1A73E8" if primary else "#3C4043",
                border_width=0 if primary else 1, border_color="#E0E0E0",
                command=command,
            ).grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))

    def _provider_label(self) -> str:
        from mchanhua.translate.providers import find_preset

        preset = find_preset(self.config.translate.provider)
        return preset.label.split("（")[0] if preset else self.config.translate.provider

    # ---- 窗口行为 ----
    def _apply_light_title_bar(self) -> None:
        """外框（标题栏）保持白色：系统深色主题下默认是黑的，这里强制浅色。"""

        use_light_title_bar(self.root)
        # 窗口映射 / DWM 处理标题栏是在之后发生的，再补两次更稳
        self.root.after(150, lambda: use_light_title_bar(self.root))
        self.root.after(500, lambda: use_light_title_bar(self.root))

    def _apply_alpha(self) -> None:
        opacity = float(self.config.ui.opacity)
        if opacity >= 0.999:
            return
        try:
            self.root.attributes("-alpha", opacity)
        except tk.TclError:  # pragma: no cover
            pass

    def _start_drag(self, event) -> None:
        self._drag_origin = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def _drag(self, event) -> None:
        if self._drag_origin is None:
            return
        self.root.geometry(f"+{event.x_root - self._drag_origin[0]}+{event.y_root - self._drag_origin[1]}")

    def _minimize(self) -> None:
        self.root.iconify()

    def toggle_collapsed(self) -> None:
        """折叠：只留标题行与译文；再双击展开。"""

        self.collapsed = not self.collapsed
        self.compare_mode = not self.collapsed
        if self.collapsed:
            self.source_area.pack_forget()
            for bar in self.action_bars:
                bar.pack_forget()
            self.set_status("已折叠（双击标题行可展开）")
        else:
            self.source_area.pack(fill="x", padx=12)
            for bar in self.action_bars:
                bar.pack(fill="x", padx=12, pady=(8, 8))
            self.set_status("已展开（译文在上，原文在下）")
        self._place_window()          # 折叠后也要贴着内容收小，不留一大块空白

    def set_compare_mode(self, enabled: bool) -> None:
        if bool(enabled) == (not self.collapsed):
            return
        self.toggle_collapsed()

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
        self.set_status("待取词：把鼠标移到物品上按热键")

    # ---- 显示 ----
    def set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def status_text(self) -> str:
        return str(self.status.cget("text"))

    def show_source(self, lines: list[str], elapsed_ms: float) -> None:
        self.source.delete("1.0", "end")
        self.source.insert("1.0", "\n".join(lines))
        self.set_status(f"OCR {elapsed_ms:.0f} ms · 正在翻译…")

    def show_result(self, result: PipelineResult) -> None:
        self.target.delete("1.0", "end")
        self.target.insert("1.0", "\n".join(result.output_lines))
        self.source.delete("1.0", "end")
        self.source.insert("1.0", "\n".join(result.source_lines))
        self.provider_chip.configure(text=self._provider_label())
        if len(result.source_lines) >= 3 and self.collapsed:
            self.toggle_collapsed()
        elif len(result.source_lines) >= 3:
            self.compare_mode = True
        parts = [
            f"OCR {result.ocr_ms:.0f} ms",
            f"翻译 {result.translate_ms:.0f} ms",
            f"已翻 {result.translated_count} 行",
        ]
        if self.config.regions.custom_region() is not None:
            parts.append(f"选区 {self.config.regions.custom_region().to_csv()}")
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
