"""识别/翻译质量的度量工具（纯函数，便于测试）。"""

from __future__ import annotations

import difflib
import re

WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """归一化：去掉首尾空白，把连续空白压成一个空格。"""

    return WHITESPACE.sub(" ", text.replace("\r\n", "\n")).strip()


def edit_distance(left: str, right: str) -> int:
    """Levenshtein 距离（滚动数组实现）。"""

    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, 1):
        current = [i]
        for j, right_char in enumerate(right, 1):
            cost = 0 if left_char == right_char else 1
            current.append(
                min(
                    previous[j] + 1,          # 删除
                    current[j - 1] + 1,       # 插入
                    previous[j - 1] + cost,   # 替换
                )
            )
        previous = current
    return previous[-1]


def cer(expected: str, actual: str) -> float:
    """字符错误率：编辑距离 / 期望文本长度。0 表示完全一致。"""

    expected_norm = normalize(expected)
    actual_norm = normalize(actual)
    if not expected_norm:
        return 0.0 if not actual_norm else 1.0
    return edit_distance(expected_norm, actual_norm) / len(expected_norm)


def similarity(expected: str, actual: str) -> float:
    """相似度（0~1），用于对 OCR 结果做粗判。"""

    return difflib.SequenceMatcher(None, normalize(expected), normalize(actual)).ratio()

