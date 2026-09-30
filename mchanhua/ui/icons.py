"""界面小图标：从 assets/icons 加载成 CTkImage（高 DPI 下自动用大图缩）。

图标由 tools/make_icons.py 生成（Pillow 画线稿再缩放，边缘干净）。
找不到文件时返回 None，调用方就把图片参数留空——界面照样能用，不会因为缺图起不来。
"""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk
from PIL import Image

from mchanhua.logging_setup import get_logger
from mchanhua.paths import resource_dir

ICONS_SUBDIR = Path("assets") / "icons"
DEFAULT_SIZE = (18, 18)

# 只缓存 PIL 原图（读盘一次）。CTkImage 不能跨 Tk 解释器复用：
# 它内部缓存了绑定到某个 Tk 的 PhotoImage，换个 root 再用就会报
# `image "pyimage1" doesn't exist`，所以每次调用都新建一个。
_images: dict[tuple[str, bool], Image.Image | None] = {}


def icons_dir() -> Path:
    return resource_dir() / ICONS_SUBDIR


def icon_path(name: str, accent: bool = False) -> Path:
    suffix = "_accent" if accent else ""
    return icons_dir() / f"{name}{suffix}.png"


def icon(name: str, size: tuple[int, int] = DEFAULT_SIZE, accent: bool = False):
    """取一个图标（拿不到就返回 None）。原图带缓存，CTkImage 每次新建。"""

    key = (name, accent)
    if key not in _images:
        _images[key] = _load_image(name, accent)
    image = _images[key]
    if image is None:
        return None
    try:
        return ctk.CTkImage(light_image=image, dark_image=image, size=size)
    except Exception:  # pragma: no cover - 极少数情况下 Tk 还没就绪
        get_logger().warning("图标创建失败：%s", name, exc_info=True)
        return None


def _load_image(name: str, accent: bool) -> Image.Image | None:
    path = icon_path(name, accent)
    try:
        if path.exists():
            with Image.open(path) as raw:
                converted = raw.convert("RGBA")
                converted.load()
            return converted
    except Exception:  # pragma: no cover - 图标坏了不该影响界面
        get_logger().warning("图标读取失败：%s", path, exc_info=True)
    return None


def clear_cache() -> None:
    """测试用：换目录/重新生成图标后清一下缓存。"""

    _images.clear()
