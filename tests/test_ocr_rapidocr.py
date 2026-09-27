"""RapidOCR 后端测试（未安装依赖时自动跳过）。"""

from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from mchanhua.metrics import similarity
from mchanhua.ocr.base import OcrUnavailable
from mchanhua.ocr.rapidocr import RapidOcr

ARIAL = Path("C:/Windows/Fonts/arial.ttf")


def _font(size: int):
    if ARIAL.exists():
        return ImageFont.truetype(str(ARIAL), size)
    return ImageFont.load_default()


def _sample_image() -> Image.Image:
    image = Image.new("RGB", (640, 200), (16, 0, 16))
    draw = ImageDraw.Draw(image)
    draw.text((16, 16), "Steel Ingot", font=_font(26), fill=(255, 255, 255))
    draw.text((16, 60), "Right-click to place", font=_font(26), fill=(170, 170, 170))
    draw.text((16, 104), "Durability 1234", font=_font(26), fill=(85, 255, 85))
    return image


def _engine() -> RapidOcr:
    engine = RapidOcr(upscale=1.0)
    if not engine.ready:
        pytest.skip("未安装 rapidocr-onnxruntime")
    return engine


def test_rapidocr_reads_clean_text_accurately():
    result = _engine().recognize(_sample_image())
    expected = "Steel Ingot Right-click to place Durability 1234"
    assert result.lines
    assert similarity(expected, result.text.replace("\n", " ")) > 0.9, result.text


def test_rapidocr_returns_boxes_inside_image():
    result = _engine().recognize(_sample_image())
    boxes = [line.box for line in result.lines if line.box]
    assert boxes
    assert max(box.right for box in boxes) <= 640
    assert max(box.bottom for box in boxes) <= 200
    assert result.elapsed_ms > 0


def test_rapidocr_rejects_bad_upscale():
    with pytest.raises(ValueError):
        RapidOcr(upscale=0)


def test_create_engine_unknown_backend_message():
    from mchanhua.ocr import create_engine

    with pytest.raises(OcrUnavailable):
        create_engine("nonexistent")
