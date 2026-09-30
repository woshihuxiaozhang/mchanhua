"""行合并：同一句话被 OCR 切碎时要拼回去，不相干的行绝不能粘在一起。"""

from mchanhua.geometry import Region
from mchanhua.ocr.base import OcrLine, OcrResult
from mchanhua.ocr.lines import merge_lines, merge_result


def _line(text: str, x: int, y: int, width: int = 300, height: int = 24) -> OcrLine:
    return OcrLine(text=text, box=Region(x, y, width, height), words=(text,))


def _result(*lines: OcrLine) -> OcrResult:
    return OcrResult(lines=list(lines), elapsed_ms=5.0, backend="fake", language="en")


def test_continuation_line_is_merged():
    """英文续行（小写开头）要拼回上一行。"""

    merged, labels = merge_lines([
        _line("No way through,", 100, 100),
        _line("unless I stop that leak.", 100, 130),
    ])

    assert len(merged) == 1
    assert merged[0].text == "No way through, unless I stop that leak."
    assert labels == []                        # 没传标签时返回空


def test_sentence_end_stops_merging():
    merged, _ = merge_lines([
        _line("Main Gear unit missing.", 100, 100),
        _line("must replace it.", 100, 130),
    ])
    assert len(merged) == 2


def test_capitalised_new_entry_is_not_merged():
    """物品条目（大写开头）是各自独立的，别粘成一句。"""

    merged, _ = merge_lines([
        _line("Steel Ingot", 100, 100, width=120),
        _line("Redstone Dust", 100, 130, width=140),
    ])
    assert len(merged) == 2


def test_bullet_start_is_not_merged():
    merged, _ = merge_lines([
        _line("Main Gear unit", 100, 100),
        _line("- Power feed", 100, 130),
    ])
    assert len(merged) == 2


def test_columns_are_not_merged():
    """左右两栏：水平不重叠，不能合并。"""

    merged, _ = merge_lines([
        _line("Maintenance Log", 100, 100, width=200),
        _line("system disconnected.", 400, 130, width=200),
    ])
    assert len(merged) == 2


def test_far_apart_lines_are_not_merged():
    merged, _ = merge_lines([
        _line("Maintenance Log", 100, 100),
        _line("system disconnected.", 100, 400),
    ])
    assert len(merged) == 2


def test_cjk_continuation_is_joined_without_space():
    merged, _ = merge_lines([
        _line("维护日志——系统已断开，", 100, 100),
        _line("需要更换绳索。", 100, 130),
    ])

    assert len(merged) == 1
    assert merged[0].text == "维护日志——系统已断开，需要更换绳索。"


def test_merged_box_covers_both_lines():
    merged, _ = merge_lines([
        _line("No way through,", 100, 100, width=200),
        _line("unless I stop that leak.", 120, 130, width=300),
    ])

    assert merged[0].box.x == 100
    assert merged[0].box.right == 420
    assert merged[0].box.bottom == 154
    assert merged[0].words == ("No way through,", "unless I stop that leak.")


def test_labels_follow_the_merged_lines():
    merged, labels = merge_lines(
        [
            _line("No way through,", 100, 100),
            _line("unless I stop that leak.", 100, 130),
            _line("You shouldn't be here.", 100, 300),
        ],
        labels=["区域1", "区域2", "区域2"],
    )

    assert len(merged) == 2
    assert labels == ["区域1", "区域2"]        # 合并后取第一条的标签


def test_merge_result_keeps_backend_info():
    result, labels = merge_result(_result(
        _line("No way through,", 100, 100),
        _line("unless I stop that leak.", 100, 130),
    ))

    assert len(result.lines) == 1
    assert result.backend == "fake" and result.elapsed_ms == 5.0
    assert labels == []


def test_very_long_result_is_not_merged():
    """拼起来会太长就不拼（避免把一整段话当成一句）。"""

    merged, _ = merge_lines([
        _line("word " * 30, 100, 100),
        _line("more words " * 5, 100, 130),
    ])
    assert len(merged) == 2
