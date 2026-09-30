"""生成界面用的小图标（PNG，48px，透明背景）。

为什么不用 emoji：emoji 在不同 Windows 版本上会变成彩色或方框，和界面风格也不搭。
这里用 Pillow 在 4 倍尺寸上画线稿、再缩回 48px（抗锯齿），每套两个颜色：
  assets/icons/<名字>.png        中性灰（白底按钮用）
  assets/icons/<名字>_accent.png 主题蓝（浅蓝按钮用）

用法：.venv\\Scripts\\python.exe tools\\make_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 48            # 逻辑尺寸
SCALE = 4            # 先按 4 倍画再缩回来，边缘才不毛糙
STROKE = 3           # 线宽（逻辑像素）
NEUTRAL = "#3C4043"
ACCENT = "#1A73E8"
OUT_DIR = Path(__file__).resolve().parents[1] / "assets" / "icons"


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (SIZE * SCALE, SIZE * SCALE), (0, 0, 0, 0))
    return image, ImageDraw.Draw(image)


def _box(*values: float) -> tuple[float, ...]:
    return tuple(value * SCALE for value in values)


def _line(draw, points, color, width=STROKE):
    draw.line([_box(x, y) for x, y in points], fill=color, width=int(width * SCALE), joint="curve")


def _ellipse(draw, xy, color, width=STROKE, fill=None):
    draw.ellipse(_box(*xy), outline=color, width=int(width * SCALE), fill=fill)


def _rect(draw, xy, color, width=STROKE, radius: float = 0.0, fill=None):
    draw.rounded_rectangle(
        _box(*xy), radius=radius * SCALE, outline=color, width=int(width * SCALE), fill=fill
    )


def _arc(draw, xy, start, end, color, width=STROKE):
    draw.arc(_box(*xy), start=start, end=end, fill=color, width=int(width * SCALE))


def _polygon(draw, points, color, fill=None):
    draw.polygon([_box(x, y) for x, y in points], fill=fill, outline=color)


def draw(name: str, color: str) -> Image.Image:
    image, draw = _canvas()
    if name == "scan":                       # 取词：一块文本区域
        _rect(draw, (7, 10, 41, 38), color, radius=4)
        _line(draw, [(14, 19), (34, 19)], color, width=2.5)
        _line(draw, [(14, 24.5), (34, 24.5)], color, width=2.5)
        _line(draw, [(14, 30), (26, 30)], color, width=2.5)
    elif name == "crop":                     # 框选：四个角
        for x1, y1, x2, y2 in ((10, 18, 10, 10), (10, 10, 18, 10),
                               (38, 18, 38, 10), (38, 10, 30, 10),
                               (10, 30, 10, 38), (10, 38, 18, 38),
                               (38, 30, 38, 38), (38, 38, 30, 38)):
            _line(draw, [(x1, y1), (x2, y2)], color)
    elif name == "monitor":                  # 全屏：整块屏幕
        _rect(draw, (6, 10, 42, 32), color, radius=3)
        _line(draw, [(24, 32), (24, 38)], color)
        _line(draw, [(16, 38), (32, 38)], color)
    elif name == "sliders":                  # 设置：三根滑块
        for y, knob in ((15, 30), (24, 18), (33, 27)):
            _line(draw, [(9, y), (39, y)], color, width=2.5)
            _ellipse(draw, (knob - 4, y - 4, knob + 4, y + 4), color, width=3, fill="#FFFFFF")
    elif name == "clock":                    # 历史：时钟
        _ellipse(draw, (9, 9, 39, 39), color)
        _line(draw, [(24, 24), (24, 15)], color, width=2.5)
        _line(draw, [(24, 24), (31, 28)], color, width=2.5)
    elif name == "check":                    # 保存修正：对勾
        _line(draw, [(13, 25), (21, 33), (35, 16)], color, width=4)
    elif name == "bolt":                     # 测试连接：闪电
        _polygon(draw, [(27, 6), (14, 27), (23, 27), (20, 42), (34, 20), (25, 20)], color,
                 fill=color)
    elif name == "folder":                   # 打开目录
        _line(draw, [(7, 16), (19, 16), (22, 11), (41, 11), (41, 37), (7, 37), (7, 16)], color)
    elif name == "doc":                      # 日志文件
        _line(draw, [(13, 7), (30, 7), (37, 14), (37, 41), (13, 41), (13, 7)], color)
        _line(draw, [(29, 7), (29, 15), (37, 15)], color, width=2)
        for y in (21, 27, 33):
            _line(draw, [(19, y), (31, y)], color, width=2)
    elif name == "trash":                    # 删除 / 清空
        _line(draw, [(9, 14), (39, 14)], color)
        _line(draw, [(20, 14), (20, 9), (28, 9), (28, 14)], color, width=2.5)
        _line(draw, [(13, 14), (15, 41), (33, 41), (35, 14)], color)
        _line(draw, [(21, 20), (21, 35)], color, width=2)
        _line(draw, [(27, 20), (27, 35)], color, width=2)
    elif name == "plus":                     # 框选新区域
        _line(draw, [(24, 11), (24, 37)], color, width=4)
        _line(draw, [(11, 24), (37, 24)], color, width=4)
    elif name == "eye":                      # 显示密钥
        _ellipse(draw, (8, 15, 40, 33), color, width=2.5)
        _ellipse(draw, (19, 18, 29, 30), color, width=2.5, fill=color)
    elif name == "pulse":                    # 实时：信号 + 圆点
        _ellipse(draw, (7, 19, 17, 29), color, width=3, fill=color)
        _arc(draw, (15, 11, 33, 37), 300, 60, color, width=3)
        _arc(draw, (22, 4, 46, 44), 300, 60, color, width=3)
    elif name == "refresh":                  # 刷新
        _arc(draw, (9, 9, 39, 39), 40, 320, color)
        _polygon(draw, [(33, 8), (39, 16), (29, 16)], color, fill=color)
    else:  # pragma: no cover - 名字写错时给个可见的占位
        _rect(draw, (10, 10, 38, 38), color, radius=4)
    return image.resize((SIZE, SIZE), Image.LANCZOS)


NAMES = (
    "scan", "crop", "monitor", "sliders", "clock", "check", "bolt",
    "folder", "doc", "trash", "plus", "eye", "pulse", "refresh",
)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in NAMES:
        draw(name, NEUTRAL).save(OUT_DIR / f"{name}.png")
        draw(name, ACCENT).save(OUT_DIR / f"{name}_accent.png")

    # 顺手拼一张预览图，方便一眼检查画得对不对
    sheet = Image.new("RGBA", (SIZE * len(NAMES), SIZE * 2), (255, 255, 255, 255))
    for index, name in enumerate(NAMES):
        sheet.paste(draw(name, NEUTRAL), (index * SIZE, 0), draw(name, NEUTRAL))
        sheet.paste(draw(name, ACCENT), (index * SIZE, SIZE), draw(name, ACCENT))
    sheet.save(OUT_DIR / "_preview.png")
    print(f"生成 {len(NAMES) * 2} 个图标 -> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
