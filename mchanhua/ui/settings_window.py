"""设置窗口：翻译服务（含 API Key 输入框）、热键自定义、界面外观。"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk
from typing import Callable

from mchanhua.config import Config, save_config
from mchanhua.hotkey import find_conflicts, normalize_hotkey
from mchanhua.logging_setup import get_logger
from mchanhua.paths import app_dir, log_dir
from mchanhua.translate.connection import test_connection
from mchanhua.translate.providers import PRESETS, guess_provider
from mchanhua.ui.hotkey_capture import hotkey_from_event

HOTKEY_LABELS = (
    ("translate", "翻译自定义选区"),
    ("translate_region", "框选并立即翻译"),
    ("translate_fullscreen", "全屏翻译"),
    ("translate_clipboard", "翻译剪贴板图片"),
    ("select_region", "只框选选区"),
    ("quit", "退出程序"),
)


class SettingsWindow:
    """所有设置项都从配置读、保存时写回配置。"""

    def __init__(
        self,
        config: Config,
        on_saved: Callable[[Config], None] | None = None,
        parent: tk.Misc | None = None,
    ) -> None:
        self.config = config
        self.on_saved = on_saved
        # 有父窗口时用 Toplevel，避免在同一进程里开两个 Tk root
        self.root = tk.Toplevel(parent) if parent is not None else tk.Tk()
        self.root.title("mchanhua 设置")
        self.root.geometry("640x580")
        self._vars: dict[str, tk.Variable] = {}
        self._build()
        if parent is not None:
            self.root.transient(parent)
            self.root.grab_set()

    def _build(self) -> None:
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        service = ttk.Frame(notebook)
        hotkeys = ttk.Frame(notebook)
        appearance = ttk.Frame(notebook)
        notebook.add(service, text="翻译服务")
        notebook.add(hotkeys, text="热键")
        notebook.add(appearance, text="界面外观")

        self._build_service(service)
        self._build_hotkeys(hotkeys)
        self._build_appearance(appearance)

        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(bar, text="保存并应用", command=self.save).pack(side="left")
        ttk.Button(bar, text="取消", command=self.root.destroy).pack(side="left", padx=6)
        ttk.Button(bar, text="打开日志目录", command=self._open_log_dir).pack(side="right")
        ttk.Button(bar, text="打开配置目录", command=self._open_config_dir).pack(side="right", padx=6)

    # ---- 翻译服务 ----
    def _build_service(self, parent: ttk.Frame) -> None:
        translate = self.config.translate
        provider_key = guess_provider(translate.base_url, translate.model)
        default_label = next(
            (preset.label for preset in PRESETS if preset.key == provider_key), PRESETS[0].label
        )
        self._vars["provider"] = tk.StringVar(value=default_label)
        self._vars["base_url"] = tk.StringVar(value=translate.base_url)
        self._vars["model"] = tk.StringVar(value=translate.model)
        self._vars["api_key"] = tk.StringVar(value=translate.api_key)
        self._vars["show_key"] = tk.BooleanVar(value=False)

        ttk.Label(parent, text="服务商").grid(row=0, column=0, sticky="w", padx=10, pady=8)
        combo = ttk.Combobox(
            parent,
            textvariable=self._vars["provider"],
            values=[preset.label for preset in PRESETS],
            state="readonly",
            width=42,
        )
        combo.grid(row=0, column=1, sticky="we", pady=8)
        combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_preset())

        ttk.Label(parent, text="接口地址").grid(row=1, column=0, sticky="w", padx=10, pady=8)
        ttk.Entry(parent, textvariable=self._vars["base_url"], width=46).grid(
            row=1, column=1, sticky="we", pady=8
        )

        ttk.Label(parent, text="模型名").grid(row=2, column=0, sticky="w", padx=10, pady=8)
        ttk.Entry(parent, textvariable=self._vars["model"], width=46).grid(
            row=2, column=1, sticky="we", pady=8
        )

        ttk.Label(parent, text="API Key").grid(row=3, column=0, sticky="w", padx=10, pady=8)
        self._api_entry = ttk.Entry(parent, textvariable=self._vars["api_key"], width=46, show="*")
        self._api_entry.grid(row=3, column=1, sticky="we", pady=8)
        ttk.Checkbutton(
            parent,
            text="显示 API Key",
            variable=self._vars["show_key"],
            command=self._toggle_key_visibility,
        ).grid(row=4, column=1, sticky="w", pady=(0, 8))

        ttk.Button(parent, text="测试连接", command=self.test_connection).grid(
            row=5, column=1, sticky="w", pady=6
        )
        self._test_label = ttk.Label(parent, text="", foreground="#0a7")
        self._test_label.grid(row=6, column=1, sticky="w")
        ttk.Label(
            parent,
            text="API Key 只保存在本机配置文件里，不会上传到别处（翻译时只发给所选服务商）",
            wraplength=520,
        ).grid(row=7, column=0, columnspan=2, sticky="w", padx=10, pady=(12, 0))
        parent.columnconfigure(1, weight=1)

    # ---- 热键 ----
    def _build_hotkeys(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="点输入框后直接按下组合键即可（例如 Ctrl+Alt、Alt+/）；也可以手动输入",
            wraplength=560,
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 6))
        for index, (key, label) in enumerate(HOTKEY_LABELS, start=1):
            ttk.Label(parent, text=label).grid(row=index, column=0, sticky="w", padx=10, pady=6)
            var = tk.StringVar(value=getattr(self.config.hotkeys, key))
            self._vars[f"hotkey.{key}"] = var
            entry = ttk.Entry(parent, textvariable=var, width=24)
            entry.grid(row=index, column=1, sticky="w", pady=6)
            entry.bind("<KeyPress>", lambda event, k=key: self._capture(event, k))
        ttk.Label(
            parent,
            text="提示：纯修饰键（如 ctrl+alt）按下即触发，会与所有以它为前缀的组合冲突，保存时会检查。",
            wraplength=560,
        ).grid(row=len(HOTKEY_LABELS) + 1, column=0, columnspan=3, sticky="w", padx=10, pady=(12, 0))
        parent.columnconfigure(1, weight=1)

    # ---- 界面外观 ----
    def _build_appearance(self, parent: ttk.Frame) -> None:
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
            ttk.Label(parent, text=label).grid(row=index, column=0, sticky="w", padx=10, pady=6)
            var = tk.StringVar(value=str(value))
            self._vars[f"ui.{key}"] = var
            ttk.Entry(parent, textvariable=var, width=12).grid(row=index, column=1, sticky="w")

        colors = (
            ("背景色", "background", ui.background),
            ("面板色", "panel", ui.panel),
            ("文字色", "text", ui.text),
            ("强调色", "accent", ui.accent),
        )
        for offset, (label, key, value) in enumerate(colors):
            row = len(numbers) + offset
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=6)
            var = tk.StringVar(value=value)
            self._vars[f"ui.{key}"] = var
            ttk.Entry(parent, textvariable=var, width=12).grid(row=row, column=1, sticky="w")
            ttk.Button(parent, text="选择…", command=lambda v=var: self._pick_color(v)).grid(
                row=row, column=2, sticky="w", padx=6
            )
        ttk.Label(parent, text="界面外观改动在重启程序后生效").grid(
            row=len(numbers) + len(colors), column=1, sticky="w", pady=(10, 0)
        )
        parent.columnconfigure(1, weight=1)

    # ---- 交互 ----
    def _apply_preset(self) -> None:
        label = self._vars["provider"].get()
        preset = next((item for item in PRESETS if item.label == label), None)
        if preset is None or preset.key == "custom":
            return
        self._vars["base_url"].set(preset.base_url)
        self._vars["model"].set(preset.model)

    def _toggle_key_visibility(self) -> None:
        self._api_entry.configure(show="" if self._vars["show_key"].get() else "*")

    def _capture(self, event, key: str) -> str:
        hotkey = hotkey_from_event(event.keysym, int(event.state))
        if hotkey:
            self._vars[f"hotkey.{key}"].set(hotkey)
        return "break"

    def _pick_color(self, var: tk.StringVar) -> None:
        chosen = colorchooser.askcolor(color=var.get() or "#ffffff")[1]
        if chosen:
            var.set(chosen)

    def _open_config_dir(self) -> None:
        path = app_dir()
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)  # noqa: S606 - 用户主动点按钮打开文件夹

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
        config.translate.base_url = self._vars["base_url"].get().strip()
        config.translate.model = self._vars["model"].get().strip()
        config.translate.api_key = self._vars["api_key"].get().strip()

        for key, _label in HOTKEY_LABELS:
            value = self._vars[f"hotkey.{key}"].get().strip()
            if value:
                setattr(config.hotkeys, key, value)

        for key in ("width", "height", "source_font_size", "result_font_size", "padding"):
            raw = self._vars[f"ui.{key}"].get().strip()
            if raw.isdigit():
                setattr(config.ui, key, int(raw))
        try:
            config.ui.opacity = float(self._vars["ui.opacity"].get().strip())
        except ValueError:
            pass
        for key in ("background", "panel", "text", "accent"):
            value = self._vars[f"ui.{key}"].get().strip()
            if value:
                setattr(config.ui, key, value)
        return config

    def validate(self) -> list[str]:
        problems: list[str] = []
        bindings: dict[str, str] = {}
        for key, label in HOTKEY_LABELS:
            value = self._vars[f"hotkey.{key}"].get().strip()
            if not value:
                continue
            try:
                normalize_hotkey(value)
            except ValueError as exc:
                problems.append(f"{label}：{exc}")
                continue
            bindings[label] = value
        problems.extend(find_conflicts(bindings))
        if not self._vars["base_url"].get().strip():
            problems.append("接口地址不能为空")
        if not self._vars["model"].get().strip():
            problems.append("模型名不能为空")
        return problems

    def test_connection(self) -> None:
        self._test_label.configure(text="正在测试…", foreground="#888")
        self.root.update_idletasks()
        try:
            config = self.collect()
            result = test_connection(config.translate, config.resolved_api_key)
            self._test_label.configure(text=f"连接正常：{result}", foreground="#0a7")
        except Exception as exc:  # noqa: BLE001 - 错误要显示在界面上
            get_logger().warning("测试连接失败：%s", exc)
            self._test_label.configure(text=f"失败：{exc}", foreground="#c00")

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
        SettingsWindow(config, on_saved, parent=parent)   # 模态窗口，由父窗口管理生命周期
        return
    SettingsWindow(config, on_saved).run()
