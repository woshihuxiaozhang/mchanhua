"""OCR 的通用数据结构与纯函数后处理。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence

from PIL import Image

from mchanhua.geometry import Region


class OcrUnavailable(Exception):
    """OCR 引擎不可用（缺少组件或语言包）。"""


@dataclass(frozen=True)
class OcrLine:
    text: str
    box: Region | None = None
    words: tuple[str, ...] = ()


@dataclass
class OcrResult:
    lines: list[OcrLine] = field(default_factory=list)
    elapsed_ms: float = 0.0
    backend: str = ""
    language: str | None = None

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines if line.text.strip())

    @property
    def char_count(self) -> int:
        """识别出的字符数（不含换行）。"""

        return sum(len(line.text.strip()) for line in self.lines)


class OcrEngine(Protocol):
    name: str

    def recognize(self, image: Image.Image) -> OcrResult: ...


def union_boxes(boxes: Sequence[Region]) -> Region | None:
    if not boxes:
        return None
    left = min(b.x for b in boxes)
    top = min(b.y for b in boxes)
    right = max(b.right for b in boxes)
    bottom = max(b.bottom for b in boxes)
    return Region(left, top, right - left, bottom - top)


def group_words_into_lines(
    words: Sequence[tuple[str, Region]],
    y_overlap: float = 0.5,
) -> list[OcrLine]:
    """把带坐标的词聚成行。

    Windows OCR 会直接给出行，这个函数用于其它只返回词框的后端（例如 RapidOCR）。
    判定规则：两个词框的垂直重叠超过较小框高度的 y_overlap 倍，就算同一行。
    """

    items = [(text, box) for text, box in words if text.strip()]
    if not items:
        return []
    items.sort(key=lambda item: (item[1].y, item[1].x))

    groups: list[list[tuple[str, Region]]] = []
    for text, box in items:
        for group in groups:
            group_box = union_boxes([b for _, b in group])
            assert group_box is not None
            overlap = min(group_box.bottom, box.bottom) - max(group_box.y, box.y)
            if overlap > y_overlap * min(group_box.height, box.height):
                group.append((text, box))
                break
        else:
            groups.append([(text, box)])

    lines: list[OcrLine] = []
    for group in groups:
        group.sort(key=lambda item: item[1].x)
        texts = tuple(text for text, _ in group)
        lines.append(
            OcrLine(
                text=" ".join(texts),
                box=union_boxes([box for _, box in group]),
                words=texts,
            )
        )
    lines.sort(key=lambda line: line.box.y if line.box else 0)
    return lines
