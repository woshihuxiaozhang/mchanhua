"""首次使用向导：填 API Key → 知道怎么框选区 → 完成（可顺手开开机自启）。

只做三件事：把 key 填好、把热键讲清楚、把「开机自启」这种可选项摆出来。
界面风格与设置窗口一致：白卡片 + 灰底输入框。
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

import customtkinter as ctk

from mchanhua import autostart
from mchanhua.config import Config, save_config
from mchanhua.logging_setup import get_logger
from mchanhua.translate.connection import test_connection
from mchanhua.translate.providers import PRESETS, guess_provider
from mchanhua.ui.titlebar import use_light_title_bar
from mchanhua.ui.window import _is_dark

CARD = "#FFFFFF"
FIELD = "#F5F5F5"
LINE = "#E8E8E8"
TEXT = "#1B1B1B"
LABEL = "#8A8A8A"
BLUE = "#1A73E8"
BLUE_SOFT = "#E8F0FE"

STEP_TITLES = ("欢迎", "填个 API Key", "框选区 · 热键")


class SetupWizard:
    """三步向导；parent 不为空时是模态子窗口。"""

    def __init__(
        self,
        config: Config,
        on_done: Callable[[Config], None] | None = None,
        parent: tk.Misc | None = None,
    ) -> None:
        self.config = config
        self.on_done = on_done
        ctk.set_appearance_mode("dark" if _is_dark(config.ui.background) else "light")
        self.root = ctk.CTkToplevel(parent) if parent is not None else ctk.CTk()
        self.root.title("mchanhua 首次使用向导")
        self.root.geometry("620x460")
        self.root.minsize(560, 420)
        self.root.configure(fg_color="#F7F7F7")
        use_light_title_bar(self.root)
        self.root.after(300, lambda: use_light_title_bar(self.root))

        family = config.ui.font_family or "Microsoft YaHei UI"
        self.f_label = ctk.CTkFont(family=family, size=13)
        self.f_field = ctk.CTkFont(family=family, size=14)
        self.f_small = ctk.CTkFont(family=family, size=11)
        self.f_title = ctk.CTkFont(family=family, size=17, weight="bold")

        self.card = ctk.CTkFrame(self.root, corner_radius=12, fg_color=CARD,
                                 border_width=1, border_color=LINE)
        self.card.pack(fill="both", expand=True, padx=10, pady=10)
        self.step_label = ctk.CTkLabel(self.card, text="", font=self.f_small, text_color=LABEL)
        self.step_label.pack(anchor="w", padx=18, pady=(14, 0))
        self.body = ctk.CTkFrame(self.card, corner_radius=0, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=18, pady=(4, 0))

        self._vars: dict[str, tk.Variable] = {}
        self._pages: list[ctk.CTkFrame] = []
        self._build_pages()
        self._build_footer()
        self.step = 0
        self._show_step(0)

        if parent is not None:
            self.root.transient(parent)
            self.root.grab_set()
            self.root.after(200, self.root.focus_force)

    # ---- 步骤 ----
    def _build_pages(self) -> None:
        self._pages = [self._build_welcome(), self._build_service(), self._build_finish()]

    def _build_welcome(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.body, corner_radius=0, fg_color="transparent")
        ctk.CTkLabel(page, text="欢迎使用 mchanhua", font=self.f_title,
                     text_color=TEXT).pack(anchor="w", pady=(6, 10))
        ctk.CTkLabel(
            page,
            text="这是一个给自己玩的时候看懂外语的小工具：\n"
                 "按热键框住游戏里的文字 → 本地 OCR 识别 → 交给 AI 翻译 → 小窗里显示译文。\n\n"
                 "它只读取屏幕画面：不改动游戏文件，也不注入游戏进程。",
            font=self.f_label, text_color=TEXT, justify="left", anchor="w",
        ).pack(anchor="w", pady=(0, 14))
        box = ctk.CTkFrame(page, corner_radius=8, fg_color=FIELD)
        box.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(box, text="接下来两步：填一个翻译服务的 API Key（没有就选 Ollama 本地免费），"
                              "然后知道怎么框选区。大概一分钟。",
                     font=self.f_small, text_color=LABEL, justify="left", anchor="w",
                     wraplength=520).pack(anchor="w", padx=12, pady=10)
        return page

    def _build_service(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.body, corner_radius=0, fg_color="transparent")
        ctk.CTkLabel(page, text="选一个翻译服务", font=self.f_title,
                     text_color=TEXT).grid(row=0, column=0, columnspan=2, sticky="w", pady=(6, 10))

        translate = self.config.translate
        current = guess_provider(translate.base_url, translate.model)
        label = next(
            (preset.label for preset in PRESETS if preset.key == current), PRESETS[0].label
        )
        self._vars["provider"] = tk.StringVar(value=label)
        self._vars["api_key"] = tk.StringVar(value=translate.api_key)

        ctk.CTkLabel(page, text="服务商", font=self.f_label, text_color=LABEL, width=80,
                     anchor="w").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=8)
        ctk.CTkComboBox(
            page, variable=self._vars["provider"], values=[p.label for p in PRESETS],
            height=34, corner_radius=6, font=self.f_field, state="readonly", fg_color=FIELD,
            border_color=LINE, button_color=FIELD, text_color=TEXT,
            dropdown_fg_color=CARD, dropdown_text_color=TEXT,
        ).grid(row=1, column=1, sticky="we", pady=8)

        ctk.CTkLabel(page, text="API Key", font=self.f_label, text_color=LABEL, width=80,
                     anchor="w").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=8)
        ctk.CTkEntry(
            page, textvariable=self._vars["api_key"], height=34, corner_radius=6,
            font=self.f_field, fg_color=FIELD, text_color=TEXT, border_width=1,
            border_color=LINE, show="•",
        ).grid(row=2, column=1, sticky="we", pady=8)

        actions = ctk.CTkFrame(page, corner_radius=0, fg_color="transparent")
        actions.grid(row=3, column=1, sticky="w", pady=(2, 6))
        ctk.CTkButton(actions, text="⚡ 测试连接", command=self.test_connection, height=32,
                      corner_radius=6, font=self.f_label, fg_color=BLUE_SOFT,
                      hover_color="#DCE7FB", text_color=BLUE, border_width=0).pack(side="left")
        self._test_label = ctk.CTkLabel(actions, text="", font=self.f_small, text_color=LABEL)
        self._test_label.pack(side="left", padx=10)

        ctk.CTkLabel(
            page,
            text="DeepSeek 便宜、中文好（platform.deepseek.com）；想完全免费离线就选「Ollama 本地模型（免 key）」，"
                 "需要本机装好 Ollama。\nKey 只保存在本机的 config.toml 里，翻译时只会把识别出的文字发给所选服务商。",
            font=self.f_small, text_color=LABEL, justify="left", anchor="w", wraplength=520,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))
        return page

    def _build_finish(self) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.body, corner_radius=0, fg_color="transparent")
        ctk.CTkLabel(page, text="怎么用（热键都能在设置里改）", font=self.f_title,
                     text_color=TEXT).pack(anchor="w", pady=(6, 10))
        hotkeys = self.config.hotkeys
        rows = (
            (hotkeys.select_region or "（未设置）", "在游戏里框出要翻译的地方：Enter 存一个区域，Esc 结束"),
            (hotkeys.translate or "（未设置）", "翻译已保存的所有区域"),
            (hotkeys.watch or "（未设置）", "连续翻译：盯着选区，文字一变就自动翻（再按一次停止）"),
            (hotkeys.translate_region or "（未设置）", "框一块并立刻翻译，不保存"),
        )
        table = ctk.CTkFrame(page, corner_radius=8, fg_color=FIELD)
        table.pack(fill="x", pady=(0, 12))
        for index, (keys, text) in enumerate(rows):
            row = ctk.CTkFrame(table, corner_radius=0, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=(8 if index == 0 else 2, 0))
            ctk.CTkLabel(row, text=keys, font=self.f_label, text_color=BLUE, width=110,
                         anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=text, font=self.f_small, text_color=TEXT,
                         anchor="w", justify="left").pack(side="left")

        self._vars["autostart"] = tk.BooleanVar(value=autostart.is_enabled())
        ctk.CTkCheckBox(
            page, text="开机自动启动（登录后自动运行，想关掉随时在「设置」里取消）",
            variable=self._vars["autostart"], font=self.f_small, text_color=TEXT,
            fg_color=BLUE, hover_color=BLUE, checkbox_width=16, checkbox_height=16,
        ).pack(anchor="w", pady=(0, 6))
        ctk.CTkLabel(page, text="填好点「完成」就能用了；之后所有设置都在小窗右下角的「设置」里。",
                     font=self.f_small, text_color=LABEL, anchor="w",
                     justify="left", wraplength=520).pack(anchor="w")
        return page

    def _build_footer(self) -> None:
        row = ctk.CTkFrame(self.card, corner_radius=0, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(8, 14))
        self.back_button = ctk.CTkButton(
            row, text="上一步", command=self.back, width=90, height=34, corner_radius=6,
            font=self.f_label, fg_color=CARD, hover_color=FIELD, text_color="#3C4043",
            border_width=1, border_color="#E0E0E0",
        )
        self.back_button.pack(side="left")
        self.next_button = ctk.CTkButton(
            row, text="下一步", command=self.next, width=110, height=34, corner_radius=6,
            font=self.f_label, fg_color=BLUE_SOFT, hover_color="#DCE7FB", text_color=BLUE,
        )
        self.next_button.pack(side="right")
        ctk.CTkButton(
            row, text="跳过", command=self.skip, width=80, height=34, corner_radius=6,
            font=self.f_label, fg_color="transparent", hover_color=FIELD, text_color=LABEL,
        ).pack(side="right", padx=8)

    # ---- 步骤切换 ----
    def _show_step(self, step: int) -> None:
        self.step = max(0, min(step, len(self._pages) - 1))
        for page in self._pages:
            page.pack_forget()
        self._pages[self.step].pack(fill="both", expand=True)
        self.step_label.configure(
            text=f"第 {self.step + 1} / {len(self._pages)} 步 · {STEP_TITLES[self.step]}"
        )
        self.back_button.configure(state="normal" if self.step else "disabled")
        self.next_button.configure(text="完成" if self.step == len(self._pages) - 1 else "下一步")

    def next(self) -> None:
        if self.step >= len(self._pages) - 1:
            self.finish()
            return
        self._show_step(self.step + 1)

    def back(self) -> None:
        self._show_step(self.step - 1)

    # ---- 动作 ----
    def test_connection(self) -> None:
        self._test_label.configure(text="正在测试…", text_color=LABEL)
        self.root.update_idletasks()
        try:
            self._collect_translate()
            result = test_connection(self.config.translate, self.config.resolved_api_key)
            self._test_label.configure(text=f"连接正常：{result}", text_color=BLUE)
        except Exception as exc:  # noqa: BLE001 - 错误显示在界面上
            get_logger().warning("向导里测试连接失败：%s", exc)
            self._test_label.configure(text=f"失败：{exc}", text_color="#D93025")

    def _collect_translate(self) -> None:
        """把向导里选的服务商与 key 写进配置（还没落盘）。"""

        label = self._vars["provider"].get()
        preset = next((item for item in PRESETS if item.label == label), None)
        if preset is not None:
            self.config.translate.provider = preset.key
            self.config.translate.base_url = preset.base_url
            self.config.translate.model = preset.model
        self.config.translate.api_key = str(self._vars["api_key"].get()).strip()

    def finish(self) -> None:
        self._collect_translate()
        enabled = bool(self._vars["autostart"].get())
        try:
            autostart.set_enabled(enabled)
        except OSError:
            get_logger().warning("设置开机自启失败", exc_info=True)
        self.config.setup_done = True
        try:
            path = save_config(self.config)
            get_logger().info("首次使用向导完成，配置写入：%s", path)
        except Exception:  # noqa: BLE001 - 存不下去也得让用户进界面
            get_logger().exception("向导保存配置失败")
        self.root.destroy()
        if self.on_done is not None:
            self.on_done(self.config)

    def skip(self) -> None:
        """不想现在设置：记下"问过了"，下次启动不再弹。"""

        self.config.setup_done = True
        try:
            save_config(self.config)
        except Exception:  # noqa: BLE001
            get_logger().warning("向导跳过时保存配置失败", exc_info=True)
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def open_wizard(
    config: Config,
    on_done: Callable[[Config], None] | None = None,
    parent: tk.Misc | None = None,
) -> None:
    wizard = SetupWizard(config, on_done, parent=parent)
    if parent is None:
        wizard.run()
