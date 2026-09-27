"""把采集、OCR、翻译和界面串起来的控制器。"""

from __future__ import annotations

import queue
import threading
from pathlib import Path

from mchanhua.capture import create_grabber, grab_screen
from mchanhua.config import Config
from mchanhua.diagnostics import UiWatchdog, make_dump_all_threads
from mchanhua.geometry import Region, enable_dpi_awareness, follow_cursor_region
from mchanhua.hotkey import HotkeyManager
from mchanhua.logging_setup import fault_stream, get_logger
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
        diagnose: bool = False,
    ) -> None:
        enable_dpi_awareness()
        logger = get_logger()
        self.config = config
        self.use_hotkeys = use_hotkeys
        logger.info("步骤 1/3：创建采集后端")
        self.grabber = grabber or create_grabber(config.capture.backend, config.capture.monitor)
        logger.info("步骤 2/3：加载 OCR 引擎（首次加载模型约需 1~2 秒）")
        self.ocr = ocr or create_engine(
            config.ocr.backend, config.ocr.language, config.ocr.upscale, invert=config.ocr.invert
        )
        logger.info("步骤 3/3：创建小窗界面")
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
        self.diagnose = diagnose
        self.watchdog = UiWatchdog(
            stall_seconds=5.0,
            interval=2.0,
            dump=make_dump_all_threads(fault_stream()),
        )
        self.heartbeat_interval = 2 if diagnose else 10
        self.beat_count = 0
        self._translate_lock = threading.Lock()
        logger.info(
            "初始化完成：采集后端 %s，OCR 后端 %s，标定区域 %s，跟随光标区域 %s",
            self.grabber.name,
            getattr(self.ocr, "name", "?"),
            self.last_region,
            config.regions.follow_cursor,
        )

    # ---- 翻译器 ----
    def _ensure_translator(self):
        if self.translator is not None or self.translator_error is not None:
            return self.translator
        api_key = self.config.resolved_api_key
        if not api_key:
            self.translator_error = "未配置 DeepSeek API key，只显示 OCR 原文"
            get_logger().warning(self.translator_error)
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
            get_logger().error("创建翻译器失败：%s", exc)
        return self.translator

    # ---- 热键回调（可能来自其它线程，只往队列里丢消息） ----
    def request_translate(self) -> None:
        self.queue.put(("call", self.perform_translate))

    def request_select_region(self) -> None:
        self.queue.put(("call", self.perform_select_region))

    def quit(self) -> None:
        self.queue.put(("call", self.window.root.destroy))

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

    def perform_translate(self, region: Region | None = None) -> None:
        """在主线程里启动一次取词翻译（真正的活儿交给工作线程）。"""

        if not self._translate_lock.acquire(blocking=False):
            self.window.set_status("上一次取词还在处理中，请稍等…")
            get_logger().info("上一次取词尚未结束，忽略这次请求")
            return
        target = region if region is not None else self._current_region()
        self.window.set_status("正在采集并识别…")
        try:
            threading.Thread(target=self._worker, args=(target,), daemon=True).start()
        except Exception:
            self._translate_lock.release()
            raise

    def _worker(self, region: Region | None) -> None:
        try:
            image = grab_screen(self.grabber, region)
        except Exception as exc:
            get_logger().exception("采集失败")
            self.queue.put(("status", f"采集失败：{exc}"))
            return
        try:
            translator = self._ensure_translator()
            try:
                result = run_pipeline(
                    image,
                    self.ocr,
                    translator,
                    on_ocr=lambda lines, ms: self.queue.put(("ocr", lines, ms)),
                )
            except Exception as exc:
                get_logger().exception("处理失败")
                self.queue.put(("status", f"处理失败：{exc}"))
                return

            get_logger().info(
                "完成：区域 %s，识别 %d 行，翻译 %d 行，OCR %.0f ms，翻译 %.0f ms",
                region,
                len(result.source_lines),
                result.translated_count,
                result.ocr_ms,
                result.translate_ms,
            )
            self.queue.put(("result", result))
            if translator is None and self.translator_error:
                self.queue.put(("status", self.translator_error))
        finally:
            self._translate_lock.release()

    def perform_select_region(self) -> None:
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
        logger = get_logger()
        self.window.root.report_callback_exception = self._on_tk_error
        self.window.heartbeat = self.watchdog.beat
        self.watchdog.start()
        self.window.poll(self.queue)
        self._schedule_heartbeat()
        if self.use_hotkeys:
            threading.Thread(
                target=self._register_hotkeys, name="hotkey-register", daemon=True
            ).start()
        else:
            self.window.set_status("就绪：热键已禁用，可点「重新取词」按钮")
        logger.info("进入界面主循环")
        self.window.run()
        logger.info("界面退出")
        self.watchdog.stop()
        self.hotkeys.stop()
        self.grabber.close()

    def _schedule_heartbeat(self) -> None:
        """每秒一次心跳：界面只要在正常处理事件，日志里就会持续打点。"""

        def tick() -> None:
            self.beat_count += 1
            if self.beat_count % self.heartbeat_interval == 0:
                get_logger().info("心跳 %d：界面正常", self.beat_count)
            self.window.root.after(1000, tick)

        self.window.root.after(1000, tick)

    def _register_hotkeys(self) -> None:
        """在后台线程注册全局热键：避免键盘钩子与 Tk 消息循环互相影响。"""

        logger = get_logger()
        bindings = self.config.hotkeys
        registered = 0
        for action, hotkey, callback in (
            ("取词翻译", bindings.translate, self.request_translate),
            ("框选区域", bindings.select_region, self.request_select_region),
            ("退出", bindings.quit, self.quit),
        ):
            try:
                self.hotkeys.register(action, hotkey, callback)
                registered += 1
            except RuntimeError as exc:
                logger.error("注册热键失败：%s", exc)
                self.queue.put(("status", str(exc)))
        logger.info("热键注册完成：%d 个", registered)
        self.queue.put(
            ("status", f"就绪：{registered} 个热键已注册，把鼠标移到物品上按热键取词")
        )

    def _on_tk_error(self, exc_type, exc_value, exc_tb) -> None:
        get_logger().error("界面回调异常", exc_info=(exc_type, exc_value, exc_tb))
