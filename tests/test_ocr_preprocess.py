"""OCR 预处理：画面发灰时自动增强，画面本来就清楚就不动它。"""

from PIL import Image

from mchanhua.config import Config, ConfigError, load_config, save_config
from mchanhua.ocr.preprocess import MODES, contrast_spread, enhance, should_enhance


def _flat(level: int = 120, ink: int | None = None) -> Image.Image:
    """一张低对比度图：底色 120，中间画一块 132 的'字'。"""

    image = Image.new("RGB", (160, 80), (level, level, level))
    if ink is not None:
        for x in range(20, 120):
            for y in range(30, 50):
                image.putpixel((x, y), (ink, ink, ink))
    return image


def test_flat_image_counts_as_low_contrast():
    assert should_enhance(_flat(ink=132)) is True
    assert contrast_spread(_flat(ink=132)) < 20


def test_high_contrast_image_is_left_alone():
    image = _flat(ink=255)                      # 白字黑底：很清楚
    image.paste((0, 0, 0), (0, 0, 80, 80))
    assert should_enhance(image) is False
    assert enhance(image, "auto") is image      # 原样返回，不做任何处理


def test_auto_mode_raises_contrast_on_washed_out_image():
    image = _flat(ink=132)

    out = enhance(image, "auto")

    assert out.size == image.size               # 尺寸不变，坐标才有效
    assert contrast_spread(out) > contrast_spread(image)


def test_all_modes_keep_size_and_type():
    image = _flat(ink=180)

    for mode in MODES:
        out = enhance(image, mode)
        assert isinstance(out, Image.Image)
        assert out.size == image.size
        assert out.mode == "RGB"


def test_unknown_mode_is_ignored():
    image = _flat(ink=180)
    assert enhance(image, "不认识的模式") is image


def test_preprocess_setting_round_trip(workdir):
    config = Config()
    config.ocr.preprocess = "contrast"
    config.ocr.merge_lines = False

    path = save_config(config, workdir / "config.toml")
    loaded = load_config(path)

    assert loaded.ocr.preprocess == "contrast"
    assert loaded.ocr.merge_lines is False


def test_bad_preprocess_mode_is_rejected():
    import pytest

    config = Config()
    config.ocr.preprocess = "sharpen2"
    with pytest.raises(ConfigError):
        config.validate()


def test_merged_lines_setting_can_be_turned_off(workdir):
    config = Config()
    config.ocr.merge_lines = False
    path = save_config(config, workdir / "config.toml")
    assert load_config(path).ocr.merge_lines is False
