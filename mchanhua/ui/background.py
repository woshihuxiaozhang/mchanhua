"""窗口背景图：给任意大小的图片做"等比裁切铺满"。

纯函数 + 一个加载函数，方便测试；界面只管拿来贴上去。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

# 支持的图片格式（给文件选择框用）
IMAGE_PATTERNS = "*.png *.jpg *.jpeg *.bmp *.webp *.gif"


def cover_resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """等比缩放并居中裁切，铺满 size（不变形、不留空边）。"""

    width, height = int(size[0]), int(size[1])
    if width <= 0 or height <= 0:
        raise ValueError(f"目标尺寸非法：{size}")
    ratio = max(width / image.width, height / image.height)
    scaled = image.resize(
        (max(1, round(image.width * ratio)), max(1, round(image.height * ratio))),
        Image.LANCZOS,
    )
    left = (scaled.width - width) // 2
    top = (scaled.height - height) // 2
    return scaled.crop((left, top, left + width, top + height))


def load_background(path: str | Path, size: tuple[int, int]) -> Image.Image | None:
    """读图并裁成 size；路径为空、文件不存在或不是图片时返回 None（界面退回纯色）。"""

    text = str(path or "").strip()
    if not text:
        return None
    target = Path(text)
    if not target.is_file():
        return None
    try:
        with Image.open(target) as image:
            image.load()
            return cover_resize(image.convert("RGB"), size)
    except Exception:
        return None
