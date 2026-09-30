"""内置的 Minecraft 常用术语译法。

模型偶尔会把 Redstone 翻成"红石粉"、把 Netherite 翻成"下界岩"之类，
固定术语能显著提升一致性。用户配置里的 [glossary] 会覆盖这里的同名条目。
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable

DEFAULT_GLOSSARY: dict[str, str] = {
    "Redstone": "红石",
    "Redstone Dust": "红石粉",
    "Netherite": "下界合金",
    "Nether": "下界",
    "End": "末地",
    "Overworld": "主世界",
    "Ender": "末影",
    "Enchantment": "附魔",
    "Enchanting Table": "附魔台",
    "Anvil": "铁砧",
    "Durability": "耐久",
    "Stack": "堆叠",
    "Potion": "药水",
    "Splash Potion": "喷溅药水",
    "Lingering Potion": "滞留药水",
    "Beacon": "信标",
    "Crafting": "合成",
    "Inventory": "物品栏",
    "Hotbar": "快捷栏",
    "Right-click": "右键",
    "Left-click": "左键",
    "Shift-click": "Shift 点击",
    "Sneak": "潜行",
    "Spawn": "生成",
    "Biome": "生物群系",
    "Mob": "生物",
    "NPC": "NPC",
    "Quest": "任务",
    "Objective": "目标",
}


# OCR 常见的形近替换：先归一化再比，比硬放宽相似度阈值更准
_OCR_FIXES = str.maketrans({"0": "o", "1": "l", "5": "s", "8": "b", "3": "e"})
_SPLIT = re.compile(r"[\s/\\|,，。！？!?;；:：\"'“”‘’()（）\[\]【】]+")


def _tokens(text: str) -> set[str]:
    return {token for token in _SPLIT.split(text) if token}


def _fuzzy_hit(needle: str, lowered: str, tokens: set[str], threshold: float = 0.85) -> bool:
    """OCR 抖动容错：`MychaeI`、`P0ISON` 这类认错的写法也要能命中术语。"""

    parts = [part for part in needle.split(" ") if len(part) >= 4]
    if not parts:
        return False
    for part in parts:
        if part in lowered:
            continue
        fixed = part.translate(_OCR_FIXES)
        head = fixed[:2]
        if not any(_close_enough(fixed, head, token, threshold) for token in tokens):
            return False
    return True


def _close_enough(fixed: str, head: str, token: str, threshold: float) -> bool:
    if abs(len(token) - len(fixed)) > 1:
        return False
    shape = token.translate(_OCR_FIXES)
    if shape[:2] != head:          # 头两个字母都认错的很少见，卡住这里能少很多误命中
        return False
    if shape == fixed:
        return True
    return SequenceMatcher(None, fixed, shape).ratio() >= threshold


def select_relevant(
    glossary: dict[str, str] | None,
    lines: Iterable[str] | None,
    fuzzy: bool = True,
) -> dict[str, str]:
    """只挑出**这批文本里真的出现过**的术语。

    术语表越长，全量塞进提示词就越费钱、也越分散模型注意力；
    人名地名攒到上百条时尤其明显，所以按批筛选后再注入。
    """

    if not glossary:
        return {}
    haystack = "\n".join(str(line) for line in (lines or ()))
    lowered = haystack.casefold()
    if not lowered.strip():
        return {}
    tokens = _tokens(lowered) if fuzzy else set()
    chosen: dict[str, str] = {}
    for source, target in glossary.items():
        needle = " ".join((source or "").split()).casefold()
        if not needle:
            continue
        if needle in lowered:
            chosen[source] = target
        elif fuzzy and _fuzzy_hit(needle, lowered, tokens):
            chosen[source] = target
    return chosen
