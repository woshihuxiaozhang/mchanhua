"""把采集、OCR、翻译和界面串起来的控制器。"""

from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

from PIL import Image

from mchanhua.autoregion import capture_region_for, filter_area_lines, filter_capture
from mchanhua.capture import create_grabber, frames_similar, grab_clipboard_image, grab_screen
from mchanhua.config import CUSTOM_REGION_KEY, Config, save_config
from mchanhua.debugdump import dump_last_run
from mchanhua.diagnostics import UiWatchdog, make_dump_all_threads
from mchanhua.geometry import Region, enable_dpi_awareness, follow_cursor_region
from mchanhua.history import TranslationHistory
from mchanhua.hotkey import HotkeyManager, reset_pressed_state
from mchanhua.logging_setup import fault_stream, get_logger
from mchanhua.ocr import create_engine
from mchanhua.pipeline import run_from_ocr
from mchanhua.translate import TranslationError, create_translator
from mchanhua.ui.region_picker import pick_region
from mchanhua.ui.theme import heal_theme
from mchanhua.ui.window import ResultWindow, WindowCallbacks

# 全屏翻译时最多翻译多少行（整屏识别出来的行可能很多，这里限制成本与噪音）
FULLSCREEN_MAX_LINES = 60

# 抓屏时最多连抓几帧来判断画面是否已经稳定，以及每帧之间等多久
STABLE_INTERVAL_SECONDS = 0.12


class Application:
    def __init__(
        self,
        config: Config,
        cache_path: Path | None = None,
        config_path: Path | None = None,
        use_hotkeys: bool = True,
        grabber=None,
        ocr=None,
        window=None,
        diagnose: bool = False,
    ) -> None:
        enable_dpi_awareness()
        logger = get_logger()
        self.config = config
        self.config_path = config_path or config.loaded_from
        self.use_hotkeys = use_hotkeys
        # 主题自愈：配置被旧实例写坏（配色不达标）时恢复默认浅色并落盘
        healed = heal_theme(config)
        if healed:
            logger.warning("检测到配色不达标，已恢复默认浅色主题：%s", "；".join(healed))
            try:
                save_config(config, self.config_path)
            except Exception:
                logger.warning("恢复后的主题写盘失败", exc_info=True)
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
        # 翻译历史只放在内存里：退出程序就没了，不落盘、不占空间
        self.history = TranslationHistory()
        self.window = window or ResultWindow(
            config,
            WindowCallbacks(
                on_translate=self.request_translate,
                on_select_and_translate=self.request_translate_region,
                on_translate_fullscreen=self.request_translate_fullscreen,
                on_open_settings=self.request_open_settings,
                on_open_image=self.request_open_image,
                on_select_region=self.request_select_region,
                on_quit=self.quit,
            ),
        )
        # 小窗里的时钟按钮点开时，用这个函数现取最近 20 条
        self.window.history_provider = self.recent_history
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
        self._pending_jobs: list[tuple[str, Region | None]] = []
        self._hidden_for_capture = False
        # 框选遮罩是用嵌套事件循环弹出来的（wait_window），期间热键消息照样会被处理——
        # 不挡住就会出现"按一次弹一层遮罩、连着截好几次"（见日志里的连续触发）
        self._picking = False
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
        # 只有"需要 key 的服务"才因为缺 key 而停用；Ollama 这类本地服务不需要 key
        from mchanhua.translate.providers import find_preset

        preset = find_preset(self.config.translate.provider)
        needs_key = preset.needs_key if preset is not None else True
        if needs_key and not api_key:
            label = preset.label if preset is not None else "翻译服务"
            self.translator_error = f"未配置 {label} 的 API key，只显示 OCR 原文"
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
        get_logger().info("热键触发：翻译自定义选区")
        self.queue.put(("call", self.perform_translate))

    def request_translate_region(self) -> None:
        get_logger().info("热键触发：框选并翻译")
        self.queue.put(("call", self.perform_select_and_translate))

    def request_translate_fullscreen(self) -> None:
        get_logger().info("热键触发：全屏翻译")
        self.queue.put(("call", self.perform_translate_fullscreen))

    def request_translate_clipboard(self) -> None:
        get_logger().info("热键触发：翻译剪贴板图片")
        self.queue.put(("call", self.perform_translate_clipboard))

    def request_open_image(self) -> None:
        self.queue.put(("call", self.perform_open_image))

    def request_open_settings(self) -> None:
        self.queue.put(("call", self.open_settings))

    def request_select_region(self) -> None:
        get_logger().info("热键触发：只框选选区")
        self.queue.put(("call", self.perform_select_region))

    def quit(self) -> None:
        self.queue.put(("call", self.window.root.destroy))

    # ---- 实际工作 ----
    def _current_region(self) -> Region | None:
        """采集区域优先级：已保存的自定义选区 > 跟随光标 > 上次框选的区域。"""

        monitor = self.grabber.primary_monitor()
        areas = self._current_areas()
        if areas:
            return areas[0][1]          # 单区域入口（比如"只翻第一个区域"）用第一个
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

    def _current_areas(self) -> list[tuple[str, Region]]:
        """当前启用的区域（坐标裁到屏幕内，越界的跳过）。"""

        monitor = self.grabber.primary_monitor()
        result: list[tuple[str, Region]] = []
        for name, region in self.config.regions.enabled_areas():
            try:
                result.append((name, region.clamp(monitor)))
            except ValueError:
                get_logger().warning("区域「%s」%s 超出屏幕 %s，已跳过", name, region, monitor)
        return result

    def perform_translate(self, region: Region | None = None) -> None:
        """在主线程里启动一次取词翻译（真正的活儿交给工作线程）。"""

        if self._picking:
            get_logger().info("正在框选，忽略这次取词")
            return
        if not self._translate_lock.acquire(blocking=False):
            self._queue_pending("region", region)
            return
        if region is not None:
            # 刚框完的那一块：单区域
            self.window.set_status("正在采集并识别…")
            self._capture_after_hiding(lambda: self._start_worker(region, None), region)
            return
        areas = self._current_areas()
        if areas:
            # 多区域：一次抓屏 + 一次 OCR，按区域筛行后合成一次翻译
            first = areas[0][1]
            self.window.set_status(f"正在采集并识别（{len(areas)} 个区域）…")
            self._capture_after_hiding(
                lambda: self._start_worker(None, None, None, areas), first
            )
            return
        target = self._current_region()
        self.window.set_status("正在采集并识别…")
        self._capture_after_hiding(lambda: self._start_worker(target, None), target)

    def perform_translate_fullscreen(self) -> None:
        """全屏翻译：整屏识别后翻译，行数超过上限时只翻前若干行。"""

        if self._picking:
            get_logger().info("正在框选，忽略这次全屏翻译")
            return
        if not self._translate_lock.acquire(blocking=False):
            self._queue_pending("fullscreen")
            return
        monitor = self.grabber.primary_monitor()
        self.window.set_status(f"正在全屏识别（{monitor.width}x{monitor.height}）…")
        self._capture_after_hiding(
            lambda: self._start_worker(None, None, FULLSCREEN_MAX_LINES), None
        )

    # ---- 抓屏前把自己藏起来 ----
    def _capture_after_hiding(self, start, region: Region | None) -> None:
        """只在窗口挡住抓图区域时才把它藏起来，停一拍再开始抓图。

        否则全屏翻译会把界面本身也 OCR 进去（"翻译选区/设置"这些字全被翻译）。
        但窗口离得远就别动它了——每次按热键窗口都闪一下很烦人。
        隐藏/恢复都必须发生在主线程（Tk 只能在主线程碰）。
        """

        root = getattr(self.window, "root", None)
        if root is not None and hasattr(root, "after") and self._region_hits_window(region):
            try:
                root.withdraw()
                self._hidden_for_capture = True
                root.update_idletasks()
            except Exception:  # pragma: no cover - 隐藏失败也要继续抓图
                get_logger().warning("抓图前隐藏窗口失败", exc_info=True)
        try:
            if self._hidden_for_capture and hasattr(root, "after"):
                # 等窗口真的看不见了、残影也散掉，再抓图
                self._start_when_hidden(root, start)
            else:
                start()
        except Exception:
            self._translate_lock.release()
            self._show_after_capture()
            raise

    def _start_when_hidden(self, root, start, attempt: int = 0) -> None:
        """轮询到窗口不可见之后再等一小会儿（Windows 的淡出动画会留残影）。"""

        try:
            visible = bool(root.winfo_viewable())
        except Exception:  # pragma: no cover - 窗口已销毁
            visible = False
        if visible and attempt < 20:
            root.after(25, lambda: self._start_when_hidden(root, start, attempt + 1))
            return
        root.after(80, start)

    def _region_hits_window(self, region: Region | None) -> bool:
        """抓图区域跟程序窗口有没有重叠（重叠才需要把窗口藏起来）。"""

        root = getattr(self.window, "root", None)
        if root is None:
            return False
        try:
            x, y = int(root.winfo_x()), int(root.winfo_y())
            width, height = int(root.winfo_width()), int(root.winfo_height())
        except Exception:  # pragma: no cover - 拿不到就保守处理
            return True
        if width <= 1 or height <= 1:
            return False                     # 窗口本来就没显示
        window = Region(x, y, width, height)
        target = region if region is not None else self.grabber.primary_monitor()
        return window.intersect(target) is not None

    def _start_worker(
        self,
        region: Region | None,
        image,
        max_lines: int | None = None,
        areas: list[tuple[str, Region]] | None = None,
    ) -> None:
        try:
            threading.Thread(
                target=self._worker, args=(region, image, max_lines, areas), daemon=True
            ).start()
        except Exception:
            self._translate_lock.release()
            self._show_after_capture()
            raise

    def _show_after_capture(self) -> None:
        """把抓图时藏起来的窗口放回来（主线程调用）。"""

        if not self._hidden_for_capture:
            return
        self._hidden_for_capture = False
        root = getattr(self.window, "root", None)
        if root is None or not hasattr(root, "deiconify"):
            return
        try:
            root.deiconify()
        except Exception:  # pragma: no cover - 窗口已销毁
            pass

    def perform_translate_clipboard(self) -> None:
        """翻译剪贴板里的图片（Win+Shift+S 截图后按热键即可）。"""

        if not self._translate_lock.acquire(blocking=False):
            self._queue_pending("clipboard")
            return
        try:
            image = grab_clipboard_image()
        except Exception as exc:
            self._translate_lock.release()
            get_logger().warning("读取剪贴板图片失败：%s", exc)
            self.window.set_status(f"读取剪贴板失败：{exc}")
            return
        self.window.set_status("正在识别剪贴板图片…")
        threading.Thread(target=self._worker, args=(None, image), daemon=True).start()

    def perform_open_image(self) -> None:
        """弹出文件选择框，翻译选中的图片。"""

        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title="选择要翻译的图片",
            filetypes=[("图片", "*.png *.jpg *.jpeg *.bmp *.webp"), ("所有文件", "*.*")],
        )
        if path:
            self.perform_translate_file(Path(path))

    # ---- 设置 ----
    def open_settings(self) -> None:
        """打开设置窗口（与主窗口同一个 Tk root，模态）。"""

        from mchanhua.ui.settings_window import open_settings

        self.window.set_status("设置窗口已打开")
        open_settings(
            self.config,
            on_saved=self.apply_config,
            parent=self.window.root,
            pause_hotkeys=self.suspend_hotkeys,
            resume_hotkeys=self.resume_hotkeys,
            history=self.history,
            on_history_cleared=self.refresh_history,
            preview_opacity=self.preview_opacity,
        )

    def preview_opacity(self, value: float) -> None:
        """设置里拖透明度滑块时即时预览（不用先保存）。"""

        setter = getattr(self.window, "set_opacity", None)
        if setter is not None:
            setter(value)

    def recent_history(self):
        """最近 20 条翻译记录（小窗历史面板用）。"""

        return self.history.recent()

    def refresh_history(self) -> None:
        """把最新历史推给界面（设置里清空历史后也会调一次）。"""

        self.queue.put(("history", self.history.recent()))

    def suspend_hotkeys(self) -> None:
        """临时卸掉全局热键（设置界面录热键时用）：否则录 Ctrl+Alt 会顺手触发翻译。"""

        self.hotkeys.stop()
        get_logger().info("热键已暂停（正在录制新热键）")

    def resume_hotkeys(self) -> None:
        if not self.use_hotkeys:
            return
        self.hotkeys.start()
        get_logger().info("热键已恢复")

    def apply_config(self, config: Config) -> None:
        """设置保存后：热键与服务立即重建，界面外观重启后生效。"""

        self.config = config
        self.translator = None
        self.translator_error = None
        self.hotkeys.stop()
        self.hotkeys = HotkeyManager()
        threading.Thread(
            target=self._register_hotkeys, name="hotkey-reregister", daemon=True
        ).start()
        get_logger().info("设置已应用：热键重新注册，翻译服务已重建")
        self.window.set_status("设置已更新：热键与翻译服务已生效（界面外观重启后生效）")

    def perform_translate_file(self, path: Path) -> None:
        """翻译一个图片文件。"""

        if not self._translate_lock.acquire(blocking=False):
            self._queue_pending("file")
            return
        try:
            image = Image.open(path)
            image.load()
            image = image.convert("RGB")
        except Exception as exc:
            self._translate_lock.release()
            get_logger().exception("打开图片失败")
            self.window.set_status(f"打开图片失败：{exc}")
            return
        self.window.set_status(f"正在识别图片：{path.name}")
        threading.Thread(target=self._worker, args=(None, image), daemon=True).start()

    def _capture_and_ocr(self, region: Region | None):
        """抓图并识别；选区模式向外多抓一圈，只保留选区内的完整行。"""

        capture, image = self._grab_image(region)
        return capture, image, self._recognize(capture, image, region)

    def _grab_image(self, region: Region | None):
        """按模式抓一张图：screen = 整屏，padded = 选区外扩一圈。

        连抓两帧比较，等画面稳定了再用（同类工具 UGTLive 就是"等画面停下来再翻"）：
        游戏里的提示框是淡入的，抓早了会翻到半截；画面没变就直接用最新那帧。
        """

        capture = capture_region_for(
            region, self.grabber.primary_monitor(), self.config.ocr.capture_mode
        )
        frames = max(1, min(3, int(self.config.ocr.settle_frames)))
        image = grab_screen(self.grabber, capture)
        for attempt in range(1, frames):
            time.sleep(STABLE_INTERVAL_SECONDS)
            latest = grab_screen(self.grabber, capture)
            if frames_similar(image, latest):
                image = latest
                break
            image = latest
            if attempt + 1 == frames:
                break
        return capture, image

    def _recognize(self, capture: Region | None, image, region: Region | None):
        """识别；选区模式再按选区筛一遍行。"""

        result = self.ocr.recognize(image)
        if region is None or capture is None:
            return result
        return filter_capture(region, capture, result, mode=self.config.ocr.capture_mode)

    def _no_text_message(self, region: Region | None) -> str:
        """选区/整屏没识别到文字时的提示语。"""

        if region is None:
            return "没有识别到文字：换个画面或把字调大一点再试"
        return f"选区内没有识别到文字（{region.to_csv()}），把框拉大一点圈住文字再试"

    def _worker(
        self,
        region: Region | None,
        image=None,
        max_lines: int | None = None,
        areas: list[tuple[str, Region]] | None = None,
    ) -> None:
        line_areas: list[str] = []
        try:
            translator = self._ensure_translator()
            try:
                if areas:
                    # 多区域：整屏抓一次、OCR 一次，再按区域筛行合成
                    capture, image = self._grab_image(None)
                    self.queue.put(("call", self._show_after_capture))
                    raw_result = self.ocr.recognize(image)
                    lines, line_areas = filter_area_lines(raw_result, capture, areas)
                    ocr_result = type(raw_result)(
                        lines=lines,
                        elapsed_ms=getattr(raw_result, "elapsed_ms", 0.0),
                        backend=getattr(raw_result, "backend", ""),
                        language=getattr(raw_result, "language", None),
                    )
                elif image is None:
                    capture, image = self._grab_image(region)
                    # 抓完这一张就把窗口放回来：OCR 和翻译都不需要它继续藏着，
                    # 拖着不放窗口会"消失好久"。
                    self.queue.put(("call", self._show_after_capture))
                    ocr_result = self._recognize(capture, image, region)
                else:
                    capture = None
                    ocr_result = self.ocr.recognize(image)
                if not ocr_result.lines:
                    # 选区内没有文字时以前会退回整屏结果（等于把屏幕上别的文字翻出来），
                    # 现在明确提示，不翻译、也不覆盖上次的译文。
                    self.queue.put(
                        ("notice", self._no_text_message(region if not areas else None))
                    )
                    return
                result = run_from_ocr(
                    ocr_result,
                    translator,
                    on_ocr=lambda lines, ms: self.queue.put(("ocr", lines, ms)),
                    max_lines=max_lines,
                    line_areas=line_areas,
                )
                dump_last_run(image, ocr_result, result)
            except Exception as exc:
                get_logger().exception("处理失败")
                self.queue.put(("status", f"处理失败：{exc}"))
                return

            get_logger().info(
                "完成：选区 %s，实际抓图 %s，识别 %d 行，翻译 %d 行，OCR %.0f ms，翻译 %.0f ms",
                self._describe_target(region, areas),
                capture.to_csv() if capture is not None else "n/a",
                len(result.source_lines),
                result.translated_count,
                result.ocr_ms,
                result.translate_ms,
            )
            # 记进历史（含"本次"），再刷新小窗里的历史面板
            self.history.add(
                result.source_lines,
                result.output_lines,
                region=("/".join(label for label, _ in areas) if areas else
                        (region.to_csv() if region is not None else "")),
            )
            self.queue.put(("history", self.history.recent()))
            self.queue.put(("result", result))
            if translator is None and self.translator_error:
                self.queue.put(("status", self.translator_error))
        finally:
            self._translate_lock.release()
            if self._pending_jobs:
                # 交回主线程执行，避免在工作线程里碰 Tk
                self.queue.put(("call", self._drain_pending))
            else:
                # 抓图时藏起来的窗口，这会儿放回来
                self.queue.put(("call", self._show_after_capture))

    @staticmethod
    def _describe_target(region: Region | None, areas: list[tuple[str, Region]] | None) -> str:
        if areas:
            return "多区域 " + "/".join(f"{name} {box.to_csv()}" for name, box in areas)
        return region.to_csv() if region is not None else "整屏"

    # ---- 繁忙时的排队 ----
    def _queue_pending(self, kind: str, region: Region | None = None) -> None:
        """上一次还没结束时，把这次请求记下来（只保留最后一次，避免连按堆积）。"""

        self._pending_jobs = [(kind, region)]
        self.window.set_status("上一次取词还没结束，已记下这次请求，结束后自动执行")
        get_logger().info("上一次取词尚未结束，已排队：%s", kind)

    def _drain_pending(self) -> None:
        if not self._pending_jobs:
            return
        self._show_after_capture()          # 排队的是剪贴板/文件时窗口得先回来
        kind, region = self._pending_jobs.pop(0)
        get_logger().info("开始执行排队的请求：%s", kind)
        if kind == "region":
            self.perform_translate(region)
        elif kind == "fullscreen":
            self.perform_translate_fullscreen()
        elif kind == "clipboard":
            self.perform_translate_clipboard()

    def _pick_and_save_region(self) -> Region | None:
        """弹出框选并保存为自定义选区；取消时返回 None。"""

        region = self._pick_region()
        if region is None:
            return None
        self.last_region = region
        self.config.regions.set_custom_region(region)
        if self._save_config():
            self.window.set_status(f"已保存自定义选区 {region.to_csv()}，按 Ctrl+Alt 即可翻译它")
        else:
            self.window.set_status(f"已应用选区 {region.to_csv()}（写入配置文件失败，重启后不保留）")
        return region

    def _pick_areas(self) -> list[str]:
        """连续框选多个区域并保存：每按一次 Enter 存一个，Backspace/Esc 结束。"""

        saved: list[str] = []
        shown: list[tuple[str, Region]] = self._existing_areas()   # 遮罩上要画的（真实名字）

        def handle(region: Region) -> None:
            name = self.config.regions.add_area(region)
            saved.append(name)
            self.last_region = region
            shown.append((name, region))
            if self._save_config():
                self.window.set_status(
                    f"已保存「{name}」{region.to_csv()}（可继续框，Backspace/Esc 结束）"
                )
            else:
                get_logger().warning("区域保存失败：%s", region.to_csv())

        def handle_remove() -> None:
            """Delete：撤掉刚框的那个区域（框错了不用退出重来）。"""

            if not saved:
                self.window.set_status("还没框过新区域，没有可删除的")
                return
            name = saved.pop()
            self.config.regions.remove_area(name)
            shown[:] = [(item, box) for item, box in shown if item != name]
            self._save_config()
            self.window.set_status(f"已删除「{name}」")
            get_logger().info("框选时删除了区域：%s", name)

        pick_region(
            self.grabber.primary_monitor(),
            self.window.root,
            existing=shown,
            on_accept=handle,
            on_remove=handle_remove,
        )
        return saved

    def _existing_areas(self) -> list[tuple[str, Region]]:
        """已保存的区域（画到遮罩上，避免重复框）。"""

        monitor = self.grabber.primary_monitor()
        areas: list[tuple[str, Region]] = []
        for name in self.config.regions.area_names():
            region = self.config.regions.fixed_region(name)
            if region is None:
                continue
            try:
                areas.append((name, region.clamp(monitor)))
            except ValueError:
                continue
        return areas

    def perform_select_region(self) -> None:
        """连续框选多个区域并保存，不翻译（默认 Alt+V）。

        每按一次 Enter 存一个区域（区域1、区域2……），Backspace/Esc 结束。
        """

        if self._picking:
            get_logger().info("上一次框选还没结束，忽略这次 Alt+V")
            return
        self._picking = True
        try:
            self._hide_window_for_pick()
            saved = self._pick_areas()
            if saved:
                self.window.set_status(
                    f"已保存 {len(saved)} 个区域：{'、'.join(saved)}，按 Ctrl+Alt 一起翻译"
                )
            else:
                self.window.set_status("已取消框选")
        finally:
            self._picking = False
            self._show_after_capture()      # 这一路不抓图，框完就把窗口放回来

    def perform_select_and_translate(self) -> None:
        """框选后立即翻译该选区（Alt+/）。**不保存**选区，避免覆盖 Alt+V 设定的区域。"""

        if self._picking:
            get_logger().info("上一次框选还没结束，忽略这次 Alt+/")
            return
        region = self._pick_region()
        if region is None:
            self._show_after_capture()      # 取消框选：窗口放回来
            self.window.set_status("已取消框选")
            return
        # 框选时窗口已经藏起来了，这里保持藏着直到抓完图（抓到图后自动恢复），
        # 否则刚框完就把窗口露出来，又会被拍进画面。
        self.perform_translate(region)

    def _pick_region(self) -> Region | None:
        """只弹出框选，不做任何持久化（供 Alt+/ 临时取词使用）。"""

        # 框选时先把自己的窗口收起来：不然挡在屏幕上的字幕根本框不到
        self._picking = True
        try:
            self._hide_window_for_pick()
            return pick_region(self.grabber.primary_monitor(), self.window.root)
        finally:
            self._picking = False
            cleared = reset_pressed_state()
            if cleared:
                get_logger().info("框选结束后清理了 %d 个残留按键状态", cleared)

    def _hide_window_for_pick(self) -> None:
        """框选期间把窗口藏起来（抓图或框选结束后用 _show_after_capture 放回来）。"""

        root = getattr(self.window, "root", None)
        if root is None or not hasattr(root, "withdraw"):
            return
        try:
            root.withdraw()
            self._hidden_for_capture = True
            root.update_idletasks()
        except Exception:  # pragma: no cover - 隐藏失败不影响框选
            get_logger().warning("框选前隐藏窗口失败", exc_info=True)

    def _save_config(self) -> bool:
        """把当前配置（含自定义选区）写回配置文件。"""

        if self.config_path is None:
            get_logger().warning("没有配置文件路径，无法保存自定义选区")
            return False
        try:
            save_config(self.config, self.config_path)
            get_logger().info(
                "配置已保存：%s（自定义选区 %s）",
                self.config_path,
                self.config.regions.fixed.get(CUSTOM_REGION_KEY),
            )
            return True
        except Exception:
            get_logger().exception("保存配置失败")
            return False

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
            ("翻译自定义选区", bindings.translate, self.request_translate),
            ("框选并翻译", bindings.translate_region, self.request_translate_region),
            ("全屏翻译", bindings.translate_fullscreen, self.request_translate_fullscreen),
            ("翻译剪贴板图片", bindings.translate_clipboard, self.request_translate_clipboard),
            ("只框选选区", bindings.select_region, self.request_select_region),
            ("退出", bindings.quit, self.quit),
        ):
            if not (hotkey or "").strip():
                continue          # 留空 = 不注册这个热键
            try:
                self.hotkeys.register(action, hotkey, callback)
                registered += 1
            except RuntimeError as exc:
                logger.error("注册热键失败：%s", exc)
                self.queue.put(("status", str(exc)))
        self.hotkeys.start()
        logger.info("热键注册完成：%d 个", registered)
        self.queue.put(
            ("status", f"就绪：{registered} 个热键已注册，把鼠标移到物品上按热键取词")
        )

    def _on_tk_error(self, exc_type, exc_value, exc_tb) -> None:
        get_logger().error("界面回调异常", exc_info=(exc_type, exc_value, exc_tb))
