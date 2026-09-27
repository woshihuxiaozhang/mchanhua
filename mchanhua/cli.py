"""命令行入口，用于环境自检与手动验证 OCR 效果。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

from mchanhua import __version__
from mchanhua.capture import create_grabber, grab_screen
from mchanhua.config import Config, load_config, save_config
from mchanhua.geometry import Region, enable_dpi_awareness
from mchanhua.ocr import create_engine
from mchanhua.ocr import windows as windows_ocr
from mchanhua.ocr.base import OcrUnavailable


def configure_stdio() -> None:
    """让中文在 Windows 控制台里正常输出（默认代码页是 GBK）。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _load_image(path: Path, region: Region | None) -> Image.Image:
    image = Image.open(path)
    image.load()
    if region is not None:
        image = image.crop((region.x, region.y, region.right, region.bottom))
    return image.convert("RGB")


def _print_result(result, as_json: bool) -> None:
    if as_json:
        payload = {
            "backend": result.backend,
            "language": result.language,
            "elapsed_ms": round(result.elapsed_ms, 1),
            "lines": [
                {
                    "text": line.text,
                    "box": line.box.to_tuple() if line.box else None,
                    "words": list(line.words),
                }
                for line in result.lines
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"后端 {result.backend} / 语言 {result.language} / 耗时 {result.elapsed_ms:.1f} ms")
    print(f"识别到 {len(result.lines)} 行，{result.char_count} 个字符：")
    for index, line in enumerate(result.lines, 1):
        print(f"  {index:>2}. {line.text}")


def cmd_probe(args: argparse.Namespace) -> int:
    mode = enable_dpi_awareness()
    config = load_config(args.config)
    print(f"mchanhua {__version__}")
    print(f"DPI 感知模式：{mode}")
    print(f"配置文件：{args.config or '<默认路径>'}")
    try:
        grabber = create_grabber(config.capture.backend, config.capture.monitor)
        monitors = grabber.monitors()
        print(f"采集后端：{grabber.name}，显示器 {len(monitors)} 个")
        for index, monitor in enumerate(monitors):
            marker = "主显示器" if index == config.capture.monitor else ""
            print(f"  [{index}] {monitor.to_csv()} {marker}")
    except Exception as exc:
        print(f"采集后端不可用：{exc}")

    try:
        languages = windows_ocr.available_languages()
        print(f"Windows OCR 语言：{languages if languages else '无'}")
        print(f"将使用：{windows_ocr.pick_language(config.ocr.language)}")
    except OcrUnavailable as exc:
        print(f"Windows OCR 不可用：{exc}")

    key_state = "已设置" if config.resolved_api_key else "未设置"
    print(f"DeepSeek API key：{key_state}（模型 {config.translate.model}）")
    return 0


def cmd_ocr_image(args: argparse.Namespace) -> int:
    enable_dpi_awareness()
    config = load_config(args.config)
    region = Region.parse(args.region) if args.region else None
    image = _load_image(Path(args.image), region)
    engine = create_engine(config.ocr.backend, config.ocr.language, args.upscale or config.ocr.upscale)
    result = engine.recognize(image)
    _print_result(result, args.json)
    return 0


def cmd_ocr_screen(args: argparse.Namespace) -> int:
    enable_dpi_awareness()
    config = load_config(args.config)
    grabber = create_grabber(config.capture.backend, config.capture.monitor)

    region = None
    if args.region:
        region = Region.parse(args.region)
    elif args.name:
        region = config.regions.fixed_region(args.name)
        if region is None:
            print(f"配置里没有名为 {args.name} 的区域", file=sys.stderr)
            return 2

    image = grab_screen(grabber, region)
    if args.save:
        target = Path(args.save)
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target)
        print(f"截图已保存：{target}（{image.width}x{image.height}）")

    engine = create_engine(config.ocr.backend, config.ocr.language, args.upscale or config.ocr.upscale)
    result = engine.recognize(image)
    _print_result(result, args.json)
    grabber.close()
    return 0


def cmd_config_init(args: argparse.Namespace) -> int:
    config = Config()
    path = save_config(config, args.config)
    print(f"已写入默认配置：{path}")
    return 0


def cmd_config_path(args: argparse.Namespace) -> int:
    from mchanhua.config import default_config_path

    print(args.config or default_config_path())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mchanhua", description="Minecraft 屏幕取词汉化小工具")
    parser.add_argument("--config", help="配置文件路径（默认 %%APPDATA%%\\mchanhua\\config.toml）")
    sub = parser.add_subparsers(dest="command", required=True)

    probe = sub.add_parser("probe", help="检查运行环境")
    probe.set_defaults(func=cmd_probe)

    ocr_image = sub.add_parser("ocr-image", help="对图片文件做 OCR")
    ocr_image.add_argument("image")
    ocr_image.add_argument("-r", "--region", help="只处理图片中的 x,y,w,h 区域")
    ocr_image.add_argument("--upscale", type=float, help="识别前放大倍数，默认取配置值")
    ocr_image.add_argument("--json", action="store_true", help="输出 JSON")
    ocr_image.set_defaults(func=cmd_ocr_image)

    ocr_screen = sub.add_parser("ocr-screen", help="截取屏幕并 OCR")
    ocr_screen.add_argument("-r", "--region", help="截取区域 x,y,w,h，缺省为整屏")
    ocr_screen.add_argument("-n", "--name", help="使用配置里的命名区域")
    ocr_screen.add_argument("--upscale", type=float, help="识别前放大倍数，默认取配置值")
    ocr_screen.add_argument("--save", help="把截图保存到指定路径，便于排查")
    ocr_screen.add_argument("--json", action="store_true", help="输出 JSON")
    ocr_screen.set_defaults(func=cmd_ocr_screen)

    config_init = sub.add_parser("config-init", help="写出默认配置文件")
    config_init.set_defaults(func=cmd_config_init)

    config_path = sub.add_parser("config-path", help="打印配置文件路径")
    config_path.set_defaults(func=cmd_config_path)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except OcrUnavailable as exc:
        print(f"OCR 不可用：{exc}", file=sys.stderr)
        return 3
