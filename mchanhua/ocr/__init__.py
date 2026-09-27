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

    auto 表示质量优先：能用 RapidOCR 就用它（实测在真实游戏文本上比系统 OCR 准得多），
    没装再退回 Windows 自带 OCR。额外参数（例如 invert）会透传给具体后端。
    """

    if backend == "auto":
        engine = RapidOcr(language=language, upscale=upscale, **options)
        if engine.ready:
            return engine
        return WindowsOcr(language=language, upscale=upscale, **options)
    if backend == "windows":
        try:
            return WindowsOcr(language=language, upscale=upscale, **options)
        except OcrUnavailable:
            raise
    if backend == "rapidocr":
        engine = RapidOcr(language=language, upscale=upscale, **options)
        if engine.ready:
            return engine
        engine._ensure_engine()
    raise OcrUnavailable(f"未知的 OCR 后端：{backend}")
