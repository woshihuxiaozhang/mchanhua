"""Windows OCR 的端到端冒烟测试。

没有可用的 OCR 语言包时自动跳过——本机目前的可用语言取决于系统语言包。
"""

from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from mchanhua.ocr import create_engine
from mchanhua.ocr.base import OcrUnavailable
from mchanhua.ocr.windows import available_languages, pick_language
from mchanhua.metrics import similarity

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


def test_windows_ocr_languages_are_listed():
    try:
        languages = available_languages()
    except OcrUnavailable as exc:
        pytest.skip(f"Windows OCR 不可用：{exc}")
    assert languages, "系统应至少有一个 OCR 语言"
    assert pick_language("auto") in languages


def test_windows_ocr_recognizes_synthetic_tooltip():
    try:
        engine = create_engine("windows", language="auto", upscale=2.0)
        result = engine.recognize(_sample_image())
    except OcrUnavailable as exc:
        pytest.skip(f"Windows OCR 不可用：{exc}")

    assert result.lines, "应至少识别出一行"
    assert result.elapsed_ms > 0
    # 断言的是"链路可用且结果接近"，不追求逐字准确：
    # 识别精度取决于系统已安装的 OCR 语言包，本机只有 zh-Hans，
    # 对拉丁字母有系统性混淆（l/I、o/0），真实数据见 tools/measure_ocr.py。
    expected = "Steel Ingot Right-click to place Durability 1234"
    assert similarity(expected, result.text.replace("\n", " ")) > 0.75, result.text
    for line in result.lines:
        assert line.box is None or line.box.width <= 640


def test_windows_ocr_upscale_keeps_box_in_original_coordinates():
    try:
        engine = create_engine("windows", language="auto", upscale=2.0)
        result = engine.recognize(_sample_image())
    except OcrUnavailable as exc:
        pytest.skip(f"Windows OCR 不可用：{exc}")

    boxes = [line.box for line in result.lines if line.box]
    assert boxes, "应给出词框坐标"
    assert max(box.bottom for box in boxes) <= 200
    assert max(box.right for box in boxes) <= 640
