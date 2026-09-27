from mchanhua.translate.placeholders import missing_tokens, protect, protect_lines, restore


def test_protect_and_restore_round_trip():
    text = "§aRight-click §rto place %s blocks, %1$s left, {0} slots"
    masked, tokens = protect(text)
    assert "§a" not in masked
    assert "%s" not in masked
    assert restore(masked, tokens) == text
    # 占位符按模式逐个应用，编号顺序 = 模式顺序，不要求与文本顺序一致
    assert set(tokens) == {"§a", "§r", "%s", "%1$s", "{0}"}


def test_protect_handles_escapes_and_template_vars():
    text = r"Line\nbreak ${player} end\t"
    masked, tokens = protect(text)
    assert restore(masked, tokens) == text
    assert set(tokens) == {r"\n", r"\t", "${player}"}


def test_protect_lines_reports_each_line_table():
    lines = ["§cHealth: %s", "No formats here"]
    masked, tables = protect_lines(lines)
    assert len(masked) == len(tables) == 2
    assert tables[1] == []
    assert restore(masked[0], tables[0]) == lines[0]


def test_missing_tokens_detects_lost_placeholders():
    _, tokens = protect("§aDamage %s")
    assert missing_tokens("伤害 %s", tokens) == ["§a"]
    assert missing_tokens("§a伤害 %s", tokens) == []


def test_restore_leaves_unknown_sentinels_untouched():
    masked, tokens = protect("value %s")
    broken = masked + "\ue00099\ue001"
    assert restore(broken, tokens).endswith("\ue00099\ue001")
