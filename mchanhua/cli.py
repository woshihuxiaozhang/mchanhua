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
from mchanhua.console import configure_stdio
from mchanhua.geometry import Region, enable_dpi_awareness
from mchanhua.logging_setup import get_logger, setup_logging
from mchanhua.ocr import create_engine
from mchanhua.ocr import windows as windows_ocr
from mchanhua.ocr.base import OcrUnavailable
from mchanhua.pipeline import render_pairs, run_pipeline
from mchanhua.translate import create_translator


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
    from mchanhua.config import resolve_config_path

    resolved = resolve_config_path(args.config)
    print(f"配置文件：{resolved}{'' if resolved.exists() else '（不存在，使用默认值）'}")
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
    engine = create_engine(
        args.backend or config.ocr.backend,
        config.ocr.language,
        args.upscale or config.ocr.upscale,
        invert=config.ocr.invert,
    )
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

    engine = create_engine(
        args.backend or config.ocr.backend,
        config.ocr.language,
        args.upscale or config.ocr.upscale,
        invert=config.ocr.invert,
    )
    result = engine.recognize(image)
    _print_result(result, args.json)
    grabber.close()
    return 0


def cmd_translate_image(args: argparse.Namespace) -> int:
    """对图片做「OCR + 真实翻译」，用来验证 API key 与翻译效果（不开界面）。"""

    enable_dpi_awareness()
    config = load_config(args.config)
    region = Region.parse(args.region) if args.region else None
    image = _load_image(Path(args.image), region)
    engine = create_engine(
        args.backend or config.ocr.backend,
        config.ocr.language,
        args.upscale or config.ocr.upscale,
        invert=config.ocr.invert,
    )

    translator = None
    api_key = config.resolved_api_key
    if api_key:
        translator = create_translator(config.translate, api_key, glossary=config.glossary)
    else:
        print("未配置 DeepSeek API key，只输出识别原文。", file=sys.stderr)

    result = run_pipeline(image, engine, translator)
    print(render_pairs(result))
    print()
    print(
        f"--- OCR {result.ocr_ms:.0f} ms / 翻译 {result.translate_ms:.0f} ms / "
        f"已翻 {result.translated_count} 行 / 后端 {result.ocr_backend} ---"
    )
    for warning in result.warnings:
        print(f"提示：{warning}", file=sys.stderr)
    return 0


def cmd_config_init(args: argparse.Namespace) -> int:
    config = Config()
    if args.config:
        target = args.config
    elif args.global_config:
        from mchanhua.config import default_config_path

        target = default_config_path()
    else:
        from mchanhua.config import project_config_path

        target = project_config_path()
    path = save_config(config, target)
    print(f"已写入默认配置：{path}")
    return 0


def cmd_config_path(args: argparse.Namespace) -> int:
    from mchanhua.config import resolve_config_path

    print(resolve_config_path(args.config))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from mchanhua.app import Application

    enable_dpi_awareness()
    config = load_config(args.config)
    if args.region:
        config.regions.fixed["tooltip"] = args.region
    app = Application(config, use_hotkeys=not args.no_hotkeys)
    print("小窗已启动。热键：取词翻译 / 框选区域 / 退出（见配置文件 [hotkeys]）")
    print(f"日志文件：{LOG_PATH}")
    get_logger().info("启动界面：配置 %r，OCR 后端 %s", args.config, config.ocr.backend)
    app.start()
    return 0


LOG_PATH: Path | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mchanhua", description="Minecraft 屏幕取词汉化小工具")
    parser.add_argument(
        "--config",
        help="配置文件路径（缺省优先用项目内 config.local.toml，其次 %%APPDATA%%\\mchanhua\\config.toml）",
    )
    # 故意不设 required：不给子命令时由 main() 给出中文提示，而不是 argparse 的英文报错
    sub = parser.add_subparsers(dest="command")

    probe = sub.add_parser("probe", help="检查运行环境")
    probe.set_defaults(func=cmd_probe)

    ocr_image = sub.add_parser("ocr-image", help="对图片文件做 OCR")
    ocr_image.add_argument("image")
    ocr_image.add_argument("-r", "--region", help="只处理图片中的 x,y,w,h 区域")
    ocr_image.add_argument("--upscale", type=float, help="识别前放大倍数，默认取配置值")
    ocr_image.add_argument("--backend", choices=("auto", "windows", "rapidocr"), help="OCR 后端，默认取配置值")
    ocr_image.add_argument("--json", action="store_true", help="输出 JSON")
    ocr_image.set_defaults(func=cmd_ocr_image)

    ocr_screen = sub.add_parser("ocr-screen", help="截取屏幕并 OCR")
    ocr_screen.add_argument("-r", "--region", help="截取区域 x,y,w,h，缺省为整屏")
    ocr_screen.add_argument("-n", "--name", help="使用配置里的命名区域")
    ocr_screen.add_argument("--upscale", type=float, help="识别前放大倍数，默认取配置值")
    ocr_screen.add_argument("--backend", choices=("auto", "windows", "rapidocr"), help="OCR 后端，默认取配置值")
    ocr_screen.add_argument("--save", help="把截图保存到指定路径，便于排查")
    ocr_screen.add_argument("--json", action="store_true", help="输出 JSON")
    ocr_screen.set_defaults(func=cmd_ocr_screen)

    translate_image = sub.add_parser("translate-image", help="对图片做 OCR + 翻译（验证 API key 用）")
    translate_image.add_argument("image")
    translate_image.add_argument("-r", "--region", help="只处理图片中的 x,y,w,h 区域")
    translate_image.add_argument("--upscale", type=float, help="识别前放大倍数，默认取配置值")
    translate_image.add_argument("--backend", choices=("auto", "windows", "rapidocr"), help="OCR 后端")
    translate_image.set_defaults(func=cmd_translate_image)

    config_init = sub.add_parser("config-init", help="写出默认配置文件")
    config_init.add_argument(
        "--global",
        dest="global_config",
        action="store_true",
        help="写到 %%APPDATA%%\\mchanhua\\config.toml，而不是项目目录下的 config.local.toml",
    )
    config_init.set_defaults(func=cmd_config_init)

    config_path = sub.add_parser("config-path", help="打印配置文件路径")
    config_path.set_defaults(func=cmd_config_path)

    run = sub.add_parser("run", help="启动取词小窗（热键 + 框选）")
    run.add_argument("-r", "--region", help="预先指定固定采集区域 x,y,w,h")
    run.add_argument("--no-hotkeys", action="store_true", help="不注册全局热键（只点按钮）")
    run.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    global LOG_PATH
    configure_stdio()
    LOG_PATH = setup_logging()
    parser = build_parser()
    effective = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(argv)
    get_logger().info("命令：%s", " ".join(effective) if effective else "(无子命令)")
    if getattr(args, "command", None) is None:
        # 不给子命令时给出明确提示，而不是 argparse 的原始报错
        parser.print_help()
        print()
        print("提示：要启动取词小窗请用  mchanhua run")
        print("      想先看看环境是否正常用  mchanhua probe")
        print("      最省事的办法是直接双击项目目录里的「启动.cmd」")
        get_logger().warning("未指定子命令，已打印用法提示")
        return 2
    try:
        return args.func(args)
    except OcrUnavailable as exc:
        get_logger().error("OCR 不可用：%s", exc)
        print(f"OCR 不可用：{exc}", file=sys.stderr)
        return 3
    except Exception:
        get_logger().exception("命令执行失败")
        raise
