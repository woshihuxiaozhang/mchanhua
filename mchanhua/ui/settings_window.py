"""设置窗口（与主界面同一套外观：圆角卡片 + 浅色主题）。

三个标签页：翻译服务（含 API Key 输入框）、热键（可录制）、界面外观。
所有值最终写回 config.toml；热键与服务保存后立即生效，外观重启后生效。
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import colorchooser, messagebox
from typing import Callable

import customtkinter as ctk

from mchanhua.config import Config, save_config
from mchanhua.hotkey import find_conflicts, normalize_hotkey
from mchanhua.logging_setup import get_logger
from mchanhua.paths import app_dir, log_dir
from mchanhua.translate.connection import test_connection
from mchanhua.translate.providers import PRESETS, guess_provider
from mchanhua.ui.hotkey_capture import hotkey_from_event
from mchanhua.ui.theme import Theme
from mchanhua.ui.window import _is_dark

HOTKEY_LABELS = (
    ("translate", "翻译自定义选区"),
    ("translate_region", "框选并立即翻译"),
    ("translate_fullscreen", "全屏翻译"),
    ("translate_clipboard", "翻译剪贴板图片"),
    ("select_region", "只框选选区"),
    ("quit", "退出程序"),
)


class SettingsWindow:
    def __init__(
        self,
        config: Config,
        on_saved: Callable[[Config], None] | None = None,
        parent: tk.Misc | None = None,
    ) -> None:
        self.config = config
        self.on_saved = on_saved
        self.theme = Theme.from_config(config.ui)
        ctk.set_appearance_mode("dark" if _is_dark(self.theme.background) else "light")

        self.root = ctk.CTkToplevel(parent) if parent is not None else ctk.CTk()
        self.root.title("mchanhua 设置")
        self.root.geometry("660x620")
        self.root.configure(fg_color=self.theme.background)
        self._vars: dict[str, tk.Variable] = {}

        theme = self.theme
        self.font = ctk.CTkFont(family=theme.font_family, size=max(11, theme.font_size))
        self.small = ctk.CTkFont(family=theme.font_family, size=max(9, theme.source_font_size))

        self._build_header()
        self._build_tabs()
        self._build_footer()

        if parent is not None:
            self.root.transient(parent)
            self.root.grab_set()

    # ---- 外观小工具 ----
    def _label(self, parent, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(parent, text=text, font=self.small, text_color=self.theme.text_dim)

    def _entry(self, parent, key: str, value: str, show: str = "") -> ctk.CTkEntry:
        var = tk.StringVar(value=value)
        self._vars[key] = var
        return ctk.CTkEntry(
            parent, textvariable=var, height=30, corner_radius=6, font=self.font,
            fg_color=self.theme.panel, text_color=self.theme.text, border_width=1,
            border_color=self.theme.button_background, show=show,
        )

    def _button(self, parent, text: str, command, primary: bool = False) -> ctk.CTkButton:
        theme = self.theme
        return ctk.CTkButton(
            parent, text=text, command=command, height=30, corner_radius=6, font=self.small,
            fg_color=theme.accent if primary else theme.button_background,
            hover_color=theme.accent if primary else theme.panel,
            text_color=theme.background if primary else theme.button_text,
            border_width=0 if primary else 1, border_color=theme.button_background,
        )

    def _build_header(self) -> None:
        bar = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        bar.pack(fill="x", padx=14, pady=(12, 4))
        ctk.CTkLabel(
            bar, text="译", width=24, height=24, corner_radius=6,
            fg_color=self.theme.accent, text_color=self.theme.background, font=self.small,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(bar, text="设置", font=self.font, text_color=self.theme.text).pack(side="left")
        ctk.CTkButton(
            bar, text="✕", width=28, height=24, corner_radius=6, fg_color="transparent",
            hover_color=self.theme.panel, text_color=self.theme.text_dim, font=self.small,
            command=self.root.destroy,
        ).pack(side="right")

    def _build_tabs(self) -> None:
        tabs = ctk.CTkTabview(
            self.root, corner_radius=8, fg_color=self.theme.panel,
            segmented_button_selected_color=self.theme.accent,
            segmented_button_selected_hover_color=self.theme.accent,
            text_color=self.theme.text,
        )
        tabs.pack(fill="both", expand=True, padx=14, pady=4)
        self._build_service(tabs.add("翻译服务"))
        self._build_hotkeys(tabs.add("热键"))
        self._build_appearance(tabs.add("界面外观"))

    # ---- 翻译服务 ----
    def _build_service(self, parent) -> None:
        translate = self.config.translate
        provider_key = guess_provider(translate.base_url, translate.model)
        default_label = next(
            (preset.label for preset in PRESETS if preset.key == provider_key), PRESETS[0].label
        )
        provider_var = tk.StringVar(value=default_label)
        self._vars["provider"] = provider_var

        rows = (
            ("服务商", None),
            ("接口地址", ("base_url", translate.base_url)),
            ("模型名", ("model", translate.model)),
            ("API Key", ("api_key", translate.api_key)),
        )
        for index, (label, spec) in enumerate(rows):
            self._label(parent, label).grid(row=index, column=0, sticky="w", padx=(4, 12), pady=8)
            if spec is None:
                combo = ctk.CTkComboBox(
                    parent, variable=provider_var, values=[preset.label for preset in PRESETS],
                    height=30, corner_radius=6, font=self.font, state="readonly",
                    fg_color=self.theme.panel, border_color=self.theme.button_background,
                    button_color=self.theme.button_background, text_color=self.theme.text,
                    command=lambda _value: self._apply_preset(),
                )
                combo.grid(row=index, column=1, sticky="we", pady=8)
                self._combo = combo
            else:
                key, value = spec
                show = "•" if key == "api_key" else ""
                entry = self._entry(parent, key, value, show=show)
                entry.grid(row=index, column=1, sticky="we", pady=8)
                if key == "api_key":
                    self._api_entry = entry

        self._vars["show_key"] = tk.BooleanVar(value=False)
        ctk.CTkSwitch(
            parent, text="显示 API Key", variable=self._vars["show_key"], font=self.small,
            progress_color=self.theme.accent, command=self._toggle_key_visibility,
        ).grid(row=4, column=1, sticky="w", pady=(0, 6))

        actions = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        actions.grid(row=5, column=1, sticky="w", pady=6)
        self._button(actions, "测试连接", self.test_connection).pack(side="left")
        self._test_label = ctk.CTkLabel(actions, text="", font=self.small, text_color=self.theme.text_dim)
        self._test_label.pack(side="left", padx=10)

        self._label(
            parent,
            "API Key 只保存在本机的 config.toml 里；翻译时仅发送识别出的文字给所选服务商。",
        ).grid(row=6, column=0, columnspan=2, sticky="w", padx=4, pady=(14, 0))
        parent.columnconfigure(1, weight=1)

    def _toggle_key_visibility(self) -> None:
        self._api_entry.configure(show="" if self._vars["show_key"].get() else "•")

    def _apply_preset(self) -> None:
        label = self._vars["provider"].get()
        preset = next((item for item in PRESETS if item.label == label), None)
        if preset is None or preset.key == "custom":
            return
        self._vars["base_url"].set(preset.base_url)
        self._vars["model"].set(preset.model)

    # ---- 热键 ----
    def _build_hotkeys(self, parent) -> None:
        self._label(
            parent, "点输入框后直接按下组合键即可；也可手动输入（例如 ctrl+alt、alt+/）"
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=4, pady=(6, 10))
        for index, (key, label) in enumerate(HOTKEY_LABELS, start=1):
            self._label(parent, label).grid(row=index, column=0, sticky="w", padx=(4, 12), pady=7)
            entry = self._entry(parent, f"hotkey.{key}", getattr(self.config.hotkeys, key))
            entry.grid(row=index, column=1, sticky="we", pady=7)
            entry.bind("<KeyPress>", lambda event, k=key: self._capture(event, k))
        self._label(
            parent,
            "提示：纯修饰键（如 ctrl+alt）按下即触发，会与以它为前缀的组合冲突，保存时会检查。",
        ).grid(row=len(HOTKEY_LABELS) + 1, column=0, columnspan=2, sticky="w", padx=4, pady=(12, 0))
        parent.columnconfigure(1, weight=1)

    def _capture(self, event, key: str) -> str:
        hotkey = hotkey_from_event(event.keysym, int(event.state))
        if hotkey:
            self._vars[f"hotkey.{key}"].set(hotkey)
        return "break"

    # ---- 界面外观 ----
    def _build_appearance(self, parent) -> None:
        ui = self.config.ui
        numbers = (
            ("窗口宽度", "width", ui.width),
            ("窗口高度", "height", ui.height),
            ("原文字号", "source_font_size", ui.source_font_size),
            ("译文字号", "result_font_size", ui.result_font_size),
            ("内边距", "padding", ui.padding),
            ("透明度(0.3~1.0)", "opacity", ui.opacity),
        )
        for index, (label, key, value) in enumerate(numbers):
            self._label(parent, label).grid(row=index, column=0, sticky="w", padx=(4, 12), pady=7)
            self._entry(parent, f"ui.{key}", str(value)).grid(row=index, column=1, sticky="w", pady=7)

        colors = (
            ("背景色", "background", ui.background),
            ("面板色", "panel", ui.panel),
            ("文字色", "text", ui.text),
            ("强调色", "accent", ui.accent),
        )
        for offset, (label, key, value) in enumerate(colors):
            row = len(numbers) + offset
            self._label(parent, label).grid(row=row, column=0, sticky="w", padx=(4, 12), pady=7)
            self._entry(parent, f"ui.{key}", value).grid(row=row, column=1, sticky="w", pady=7)
            self._button(parent, "选择…", lambda k=key: self._pick_color(k)).grid(
                row=row, column=2, sticky="w", padx=8
            )
        self._label(parent, "界面外观改动在重启程序后生效").grid(
            row=len(numbers) + len(colors), column=1, sticky="w", pady=(12, 0)
        )
        parent.columnconfigure(1, weight=1)

    def _pick_color(self, key: str) -> None:
        var = self._vars[f"ui.{key}"]
        chosen = colorchooser.askcolor(color=str(var.get()) or "#ffffff")[1]
        if chosen:
            var.set(chosen)

    # ---- 底部按钮 ----
    def _build_footer(self) -> None:
        bar = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        bar.pack(fill="x", padx=14, pady=(4, 12))
        self._button(bar, "保存并应用", self.save, primary=True).pack(side="left")
        self._button(bar, "取消", self.root.destroy).pack(side="left", padx=6)
        self._button(bar, "打开日志目录", self._open_log_dir).pack(side="right")
        self._button(bar, "打开配置目录", self._open_config_dir).pack(side="right", padx=6)

    def _open_config_dir(self) -> None:
        path = app_dir()
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)  # noqa: S606 - 用户主动点按钮

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
            if value:
                setattr(config.hotkeys, key, value)

        for key in ("width", "height", "source_font_size", "result_font_size", "padding"):
            raw = str(self._vars[f"ui.{key}"].get()).strip()
            if raw.isdigit():
                setattr(config.ui, key, int(raw))
        try:
            config.ui.opacity = float(str(self._vars["ui.opacity"].get()).strip())
        except ValueError:
            pass
        for key in ("background", "panel", "text", "accent"):
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
        problems.extend(find_conflicts(bindings))
        from mchanhua.ui.contrast import check_colors

        problems.extend(
            check_colors(
                {
                    "background": str(self._vars["ui.background"].get()),
                    "panel": str(self._vars["ui.panel"].get()),
                    "text": str(self._vars["ui.text"].get()),
                    "text_dim": str(self._vars.get("ui.text_dim", tk.StringVar(value="#5f6470")).get()),
                    "accent": str(self._vars["ui.accent"].get()),
                }
            )
        )
        if not str(self._vars["base_url"].get()).strip():
            problems.append("接口地址不能为空")
        if not str(self._vars["model"].get()).strip():
            problems.append("模型名不能为空")
        return problems

    def test_connection(self) -> None:
        self._test_label.configure(text="正在测试…", text_color=self.theme.text_dim)
        self.root.update_idletasks()
        try:
            config = self.collect()
            result = test_connection(config.translate, config.resolved_api_key)
            self._test_label.configure(text=f"连接正常：{result}", text_color="#1a9e5f")
        except Exception as exc:  # noqa: BLE001 - 错误要显示在界面上
            get_logger().warning("测试连接失败：%s", exc)
            self._test_label.configure(text=f"失败：{exc}", text_color="#d23f3f")

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
        messagebox.showinfo(
            "已保存",
            f"已保存到：\n{path}\n\n热键与翻译服务立即生效，界面外观重启后生效。",
        )

    def run(self) -> None:
        self.root.mainloop()


def open_settings(
    config: Config,
    on_saved: Callable[[Config], None] | None = None,
    parent: tk.Misc | None = None,
) -> None:
    if parent is not None:
        SettingsWindow(config, on_saved, parent=parent)   # 模态窗口
        return
    SettingsWindow(config, on_saved).run()
