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
from mchanhua.history import HistoryEntry, render_entries
from mchanhua.logging_setup import get_logger
from mchanhua.pipeline import PipelineResult
from mchanhua.ui.titlebar import use_light_title_bar

FONT_STEPS = (11, 13, 15, 19)
TRANSPARENT = "#010203"          # 只用来做透明键，不参与主题

# 历史翻译浮层：刻意做得比主窗口小、纯白不透明，盖在窗口内容之上
HISTORY_PANEL_W = 300
HISTORY_PANEL_H = 230
HISTORY_PANEL_TOP = 46
HISTORY_PANEL_RIGHT = 10
HISTORY_WINDOW_MIN_H = 340       # 展开浮层时窗口至少这么高（逻辑像素）


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
    on_toggle_watch: Callable[[], None] | None = None
    on_save_corrections: Callable[[list], None] | None = None
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
        elif kind == "notice":
            handler = getattr(sink, "show_notice", None)
            if handler is not None:
                handler(message[1])
            else:  # pragma: no cover - 老界面/测试替身没有这个方法
                sink.set_status(message[1])
        elif kind == "history":
            handler = getattr(sink, "show_history", None)
            if handler is not None:
                handler(message[1])
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
        # 最小尺寸要够小，否则它会把"按内容自适应"卡住（曾经把高度顶在 190）
        self.root.minsize(360, 110)

        family = ui.font_family or "Microsoft YaHei UI"
        self.f_title = ctk.CTkFont(family=family, size=snap_font_size(ui.font_size))
        self.f_result = ctk.CTkFont(family=family, size=snap_font_size(ui.result_font_size))
        self.f_source = ctk.CTkFont(family=family, size=snap_font_size(ui.source_font_size))
        self.f_meta = ctk.CTkFont(family=family, size=FONT_STEPS[0])
        # 时钟图标：Windows 自带 Segoe UI Emoji，用它才能显示出图标而不是方框
        self.f_icon = ctk.CTkFont(family="Segoe UI Emoji", size=snap_font_size(ui.font_size))

        self.card = ctk.CTkFrame(
            self.root, corner_radius=0, fg_color="#FFFFFF", border_width=0   # 直角内框
        )
        self.card.pack(fill="both", expand=True)      # 白卡片直接铺满窗口：没有外框、没有留白

        self.collapsed = False
        self.compare_mode = False
        self.history_open = False
        self.history_provider = None      # Application 会挂上"取最近 20 条"的函数
        self._status_before_history = ""
        self._history_entries: list[HistoryEntry] = []
        self._height_before_history = 0
        self._user_moved = False          # 用户手动挪过窗口后，不再自动改位置
        self._user_resized = False        # 用户手动拉过窗口大小后，不再自动改尺寸
        self._side_by_side = False        # 译文/原文是不是左右并排（横向拉长时）
        self._expected_size = (0, 0)      # 程序自己设的尺寸，用来分辨"是不是用户改的"
        self._layout_pending = None
        self.source_visible = True
        self.action_bars: list = []
        self._drag_origin = None
        # 手动修正译文：记住"译文框里第几行对应识别结果的第几行"
        self._result: PipelineResult | None = None
        self._target_map: list[int | None] = []
        self._editing_programmatically = False
        self._corrections_pending = False

        self._build_title()
        # 先占住底部：按钮和状态行贴底，内容区再吃剩下的空间。
        # 这样窗口被压小的时候是内容区变矮（可滚动），而不是把按钮挤出窗口外。
        self._build_buttons()
        self._build_meta()
        self._build_text()
        self.set_status("待取词：把鼠标移到物品上按热键")
        self._build_history_panel()
        self._fit_text_areas(1, 1)        # 空闲时只留一行高，不留一大片空白
        self._place_window()
        self.card.bind("<Configure>", self._on_card_configure)
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
        logical_w, logical_h = self._required_size()
        if self._user_moved or self._user_resized:
            # 用户已经挪过位置/拉过大小：别再按配置摆一次，只按内容调整排版
            return self._resize_keep_position(
                HISTORY_WINDOW_MIN_H if self.history_open else 0
            )
        scaling = self._scaling()
        physical_w = int(round(logical_w * scaling))
        physical_h = int(round(logical_h * scaling))
        screen_w = self.root.winfo_screenwidth()      # 物理像素
        screen_h = self.root.winfo_screenheight()
        x, y = resolve_position(ui, (screen_w, screen_h), (physical_w, physical_h))
        self._expected_size = (physical_w, physical_h)
        self.root.geometry(f"{logical_w}x{logical_h}+{x}+{y}")
        return physical_w, physical_h

    def _scaling(self) -> float:
        """customtkinter 实际使用的 DPI 缩放系数。"""

        return float(ScalingTracker.get_window_dpi_scaling(self.root)) or 1.0

    def _required_size(self) -> tuple[int, int]:
        """按内容算出窗口需要的逻辑尺寸（配置里的宽高只当下限）。"""

        ui = self.config.ui
        self.root.update_idletasks()
        scaling = self._scaling()
        # winfo_req* 是物理像素，先换回逻辑像素跟配置取大，再换回物理算位置
        needed_w = int(self.root.winfo_reqwidth() / scaling + 0.5)
        needed_h = int(self.root.winfo_reqheight() / scaling + 0.5)
        logical_w = max(int(ui.width), needed_w)
        logical_h = max(needed_h, int(ui.height))     # 高度贴内容，配置值只当下限
        return logical_w, logical_h

    def _resize_keep_position(self, extra_h: int = 0) -> tuple[int, int]:
        """只按内容改尺寸、**不动位置**。

        窗口被挪过之后，再触发翻译/折叠/历史时不能跳回初始位置（曾经的 bug）。
        extra_h 用来给历史浮层留出高度。
        """

        logical_w, logical_h = self._required_size()
        if extra_h:
            logical_h = max(logical_h, int(extra_h))
        if self._user_resized:
            # 用户自己拉过大小：只根据当前尺寸调整排版，不再改尺寸
            self._apply_layout()
            return (self.root.winfo_width(), self.root.winfo_height())
        scaling = self._scaling()
        physical_w = int(round(logical_w * scaling))
        physical_h = int(round(logical_h * scaling))
        x, y = self.root.winfo_x(), self.root.winfo_y()      # 当前位置（物理像素）
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, min(x, screen_w - physical_w))
        y = max(0, min(y, screen_h - physical_h))
        self._expected_size = (physical_w, physical_h)
        self.root.geometry(f"{logical_w}x{logical_h}+{x}+{y}")
        return physical_w, physical_h

    # ---- 排版：横向拉长左右并排，纵向拉宽上下排列 ----
    def _on_card_configure(self, event) -> None:
        """窗口尺寸变化（含用户拖边缘）时，重新决定译文/原文怎么排。"""

        if self._layout_pending is not None:
            try:
                self.root.after_cancel(self._layout_pending)
            except Exception:  # pragma: no cover
                pass
        width, height = int(event.width), int(event.height)
        self._layout_pending = self.root.after(120, lambda: self._after_resize(width, height))

    def _after_resize(self, width: int, height: int) -> None:
        self._layout_pending = None
        expected_w, expected_h = self._expected_size
        if abs(width - expected_w) > 8 or abs(height - expected_h) > 8:
            self._user_resized = True       # 是用户自己拉的，别再被自动尺寸覆盖
        self._apply_layout()

    def _apply_layout(self) -> None:
        """横向拉长的窗口：译文和原文左右并排；否则上下排列（默认）。"""

        if self.history_open:
            return                          # 看历史时不掺和
        width = max(1, self.card.winfo_width())
        height = max(1, self.card.winfo_height())
        side_by_side = width >= height * 1.4
        if side_by_side == self._side_by_side:
            return
        self._side_by_side = side_by_side
        self.target.pack_forget()
        self.source_area.pack_forget()
        if side_by_side:
            self.target.pack(side="left", fill="both", expand=True, padx=(12, 6), pady=(8, 0))
            self.source_area.pack(side="left", fill="both", expand=True, padx=(6, 12), pady=(8, 0))
        elif not self.collapsed:
            self.target.pack(fill="x", padx=12, pady=(6, 0))
            self.source_area.pack(fill="x", padx=12)
        else:
            self.target.pack(fill="x", padx=12, pady=(6, 0))
        self._fit_text_areas(
            max(1, len(self.target.get("1.0", "end").strip().splitlines())),
            max(1, len(self.source.get("1.0", "end").strip().splitlines())),
            resize=False,          # 这里已经在处理尺寸了，别再回头调一次（会递归）
        )

    # ---- 顶部标题行 ----
    def _build_title(self) -> None:
        row = ctk.CTkFrame(self.card, corner_radius=0, fg_color="transparent")
        self.title_row = row
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
        # 时钟按钮：就在原来 ✕ 的位置（标题行最右），点开是窗内展开的历史翻译
        self.history_button = ctk.CTkButton(
            row, text="🕘", width=30, height=24, corner_radius=6, font=self.f_icon,
            fg_color="transparent", hover_color="#F1F1F1", text_color="#5F6368",
            command=self.toggle_history,
        )
        self.history_button.pack(side="right", padx=2)
        # 「连续」开关：守护选区，文字一变就自动翻译（和 Alt+C 一个作用）
        self.watch_button = ctk.CTkButton(
            row, text="连续", width=52, height=24, corner_radius=6, font=self.f_meta,
            fg_color="transparent", hover_color="#F1F1F1", text_color="#5F6368",
            command=self._toggle_watch,
        )
        self.watch_button.pack(side="right", padx=2)
        # 最小化 / 关闭交给外框的标题栏按钮，这里不再重复放一份
        for widget in (row, self.card):
            widget.bind("<Button-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag)
            widget.bind("<Double-Button-1>", lambda _event: self.toggle_collapsed())

    # ---- 译文 / 原文 ----
    def _build_text(self) -> None:
        # 译文/原文与历史面板都放在 body 里，切换时只换 body 的内容
        self.body = ctk.CTkFrame(self.card, corner_radius=0, fg_color="transparent")
        self.body.pack(fill="both", expand=True)      # 铺满，避免底下留一片白
        self.target = ctk.CTkTextbox(
            self.body, wrap="word", font=self.f_result, fg_color="transparent",
            text_color="#111111", corner_radius=0, border_width=0, height=44,
        )
        self.target.pack(fill="x", padx=12, pady=(6, 0))
        # 译文可以直接改：改完点状态栏右边的「保存修正」，写回缓存与术语表
        self.target.bind("<<Modified>>", self._on_target_modified)
        self.source_area = ctk.CTkFrame(self.body, corner_radius=0, fg_color="transparent")
        self.source_area.pack(fill="x", padx=12)
        self.source = ctk.CTkTextbox(
            self.source_area, wrap="word", font=self.f_source, fg_color="transparent",
            text_color="#8A8A8A", corner_radius=0, border_width=0, height=30,
        )
        self.source.pack(fill="x")

    def _build_meta(self) -> None:
        row = ctk.CTkFrame(self.card, corner_radius=0, fg_color="transparent")
        row.pack(side="bottom", fill="x", padx=16, pady=(0, 2))
        self.meta_row = row
        self.status = ctk.CTkLabel(
            row, text="", anchor="w", justify="left",
            font=self.f_meta, text_color="#9A9A9A",
        )
        self.status.pack(side="left", fill="x", expand=True)
        # 只有用户动过译文才露出来（平时不占地方）
        self.correction_button = ctk.CTkButton(
            row, text="保存修正", width=72, height=20, corner_radius=4, font=self.f_meta,
            fg_color="#E8F0FE", hover_color="#DCE7FB", text_color="#1A73E8",
            command=self.save_corrections,
        )

    # ---- 底部按钮 ----
    def _build_buttons(self) -> None:
        bar = ctk.CTkFrame(self.card, corner_radius=0, fg_color="transparent")
        bar.pack(side="bottom", fill="x", padx=12, pady=(8, 8))
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

    # ---- 历史翻译（叠在原窗口上的小浮层）----
    def _build_history_panel(self) -> None:
        """一块比主窗口小、纯白不透明的浮层，用 place 盖在窗口内容上。

        它的样式刻意跟主窗口不一样：自己的标题条 + 列表式记录（时间徽章、译文、原文）。
        """

        panel = ctk.CTkFrame(
            self.card, corner_radius=10, fg_color="#FFFFFF", border_width=1,
            border_color="#D5D8DD", width=HISTORY_PANEL_W, height=HISTORY_PANEL_H,
        )
        self.history_panel = panel

        bar = ctk.CTkFrame(panel, corner_radius=0, fg_color="#EDF1F7", height=28)
        bar.pack(fill="x")
        ctk.CTkLabel(bar, text="🕘 历史翻译", font=self.f_source,
                     text_color="#33415C").pack(side="left", padx=10)
        ctk.CTkButton(bar, text="✕", width=22, height=20, corner_radius=4,
                      fg_color="transparent", hover_color="#DDE3EC", text_color="#5F6368",
                      font=self.f_meta, command=self.toggle_history).pack(side="right", padx=6, pady=4)
        ctk.CTkLabel(bar, text="最近 20 次 · 退出后清空", font=self.f_meta,
                     text_color="#8A93A5").pack(side="right", padx=2)

        self.history_list = ctk.CTkScrollableFrame(panel, corner_radius=0, fg_color="transparent")
        self.history_list.pack(fill="both", expand=True, padx=6, pady=6)
        self._render_history_list([])

        # 浮层的空白处按住也能拖整个窗口（它自己不能单独移动，只跟着窗口走）
        for widget in (panel, bar):
            widget.bind("<Button-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag)

    def _clear_history_list(self) -> None:
        for child in list(self.history_list.winfo_children()):
            child.destroy()

    def _render_history_list(self, entries: list[HistoryEntry]) -> None:
        self._clear_history_list()
        if not entries:
            ctk.CTkLabel(self.history_list, text="还没有翻译记录", font=self.f_source,
                         text_color="#9AA0A6").pack(anchor="w", padx=6, pady=14)
            return
        for entry in entries:
            block = ctk.CTkFrame(self.history_list, corner_radius=6, fg_color="#F7F8FA")
            block.pack(fill="x", padx=1, pady=(0, 6))
            head = ctk.CTkFrame(block, corner_radius=0, fg_color="transparent")
            head.pack(fill="x", padx=8, pady=(6, 0))
            ctk.CTkLabel(head, text=entry.clock, font=self.f_meta, text_color="#1A73E8",
                         fg_color="#E8F0FE", corner_radius=4, width=44, height=18).pack(side="left")
            if entry.region:
                ctk.CTkLabel(head, text=entry.region, font=self.f_meta,
                             text_color="#B0B4BA").pack(side="right")
            for source, target in entry.pairs():
                ctk.CTkLabel(block, text=target, font=self.f_source, text_color="#1B1B1B",
                             anchor="w", justify="left", wraplength=240).pack(
                    fill="x", padx=10, pady=(4, 0)
                )
                ctk.CTkLabel(block, text=source, font=self.f_meta, text_color="#8A8F98",
                             anchor="w", justify="left", wraplength=240).pack(
                    fill="x", padx=10, pady=(0, 4)
                )

    def show_history(self, entries: list[HistoryEntry]) -> None:
        """更新历史内容（浮层没展开也照更新，下次打开就是最新的）。"""

        self._history_entries = list(entries)
        if self.history_open:
            self._render_history_list(self._history_entries)

    def refresh_history(self) -> None:
        provider = self.history_provider
        if provider is not None:
            self.show_history(provider())
        elif self.history_open:
            self._render_history_list(self._history_entries)

    def history_text(self) -> str:
        """把当前历史内容拼成文本（测试与排查用）。"""

        return render_entries(self._history_entries)

    def toggle_history(self) -> None:
        """时钟按钮：在窗口上叠一块小浮层显示历史，再点收起。"""

        if not self.history_open and self.collapsed:
            self.toggle_collapsed()          # 折叠状态下先展开
        self.history_open = not self.history_open
        if self.history_open:
            self._status_before_history = self.status_text()
            self._height_before_history = self.root.winfo_height()
            self.refresh_history()
            self.history_panel.place(
                relx=1.0, x=-HISTORY_PANEL_RIGHT, y=HISTORY_PANEL_TOP, anchor="ne"
            )
            self.history_button.configure(fg_color="#E8F0FE", text_color="#1A73E8")
            self.set_status("历史翻译：最近 20 次（再点时钟收起，设置里可看全部）")
        else:
            self.history_panel.place_forget()
            self.history_button.configure(fg_color="transparent", text_color="#5F6368")
            # 收起后恢复原来的状态文字，别让"历史翻译…"留在状态栏里
            self.set_status(self._status_before_history or "待取词：把鼠标移到物品上按热键")
        # 只改尺寸、不动位置：挪过窗口之后也不会跳回原位
        self._resize_keep_position(HISTORY_WINDOW_MIN_H if self.history_open else 0)

    def _provider_label(self) -> str:
        from mchanhua.translate.providers import find_preset

        preset = find_preset(self.config.translate.provider)
        return preset.label.split("（")[0] if preset else self.config.translate.provider

    # ---- 窗口行为 ----
    def set_opacity(self, value: float) -> None:
        """立即调整窗口透明度（设置里拖滑块时实时预览）。"""

        try:
            opacity = max(0.3, min(1.0, float(value)))
        except (TypeError, ValueError):
            return
        self.config.ui.opacity = opacity
        self._apply_alpha()

    def _apply_light_title_bar(self) -> None:
        """外框（标题栏）保持白色：系统深色主题下默认是黑的，这里强制浅色。"""

        use_light_title_bar(self.root)
        # 窗口映射 / DWM 处理标题栏是在之后发生的，再补两次更稳
        self.root.after(150, lambda: use_light_title_bar(self.root))
        self.root.after(500, lambda: use_light_title_bar(self.root))

    def _apply_alpha(self) -> None:
        try:
            # 总是写一遍：透明度调回 1.0 时也要真的恢复不透明
            self.root.attributes("-alpha", max(0.3, min(1.0, float(self.config.ui.opacity))))
        except (tk.TclError, TypeError, ValueError):  # pragma: no cover
            pass

    def _start_drag(self, event) -> None:
        self._user_moved = True           # 用户开始拖窗口：之后不再自动摆位置
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
            # 按钮行不再藏起来：它固定在窗口底部，折叠时也一直点得到
            self.set_status("已折叠（双击标题行可展开）")
        else:
            if not self.history_open:      # 正在看历史时别把原文区又塞回来
                self._side_by_side = False          # 强制重新按当前尺寸排版
                self._apply_layout()
            self.set_status("已展开（译文在上，原文在下）")
        # 折叠/展开只改尺寸，别把挪过的窗口拉回原位
        self._resize_keep_position(HISTORY_WINDOW_MIN_H if self.history_open else 0)

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

    def _toggle_watch(self) -> None:
        self._call("on_toggle_watch")

    def set_watch_active(self, active: bool) -> None:
        """连续翻译开着的时候把按钮点亮，一眼看得出现在正守着选区。"""

        self.watch_button.configure(
            text="连续中" if active else "连续",
            fg_color="#E8F0FE" if active else "transparent",
            text_color="#1A73E8" if active else "#5F6368",
        )

    def _open_settings(self) -> None:
        self._call("on_open_settings")

    def _quit(self) -> None:
        self._call("on_quit")

    def _clear(self) -> None:
        self._write_text(self.target, [])
        self._write_text(self.source, [])
        self._result = None
        self._target_map = []
        self._hide_correction_button()
        self.set_status("待取词：把鼠标移到物品上按热键")
        self._fit_text_areas(1, 1)        # 清空后收回一行高，窗口跟着变矮

    def show_notice(self, text: str) -> None:
        """只显示一条提示（例如"选区内没有识别到文字"），并清掉上一次的结果。"""

        if self.history_open:
            self.toggle_history()
        self._clear()
        self.set_status(text)

    # ---- 显示 ----
    def set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def status_text(self) -> str:
        return str(self.status.cget("text"))

    def show_source(self, lines: list[str], elapsed_ms: float) -> None:
        self.source.delete("1.0", "end")
        self.source.insert("1.0", "\n".join(lines))
        self._fit_text_areas(result_lines=1, source_lines=len(lines))
        self.set_status(f"OCR {elapsed_ms:.0f} ms · 正在翻译…")

    def show_result(self, result: PipelineResult) -> None:
        if self.history_open:              # 有新结果就先回到译文视图
            self.toggle_history()
        self._result = result
        self._hide_correction_button()
        # 多区域结果按区域分组，插一行「［区域1］」当标题
        if getattr(result, "paragraph", ""):
            # 模型整理过的整段译文更好读；原始行放在下面（按区域标注）方便对照
            body_lines, body_map = self._labelled_with_map(result.output_lines, result.line_areas)
            target_lines = [result.paragraph, ""] + body_lines
            target_map: list[int | None] = [None, None] + body_map
        else:
            target_lines, target_map = self._labelled_with_map(
                result.output_lines, result.line_areas
            )
        source_lines = self._with_area_labels(result.source_lines, result.line_areas)
        self._write_text(self.target, target_lines)
        self._write_text(self.source, source_lines)
        self._target_map = target_map
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
        areas = [name for name in result.line_areas if name]
        unique_areas = list(dict.fromkeys(areas))
        if unique_areas:
            parts.append(f"{len(unique_areas)} 个区域：{'/'.join(unique_areas)}")
        if getattr(result, "paragraph", ""):
            parts.append("已整理成段")
        if result.warnings:
            parts.append(f"提示：{result.warnings[0]}")
        self.set_status(" · ".join(parts))
        self._fit_text_areas(len(target_lines) or 1, len(source_lines) or 1)

    @staticmethod
    def _with_area_labels(lines: list[str], labels: list[str]) -> list[str]:
        """给多区域的每一组前面插一行「［区域1］」；单区域时原样返回。"""

        return ResultWindow._labelled_with_map(lines, labels)[0]

    @staticmethod
    def _labelled_with_map(
        lines: list[str], labels: list[str]
    ) -> tuple[list[str], list[int | None]]:
        """同上，但额外给出「显示的每一行对应原来的第几行」——分组标题是 None。

        手动修正译文时要靠这个映射把改过的行对回原文，所以不能只有文本。
        """

        if not labels or len(labels) != len(lines) or not any(labels):
            return list(lines), list(range(len(lines)))
        out: list[str] = []
        mapping: list[int | None] = []
        current: str | None = None
        for index, (text, label) in enumerate(zip(lines, labels)):
            if label != current:
                out.append(f"［{label}］")
                mapping.append(None)
                current = label
            out.append(text)
            mapping.append(index)
        return out, mapping

    def _write_text(self, box, lines: list[str]) -> None:
        """程序自己往文本框里写：期间不要算成"用户改了译文"。"""

        self._editing_programmatically = True
        try:
            box.delete("1.0", "end")
            box.insert("1.0", "\n".join(lines))
        finally:
            self._editing_programmatically = False
            try:
                box.edit_modified(False)
            except Exception:  # pragma: no cover - 个别实现没有这个开关
                pass

    # ---- 手动修正译文 ----
    def _on_target_modified(self, _event=None) -> None:
        """用户在译文框里敲字了：把「保存修正」露出来。"""

        try:
            changed = bool(self.target.edit_modified())
            self.target.edit_modified(False)      # 复位标志，下一次改动还能触发
        except Exception:  # pragma: no cover
            changed = True
        if not changed or self._editing_programmatically:
            return
        self._show_correction_button()

    def _show_correction_button(self) -> None:
        if self._corrections_pending:
            return
        self._corrections_pending = True
        self.correction_button.pack(side="right", padx=(8, 0))
        self.set_status("译文可以直接改：改完点「保存修正」写回缓存与术语表")

    def _hide_correction_button(self) -> None:
        self._corrections_pending = False
        try:
            self.correction_button.pack_forget()
        except Exception:  # pragma: no cover
            pass

    def correction_pairs(self) -> list[tuple[str, str]]:
        """把改过的译文对回原文，返回 [(原文, 新译文), …]（没改的行不算）。"""

        result = self._result
        if result is None or not self._target_map:
            return []
        lines = self.target.get("1.0", "end").splitlines()
        pairs: list[tuple[str, str]] = []
        for shown, line in zip(self._target_map, lines):
            if shown is None or not 0 <= shown < len(result.source_lines):
                continue
            if line.strip() and line.strip() != result.output_lines[shown].strip():
                pairs.append((result.source_lines[shown], line.strip()))
        return pairs

    def save_corrections(self) -> None:
        """点「保存修正」：交给控制器写回缓存/术语表。"""

        result = self._result
        if result is None:
            self.set_status("还没有译文可以修正")
            return
        lines = self.target.get("1.0", "end").splitlines()
        if len(lines) != len(self._target_map):
            self.set_status(
                f"行数对不上了（现在 {len(lines)} 行，原本 {len(self._target_map)} 行）："
                "修正时别增删行，改文字就行"
            )
            return
        pairs = self.correction_pairs()
        if not pairs:
            self._hide_correction_button()
            self.set_status("译文没有变化，不用保存")
            return
        # 记下改过哪几行：保存之后结果本身也要跟着更新，不然再点一次又会被当成"改了"
        keep = list(result.output_lines)
        for shown, line in zip(self._target_map, lines):
            if shown is not None and 0 <= shown < len(keep):
                keep[shown] = line.strip()
        callback = getattr(self.callbacks, "on_save_corrections", None)
        if callback is not None:
            callback(pairs)
        result.output_lines = keep
        self._hide_correction_button()

    def _fit_text_areas(self, result_lines: int, source_lines: int, resize: bool = True) -> None:
        """译文/原文区跟着内容长高：没有结果时只留一行，不留一大片空白。"""

        def units(lines: int, font, max_lines: int) -> int:
            size = abs(int(font.cget("size"))) or 13
            # 1.6 倍字号：行高 1.5 倍再留一点余量，避免出现滚动条
            return max(1, min(lines, max_lines)) * round(size * 1.6)

        if self._side_by_side:
            # 左右并排时，两个框都撑到差不多半窗高，不然右边会空一大截
            scaling = self._scaling()
            half = max(60, int(self.card.winfo_height() / scaling * 0.55))
            self.target.configure(height=half)
            self.source.configure(height=half)
        else:
            self.target.configure(height=units(result_lines, self.f_result, 5))
            self.source.configure(height=units(source_lines, self.f_source, 4))
        if resize and not self._user_resized:
            self._resize_keep_position()

    def on_poll(self) -> None:
        if self.heartbeat is not None:
            self.heartbeat()

    def drain(self, message_queue: "queue.Queue[tuple]", max_messages: int = 50) -> int:
        return drain_queue(message_queue, self, max_messages)

    def poll(self, message_queue: "queue.Queue[tuple]", interval_ms: int = 60) -> None:
        # 先把下一次心跳排进队列再干活：drain 里可能弹框选遮罩（wait_window 会阻塞
        # 这个回调），要是把 after 放在最后，遮罩开着的几秒中心跳就断了，
        # 看门狗会误报"界面卡死"。
        self.root.after(interval_ms, lambda: self.poll(message_queue, interval_ms))
        self.on_poll()
        self.drain(message_queue)

    def run(self) -> None:
        self.root.mainloop()
