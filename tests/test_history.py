"""翻译历史：内存存储、最近 20 条、退出即消失。"""

from datetime import datetime

from mchanhua.history import (
    EMPTY_TEXT,
    MAX_ENTRIES,
    TranslationHistory,
    render_entries,
)


def test_add_keeps_source_and_target_in_one_entry():
    history = TranslationHistory()
    entry = history.add(["Steel Ingot"], ["钢锭"], at=datetime(2026, 9, 28, 15, 7))

    assert entry is not None
    assert entry.clock == "15:07"          # 只要 时:分
    assert entry.pairs() == [("Steel Ingot", "钢锭")]
    assert len(history) == 1


def test_add_skips_blank_lines():
    history = TranslationHistory()
    entry = history.add(["  ", "Redstone"], ["", "红石"])

    assert entry is not None
    assert entry.pairs() == [("Redstone", "红石")]


def test_nothing_is_recorded_when_all_lines_are_blank():
    history = TranslationHistory()
    assert history.add([], []) is None
    assert history.add(["  "], ["  "]) is None
    assert len(history) == 0


def test_recent_returns_last_20_by_default():
    history = TranslationHistory()
    for index in range(25):
        history.add([f"line {index}"], [f"第 {index} 行"], at=datetime(2026, 9, 28, 10, index % 60))

    recent = history.recent()

    assert len(recent) == 20
    assert recent[0].source == ("line 5",)      # 最新的 20 条
    assert recent[-1].source == ("line 24",)
    assert len(history.all()) == 25             # 设置里能看到全部


def test_capacity_drops_oldest():
    history = TranslationHistory(capacity=3)
    for index in range(5):
        history.add([f"line {index}"], [f"第 {index} 行"])

    assert [entry.source[0] for entry in history.all()] == ["line 2", "line 3", "line 4"]
    assert history.capacity == 3
    assert MAX_ENTRIES >= 100                   # 默认上限要够大，免得挂机时爆内存


def test_clear_removes_everything():
    history = TranslationHistory()
    history.add(["a"], ["甲"])
    history.add(["b"], ["乙"])

    assert history.clear() == 2
    assert history.all() == []
    assert history.recent() == []


def test_render_entries_has_time_source_and_target():
    history = TranslationHistory()
    history.add(["Steel Ingot", "Redstone"], ["钢锭", "红石"], at=datetime(2026, 9, 28, 9, 5))

    text = render_entries(history.all())

    assert "[09:05]" in text
    assert "钢锭" in text and "Steel Ingot" in text
    assert "红石" in text and "Redstone" in text


def test_render_entries_handles_empty_history():
    assert render_entries([]) == EMPTY_TEXT
