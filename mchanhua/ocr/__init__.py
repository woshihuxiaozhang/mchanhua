"""OCR 后端。"""

from __future__ import annotations

from mchanhua.ocr.base import OcrEngine, OcrLine, OcrResult, OcrUnavailable, group_words_into_lines
from mchanhua.ocr.windows import WindowsOcr

__all__ = [
    "OcrEngine",
    "OcrLine",
    "OcrResult",
    "OcrUnavailable",
    "WindowsOcr",
    "create_engine",
    "group_words_into_lines",
]


def create_engine(backend: str = "auto", language: str = "auto", upscale: float = 1.0) -> OcrEngine:
    """创建 OCR 引擎。

    auto 表示优先用 Windows 自带 OCR；rapidocr 属于可选后端，
    需要自行安装 rapidocr-onnxruntime。
    """

    if backend in ("auto", "windows"):
        try:
            return WindowsOcr(language=language, upscale=upscale)
        except OcrUnavailable:
            if backend == "windows":
                raise
    if backend in ("auto", "rapidocr"):
        try:
            import rapidocr_onnxruntime  # noqa: F401
        except ImportError as exc:
            raise OcrUnavailable(
                "未安装 rapidocr-onnxruntime，无法使用 rapidocr 后端："
                "请执行 python -m pip install rapidocr-onnxruntime"
            ) from exc
        raise OcrUnavailable("rapidocr 后端尚未实现，请先使用 windows 后端")
    raise OcrUnavailable(f"未知的 OCR 后端：{backend}")

