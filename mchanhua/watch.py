"""连续翻译模式的判定逻辑（纯函数，方便测试）。

守护一块区域时，每隔一小会儿抓一次图、跑一次 OCR（都在本机，几乎不花钱），
只有**文字真的变了**才去调用翻译接口——这样既实时又不烧额度。

判断"变了没"用两步：
1. 归一化（去掉所有空白、统一小写）后完全相同 → 没变；
2. 否则算相似度，高于阈值也当作"没变"（容忍 OCR 每次认出的字符有小抖动）。
"""

from __future__ import annotations

import difflib


def normalize_text(text: str) -> str:
    """去掉所有空白并统一小写：比较"内容变没变"时用。"""

    return "".join((text or "").split()).casefold()


def similarity(first: str, second: str) -> float:
    """两段文本的相似度（0~1）。"""

    if not first and not second:
        return 1.0
    if not first or not second:
        return 0.0
    return difflib.SequenceMatcher(None, first, second).ratio()


def is_changed(previous: str, current: str, threshold: float = 0.9) -> bool:
    """current 相对 previous 算不算"变了"（阈值越高越敏感）。"""

    if not current:
        return False                 # 没识别到文字：不翻，也不当作变化
    if not previous:
        return True                  # 第一次拿到内容
    return similarity(previous, current) < max(0.0, min(1.0, threshold))


def should_request(
    previous: str,
    current: str,
    threshold: float = 0.9,
    seconds_since_last: float = 999.0,
    min_interval: float = 0.0,
) -> bool:
    """要不要为这次内容发起翻译请求（内容变了 + 过了限流间隔）。"""

    if not is_changed(previous, current, threshold):
        return False
    if previous and seconds_since_last < min_interval:
        return False                 # 变得太快也先攒一攒，别一路狂发请求
    return True
