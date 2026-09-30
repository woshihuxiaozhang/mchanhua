from mchanhua.translate.base import contains_cjk, should_translate, split_translatable


def test_contains_cjk_detects_chinese_and_fullwidth():
    assert contains_cjk("磁石")
    assert contains_cjk("已解锁！")
    assert not contains_cjk("Steel Ingot")
    assert not contains_cjk("Durability 1234 / 1234")


def test_should_translate_rules():
    assert should_translate("Steel Ingot")
    assert should_translate("Right-click to place")
    # 整行已经是中文（一个英文字母都没有）原样保留
    assert not should_translate("可以放在：")
    assert not should_translate("磁石")
    # 没有词义的行
    assert not should_translate("")
    assert not should_translate("   ")
    assert not should_translate("1234 / 1234")
    assert not should_translate("---")
    assert not should_translate("A")


def test_mixed_chinese_english_still_gets_translated():
    """回归：中英混排的行以前被整个跳过，导致半截英文永远翻不出来。"""

    assert should_translate("已找到 Iron Nugget")
    assert should_translate("已将截图保存为 2026-09-27.png")
    # OCR 把系统提示和英文台词接到一起的那种行
    assert should_translate("You are one step closer to salvation, in已将截图保存为1.png")
    # 只有一个字母的（例如「按 E 键」）还是不用翻
    assert not should_translate("按 E 键打开背包")


def test_split_translatable_keeps_original_positions():
    lines = ["Switch", "可以放在：", "Durability 1234", "磁石", "已找到 Iron Nugget"]
    pending = split_translatable(lines)
    assert pending == [(0, "Switch"), (2, "Durability 1234"), (4, "已找到 Iron Nugget")]
