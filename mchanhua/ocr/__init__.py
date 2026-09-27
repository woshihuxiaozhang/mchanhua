"""OCR 后端。"""

from __future__ import annotations

from mchanhua.ocr.base import OcrEngine, OcrLine, OcrResult, OcrUnavailable, group_words_into_lines
from mchanhua.ocr.rapidocr import RapidOcr
from mchanhua.ocr.windows import WindowsOcr

__all__ = [
    "OcrEngine",
    "OcrLine",
    "OcrResult",
    "OcrUnavailable",
    "RapidOcr",
    "WindowsOcr",
    "create_engine",
    "group_words_into_lines",
]


def create_engine(
    backend: str = "auto",
    language: str = "auto",
    upscale: float = 1.0,
    **options,
) -> OcrEngine:
    """创建 OCR 引擎。

    auto 表示优先用 Windows 自带 OCR（快、零依赖），不可用时退回 RapidOCR。
    额外参数（例如 invert）会透传给具体后端。
    """

    if backend in ("auto", "windows"):
        try:
            return WindowsOcr(language=language, upscale=upscale, **options)
        except OcrUnavailable:
            if backend == "windows":
                raise
    if backend in ("auto", "rapidocr"):
        engine = RapidOcr(language=language, upscale=upscale, **options)
        if engine.ready:
            return engine
        if backend == "rapidocr":
            engine._ensure_engine()
        raise OcrUnavailable("Windows OCR 不可用，且 RapidOCR 未安装")
    raise OcrUnavailable(f"未知的 OCR 后端：{backend}")
