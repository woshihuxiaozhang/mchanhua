"""OCR → 翻译 的处理流程（纯逻辑，便于测试）。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Sequence

from PIL import Image

from mchanhua.geometry import Region
from mchanhua.ocr.base import OcrEngine
from mchanhua.translate.base import Translator, split_translatable



@dataclass
class PipelineResult:
    source_lines: list[str]
    output_lines: list[str]
    ocr_ms: float = 0.0
    translate_ms: float = 0.0
    ocr_backend: str = ""
    warnings: list[str] = field(default_factory=list)

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
) -> PipelineResult:
    """拿着已经识别好的结果继续做翻译（供"自动扩边重识别"复用）。"""

    source_lines = [line.text for line in ocr_result.lines]
    truncated = 0
    if max_lines is not None and len(source_lines) > max_lines:
        truncated = len(source_lines) - max_lines
        source_lines = source_lines[:max_lines]
    if on_ocr is not None:
        on_ocr(source_lines, ocr_result.elapsed_ms)

    result = PipelineResult(
        source_lines=list(source_lines),
        output_lines=list(source_lines),
        ocr_ms=ocr_result.elapsed_ms,
        ocr_backend=ocr_result.backend,
    )
    if truncated:
        result.warnings.append(
            f"全屏共识别 {len(ocr_result.lines)} 行，只翻译前 {max_lines} 行（已跳过 {truncated} 行）"
        )
    if translator is None or not source_lines:
        return result

    pending = split_translatable(source_lines)
    if not pending:
        result.warnings.append("没有需要翻译的行（识别结果已是中文或没有词义）")
        return result

    started = time.perf_counter()
    translated = translator.translate_lines([text for _, text in pending])
    result.translate_ms = (time.perf_counter() - started) * 1000

    for (index, source), target in zip(pending, translated):
        result.output_lines[index] = target
        if target.strip() == source.strip():
            result.warnings.append(f"第 {index + 1} 行疑似未翻译")
    result.warnings.extend(getattr(translator, "warnings", []) or [])
    return result




def render_pairs(result: PipelineResult) -> str:
    """把原文/译文对齐成一段可供阅读的文本。"""

    blocks: list[str] = []
    for source, target in result.pairs():
        if source.strip() == target.strip():
            blocks.append(source)
        else:
            blocks.append(f"{target}\n{source}")
    return "\n\n".join(blocks)
