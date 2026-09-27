from mchanhua.metrics import cer, edit_distance, normalize, similarity


def test_normalize_collapses_whitespace():
    assert normalize("  a \n b\tc  ") == "a b c"


def test_edit_distance_basics():
    assert edit_distance("abc", "abc") == 0
    assert edit_distance("", "abc") == 3
    assert edit_distance("abc", "") == 3
    assert edit_distance("Steel", "SteeI") == 1
    assert edit_distance("kitten", "sitting") == 3


def test_cer_matches_known_ocr_confusions():
    # 本机 zh-Hans OCR 会把 "Steel Ingot" 认成 "SteeI lngot"
    rate = cer("Steel Ingot", "SteeI lngot")
    assert 0 < rate < 0.25
    assert cer("Durability 1234", "Durability 1234") == 0.0


def test_similarity_range_and_extremes():
    assert similarity("abc", "abc") == 1.0
    assert similarity("abc", "") == 0.0
    assert 0.8 < similarity("Steel Ingot", "SteeI lngot") < 1.0
