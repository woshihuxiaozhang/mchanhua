"""语言支持：本地语言判定、自动识别源语言、目标语言可配。"""

from mchanhua.config import Config, load_config, save_config
from mchanhua.detect import guess_language, is_already_target, language_name
from mchanhua.translate.openai_compat import build_system_prompt


def test_guess_language_by_script():
    assert guess_language("Maintenance Log - system disconnected.") == "en"
    assert guess_language("耐久") == "zh"
    assert guess_language("こんにちは、冒険者さん") == "ja"      # 假名 → 日语
    assert guess_language("안녕하세요") == "ko"
    assert guess_language("Привет, мир") == "ru"
    assert guess_language("مرحبا") == "ar"
    assert guess_language("สวัสดี") == "th"


def test_guess_language_handles_empty_and_symbols():
    assert guess_language("") == ""
    assert guess_language("   ") == ""
    assert guess_language("1234 -=×") == ""
    assert language_name("") == "未知"
    assert language_name("ja") == "日语"


def test_already_target_detects_same_language():
    assert is_already_target("这是一个测试", "简体中文") is True
    assert is_already_target("Steel Ingot", "简体中文") is False
    assert is_already_target("Steel Ingot", "English") is True
    assert is_already_target("", "简体中文") is False


def test_auto_source_prompt_tells_model_to_detect_language():
    """源语言自动识别：提示词里不写死源语言，而是要求模型自己判断。"""

    prompt = build_system_prompt(None, target_language="简体中文", source_language="auto")

    assert "简体中文" in prompt
    assert "先自己判断" in prompt           # 让模型自己识别输入语言
    assert "英语" in prompt and "日语" in prompt   # 列出常见可能
    assert "[[" not in prompt               # 占位符都替换干净了


def test_auto_source_accepts_chinese_spelling():
    for value in ("auto", "自动", "自动识别"):
        prompt = build_system_prompt(None, "简体中文", value)
        assert "先自己判断" in prompt


def test_fixed_source_language_is_written_into_prompt():
    prompt = build_system_prompt(None, target_language="简体中文", source_language="日语")

    assert "日语" in prompt
    assert "先自己判断" not in prompt        # 已经指定源语言，就不让它自己猜


def test_prompt_supports_other_target_languages():
    prompt = build_system_prompt(None, target_language="English", source_language="简体中文")

    assert "English" in prompt
    assert "简体中文" in prompt


def test_language_settings_round_trip(workdir):
    config = Config()
    config.translate.target_language = "日本語"
    config.translate.source_language = "自动识别"

    path = save_config(config, workdir / "config.toml")
    loaded = load_config(path)

    assert loaded.translate.target_language == "日本語"
    assert loaded.translate.source_language == "自动识别"


def test_empty_target_language_is_rejected():
    import pytest

    from mchanhua.config import ConfigError

    config = Config()
    config.translate.target_language = "  "
    with pytest.raises(ConfigError):
        config.validate()
