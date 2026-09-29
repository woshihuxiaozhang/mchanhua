"""设置窗口：按参考图实现——白卡片、文字标签页、灰底输入框。

四个标签页：翻译服务（含 API Key 独立输入框）、热键（可录制 / 可选择按键）、
界面外观、历史翻译（全部记录，只存在内存里，退出程序即清空）。
保存后热键与翻译服务立即生效，界面外观重启后生效。
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import colorchooser, messagebox
from typing import Callable

import customtkinter as ctk

from mchanhua.config import MAX_AREAS, Config, save_config
from mchanhua.history import TranslationHistory, render_entries
from mchanhua.hotkey import find_conflicts, normalize_hotkey
from mchanhua.logging_setup import get_logger
from mchanhua.paths import app_dir, log_dir
from mchanhua.translate.connection import test_connection
from mchanhua.translate.providers import PRESETS, guess_provider
from mchanhua.ui.hotkey_capture import ComboTracker
from mchanhua.ui.hotkey_picker import pick_hotkey
from mchanhua.ui.theme import DEFAULT_LIGHT
from mchanhua.ui.titlebar import use_light_title_bar
from mchanhua.ui.window import _is_dark

HOTKEY_LABELS = (
    ("translate", "翻译自定义选区"),
    ("translate_region", "框选并立即翻译"),
    ("translate_fullscreen", "全屏翻译"),
    ("translate_clipboard", "翻译剪贴板图片"),
    ("select_region", "只框选选区"),
    ("quit", "退出程序"),
)

CARD = "#FFFFFF"
FIELD = "#F5F5F5"
LINE = "#E8E8E8"
TEXT = "#1B1B1B"
LABEL = "#8A8A8A"
BLUE = "#1A73E8"
BLUE_SOFT = "#E8F0FE"


class SettingsWindow:
    def __init__(
        self,
        config: Config,
        on_saved: Callable[[Config], None] | None = None,
        parent: tk.Misc | None = None,
        pause_hotkeys: Callable[[], None] | None = None,
        resume_hotkeys: Callable[[], None] | None = None,
        history: TranslationHistory | None = None,
        on_history_cleared: Callable[[], None] | None = None,
        preview_opacity: Callable[[float], None] | None = None,
    ) -> None:
        self.config = config
        self.on_saved = on_saved
        # 录制热键时把全局热键暂停，免得一边录一边把翻译触发了
        self.pause_hotkeys = pause_hotkeys
        self.resume_hotkeys = resume_hotkeys
        self.history = history
        self.on_history_cleared = on_history_cleared
        # 拖透明度滑块时给主窗口做即时预览
        self.preview_opacity = preview_opacity
        ctk.set_appearance_mode("dark" if _is_dark(config.ui.background) else "light")
        self.root = ctk.CTkToplevel(parent) if parent is not None else ctk.CTk()
        self.root.title("mchanhua 设置")
        self.root.geometry("820x540")     # 先给个初始尺寸，随后按当前页内容自适应高度
        self.root.configure(fg_color="#F7F7F7")
        use_light_title_bar(self.root)    # 外框保持白色，不跟随系统深色主题
        self.root.after(300, lambda: use_light_title_bar(self.root))
        self._vars: dict[str, tk.Variable] = {}
        self._trackers: dict[str, ComboTracker] = {}
        self._capture_previous: dict[str, str] = {}
        self._pages: dict[str, ctk.CTkFrame] = {}
        self._page_bodies: dict[str, ctk.CTkScrollableFrame] = {}
        self._tab_buttons: dict[str, ctk.CTkButton] = {}

        family = config.ui.font_family or "Microsoft YaHei UI"
        self.f_label = ctk.CTkFont(family=family, size=13)
        self.f_field = ctk.CTkFont(family=family, size=14)
        self.f_small = ctk.CTkFont(family=family, size=11)

        self.card = ctk.CTkFrame(self.root, corner_radius=12, fg_color=CARD,
                                 border_width=1, border_color=LINE)
        self.card.pack(fill="both", expand=True, padx=10, pady=10)
        self._build_header()
        self._build_tabs()
        self._build_service()
        self._build_hotkeys()
        self._build_appearance()
        self._build_areas()
        self._build_history()
        self._build_footer()
        self._show_page("翻译服务")
        # 页面高度按内容自适应：能一屏放完就不用滚（滚动容器只当兜底）
        self.root.after(250, self._fit_window_height)
        if parent is not None:
            self.root.transient(parent)
            self.root.grab_set()

    # ---- 通用小部件 ----
    def _field(self, parent, key: str, value: str, show: str = "", width: int = 0):
        var = tk.StringVar(value=value)
        self._vars[key] = var
        entry = ctk.CTkEntry(
            parent, textvariable=var, height=34, corner_radius=6, font=self.f_field,
            fg_color=FIELD, text_color=TEXT, border_width=1, border_color=LINE, show=show,
        )
        return entry

    def _button(self, parent, text: str, command, primary: bool = False, width: int = 0):
        return ctk.CTkButton(
            parent, text=text, command=command, height=34, corner_radius=6, font=self.f_label,
            fg_color=BLUE_SOFT if primary else CARD,
            hover_color="#DCE7FB" if primary else FIELD,
            text_color=BLUE if primary else "#3C4043",
            border_width=0 if primary else 1, border_color="#E0E0E0",
            width=width,
        )

    def _row(self, parent, row: int, label: str, key: str, value: str, show: str = ""):
        ctk.CTkLabel(parent, text=label, font=self.f_label, text_color=LABEL,
                     width=90, anchor="w").grid(row=row, column=0, sticky="w", padx=(8, 12), pady=9)
        entry = self._field(parent, key, value, show=show)
        entry.grid(row=row, column=1, sticky="we", pady=9, padx=(0, 8))
        return entry

    def _build_header(self) -> None:
        row = ctk.CTkFrame(self.card, corner_radius=0, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(row, text="⚙", width=20, font=self.f_label, text_color=LABEL).pack(side="left")
        ctk.CTkLabel(row, text="设置", font=self.f_field, text_color=TEXT).pack(side="left", padx=6)
        # 显示实际读取的配置文件路径，便于排查"改了配置没生效"
        from mchanhua.config import resolve_config_path

        try:
            path_hint = str(resolve_config_path())
        except Exception:  # pragma: no cover
            path_hint = "?"
        ctk.CTkLabel(row, text=path_hint, font=self.f_small, text_color=LABEL).pack(
            side="left", padx=(10, 0)
        )
        ctk.CTkLabel(row, text=f"构建 {self._build_stamp()}", font=self.f_small,
                     text_color=LABEL).pack(side="right", padx=(0, 8))

    @staticmethod
    def _build_stamp() -> str:
        """显示程序自身的构建时间：用来区分"你启动的是不是最新那一版"。"""

        import sys
        import time
        from pathlib import Path

        target = Path(sys.executable) if getattr(sys, "frozen", False) else Path(__file__)
        try:
            return time.strftime("%m-%d %H:%M", time.localtime(target.stat().st_mtime))
        except OSError:  # pragma: no cover
            return "?"
        ctk.CTkButton(row, text="✕", width=28, height=24, corner_radius=6, fg_color="transparent",
                      hover_color=FIELD, text_color=LABEL, font=self.f_small,
                      command=self.root.destroy).pack(side="right")

    def _build_tabs(self) -> None:
        row = ctk.CTkFrame(self.card, corner_radius=0, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(4, 8))
        for name in ("翻译服务", "热键", "界面外观", "选区", "历史翻译"):
            button = ctk.CTkButton(
                row, text=name, width=0, height=28, corner_radius=6, font=self.f_label,
                fg_color="transparent", hover_color=FIELD, text_color=LABEL,
                command=lambda n=name: self._show_page(n),
            )
            button.pack(side="left", padx=(0, 6))
            self._tab_buttons[name] = button
        self.pages_area = ctk.CTkFrame(self.card, corner_radius=0, fg_color="transparent")
        self.pages_area.pack(fill="both", expand=True, padx=10, pady=(0, 6))

    def _show_page(self, name: str) -> None:
        for page in self._pages.values():
            page.pack_forget()
        page = self._pages.get(name)
        if page is not None:
            page.pack(fill="both", expand=True)
        self._current_page = name
        for tab, button in self._tab_buttons.items():
            active = tab == name
            button.configure(fg_color=FIELD if active else "transparent",
                             text_color=TEXT if active else LABEL)
        self.root.after(30, self._fit_window_height)
        # 切页之后自定义控件偶尔会漏画（输入框看着是空的），补一次重绘
        self.root.after(90, self._redraw_widgets)

    def _fit_window_height(self) -> None:
        """按当前页内容把窗口调到刚好放得下（最高不超过屏幕的 90%）。"""

        try:
            from customtkinter import ScalingTracker

            self.root.update_idletasks()
            body = self._page_bodies.get(getattr(self, "_current_page", ""))
            if body is None or not self.pages_area.winfo_height():
                return
            # geometry 里的数字是"逻辑像素"，winfo_* 给的是物理像素，先换算
            scaling = float(ScalingTracker.get_window_dpi_scaling(self.root)) or 1.0
            overhead = int((self.card.winfo_height() - self.pages_area.winfo_height()) / scaling)
            needed = int(body.winfo_reqheight() / scaling + 0.5) + overhead + 12
            screen_h = int(self.root.winfo_screenheight() / scaling)
            width = 820
            target = max(520, min(int(screen_h * 0.9), needed))
            self.root.geometry(f"{width}x{target}")
            self.root.after(30, self._redraw_widgets)
        except tk.TclError:  # pragma: no cover - 窗口已销毁
            pass

    def _redraw_widgets(self) -> None:
        """滚动之后把自定义控件的画布重画一遍（customtkinter 在滚动容器里偶尔漏画）。"""

        stack = list(self.card.winfo_children())
        while stack:
            widget = stack.pop()
            stack.extend(widget.winfo_children())
            draw = getattr(widget, "_draw", None)
            if callable(draw):
                try:
                    draw()
                except Exception:  # pragma: no cover - 个别控件没有 _draw
                    pass

    def _make_page(self, name: str) -> ctk.CTkFrame:
        """一页 = 外层容器（用来显示/隐藏）+ 里面可滚动的正文。

        内容多的页（界面外观、历史翻译）以前会被窗口切掉、又滚不动，
        所以正文一律放进 CTkScrollableFrame：放不下就能滚。
        """

        holder = ctk.CTkFrame(self.pages_area, corner_radius=0, fg_color="transparent")
        body = ctk.CTkScrollableFrame(
            holder, corner_radius=0, fg_color="transparent",
            scrollbar_button_color="#C9CDD4", scrollbar_button_hover_color="#AEB4BF",
        )
        body._parent_frame.pack(fill="both", expand=True)   # 真正要显示的是外层容器
        body.columnconfigure(1, weight=1)
        # 滚动过之后补一次重绘，免得输入框里的字被"漏画"
        body.bind("<MouseWheel>", lambda _event: self.root.after(30, self._redraw_widgets), add="+")
        body._parent_canvas.bind(
            "<MouseWheel>", lambda _event: self.root.after(30, self._redraw_widgets), add="+"
        )
        body._scrollbar.bind(
            "<B1-Motion>", lambda _event: self.root.after(30, self._redraw_widgets), add="+"
        )
        self._pages[name] = holder
        self._page_bodies[name] = body
        return body

    # ---- 翻译服务 ----
    def _build_service(self) -> None:
        page = self._make_page("翻译服务")
        translate = self.config.translate
        key = guess_provider(translate.base_url, translate.model)
        label = next((p.label for p in PRESETS if p.key == key), PRESETS[0].label)
        self._vars["provider"] = tk.StringVar(value=label)

        ctk.CTkLabel(page, text="服务商", font=self.f_label, text_color=LABEL, width=90,
                     anchor="w").grid(row=0, column=0, sticky="w", padx=(8, 12), pady=9)
        combo = ctk.CTkComboBox(
            page, variable=self._vars["provider"], values=[p.label for p in PRESETS],
            height=34, corner_radius=6, font=self.f_field, state="readonly",
            fg_color=FIELD, border_color=LINE, button_color=FIELD, text_color=TEXT,
            dropdown_fg_color=CARD, dropdown_text_color=TEXT,
            command=lambda _v: self._apply_preset(),
        )
        combo.grid(row=0, column=1, sticky="we", pady=9, padx=(0, 8))
        self._row(page, 1, "接口地址", "base_url", translate.base_url)
        self._row(page, 2, "模型名", "model", translate.model)

        ctk.CTkLabel(page, text="API Key", font=self.f_label, text_color=LABEL, width=90,
                     anchor="w").grid(row=3, column=0, sticky="w", padx=(8, 12), pady=9)
        holder = ctk.CTkFrame(page, corner_radius=6, fg_color=FIELD, border_width=1, border_color=LINE)
        holder.grid(row=3, column=1, sticky="we", pady=9, padx=(0, 8))
        var = tk.StringVar(value=translate.api_key)
        self._vars["api_key"] = var
        entry = ctk.CTkEntry(holder, textvariable=var, font=self.f_field, show="•",
                             fg_color="transparent", border_width=0, text_color=TEXT)
        entry.pack(side="left", fill="x", expand=True, padx=(8, 0), pady=2)
        self._api_entry = entry
        self._vars["show_key"] = tk.BooleanVar(value=False)
        ctk.CTkButton(holder, text="👁", width=32, height=28, corner_radius=4, fg_color="transparent",
                      hover_color=CARD, text_color=LABEL, font=self.f_label,
                      command=self._toggle_key_visibility).pack(side="right", padx=2, pady=2)

        actions = ctk.CTkFrame(page, corner_radius=0, fg_color="transparent")
        actions.grid(row=4, column=1, sticky="w", pady=(4, 6), padx=(0, 8))
        self._button(actions, "⚡ 测试连接", self.test_connection).pack(side="left")
        self._test_label = ctk.CTkLabel(actions, text="", font=self.f_label, text_color="#5F6368")
        self._test_label.pack(side="left", padx=10)

        ctk.CTkLabel(page, text="API Key 只保存在本机的 config.toml 里：翻译时仅把识别出的文字发给所选服务商。",
                     font=self.f_small, text_color=LABEL, anchor="w").grid(
            row=5, column=0, columnspan=2, sticky="w", padx=8, pady=(10, 0)
        )

    def _toggle_key_visibility(self) -> None:
        self._api_entry.configure(show="" if self._vars["show_key"].get() else "•")
        self._vars["show_key"].set(not self._vars["show_key"].get())

    def _apply_preset(self) -> None:
        label = self._vars["provider"].get()
        preset = next((item for item in PRESETS if item.label == label), None)
        if preset is None or preset.key == "custom":
            return
        self._vars["base_url"].set(preset.base_url)
        self._vars["model"].set(preset.model)

    # ---- 热键 ----
    def _build_hotkeys(self) -> None:
        page = self._make_page("热键")
        ctk.CTkLabel(
            page,
            text="点「选择按键」按住一个或多个键就能选（只按 Ctrl+Alt 也算，Esc 取消）。"
                 "也可以点输入框直接按键录制。留空 = 不注册。",
            font=self.f_small, text_color=LABEL, anchor="w", justify="left", wraplength=600,
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(4, 10))
        self._vars["capture_in_entry"] = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            page, text="在输入框里直接按键录制（关掉后可以手动输入）",
            variable=self._vars["capture_in_entry"], font=self.f_small, text_color=LABEL,
            fg_color=BLUE, hover_color=BLUE, checkbox_width=16, checkbox_height=16,
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 8))
        for index, (key, label) in enumerate(HOTKEY_LABELS, start=2):
            entry = self._row(page, index, label, f"hotkey.{key}", getattr(self.config.hotkeys, key))
            self._bind_entry_capture(entry, key)
            self._button(page, "选择按键", lambda k=key: self._pick_hotkey(k), width=88).grid(
                row=index, column=2, sticky="w", padx=(0, 8)
            )

    def _bind_entry_capture(self, entry, key: str) -> None:
        """输入框里直接按键录制：按住、松开都跟着记，只按修饰键也能录出来。"""

        self._trackers[key] = ComboTracker()
        entry.bind("<FocusIn>", lambda _event, k=key: self._capture_focus_in(k))
        entry.bind("<FocusOut>", lambda _event, k=key: self._capture_focus_out(k))
        entry.bind("<KeyPress>", lambda event, k=key: self._capture_press(event, k))
        entry.bind("<KeyRelease>", lambda event, k=key: self._capture_release(event, k))

    def _capture_focus_in(self, key: str) -> None:
        if not self._capture_mode():
            return
        self._trackers[key].reset()
        self._capture_previous[key] = str(self._vars[f"hotkey.{key}"].get())
        self._set_hotkey_var(key, "")          # 进入输入框先清空，避免和旧值混在一起
        if self.pause_hotkeys is not None:
            try:
                self.pause_hotkeys()           # 录的时候别把翻译触发了
            except Exception:  # pragma: no cover - 暂停失败不该拦住录制
                pass

    def _capture_focus_out(self, key: str) -> None:
        if not self._capture_mode():
            return
        if not self._trackers[key].candidate:
            # 点进来又点走、什么都没按：把原来的热键还回去，别悄悄清空
            self._set_hotkey_var(key, self._capture_previous.get(key, ""))
        if self.resume_hotkeys is not None:
            try:
                self.resume_hotkeys()
            except Exception:  # pragma: no cover
                pass

    def _capture_press(self, event, key: str) -> str:
        if not self._capture_mode():
            return ""
        if (event.keysym or "").lower() == "escape":
            return "break"
        candidate = self._trackers[key].press(event.keysym)
        if candidate:
            self._set_hotkey_var(key, candidate)
        return "break"

    def _capture_release(self, event, key: str) -> str:
        if not self._capture_mode():
            return ""
        candidate = self._trackers[key].release(event.keysym)
        if candidate:
            self._set_hotkey_var(key, candidate)
        return "break"

    def _capture_mode(self) -> bool:
        var = self._vars.get("capture_in_entry")
        return True if var is None else bool(var.get())

    def _set_hotkey_var(self, key: str, value: str) -> None:
        self._vars[f"hotkey.{key}"].set(value)

    def _pick_hotkey(self, key: str) -> None:
        """弹「选择按键」对话框，把选好的组合写回这一行。"""

        label = dict(HOTKEY_LABELS).get(key, key)
        current = str(self._vars[f"hotkey.{key}"].get()).strip()
        chosen = pick_hotkey(
            self.root,
            title=f"选择热键：{label}",
            initial=current,
            on_pause=self.pause_hotkeys,
            on_resume=self.resume_hotkeys,
        )
        if chosen is None:          # 取消：什么都不动
            return
        self._vars[f"hotkey.{key}"].set(chosen)
        get_logger().info("热键已选择：%s = %r", label, chosen)

    # ---- 界面外观 ----
    def _build_appearance(self) -> None:
        page = self._make_page("界面外观")
        ui = self.config.ui
        numbers = (
            ("最小宽度", "width", ui.width),
            ("最小高度", "height", ui.height),
            ("原文字号", "source_font_size", ui.source_font_size),
            ("译文字号", "result_font_size", ui.result_font_size),
            ("内边距", "padding", ui.padding),
        )
        for index, (label, key, value) in enumerate(numbers):
            self._row(page, index, label, f"ui.{key}", str(value))
        colors = (
            ("面板色", "panel", ui.panel),
            ("正文色", "text", ui.text),
            ("次级色", "text_dim", ui.text_dim),
            ("强调色", "accent", ui.accent),
        )
        offset = len(numbers)
        for index, (label, key, value) in enumerate(colors):
            row = offset + index
            entry = self._row(page, row, label, f"ui.{key}", value)
            self._button(page, "选择…", lambda k=key: self._pick_color(k), width=64).grid(
                row=row, column=2, sticky="w", padx=(0, 8)
            )

        # ---- 透明度：拖滑块即时预览 ----
        opacity_row = offset + len(colors)
        self._vars.setdefault("ui.opacity", tk.StringVar(value=str(ui.opacity)))
        ctk.CTkLabel(page, text="界面透明度", font=self.f_label, text_color=LABEL,
                     width=90, anchor="w").grid(row=opacity_row, column=0, sticky="w",
                                                padx=(8, 12), pady=9)
        self._opacity_value = ctk.CTkLabel(page, text=f"{float(ui.opacity):.2f}",
                                           font=self.f_label, text_color=TEXT, width=44)
        self._opacity_value.grid(row=opacity_row, column=2, sticky="w", padx=(0, 8))
        self._opacity_slider = ctk.CTkSlider(
            page, from_=0.3, to=1.0, number_of_steps=70, height=18,
            fg_color="#E3E6EB", progress_color=BLUE, button_color=BLUE,
            button_hover_color="#1668D8", command=self._on_opacity_slide,
        )
        self._opacity_slider.set(float(ui.opacity))
        self._opacity_slider.grid(row=opacity_row, column=1, sticky="we", pady=9, padx=(0, 8))

        self._button(page, "恢复默认主题", self.restore_default_theme).grid(
            row=opacity_row + 1, column=1, sticky="w", pady=(12, 0), padx=(0, 8)
        )

    # ---- 透明度 ----
    def _on_opacity_slide(self, value: float) -> None:
        self._vars["ui.opacity"].set(f"{float(value):.2f}")
        self._opacity_value.configure(text=f"{float(value):.2f}")
        if self.preview_opacity is not None:
            self.preview_opacity(float(value))

    def _pick_color(self, key: str) -> None:
        chosen = colorchooser.askcolor(color=str(self._vars[f"ui.{key}"].get()) or "#FFFFFF")[1]
        if chosen:
            self._vars[f"ui.{key}"].set(chosen)

    def restore_default_theme(self) -> None:
        for key, value in DEFAULT_LIGHT.items():
            var = self._vars.get(f"ui.{key}")
            if var is not None:
                var.set(str(value))
        messagebox.showinfo("已恢复默认主题", "配色已恢复为默认，点「保存并应用」生效。")

    # ---- 选区（多区域）----
    def _build_areas(self) -> None:
        page = self._make_page("选区")
        ctk.CTkLabel(
            page,
            text="Ctrl+Alt 会一次翻译所有勾选的区域（整屏只抓一次、OCR 一次）。\n"
                 "新增区域：在游戏里按 Alt+V 连续框选（Enter 存一个，Delete 撤掉上一个）。\n"
                 "删除区域：下面每一行右边的「删除」按钮；勾选框只控制「要不要翻译它」。\n"
                 f"最多保存 {MAX_AREAS} 个区域；"
                 "注意：默认退出程序会清空所有区域（想留着继续用，把 config.toml 里的 "
                 "clear_on_exit 改成 false）。",
            font=self.f_small, text_color=LABEL, anchor="w", justify="left", wraplength=620,
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=(4, 8))

        self._area_rows = ctk.CTkFrame(page, corner_radius=0, fg_color="transparent")
        self._area_rows.grid(row=1, column=0, columnspan=3, sticky="we", padx=8, pady=(0, 8))
        page.columnconfigure(1, weight=1)

        actions = ctk.CTkFrame(page, corner_radius=0, fg_color="transparent")
        actions.grid(row=2, column=0, columnspan=3, sticky="w", padx=8, pady=(0, 8))
        self._button(actions, "全部启用", lambda: self._toggle_all_areas(True)).pack(side="left")
        self._button(actions, "全部停用", lambda: self._toggle_all_areas(False)).pack(
            side="left", padx=8
        )
        self._button(actions, "删除全部", self._clear_areas).pack(side="left")
        self.render_areas()

    def render_areas(self) -> None:
        """把已保存的区域列成一排排可编辑的行。"""

        for child in list(self._area_rows.winfo_children()):
            child.destroy()
        config = self.collect_areas_only()
        names = config.regions.area_names()
        if not names:
            ctk.CTkLabel(
                self._area_rows,
                text="还没有区域。在游戏里按 Alt+V 框一个：Enter 保存，Backspace/Esc 结束。",
                font=self.f_label, text_color=LABEL,
            ).pack(anchor="w", pady=8)
            return
        for name in names:
            row = ctk.CTkFrame(self._area_rows, corner_radius=6, fg_color=FIELD)
            row.pack(fill="x", pady=4)
            enabled = tk.BooleanVar(value=name in config.regions.areas)
            ctk.CTkCheckBox(
                row, text="", variable=enabled, width=24, checkbox_width=18, checkbox_height=18,
                fg_color=BLUE, hover_color=BLUE,
                command=lambda n=name, v=enabled: self._set_area_enabled(n, v.get()),
            ).pack(side="left", padx=(8, 4), pady=8)
            ctk.CTkLabel(row, text=name, font=self.f_label, text_color=TEXT, width=110,
                         anchor="w").pack(side="left")
            region = config.regions.fixed_region(name)
            ctk.CTkLabel(row, text=region.to_csv() if region else "?", font=self.f_small,
                         text_color=LABEL, anchor="w").pack(side="left", padx=6)
            self._button(row, "删除", lambda n=name: self._remove_area(n), width=56).pack(
                side="right", padx=8, pady=6
            )
            self._button(row, "改名", lambda n=name: self._rename_area_prompt(n), width=56).pack(
                side="right", pady=6
            )

    def _set_area_enabled(self, name: str, enabled: bool) -> None:
        self.collect_areas_only().regions.set_area_enabled(name, enabled)
        self._persist_areas()
        self.render_areas()

    def _toggle_all_areas(self, enabled: bool) -> None:
        config = self.collect_areas_only()
        for name in config.regions.area_names():
            config.regions.set_area_enabled(name, enabled)
        self._persist_areas()
        self.render_areas()

    def _remove_area(self, name: str) -> None:
        config = self.collect_areas_only()
        config.regions.remove_area(name)
        self._persist_areas()
        self.render_areas()
        get_logger().info("已删除区域：%s", name)

    def _clear_areas(self) -> None:
        config = self.collect_areas_only()
        if not config.regions.area_names():
            return
        if not messagebox.askyesno("删除全部区域", "确定删掉所有已保存的选区吗？"):
            return
        config.regions.fixed.clear()
        config.regions.areas = []
        self._persist_areas()
        self.render_areas()

    def _rename_area_prompt(self, name: str) -> None:
        dialog = ctk.CTkInputDialog(title="给区域改名", text=f"「{name}」改成：")
        new_name = (dialog.get_input() or "").strip()
        if not new_name:
            return
        try:
            self.collect_areas_only().regions.rename_area(name, new_name)
        except ValueError as exc:
            messagebox.showerror("改不了名字", str(exc))
            return
        self._persist_areas()
        self.render_areas()

    def _persist_areas(self) -> None:
        """区域是"在游戏里框完就生效"的东西，设置里改动也立刻落盘，免得以为删了其实没删。"""

        try:
            save_config(self.config)
        except Exception:  # pragma: no cover - 磁盘异常
            get_logger().exception("保存区域设置失败")

    def collect_areas_only(self) -> Config:
        """只把"当前的区域设置"整理出来（设置窗口里其它输入框还没保存也没关系）。"""

        return self.config

    # ---- 历史翻译 ----
    def _build_history(self) -> None:
        page = self._make_page("历史翻译")
        ctk.CTkLabel(
            page,
            text="小窗里的时钟按钮只看最近 20 次；这里是全部记录。"
                 "记录只放在内存里，退出程序后自动清除，不占空间。",
            font=self.f_small, text_color=LABEL, anchor="w", justify="left", wraplength=620,
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(4, 8))

        self._history_text = ctk.CTkTextbox(
            page, wrap="word", font=self.f_field, fg_color=FIELD, text_color=TEXT,
            corner_radius=6, border_width=1, border_color=LINE, height=300,
        )
        self._history_text.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=8, pady=(0, 8))
        page.rowconfigure(1, weight=1)

        actions = ctk.CTkFrame(page, corner_radius=0, fg_color="transparent")
        actions.grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 6))
        self._button(actions, "刷新", self.render_history).pack(side="left")
        self._button(actions, "清空历史", self.clear_history).pack(side="left", padx=8)
        self._history_count = ctk.CTkLabel(actions, text="", font=self.f_small, text_color=LABEL)
        self._history_count.pack(side="left", padx=8)
        self.render_history()

    def render_history(self) -> None:
        entries = self.history.all() if self.history is not None else []
        self._history_text.configure(state="normal")
        self._history_text.delete("1.0", "end")
        self._history_text.insert("1.0", render_entries(entries))
        self._history_text.configure(state="disabled")
        self._history_count.configure(text=f"共 {len(entries)} 条" if entries else "")

    def clear_history(self) -> None:
        if self.history is None:
            return
        if not messagebox.askyesno("清空历史", "确定要清空全部历史翻译记录吗？"):
            return
        removed = self.history.clear()
        self.render_history()
        if self.on_history_cleared is not None:
            self.on_history_cleared()
        get_logger().info("已清空历史翻译：%d 条", removed)

    # ---- 底部 ----
    def _build_footer(self) -> None:
        row = ctk.CTkFrame(self.card, corner_radius=0, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(4, 12))
        self._button(row, "保存并应用", self.save, primary=True, width=120).pack(side="left")
        self._button(row, "取消", self.root.destroy, width=90).pack(side="left", padx=8)
        self._button(row, "打开日志目录", self._open_log_dir, width=120).pack(side="right")
        self._button(row, "打开配置目录", self._open_config_dir, width=120).pack(side="right", padx=8)

    def _open_config_dir(self) -> None:
        path = app_dir()
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)  # noqa: S606 - 用户主动点击

    def _open_log_dir(self) -> None:
        path = log_dir()
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)  # noqa: S606

    # ---- 收集 / 校验 / 保存 ----
    def collect(self) -> Config:
        config = self.config
        label = self._vars["provider"].get()
        preset = next((item for item in PRESETS if item.label == label), None)
        config.translate.provider = preset.key if preset else "custom"
        config.translate.base_url = str(self._vars["base_url"].get()).strip()
        config.translate.model = str(self._vars["model"].get()).strip()
        config.translate.api_key = str(self._vars["api_key"].get()).strip()
        for key, _label in HOTKEY_LABELS:
            value = str(self._vars[f"hotkey.{key}"].get()).strip()
            setattr(config.hotkeys, key, value)
        for key in ("width", "height", "source_font_size", "result_font_size", "padding"):
            raw = str(self._vars[f"ui.{key}"].get()).strip()
            if raw.isdigit():
                setattr(config.ui, key, int(raw))
        try:
            config.ui.opacity = float(str(self._vars["ui.opacity"].get()).strip())
        except ValueError:
            pass
        for key in ("panel", "text", "text_dim", "accent"):
            value = str(self._vars[f"ui.{key}"].get()).strip()
            if value:
                setattr(config.ui, key, value)
        return config

    def validate(self) -> list[str]:
        problems: list[str] = []
        bindings: dict[str, str] = {}
        for key, label in HOTKEY_LABELS:
            value = str(self._vars[f"hotkey.{key}"].get()).strip()
            if not value:
                continue
            try:
                normalize_hotkey(value)
            except ValueError as exc:
                problems.append(f"{label}：{exc}")
                continue
            bindings[label] = value
        problems.extend(find_conflicts(bindings, include_overlap=False))
        if not str(self._vars["base_url"].get()).strip():
            problems.append("接口地址不能为空")
        if not str(self._vars["model"].get()).strip():
            problems.append("模型名不能为空")
        return problems

    def test_connection(self) -> None:
        self._test_label.configure(text="正在测试…", text_color=LABEL)
        self.root.update_idletasks()
        try:
            config = self.collect()
            result = test_connection(config.translate, config.resolved_api_key)
            self._test_label.configure(text=f"连接正常：{result}", text_color="#1A73E8")
        except Exception as exc:  # noqa: BLE001 - 错误显示在界面上
            get_logger().warning("测试连接失败：%s", exc)
            self._test_label.configure(text=f"失败：{exc}", text_color="#D93025")

    def save(self) -> None:
        problems = self.validate()
        if problems:
            messagebox.showerror("设置有误", "\n".join(problems))
            return
        config = self.collect()
        try:
            path = save_config(config)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("保存失败", str(exc))
            return
        get_logger().info("设置已保存：%s", path)
        if self.on_saved is not None:
            self.on_saved(config)
        messagebox.showinfo("已保存", f"已保存到：\n{path}\n\n热键与翻译服务立即生效，界面外观重启后生效。")

    def run(self) -> None:
        self.root.mainloop()


def open_settings(
    config: Config,
    on_saved: Callable[[Config], None] | None = None,
    parent: tk.Misc | None = None,
    pause_hotkeys: Callable[[], None] | None = None,
    resume_hotkeys: Callable[[], None] | None = None,
    history: TranslationHistory | None = None,
    on_history_cleared: Callable[[], None] | None = None,
    preview_opacity: Callable[[float], None] | None = None,
) -> None:
    if parent is not None:
        SettingsWindow(config, on_saved, parent=parent,
                       pause_hotkeys=pause_hotkeys, resume_hotkeys=resume_hotkeys,
                       history=history, on_history_cleared=on_history_cleared,
                       preview_opacity=preview_opacity)
        return
    SettingsWindow(config, on_saved,
                   pause_hotkeys=pause_hotkeys, resume_hotkeys=resume_hotkeys,
                   history=history, on_history_cleared=on_history_cleared,
                   preview_opacity=preview_opacity).run()
