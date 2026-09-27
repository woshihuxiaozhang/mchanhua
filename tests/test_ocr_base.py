from mchanhua.geometry import Region
from mchanhua.ocr.base import OcrLine, OcrResult, group_words_into_lines, union_boxes


def test_union_boxes():
    boxes = [Region(10, 10, 20, 20), Region(40, 15, 10, 10)]
    assert union_boxes(boxes).to_csv() == "10,10,40,20"
    assert union_boxes([]) is None


def test_group_words_into_lines_orders_and_joins():
    words = [
        ("Ingot", Region(100, 12, 50, 16)),
        ("Steel", Region(40, 10, 55, 16)),
        ("place", Region(180, 50, 40, 16)),
        ("to", Region(120, 52, 20, 16)),
    ]
    lines = group_words_into_lines(words)
    assert [line.text for line in lines] == ["Steel Ingot", "to place"]
    assert lines[0].words == ("Steel", "Ingot")
    assert lines[0].box.to_csv() == "40,10,110,18"


def test_group_words_ignores_blank_and_empty_input():
    assert group_words_into_lines([]) == []
    assert group_words_into_lines([("  ", Region(0, 0, 5, 5))]) == []


def test_ocr_result_text_skips_blank_lines():
    result = OcrResult(lines=[OcrLine("a"), OcrLine("  "), OcrLine("b")])
    assert result.text == "a\nb"
    assert result.char_count == 2
