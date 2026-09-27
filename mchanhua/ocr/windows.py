"""Windows 自带 OCR（Windows.Media.Ocr）。

优点：系统内置、免费、离线、无需下载模型。
注意：识别质量取决于已安装的 OCR 语言包，缺语言包时会创建失败。
"""

from __future__ import annotations

import time
from typing import Any, Sequence

from PIL import Image

from mchanhua.geometry import Region
from mchanhua.ocr.base import OcrLine, OcrResult, OcrUnavailable, union_boxes

PREFERRED_LANGUAGE_PREFIXES = ("en", "zh-Hans", "zh")


def _enum_member(enum_type: Any, *names: str) -> Any:
    for name in names:
        if hasattr(enum_type, name):
            return getattr(enum_type, name)
    raise AttributeError(f"{enum_type!r} 缺少成员 {names}")


def _win_ocr_class():
    try:
        from winrt.windows.media.ocr import OcrEngine as WinOcrEngine
    except ImportError as exc:  # pragma: no cover - 依赖缺失时才走到
        raise OcrUnavailable(
            "缺少 winrt-Windows.Media.Ocr，无法使用 Windows OCR："
            "请执行 python -m pip install winrt-Windows.Media.Ocr"
        ) from exc
    return WinOcrEngine


def available_languages() -> list[str]:
    engine_cls = _win_ocr_class()
    try:
        return [lang.language_tag for lang in engine_cls.available_recognizer_languages]
    except Exception as exc:  # pragma: no cover - 取决于系统状态
        raise OcrUnavailable(f"读取 OCR 语言列表失败：{exc}") from exc


def pick_language(preference: str = "auto") -> str:
    """选择实际使用的 OCR 语言标签。"""

    languages = available_languages()
    if not languages:
        raise OcrUnavailable(
            "系统没有安装任何 OCR 语言包。可在 设置 → 时间和语言 → 语言和区域 中"
            "为对应语言安装「可选功能 → 光学字符识别」。"
        )
    if preference and preference != "auto":
        wanted = preference.lower()
        for tag in languages:
            if tag.lower() == wanted:
                return tag
        for tag in languages:
            if tag.lower().startswith(wanted):
                return tag
        raise OcrUnavailable(f"OCR 语言 {preference} 不可用，系统可用：{languages}")
    for prefix in PREFERRED_LANGUAGE_PREFIXES:
        for tag in languages:
            if tag.lower().startswith(prefix.lower()):
                return tag
    return languages[0]


def _to_software_bitmap(image: Image.Image):
    from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.storage.streams import DataWriter

    rgba = image.convert("RGBA")
    # 直接产出 BGRA8 像素（Windows OCR 要求的格式）；图像全不透明，
    # 预乘 alpha 与直通 alpha 等价，因此不需要额外做像素格式转换。
    bgra = rgba.tobytes("raw", "BGRA")
    writer = DataWriter()
    writer.write_bytes(bgra)
    buffer = writer.detach_buffer()
    return SoftwareBitmap.create_copy_from_buffer(
        buffer,
        _enum_member(BitmapPixelFormat, "BGRA8", "Bgra8"),
        rgba.width,
        rgba.height,
    )


def _wait(operation: Any, timeout: float = 15.0) -> None:
    from winrt.windows.foundation import AsyncStatus

    started = _enum_member(AsyncStatus, "STARTED", "Started")
    deadline = time.perf_counter() + timeout
    while operation.status == started:
        if time.perf_counter() > deadline:
            raise TimeoutError(f"OCR 超过 {timeout} 秒未返回")
        time.sleep(0.002)


def _rect_region(rect: Any, scale: float) -> Region:
    x = int(round(rect.x / scale))
    y = int(round(rect.y / scale))
    width = max(1, int(round(rect.width / scale)))
    height = max(1, int(round(rect.height / scale)))
    return Region(x, y, width, height)


class WindowsOcr:
    name = "windows"

    def __init__(self, language: str = "auto", upscale: float = 1.0, invert: bool = False) -> None:
        if upscale <= 0:
            raise ValueError(f"upscale 必须为正数：{upscale}")
        self.language_setting = language
        self.upscale = upscale
        self.invert = invert
        self._engine = None
        self.language: str | None = None

    def _ensure_engine(self):
        if self._engine is not None:
            return self._engine
        engine_cls = _win_ocr_class()
        from winrt.windows.globalization import Language

        tag = pick_language(self.language_setting)
        engine = engine_cls.try_create_from_language(Language(tag))
        if engine is None:  # pragma: no cover - 取决于系统状态
            engine = engine_cls.try_create_from_user_profile_languages()
        if engine is None:  # pragma: no cover - 取决于系统状态
            raise OcrUnavailable(f"无法创建 OCR 引擎（语言 {tag}）")
        self._engine = engine
        self.language = tag
        return engine

    @property
    def ready(self) -> bool:
        try:
            self._ensure_engine()
        except OcrUnavailable:
            return False
        return True

    def recognize(self, image: Image.Image) -> OcrResult:
        engine = self._ensure_engine()
        scale = float(self.upscale)
        if scale != 1.0:
            target = image.resize(
                (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                Image.LANCZOS,
            )
        else:
            target = image

        if self.invert:
            from PIL import ImageOps

            target = ImageOps.invert(target.convert("RGB"))

        bitmap = _to_software_bitmap(target)
        started = time.perf_counter()
        operation = engine.recognize_async(bitmap)
        _wait(operation)
        raw = operation.get_results()
        elapsed_ms = (time.perf_counter() - started) * 1000

        lines: list[OcrLine] = []
        for raw_line in raw.lines:
            text = (raw_line.text or "").strip()
            if not text:
                continue
            boxes: list[Region] = []
            words: list[str] = []
            for word in raw_line.words:
                word_text = (word.text or "").strip()
                if not word_text:
                    continue
                words.append(word_text)
                boxes.append(_rect_region(word.bounding_rect, scale))
            lines.append(OcrLine(text=text, box=union_boxes(boxes), words=tuple(words)))

        return OcrResult(lines=lines, elapsed_ms=elapsed_ms, backend=self.name, language=self.language)
