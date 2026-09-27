from mchanhua.translate.base import contains_cjk, should_translate, split_translatable


def test_contains_cjk_detects_chinese_and_fullwidth():
    assert contains_cjk("磁石")
    assert contains_cjk("已解锁！")
    assert not contains_cjk("Steel Ingot")
    assert not contains_cjk("Durability 1234 / 1234")


def test_should_translate_rules():
    assert should_translate("Steel Ingot")
    assert should_translate("Right-click to place")
    # 已汉化的行不再翻译
    assert not should_translate("可以放在：")
    assert not should_translate("已将截图保存为 2026-09-27.png")
    # 没有词义的行
    assert not should_translate("")
    assert not should_translate("   ")
    assert not should_translate("1234 / 1234")
    assert not should_translate("---")
    assert not should_translate("A")


def test_split_translatable_keeps_original_positions():
    lines = ["Switch", "可以放在：", "Durability 1234", "磁石"]
    pending = split_translatable(lines)
    assert pending == [(0, "Switch"), (2, "Durability 1234")]

