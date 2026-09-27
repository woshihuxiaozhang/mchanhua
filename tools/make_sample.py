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

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FONT_ENTRY = "assets/minecraft/textures/font/ascii.png"
UNICODE_PAGE_ENTRY = "assets/minecraft/textures/font/unicode_page_{page:02x}.png"
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


def load_unicode_page(jars: list[Path], page: int = 0) -> tuple[Image.Image, Path]:
    """读取 Minecraft 的 Unifont 字形页（forceUnicodeFont:true 时游戏用的就是它）。"""

    entry = UNICODE_PAGE_ENTRY.format(page=page)
    for jar in jars:
        try:
            with zipfile.ZipFile(jar) as archive:
                if entry in archive.namelist():
                    data = archive.read(entry)
                    return Image.open(io.BytesIO(data)).convert("RGBA"), jar
        except (zipfile.BadZipFile, OSError):
            continue
    raise SystemExit(f"没有找到 {entry}")


def unicode_glyphs(page_image: Image.Image, first: int = 0x20, last: int = 0x7F) -> dict[str, Image.Image]:
    """Unifont 页是 16x16 个 16x16 像素的字形格。"""

    cell = page_image.width // 16
    glyphs: dict[str, Image.Image] = {}
    for code in range(first, last + 1):
        index = code & 0xFF
        col, row = index % 16, index // 16
        box = (col * cell, row * cell, (col + 1) * cell, (row + 1) * cell)
        if box[2] <= page_image.width and box[3] <= page_image.height:
            glyphs[chr(code)] = page_image.crop(box)
    return glyphs


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


def render_ttf(lines: list[tuple[str, tuple[int, int, int]]], font_path: Path, size: int) -> Image.Image:
    """用 TTF 渲染（模拟把游戏字体换成防锯齿 TTF 的资源包）。"""

    if not font_path.exists():
        raise SystemExit(f"找不到 TTF 字体：{font_path}")
    font = ImageFont.truetype(str(font_path), size)
    padding_x, padding_y, line_height = 4, 3, size + 2
    widest = max((int(font.getlength(text)) for text, _ in lines), default=0)

    width = widest + padding_x * 2 + 4
    height = len(lines) * line_height + padding_y * 2 + 2
    image = Image.new("RGBA", (width, height), (16, 0, 16, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width - 1, height - 1], outline=(80, 0, 255, 255))

    y = padding_y
    for text, color in lines:
        shadow = tuple(max(0, channel // SHADOW_DIVISOR) for channel in color)
        draw.text((padding_x + 1, y + 1), text, font=font, fill=shadow + (255,))
        draw.text((padding_x, y), text, font=font, fill=color + (255,))
        y += line_height
    return image.convert("RGB")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 Minecraft 风格样例截图")
    parser.add_argument("--minecraft-dir", default=str(DEFAULT_MINECRAFT_DIR))
    parser.add_argument("--out", default="tmp/mc_sample.png")
    parser.add_argument(
        "--font",
        choices=("ascii", "unicode", "ttf"),
        default="ascii",
        help="ascii 是默认位图字体；unicode 对应 forceUnicodeFont:true；ttf 模拟把游戏字体换成防锯齿 TTF 资源包",
    )
    parser.add_argument("--ttf", default="C:/Windows/Fonts/consola.ttf", help="ttf 字体文件路径")
    parser.add_argument("--ttf-size", type=int, default=12, help="ttf 字号（游戏里再按 GUI 缩放放大）")
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

    lines = [
        ("Steel Ingot", WHITE),
        ("A sturdy ingot of steel", GRAY),
        ("Right-click to place", GRAY),
        ("Durability 1234 / 1234", GREEN),
        ("Requires level 30", YELLOW),
    ]

    if args.font == "ttf":
        image = render_ttf(lines, Path(args.ttf), args.ttf_size)
        print(f"字体来源：{args.ttf}（{args.ttf_size}px TTF，模拟字体资源包）")
    else:
        if args.font == "unicode":
            sheet, jar = load_unicode_page(jars, 0)
            glyphs = unicode_glyphs(sheet)
        else:
            sheet, jar = load_font_sheet(jars)
            glyphs = split_glyphs(sheet)
        print(f"字体来源：{jar}")
        print(f"字体纹理：{sheet.width}x{sheet.height}（{args.font}）")
        image = render(lines, glyphs)

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
