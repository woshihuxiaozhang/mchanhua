"""自动扩边：选区的文字被切掉时，自动向外扩一圈重识别。

"翻译不全"最常见的原因就是选区没框住整段文字。这里的策略是：
1. 识别出的文字贴住裁剪边缘 → 说明很可能被切了；
2. 往外扩一圈重识别；
3. **只有结果变好才采纳**（否则保持原样），避免把模糊文字越弄越糟。
"""

from __future__ import annotations

from typing import Callable

from PIL import Image

from mchanhua.geometry import Region
from mchanhua.logging_setup import get_logger
from mchanhua.pipeline import (
    EXPAND_STEP,
    MAX_EXPAND_ROUNDS,
    clipped_directions,
    expand_region_for_clipping,
)


def ocr_score(ocr_result) -> int:
    """识别结果的粗略评分：认出来的字符越多越好。"""

    return sum(len(line.text.strip()) for line in getattr(ocr_result, "lines", []))


def capture_with_autoexpand(
    region: Region | None,
    monitor: Region,
    grab: Callable[[Region], Image.Image],
    recognize: Callable[[Image.Image], object],
    max_rounds: int = MAX_EXPAND_ROUNDS,
    step: int = EXPAND_STEP,
) -> tuple[Region, Image.Image, object]:
    """抓图 + 识别，必要时自动扩边。返回最终使用的 (选区, 图片, 识别结果)。"""

    current = region if region is not None else monitor
    image = grab(current)
    result = recognize(image)
    logger = get_logger()

    for _ in range(max_rounds):
        directions = clipped_directions(result, (image.width, image.height))
        if not directions:
            break
        expanded = expand_region_for_clipping(current, directions, monitor, step=step)
        if expanded is None:
            logger.info("文字贴住屏幕边界（%s），无法继续扩边", "/".join(sorted(directions)))
            break

        candidate_image = grab(expanded)
        candidate_result = recognize(candidate_image)
        before, after = ocr_score(result), ocr_score(candidate_result)
        if after <= before:
            logger.info(
                "扩边后识别结果没有变好（%d → %d 字符），保持原选区 %s",
                before,
                after,
                current.to_csv(),
            )
            break

        logger.info(
            "文字贴住选区边缘（%s），自动扩展 %s → %s（识别字符 %d → %d）",
            "/".join(sorted(directions)),
            current.to_csv(),
            expanded.to_csv(),
            before,
            after,
        )
        current, image, result = expanded, candidate_image, candidate_result

    return current, image, result
