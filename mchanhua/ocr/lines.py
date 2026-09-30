"""把被 OCR 切碎的行拼回去。

屏幕 OCR 常把一句话切成好几行（尤其是选区别名窄、字号大、换行处的文字）。
逐行翻译出来就是断句的碎片，所以这里在**送翻译之前**先尝试拼回完整句子。

合并规则刻意保守，宁可不合并也不要把不相干的行粘在一起：
1. 两行垂直紧邻（间距小于行高的一定比例）；
2. 水平方向有重叠（左右两栏的并排文字不会合并）；
3. 上一行末尾没有句末标点（句子还没结束）；
4. 英文续行用小写字母开头；中日韩续行不以数字/符号开头（避免把"耐久 3/10"这类条目粘起来）；
5. 合并后长度没超过上限。
"""

from __future__ import annotations

from mchanhua.ocr.base import OcrLine, OcrResult

SENTENCE_END = ".!?。！？…；;：:"
BULLET_START = "-•*·+>＝=@#"
MAX_LINE_CHARS = 160
MAX_GAP_RATIO = 0.9          # 行间距 / 行高 超过它就认为不是同一句
MIN_H_OVERLAP_RATIO = 0.35   # 水平重叠至少占较窄那行的这个比例
# 同一行的碎片（检测模型把一行切成左右几块）：
SAME_LINE_V_OVERLAP = 0.5    # 垂直重叠至少占行高的这个比例才算同一行
SAME_LINE_MAX_GAP = 1.2      # 两块之间的横向间距超过行高的这个倍数就不接


def _ends_sentence(text: str) -> bool:
    return text.strip().endswith(tuple(SENTENCE_END))


def _starts_lower(text: str) -> bool:
    stripped = text.lstrip()
    return bool(stripped) and stripped[0].islower()


def _starts_upper(text: str) -> bool:
    stripped = text.lstrip()
    return bool(stripped) and stripped[0].isupper()


def _is_cjk(text: str) -> bool:
    return any("\u2e80" <= char <= "\u9fff" or "\uff00" <= char <= "\uffef" for char in text)


def _join_text(first: str, second: str) -> str:
    """拼接两行文字：英文之间补空格，中文/日文直接接。"""

    left, right = first.rstrip(), second.lstrip()
    if not left:
        return right
    if not right:
        return left
    if left[-1].isascii() and right[0].isascii():
        return f"{left} {right}"
    return left + right


def _h_overlap_ratio(a, b) -> float:
    left = max(a.x, b.x)
    right = min(a.right, b.right)
    if right <= left:
        return 0.0
    narrow = min(a.width, b.width)
    return (right - left) / max(1, narrow)


def _looks_like_continuation(previous: OcrLine, current: OcrLine) -> bool:
    """current 是不是 previous 这句话的续行。"""

    if previous.box is None or current.box is None:
        return False
    if _ends_sentence(previous.text):
        return False           # 上一行已经把话说完了，下面这行是新的一句
    if len(previous.text) + len(current.text) > MAX_LINE_CHARS:
        return False
    if _h_overlap_ratio(previous.box, current.box) < MIN_H_OVERLAP_RATIO:
        return False                       # 左右两栏：不合并
    gap = current.box.y - previous.box.bottom
    line_height = max(previous.box.height, current.box.height)
    if gap > line_height * MAX_GAP_RATIO or gap < -line_height * 0.5:
        return False                       # 离太远或明显不在下一行
    stripped_current = current.text.lstrip()
    if stripped_current[:1] in tuple(BULLET_START):
        return False                       # 列表项另起一条
    if _starts_upper(stripped_current) and not _is_cjk(stripped_current):
        return False                       # 英文大写开头：多半是新条目/新句子
    if stripped_current[:1].isdigit() and not _starts_lower(stripped_current):
        return False
    return True


def merge_lines(
    lines: list[OcrLine],
    labels: list[str] | None = None,
) -> tuple[list[OcrLine], list[str]]:
    """合并可续行的行，返回 (新的行列表, 对应的标签列表)。

    labels 与 lines 平行（多区域时用），合并后取该组第一行的标签。
    """

    merged: list[OcrLine] = []
    merged_labels: list[str] = []
    track_labels = labels is not None
    for index, line in enumerate(lines):
        label = labels[index] if labels and index < len(labels) else ""
        if merged and (
            _looks_like_continuation(merged[-1], line)
            or _looks_like_same_line_piece(merged[-1], line)
        ):
            previous = merged[-1]
            box = _union(previous, line)
            merged[-1] = OcrLine(
                text=_join_text(previous.text, line.text),
                box=box,
                words=tuple(previous.words) + tuple(line.words),
            )
            continue
        merged.append(line)
        if track_labels:
            merged_labels.append(label)
    return merged, merged_labels


def _looks_like_same_line_piece(previous: OcrLine, current: OcrLine) -> bool:
    """OCR 把**同一行**切成左右几块时，把它们接回去。

    检测模型在细长的小字上很容易把一行切成 "ウィン" + "ドウサイズの初期化" 这种碎片，
    以前只处理"上下换行"的续行，碎片就一直散着（译文也成了没头没尾的两段）。
    这里要求：垂直方向基本重叠（同一行）、水平方向左右相邻且间距不大、上一块没有句末标点。
    并排的两栏文字间距通常远大于一个行高，不会误合。
    """

    if previous.box is None or current.box is None:
        return False
    if _ends_sentence(previous.text):
        return False
    if len(previous.text) + len(current.text) > MAX_LINE_CHARS:
        return False
    height = max(previous.box.height, current.box.height)
    vertical_overlap = min(previous.box.bottom, current.box.bottom) - max(
        previous.box.y, current.box.y
    )
    if vertical_overlap < height * SAME_LINE_V_OVERLAP:
        return False
    gap = current.box.x - previous.box.right
    if gap > height * SAME_LINE_MAX_GAP or gap < -height * 0.3:
        return False
    return True


def _union(first: OcrLine, second: OcrLine):
    from mchanhua.geometry import Region

    left = min(first.box.x, second.box.x)
    top = min(first.box.y, second.box.y)
    right = max(first.box.right, second.box.right)
    bottom = max(first.box.bottom, second.box.bottom)
    return Region(left, top, right - left, bottom - top)


def merge_result(ocr_result: OcrResult, labels: list[str] | None = None):
    """对 OcrResult 做行合并，返回 (新的 OcrResult, 标签列表)。"""

    lines, merged_labels = merge_lines(list(ocr_result.lines), labels)
    merged = OcrResult(
        lines=lines,
        elapsed_ms=ocr_result.elapsed_ms,
        backend=ocr_result.backend,
        language=ocr_result.language,
    )
    return merged, merged_labels
