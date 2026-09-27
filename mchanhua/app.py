"""把采集、OCR、翻译和界面串起来的控制器。"""

from __future__ import annotations

import queue
import threading
from pathlib import Path

from mchanhua.capture import create_grabber, grab_screen
from mchanhua.config import Config
from mchanhua.geometry import Region, enable_dpi_awareness, follow_cursor_region
from mchanhua.hotkey import HotkeyManager
from mchanhua.ocr import create_engine
from mchanhua.pipeline import run_pipeline
from mchanhua.translate import TranslationError, create_translator
from mchanhua.ui.region_picker import pick_region
from mchanhua.ui.window import ResultWindow, WindowCallbacks


class Application:
    def __init__(
        self,
        config: Config,
        cache_path: Path | None = None,
        use_hotkeys: bool = True,
        grabber=None,
        ocr=None,
        window=None,
    ) -> None:
        enable_dpi_awareness()
        self.config = config
        self.use_hotkeys = use_hotkeys
        self.grabber = grabber or create_grabber(config.capture.backend, config.capture.monitor)
        self.ocr = ocr or create_engine(
            config.ocr.backend, config.ocr.language, config.ocr.upscale, invert=config.ocr.invert
        )
        self.translator = None
        self.translator_error: str | None = None
        self.cache_path = cache_path
        self.queue: queue.Queue[tuple] = queue.Queue()
        self.hotkeys = HotkeyManager()
        self.window = window or ResultWindow(
            config,
            WindowCallbacks(
                on_translate=self.request_translate,
                on_select_region=self.request_select_region,
                on_quit=self.quit,
            ),
        )
        self.last_region: Region | None = config.regions.fixed_region("tooltip")

    # ---- 翻译器 ----
    def _ensure_translator(self):
        if self.translator is not None or self.translator_error is not None:
            return self.translator
        api_key = self.config.resolved_api_key
        if not api_key:
            self.translator_error = "未配置 DeepSeek API key，只显示 OCR 原文"
            return None
        try:
            self.translator = create_translator(
                self.config.translate,
                api_key,
                self.cache_path,
                self.config.glossary,
            )
        except TranslationError as exc:
            self.translator_error = str(exc)
        return self.translator

    # ---- 热键回调（可能来自其它线程，只往队列里丢消息） ----
    def request_translate(self) -> None:
        self.queue.put(("translate", None))

    def request_select_region(self) -> None:
        self.queue.put(("select_region", None))

    def quit(self) -> None:
        self.queue.put(("quit", None))

    # ---- 实际工作 ----
    def _current_region(self) -> Region | None:
        """按配置决定采集区域：跟随光标的相对区域优先，其次上次框选的区域。"""

        monitor = self.grabber.primary_monitor()
        if self.config.regions.follow_cursor:
            offset = Region.parse(self.config.regions.follow_cursor)
            cursor = self.window.root.winfo_pointerxy()
            scale = monitor.width / max(1, self.window.root.winfo_screenwidth())
            physical_cursor = (round(cursor[0] * scale), round(cursor[1] * scale))
            try:
                return follow_cursor_region(offset, physical_cursor, monitor)
            except ValueError:
                return self.last_region
        return self.last_region

    def translate_once(self, region: Region | None = None) -> None:
        target = region if region is not None else self._current_region()
        self.window.set_status("正在采集并识别…")
        threading.Thread(target=self._worker, args=(target,), daemon=True).start()

    def _worker(self, region: Region | None) -> None:
        try:
            image = grab_screen(self.grabber, region)
        except Exception as exc:
            self.queue.put(("status", f"采集失败：{exc}"))
            return

        translator = self._ensure_translator()
        try:
            result = run_pipeline(
                image,
                self.ocr,
                translator,
                on_ocr=lambda lines, ms: self.queue.put(("ocr", lines, ms)),
            )
        except Exception as exc:
            self.queue.put(("status", f"处理失败：{exc}"))
            return

        self.queue.put(("result", result))
        if translator is None and self.translator_error:
            self.queue.put(("status", self.translator_error))

    def select_region(self) -> None:
        self.window.root.withdraw()
        try:
            region = pick_region(self.grabber.primary_monitor(), self.window.root)
        finally:
            self.window.root.deiconify()
        if region is None:
            self.window.set_status("已取消框选")
            return
        self.last_region = region
        self.window.set_status(f"已选定区域 {region.to_csv()}")

    # ---- 启动 ----
    def start(self) -> None:
        registered = 0
        if self.use_hotkeys:
            bindings = self.config.hotkeys
            for action, hotkey, callback in (
                ("取词翻译", bindings.translate, self.request_translate),
                ("框选区域", bindings.select_region, self.request_select_region),
                ("退出", bindings.quit, self.quit),
            ):
                try:
                    self.hotkeys.register(action, hotkey, callback)
                    registered += 1
                except RuntimeError as exc:
                    self.window.set_status(str(exc))
        self.window.set_status(f"就绪：{registered} 个热键已注册，把鼠标移到物品上按热键取词")
        self.window.poll(self.queue)
        self.window.run()
        self.hotkeys.stop()
        self.grabber.close()
