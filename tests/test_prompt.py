"""提示词的回归检查：OCR 纠错说明与版本号（版本变动会使缓存失效）。"""

from mchanhua.translate.deepseek import PROMPT_VERSION, SYSTEM_PROMPT, build_system_prompt
from mchanhua.translate.cache import cache_key


def test_prompt_tells_model_about_ocr_typos():
    assert "OCR" in SYSTEM_PROMPT
    assert "Suitch" in SYSTEM_PROMPT and "Switch" in SYSTEM_PROMPT


def test_prompt_requires_json_line_mapping():
    assert "json" in SYSTEM_PROMPT.lower()
    assert "行数" in SYSTEM_PROMPT and "一致" in SYSTEM_PROMPT


def test_prompt_version_changes_cache_key():
    # 提示词一改，旧译文不应再命中缓存
    assert cache_key("Switch", "deepseek-chat", "v1") != cache_key("Switch", "deepseek-chat", PROMPT_VERSION)


def test_glossary_is_appended():
    prompt = build_system_prompt({"Switch": "开关"})
    assert "Switch=开关" in prompt
    assert SYSTEM_PROMPT in prompt
