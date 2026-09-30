"""识别前的图像预处理：让游戏里的半透明提示框、发灰画面更容易被 OCR 认出。

原则是"保守"：画面本来就清楚就一点都不动；只有对比度明显不足时才自动增强。
纯图像处理，不依赖任何额外库，也不改变图像尺寸（坐标保持有效）。
"""

from __future__ import annotations

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat

MODES = ("off", "auto", "contrast", "sharpen", "grayscale", "binarize")

# 灰度标准差低于这个值就认为画面"发灰/对比度不足"（游戏半透明提示框常见）
AUTO_THRESHOLD = 42.0


def contrast_spread(image: Image.Image) -> float:
    """灰度标准差：越小说明画面越灰、字和背景越分不开。"""

    return float(ImageStat.Stat(image.convert("L")).stddev[0])


def should_enhance(image: Image.Image) -> bool:
    return contrast_spread(image) < AUTO_THRESHOLD


def enhance(image: Image.Image, mode: str = "auto") -> Image.Image:
    """按模式处理图像；返回的图像尺寸与原图一致。"""

    chosen = (mode or "auto").strip().lower()
    if chosen == "off":
        return image
    if chosen == "auto":
        if not should_enhance(image):
            return image              # 本来够清楚，不动
        chosen = "contrast"

    rgb = image.convert("RGB")
    if chosen == "grayscale":
        return ImageOps.grayscale(rgb).convert("RGB")
    if chosen == "contrast":
        stretched = ImageOps.autocontrast(rgb, cutoff=1)
        return ImageEnhance.Contrast(stretched).enhance(1.4)
    if chosen == "sharpen":
        return rgb.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
    if chosen == "binarize":
        gray = ImageOps.autocontrast(rgb.convert("L"), cutoff=1)
        return gray.point(lambda value: 255 if value > 128 else 0).convert("RGB")
    return image                      # 不认识的模式就当没开
