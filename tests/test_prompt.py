"""提示词的回归检查：OCR 纠错说明与版本号（版本变动会使缓存失效）。"""

from mchanhua.translate.deepseek import PROMPT_VERSION, SYSTEM_PROMPT, build_system_prompt
from mchanhua.translate.cache import cache_key


def test_prompt_tells_model_about_ocr_typos():
    assert "OCR" in SYSTEM_PROMPT
    assert "识别错误" in SYSTEM_PROMPT
    assert "l/I" in SYSTEM_PROMPT and "o/0" in SYSTEM_PROMPT
    assert "不要原样返回英文" in SYSTEM_PROMPT


def test_prompt_requires_colloquial_emotional_style():
    """要求口语化、带情绪（不再写死英文示例，因为现在支持任意源语言）。"""

    assert "口语化" in SYSTEM_PROMPT
    assert "情绪" in SYSTEM_PROMPT
    assert "语气词" in SYSTEM_PROMPT
    assert "翻译腔" in SYSTEM_PROMPT
    assert "？！" in SYSTEM_PROMPT


def test_prompt_requires_line_order_and_src_echo():
    assert "顺序一致" in SYSTEM_PROMPT
    assert "一一对应" in SYSTEM_PROMPT
    assert '"src"' in SYSTEM_PROMPT


def test_prompt_requires_json_line_mapping():
    assert "json" in SYSTEM_PROMPT.lower()
    assert "行数" in SYSTEM_PROMPT and "一致" in SYSTEM_PROMPT


def test_prompt_tells_model_to_translate_mixed_lines():
    """回归：中英混排的行必须照翻，不能整行抄回去。"""

    assert "中英混排" in SYSTEM_PROMPT
    assert "照翻" in SYSTEM_PROMPT


def test_prompt_version_changes_cache_key():
    # 提示词一改，旧译文不应再命中缓存
    assert cache_key("Switch", "deepseek-chat", "v1") != cache_key("Switch", "deepseek-chat", PROMPT_VERSION)


def test_glossary_is_appended():
    prompt = build_system_prompt({"Switch": "开关"})
    assert "Switch=开关" in prompt
    # 模板里的占位符会被替换掉，所以比对替换后的关键片段
    assert "【格式规则】" in prompt
    assert "[[target]]" not in prompt and "[[source]]" not in prompt
