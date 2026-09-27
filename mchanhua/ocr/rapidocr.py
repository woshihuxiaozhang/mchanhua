"""RapidOCR（PP-OCR ONNX 模型）后端。

相比系统自带的 Windows OCR，PP-OCR 的识别模型在渲染字体、小字号上通常更稳，
代价是要多装约 100MB 依赖，单帧耗时也更长。
"""

from __future__ import annotations

import time

from PIL import Image

from mchanhua.geometry import Region
from mchanhua.ocr.base import OcrLine, OcrResult, OcrUnavailable


def _quad_to_region(quad, scale: float) -> Region:
    xs = [float(point[0]) for point in quad]
    ys = [float(point[1]) for point in quad]
    left = int(round(min(xs) / scale))
    top = int(round(min(ys) / scale))
    width = max(1, int(round((max(xs) - min(xs)) / scale)))
    height = max(1, int(round((max(ys) - min(ys)) / scale)))
    return Region(left, top, width, height)


class RapidOcr:
    name = "rapidocr"

    def __init__(self, language: str = "auto", upscale: float = 1.0, invert: bool = False) -> None:
        if upscale <= 0:
            raise ValueError(f"upscale 必须为正数：{upscale}")
        self.language = language
        self.upscale = upscale
        self.invert = invert
        self._engine = None

    def _ensure_engine(self):
        if self._engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
            except ImportError as exc:
                raise OcrUnavailable(
                    "缺少 rapidocr-onnxruntime，无法使用 rapidocr 后端："
                    "请执行 python -m pip install rapidocr-onnxruntime"
                ) from exc
            self._engine = RapidOCR()
        return self._engine

    def recognize(self, image: Image.Image) -> OcrResult:
        import numpy as np

        engine = self._ensure_engine()
        scale = float(self.upscale)
        if scale != 1.0:
            target = image.resize(
                (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                Image.LANCZOS,
            )
        else:
            target = image
        rgb = target.convert("RGB")
        if self.invert:
            from PIL import ImageOps

            rgb = ImageOps.invert(rgb)

        started = time.perf_counter()
        output = engine(np.array(rgb))
        elapsed_ms = (time.perf_counter() - started) * 1000

        raw = output[0] if isinstance(output, tuple) else output
        lines: list[OcrLine] = []
        if raw:
            for item in raw:
                quad, text, _score = item[0], item[1], item[2]
                text = (text or "").strip()
                if not text:
                    continue
                lines.append(OcrLine(text=text, box=_quad_to_region(quad, scale), words=(text,)))
        lines.sort(key=lambda line: (line.box.y, line.box.x) if line.box else (0, 0))
        return OcrResult(
            lines=lines,
            elapsed_ms=elapsed_ms,
            backend=self.name,
            language="ppocr",
        )

    @property
    def ready(self) -> bool:
        try:
            self._ensure_engine()
        except OcrUnavailable:
            return False
        return True

