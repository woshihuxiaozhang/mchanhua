"""生成程序图标（assets/mchanhua.ico + 一张 256 预览图）。

画的是一只简约的白猫：深色圆角底 + 白猫头（尖耳朵、闭眼、粉鼻子），
不画背景装饰，缩到 16×16 也还认得出是猫。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "assets" / "mchanhua.ico"
PREVIEW = REPO / "assets" / "mchanhua.png"

BG = (35, 40, 48, 255)          # 深蓝灰底（和界面里的深色一致）
FUR = (255, 255, 255, 255)      # 白猫
LINE = (58, 64, 74, 255)        # 轮廓线（浅一点的深灰）
NOSE = (240, 160, 170, 255)     # 粉鼻子

SIZES = [16, 24, 32, 48, 64, 128, 256]


def _head(size: int) -> tuple[float, float, float, float]:
    """猫头的外接框（留出耳朵和边距的位置）。"""

    margin = size * 0.15
    top = size * 0.34
    return (margin, top, size - margin, size * 0.86)


def _ears(size: int) -> tuple[tuple[float, float], ...]:
    """两只耳朵的三角形顶点。"""

    left, top, right, bottom = _head(size)
    width = right - left
    height = bottom - top
    def ear(outer_x: float, inner_x: float, tip_x: float) -> tuple[tuple[float, float], ...]:
        # 耳朵底边压在圆脸上，尖朝外上方——这样拼出来才像猫，不像兔子
        return (
            (outer_x, top + height * 0.34),
            (tip_x, top - height * 0.40),
            (inner_x, top + height * 0.14),
        )

    return (
        ear(left + width * 0.03, left + width * 0.44, left + width * 0.19),
        ear(right - width * 0.03, right - width * 0.44, right - width * 0.19),
    )


def render(size: int) -> Image.Image:
    """画一张 size×size 的图标。所有尺寸都用同一套比例，缩小后也不会走样。"""

    # 先按 4 倍画再缩回来，边缘更干净（小尺寸尤其明显）
    scale = 4
    canvas = size * scale
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    line_width = max(2, round(canvas * 0.030))
    left, top, right, bottom = (_head(canvas))

    # 先把「耳朵 + 头」画成一张白模，再整体描一圈边——
    # 这样耳朵和头是一体的，中间不会出现接缝黑线
    mask = Image.new("L", (canvas, canvas), 0)
    mold = ImageDraw.Draw(mask)
    for triangle in _ears(canvas):
        mold.polygon(triangle, fill=255)
    mold.ellipse([left, top, right, bottom], fill=255)      # 圆脸
    outline = mask.filter(ImageFilter.MaxFilter(line_width * 2 + 1))

    # 底：圆角方块
    draw.rounded_rectangle(
        [0, 0, canvas - 1, canvas - 1], radius=max(3, canvas // 6), fill=BG
    )
    image.paste(LINE, (0, 0, canvas, canvas), outline)
    image.paste(FUR, (0, 0, canvas, canvas), mask)

    # 眼睛：两条闭眼弧线
    eye_width = (right - left) * 0.26
    eye_y = top + (bottom - top) * 0.46
    eye_offset = (right - left) * 0.22
    center_x = (left + right) / 2
    for sign in (-1, 1):
        x = center_x + sign * eye_offset
        draw.arc(
            [x - eye_width / 2, eye_y - eye_width * 0.42, x + eye_width / 2, eye_y + eye_width * 0.42],
            start=200, end=340, fill=LINE, width=max(1, int(canvas * 0.030)),
        )

    # 鼻子：一个小粉三角
    nose_y = top + (bottom - top) * 0.66
    nose_w = (right - left) * 0.11
    draw.polygon(
        [(center_x - nose_w / 2, nose_y - nose_w * 0.3),
         (center_x + nose_w / 2, nose_y - nose_w * 0.3),
         (center_x, nose_y + nose_w * 0.7)],
        fill=NOSE,
    )

    return image.resize((size, size), Image.LANCZOS)


def main() -> int:
    images = [render(size) for size in SIZES]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    images[-1].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES])
    PREVIEW.parent.mkdir(parents=True, exist_ok=True)
    images[-1].save(PREVIEW, format="PNG")
    print(f"已生成图标：{OUT}（{', '.join(str(s) for s in SIZES)}）")
    print(f"预览图：{PREVIEW}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
