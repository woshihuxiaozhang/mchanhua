"""对比度检查（WCAG 2.1 SC 1.4.3）：正文 ≥ 4.5:1，大字/图形 ≥ 3:1。"""

from __future__ import annotations

import re

HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")


def _luminance(color: str) -> float:
    value = color.lstrip("#")
    channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    channels = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def is_hex(color: str) -> bool:
    return bool(HEX.match((color or "").strip()))


def contrast_ratio(foreground: str, background: str) -> float:
    if not (is_hex(foreground) and is_hex(background)):
        return 0.0
    first, second = _luminance(foreground), _luminance(background)
    high, low = max(first, second), min(first, second)
    return (high + 0.05) / (low + 0.05)


def text_on(background: str, light: str = "#ffffff", dark: str = "#17171b") -> str:
    """在给定背景上挑对比度更高的文字色。"""

    return light if contrast_ratio(light, background) >= contrast_ratio(dark, background) else dark


def check_colors(colors: dict[str, str]) -> list[str]:
    """按 WCAG 检查一组配色，返回需要提醒的问题（空列表代表全部达标）。"""

    problems: list[str] = []
    background = colors.get("background", "")
    panel = colors.get("panel", "")
    accent = colors.get("accent", "")
    text = colors.get("text", "")
    dim = colors.get("text_dim", "")

    for name, foreground in (("正文文字", text), ("次级文字", dim)):
        for surface_name, surface in (("面板", panel), ("背景", background)):
            if not (is_hex(foreground) and is_hex(surface)):
                continue
            ratio = contrast_ratio(foreground, surface)
            if ratio < 4.5:
                problems.append(f"{name}在{surface_name}上的对比度只有 {ratio:.2f}:1（应 ≥ 4.5）")

    if is_hex(accent):
        # 主按钮是"强调色底 + 自动文字色"，这里报告实际能达到的对比度
        ratio = max(contrast_ratio("#ffffff", accent), contrast_ratio("#17171b", accent))
        if ratio < 4.5:
            problems.append(f"强调色上的按钮文字对比度只有 {ratio:.2f}:1（建议加深强调色）")
    return problems


def audit(theme) -> list[str]:
    """对 Theme 对象做一次体检。"""

    return check_colors(
        {
            "background": theme.background,
            "panel": theme.panel,
            "text": theme.text,
            "text_dim": theme.text_dim,
            "accent": theme.accent,
        }
    )
