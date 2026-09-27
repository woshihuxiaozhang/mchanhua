"""选区取词的采集与筛选。

早期做法是"识别到文字贴边就扩边重识别"，实测几乎每次都被否掉（扩边后 OCR 反而更差），
对"选区把文字切了一半"的问题无效。现在换成更直接的做法：

1. 抓图时**向外多抓一圈**（padding），保证被选区切断的文字也能完整进入画面；
2. 识别整张图，然后**只保留中心落在用户选区内的行**；
3. 这样送去翻译的是完整的行，选区边界差几十像素也不再影响结果。
"""

from __future__ import annotations

from typing import Callable

from PIL import Image

from mchanhua.geometry import Region
from mchanhua.logging_setup import get_logger

# 采集时向外多抓的像素数（约等于游戏里一行文字的高度）
REGION_PADDING = 80


def padded_region(region: Region, monitor: Region, pad: int = REGION_PADDING) -> Region:
    """把选区向外扩一圈，并限制在屏幕范围内。"""

    left = max(monitor.x, region.x - pad)
    top = max(monitor.y, region.y - pad)
    right = min(monitor.right, region.right + pad)
    bottom = min(monitor.bottom, region.bottom + pad)
    return Region(left, top, right - left, bottom - top)


# 行与选区的重叠比例达到这个值就认为"这行是用户想看的"
MIN_OVERLAP_RATIO = 0.25


def filter_lines_in_region(
    ocr_result,
    capture: Region,
    region: Region,
    min_overlap: float = MIN_OVERLAP_RATIO,
):
    """保留用户选区内的行。

    判定规则（满足其一即可）：
    - 行的中心点落在选区内；
    - 行与选区的重叠面积占该行面积的 min_overlap 以上。

    只用中心点会误删长行（例如整行 1800px 宽、选区只盖住左半），所以加了重叠比例。
    ocr_result 里的坐标是相对 capture（抓下来的那张图）的，先换算成屏幕坐标。
    """

    kept = []
    for line in getattr(ocr_result, "lines", []):
        box = line.box
        if box is None:
            kept.append(line)
            continue
        line_region = Region(capture.x + box.x, capture.y + box.y, box.width, box.height)
        center = line_region.center
        if region.contains(int(center[0]), int(center[1])):
            kept.append(line)
            continue
        overlap = line_region.intersect(region)
        if overlap is not None and overlap.area / max(1, line_region.area) >= min_overlap:
            kept.append(line)

    return type(ocr_result)(
        lines=kept,
        elapsed_ms=getattr(ocr_result, "elapsed_ms", 0.0),
        backend=getattr(ocr_result, "backend", ""),
        language=getattr(ocr_result, "language", None),
    )


def capture_padded_and_filter(
    region: Region | None,
    monitor: Region,
    grab: Callable[[Region], Image.Image],
    recognize: Callable[[Image.Image], object],
    pad: int = REGION_PADDING,
    mode: str = "screen",
) -> tuple[Region | None, Image.Image, object]:
    """抓图 + 识别；选区模式只保留选区内的行。返回 (实际抓图区域, 图片, 识别结果)。

    mode="screen"：整屏识别后按选区筛选 —— 保证每一行都完整（默认，慢一点但稳）；
    mode="padded"：只抓选区外扩的一小圈 —— 快，但横向被切掉的长句补不回来。
    """

    if region is None or mode == "screen":
        capture: Region | None = monitor
    else:
        capture = padded_region(region, monitor, pad)
    image = grab(capture)
    result = recognize(image)

    if region is None:
        return None, image, result

    filtered = filter_lines_in_region(result, capture, region)
    if not filtered.lines and getattr(result, "lines", None):
        # 中心点都没命中（选区可能压在文字缝隙上），退回用整张抓图的结果
        get_logger().info("选区内没有命中的行，改用整张抓图的结果")
        return capture, image, result
    get_logger().info(
        "抓图区域 %s（模式 %s），识别 %d 行，其中 %d 行落在选区 %s 内",
        capture.to_csv(),
        mode,
        len(getattr(result, "lines", [])),
        len(filtered.lines),
        region.to_csv(),
    )
    return capture, image, filtered
