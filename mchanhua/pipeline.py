"""OCR → 翻译 的处理流程（纯逻辑，便于测试）。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Sequence

from PIL import Image

from mchanhua.config import AREA_KIND_ITEM, AREA_KIND_SUBTITLE
from mchanhua.geometry import Region
from mchanhua.ocr.base import OcrEngine
from mchanhua.translate.base import Translator, set_area_hint, split_translatable

# 区域类型 → 给模型的额外说明。没列出来的类型（「其他」）按默认风格翻译。
AREA_HINTS = {
    AREA_KIND_ITEM: (
        "这些行来自游戏里的物品提示框/配方表，都是物品、方块、生物或材料的名字。"
        "译名要短、是名词，用 Minecraft 中文版社区通用的叫法，不要加语气词、不要凑成句子。"
    ),
    AREA_KIND_SUBTITLE: (
        "这些行来自游戏剧情字幕/对话框/NPC 台词，是成句的话。"
        "按口语来译，保留情绪与语气，被 OCR 切碎的行要接回通顺的整句。"
    ),
}


def hint_for_kind(kind: str | None) -> str:
    return AREA_HINTS.get((kind or "").strip(), "")



@dataclass
class PipelineResult:
    source_lines: list[str]
    output_lines: list[str]
    ocr_ms: float = 0.0
    translate_ms: float = 0.0
    ocr_backend: str = ""
    warnings: list[str] = field(default_factory=list)
    # 多区域翻译时，每一行来自哪个区域（与 source_lines 平行，单区域时为空）
    line_areas: list[str] = field(default_factory=list)
    # 模型顺手整理的"整段通顺译文"（没有就用空串，界面按行显示）
    paragraph: str = ""
    # 本批里模型认出来的专有名词 [(原文, 译名)]，给自动术语表用
    terms: list[tuple[str, str]] = field(default_factory=list)

    @property
    def translated_count(self) -> int:
        return sum(1 for src, dst in zip(self.source_lines, self.output_lines) if src != dst)

    def pairs(self) -> list[tuple[str, str]]:
        return list(zip(self.source_lines, self.output_lines))


def run_pipeline(
    image: Image.Image,
    ocr: OcrEngine,
    translator: Translator | None = None,
    on_ocr: Callable[[list[str], float], None] | None = None,
    max_lines: int | None = None,
) -> PipelineResult:
    """对一张图片做 OCR（可选再翻译）。

    on_ocr 让界面能在 OCR 完成时先显示原文，不必等翻译返回。
    max_lines 用于全屏模式：识别出来的行太多时只翻译前若干行，避免成本失控。
    """

    return run_from_ocr(ocr.recognize(image), translator, on_ocr, max_lines)


def run_from_ocr(
    ocr_result,
    translator: Translator | None = None,
    on_ocr: Callable[[list[str], float], None] | None = None,
    max_lines: int | None = None,
    line_areas: list[str] | None = None,
    line_kinds: list[str] | None = None,
) -> PipelineResult:
    """拿着已经识别好的结果继续做翻译（供"自动扩边重识别"复用）。"""

    source_lines = [line.text for line in ocr_result.lines]
    areas_for_lines = list(line_areas or [])
    kinds_for_lines = list(line_kinds or [])
    truncated = 0
    if max_lines is not None and len(source_lines) > max_lines:
        truncated = len(source_lines) - max_lines
        source_lines = source_lines[:max_lines]
        areas_for_lines = areas_for_lines[:max_lines]
        kinds_for_lines = kinds_for_lines[:max_lines]
    if on_ocr is not None:
        on_ocr(source_lines, ocr_result.elapsed_ms)

    result = PipelineResult(
        source_lines=list(source_lines),
        output_lines=list(source_lines),
        ocr_ms=ocr_result.elapsed_ms,
        ocr_backend=ocr_result.backend,
        line_areas=areas_for_lines,
    )
    if truncated:
        result.warnings.append(
            f"全屏共识别 {len(ocr_result.lines)} 行，只翻译前 {max_lines} 行（已跳过 {truncated} 行）"
        )
    if translator is None or not source_lines:
        return result

    pending = split_translatable(
        source_lines, getattr(translator, "target_language", "") or "简体中文"
    )
    if not pending:
        result.warnings.append(
            "没有需要翻译的行（这些字看起来已经是目标语言了，或者没有实际词义）"
        )
        return result

    started = time.perf_counter()
    translated, paragraph, warnings, terms = _translate_pending(
        translator, pending, kinds_for_lines
    )
    result.translate_ms = (time.perf_counter() - started) * 1000

    for index, target in translated.items():
        result.output_lines[index] = target
        if target.strip() == source_lines[index].strip():
            result.warnings.append(f"第 {index + 1} 行疑似未翻译")
    result.warnings.extend(warnings)
    if paragraph:
        result.paragraph = paragraph
    result.terms = terms
    return result


def _translate_pending(
    translator: Translator,
    pending: list[tuple[int, str]],
    kinds_for_lines: list[str],
) -> tuple[dict[int, str], str, list[str], list[tuple[str, str]]]:
    """按区域类型分批翻译，返回 {行号: 译文}、「整段整理」结果与后端的提示。

    只有一种类型（最常见的情况）时就是一次普通请求；
    物品区和字幕区混在一起时分成两批，各自带上对应的提示词，效果更贴。
    """

    groups: dict[str, list[tuple[int, str]]] = {}
    for index, text in pending:
        kind = kinds_for_lines[index] if index < len(kinds_for_lines) else ""
        groups.setdefault(kind, []).append((index, text))

    translated: dict[int, str] = {}
    paragraph = ""
    warnings: list[str] = []
    terms: list[tuple[str, str]] = []
    for kind, group in groups.items():
        set_area_hint(translator, hint_for_kind(kind))
        try:
            outputs = translator.translate_lines([text for _, text in group])
        finally:
            set_area_hint(translator, "")
        for (index, _source), target in zip(group, outputs):
            translated[index] = target
        warnings.extend(getattr(translator, "warnings", []) or [])
        terms.extend(getattr(translator, "last_terms", []) or [])
        got = getattr(translator, "last_paragraph", "") or ""
        # 物品清单不整理成段（会把一堆名字凑成句子）；字幕的整段译文最有用
        if got and kind != AREA_KIND_ITEM:
            paragraph = got
    # 分批请求时后端每次调用都会清空 warnings / last_terms，所以在这里统一收着
    return translated, paragraph, warnings, terms




def render_pairs(result: PipelineResult) -> str:
    """把原文/译文对齐成一段可供阅读的文本。"""

    blocks: list[str] = []
    for source, target in result.pairs():
        if source.strip() == target.strip():
            blocks.append(source)
        else:
            blocks.append(f"{target}\n{source}")
    return "\n\n".join(blocks)
