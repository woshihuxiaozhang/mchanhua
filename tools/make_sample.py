"""用 Minecraft 自带位图字体渲染一张"游戏风格"截图，用于 OCR 精度测试。

字体纹理直接从本机已安装的客户端 jar 里读，仓库里不保存任何 Minecraft 素材。

用法：
    python tools/make_sample.py --out tmp/mc_sample.png --print-expected
"""

from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FONT_ENTRY = "assets/minecraft/textures/font/ascii.png"
ASCII_CHARS = [chr(code) for code in range(0x20, 0x7F)]
SHADOW_DIVISOR = 4

DEFAULT_MINECRAFT_DIR = Path(r"D:\youxi\PCL 正式版 2.10.3\.minecraft")

GRAY = (170, 170, 170)
WHITE = (255, 255, 255)
GREEN = (85, 255, 85)
YELLOW = (255, 255, 85)


def find_client_jars(minecraft_dir: Path) -> list[Path]:
    versions = minecraft_dir / "versions"
    if not versions.is_dir():
        return []
    return sorted(versions.glob("*/*.jar"))


def load_font_sheet(jars: list[Path]) -> tuple[Image.Image, Path]:
    for jar in jars:
        try:
            with zipfile.ZipFile(jar) as archive:
                if FONT_ENTRY in archive.namelist():
                    data = archive.read(FONT_ENTRY)
                    return Image.open(io.BytesIO(data)).convert("RGBA"), jar
        except (zipfile.BadZipFile, OSError):
            continue
    raise SystemExit(
        f"没有在这些 jar 中找到 {FONT_ENTRY}：\n" + "\n".join(str(j) for j in jars)
    )


def split_glyphs(sheet: Image.Image) -> dict[str, Image.Image]:
    cell_width = sheet.width // 16
    cell_height = sheet.height // 16
    glyphs: dict[str, Image.Image] = {}
    for index, char in enumerate(ASCII_CHARS):
        col, row = index % 16, index // 16
        box = (
            col * cell_width,
            row * cell_height,
            (col + 1) * cell_width,
            (row + 1) * cell_height,
        )
        glyphs[char] = sheet.crop(box)
    return glyphs


def glyph_advance(glyph: Image.Image) -> int:
    """按字形实际占用宽度估算步进（Minecraft 用字体描述文件里的宽度表）。"""

    bbox = glyph.getchannel("A").getbbox()
    return 0 if bbox is None else bbox[2]


def draw_line(
    image: Image.Image,
    text: str,
    position: tuple[int, int],
    glyphs: dict[str, Image.Image],
    color: tuple[int, int, int],
) -> int:
    """按 Minecraft 的方式绘制一行文字（阴影 + 主体），返回结束时的 x 坐标。"""

    alpha = Image.new("L", (1, 1))
    shadow_color = tuple(max(0, channel // SHADOW_DIVISOR) for channel in color)

    for pass_color, offset in ((shadow_color, (1, 1)), (color, (0, 0))):
        x, y = position[0] + offset[0], position[1] + offset[1]
        for char in text:
            glyph = glyphs.get(char)
            if glyph is None:
                continue
            advance = glyph_advance(glyph)
            if advance == 0:
                x += 4
                continue
            mask = glyph.getchannel("A")
            tile = Image.new("RGBA", glyph.size, pass_color + (0,))
            tile.putalpha(mask)
            image.alpha_composite(tile, (x, y))
            x += advance + 1
        _ = alpha  # 占位，避免未使用告警
    x = position[0]
    for char in text:
        glyph = glyphs.get(char)
        if glyph is None:
            continue
        advance = glyph_advance(glyph)
        x += (advance + 1) if advance else 4
    return x


def render(lines: list[tuple[str, tuple[int, int, int]]], glyphs: dict[str, Image.Image]) -> Image.Image:
    padding_x, padding_y, line_height = 4, 3, 10
    widest = 0
    for text, _ in lines:
        width = 0
        for char in text:
            glyph = glyphs.get(char)
            advance = glyph_advance(glyph) if glyph is not None else 0
            width += (advance + 1) if advance else 4
        widest = max(widest, width)

    width = widest + padding_x * 2 + 4
    height = len(lines) * line_height + padding_y * 2 + 2
    image = Image.new("RGBA", (width, height), (16, 0, 16, 255))  # 1.20 tooltip 背景色

    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width - 1, height - 1], outline=(80, 0, 255, 255))

    y = padding_y
    for text, color in lines:
        draw_line(image, text, (padding_x, y), glyphs, color)
        y += line_height
    return image.convert("RGB")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 Minecraft 风格样例截图")
    parser.add_argument("--minecraft-dir", default=str(DEFAULT_MINECRAFT_DIR))
    parser.add_argument("--out", default="tmp/mc_sample.png")
    parser.add_argument(
        "--gui-scale",
        type=int,
        default=3,
        help="模拟 Minecraft 的 GUI 缩放：整图按整数倍最近邻放大（游戏里字体像素就是这样被放大的）",
    )
    parser.add_argument("--print-expected", action="store_true", help="打印参照原文")
    args = parser.parse_args(argv)

    jars = find_client_jars(Path(args.minecraft_dir))
    if not jars:
        raise SystemExit(f"没找到客户端 jar，请检查 --minecraft-dir：{args.minecraft_dir}")
    sheet, jar = load_font_sheet(jars)
    print(f"字体来源：{jar}")
    print(f"字体纹理：{sheet.width}x{sheet.height}")

    lines = [
        ("Steel Ingot", WHITE),
        ("A sturdy ingot of steel", GRAY),
        ("Right-click to place", GRAY),
        ("Durability 1234 / 1234", GREEN),
        ("Requires level 30", YELLOW),
    ]
    image = render(lines, split_glyphs(sheet))

    if args.gui_scale > 1:
        image = image.resize(
            (image.width * args.gui_scale, image.height * args.gui_scale),
            Image.NEAREST,
        )

    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    print(f"已生成：{target}（{image.width}x{image.height}）")
    if args.print_expected:
        print("--- 参照原文 ---")
        for text, _ in lines:
            print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
