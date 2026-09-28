"""背景图：等比裁切铺满 + 坏文件安全退回。"""

from PIL import Image

from mchanhua.ui.background import cover_resize, load_background


def _image(width: int, height: int, color=(20, 40, 80)) -> Image.Image:
    return Image.new("RGB", (width, height), color)


def test_cover_resize_fills_target_without_distortion():
    # 宽图裁成窄窗口：高度铺满、左右被裁掉
    out = cover_resize(_image(400, 100), (100, 100))
    assert out.size == (100, 100)


def test_cover_resize_handles_tall_image():
    out = cover_resize(_image(100, 400), (200, 100))
    assert out.size == (200, 100)


def test_cover_resize_rejects_bad_size():
    import pytest

    with pytest.raises(ValueError):
        cover_resize(_image(10, 10), (0, 50))


def test_load_background_reads_and_resizes(workdir):
    path = workdir / "bg.png"
    _image(300, 200).save(path)

    loaded = load_background(path, (120, 60))

    assert loaded is not None
    assert loaded.size == (120, 60)


def test_load_background_returns_none_for_missing_or_bad_files(workdir):
    assert load_background("", (10, 10)) is None
    assert load_background(workdir / "没有这个文件.png", (10, 10)) is None

    broken = workdir / "broken.png"
    broken.write_text("这不是图片", encoding="utf-8")
    assert load_background(broken, (10, 10)) is None
