"""OCR 精度与耗时度量工具。

用法：
    python tools/measure_ocr.py --image shot.png --expect "Steel Ingot"
    python tools/measure_ocr.py --image shot.png --expect-file expect.txt --upscale 1 2 3

先用它把真实截图的数据跑出来，再决定 OCR 方案和后处理策略。
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mchanhua.geometry import Region, enable_dpi_awareness  # noqa: E402
from mchanhua.metrics import cer, similarity  # noqa: E402
from mchanhua.ocr import create_engine  # noqa: E402


def _load_expected(args: argparse.Namespace) -> str:
    if args.expect:
        return args.expect
    if args.expect_file:
        return Path(args.expect_file).read_text(encoding="utf-8")
    raise SystemExit("需要 --expect 或 --expect-file 作为参照文本")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="度量 OCR 精度与耗时")
    parser.add_argument("--image", required=True, help="截图路径")
    parser.add_argument("--region", help="只取图片的 x,y,w,h 区域")
    parser.add_argument("--expect", help="参照原文")
    parser.add_argument("--expect-file", help="参照原文文件")
    parser.add_argument("--upscale", type=float, nargs="+", default=[1.0, 2.0, 3.0])
    parser.add_argument("--repeat", type=int, default=3, help="每个配置重复次数")
    parser.add_argument("--backend", default="auto")
    parser.add_argument("--language", default="auto")
    args = parser.parse_args(argv)

    enable_dpi_awareness()
    expected = _load_expected(args)
    image = Image.open(args.image)
    image.load()
    image = image.convert("RGB")
    if args.region:
        region = Region.parse(args.region)
        image = image.crop((region.x, region.y, region.right, region.bottom))

    print(f"图片：{args.image}  尺寸：{image.width}x{image.height}")
    print(f"参照文本（{len(expected)} 字符）：{expected!r}")
    print()
    print(f"{'放大':>4}  {'CER':>7}  {'相似度':>7}  {'中位耗时':>9}  {'最小':>7}  {'最大':>7}")
    print("-" * 56)

    best: tuple[float, float, str] | None = None
    for upscale in args.upscale:
        engine = create_engine(args.backend, args.language, upscale)
        timings: list[float] = []
        text = ""
        for _ in range(max(1, args.repeat)):
            started = time.perf_counter()
            result = engine.recognize(image)
            timings.append((time.perf_counter() - started) * 1000)
            text = result.text
        error_rate = cer(expected, text)
        score = similarity(expected, text)
        print(
            f"{upscale:>4.1f}  {error_rate:>7.3f}  {score:>7.3f}  "
            f"{statistics.median(timings):>9.1f}  {min(timings):>7.1f}  {max(timings):>7.1f}"
        )
        if best is None or error_rate < best[0]:
            best = (error_rate, upscale, text)

    if best is not None:
        print()
        print(f"最佳放大倍数：{best[1]}（CER {best[0]:.3f}）")
        print("识别结果：")
        for line in best[2].splitlines():
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

