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

    return capture, image, filter_capture(region, capture, result, mode=mode)


def capture_region_for(region: Region | None, monitor: Region, mode: str = "screen") -> Region:
    """算出实际要抓的区域：整屏模式 = 整屏；padded 模式 = 选区外扩一圈。

    抓图和识别分成两步之后，主线程可以"抓完就恢复窗口"，不用等 OCR。
    """

    if region is None or mode == "screen":
        return monitor
    return padded_region(region, monitor)


def filter_capture(region: Region, capture: Region, ocr_result, mode: str = "screen"):
    """选区模式：只保留选区内的行，并把结果写进日志。"""

    filtered = filter_lines_in_region(ocr_result, capture, region)
    if not filtered.lines:
        # 选区里没有文字就是没有文字：**不要**退回整屏结果（那会把屏幕上的
        # 其它文字当成选区内容翻译出来）。交给上层提示"没有识别到文字"。
        get_logger().info(
            "选区内没有命中任何一行（屏幕共识别 %d 行，都在选区 %s 之外）",
            len(getattr(ocr_result, "lines", [])),
            region.to_csv(),
        )
        return filtered
    get_logger().info(
        "抓图区域 %s（模式 %s），识别 %d 行，其中 %d 行落在选区 %s 内",
        capture.to_csv(),
        mode,
        len(getattr(ocr_result, "lines", [])),
        len(filtered.lines),
        region.to_csv(),
    )
    return filtered


def filter_area_lines(
    ocr_result,
    capture: Region,
    areas: list[tuple[str, Region]],
) -> tuple[list, list[str]]:
    """多区域：按区域顺序收集行，返回 (行, 每行的区域名)。

    - 每个区域内保持 OCR 的先后顺序（从上到下）；
    - 重叠区域里同一行只算一次，归给先出现的那个区域；
    - 区域之间按用户排的顺序拼接，方便译文里按区域分组显示。
    """

    lines: list = []
    labels: list[str] = []
    seen: set[str] = set()
    for name, region in areas:
        filtered = filter_lines_in_region(ocr_result, capture, region)
        ordered = sorted(
            filtered.lines,
            key=lambda line: (line.box.y, line.box.x) if line.box else (0, 0),
        )
        for line in ordered:
            key = line.text.strip().casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            lines.append(line)
            labels.append(name)
    get_logger().info(
        "多区域取词：%d 个区域共 %d 行（%s）",
        len(areas),
        len(lines),
        "；".join(f"{name} {len([1 for item in labels if item == name])} 行" for name, _ in areas),
    )
    return lines, labels
