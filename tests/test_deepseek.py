import json

import httpx
import pytest

from mchanhua.translate.base import TranslationError
from mchanhua.translate.deepseek import DeepSeekTranslator, build_system_prompt, looks_like_word


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _reply(payload: dict, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        handler.last_request = request
        return httpx.Response(status, json=payload)

    handler.last_request = None
    return handler


def _chat_response(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def test_translate_lines_returns_ordered_results():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers.get("authorization")
        content = json.dumps({"lines": [{"i": 0, "dst": "钢锭"}, {"i": 1, "dst": "右键放置"}]})
        return httpx.Response(200, json=_chat_response(content))

    translator = DeepSeekTranslator(api_key="sk-test", client=_client(handler))
    result = translator.translate_lines(["Steel Ingot", "Right-click to place"])

    assert result == ["钢锭", "右键放置"]
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["model"] == "deepseek-chat"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert translator._endpoint() == "https://api.deepseek.com/v1/chat/completions"


def test_missing_lines_are_retried_with_ocr_correction():
    """第一次漏翻的行会带"OCR 纠错"提示再问一次。"""

    payloads = [
        json.dumps({"lines": [{"i": 0, "dst": "耐久 \ue0000\ue001"}]}, ensure_ascii=False),
        json.dumps({"lines": [{"i": 0, "dst": "第二行"}]}, ensure_ascii=False),
    ]
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=_chat_response(payloads[min(len(seen) - 1, 1)]))

    translator = DeepSeekTranslator(api_key="sk-test", client=_client(handler))
    result = translator.translate_lines(["Durability §a", "Second line"])

    assert result == ["耐久 §a", "第二行"]
    assert len(seen) == 2, "应触发一次纠错请求"
    assert "MACHINERY" in seen[1]["messages"][0]["content"]   # 纠错提示里带示例
    assert any("再问一次" in warning for warning in translator.warnings)


def test_output_order_is_correct_even_if_model_returns_shuffled_lines():
    """回归：模型把行序打乱返回时，输出必须仍按输入顺序排列。"""

    def handler(request: httpx.Request) -> httpx.Response:
        content = json.dumps(
            {
                "lines": [
                    {"i": 2, "src": "third", "dst": "第三"},
                    {"i": 0, "src": "first", "dst": "第一"},
                    {"i": 1, "src": "second", "dst": "第二"},
                ]
            },
            ensure_ascii=False,
        )
        return httpx.Response(200, json=_chat_response(content))

    translator = DeepSeekTranslator(api_key="sk-test", client=_client(handler))
    assert translator.translate_lines(["first", "second", "third"]) == ["第一", "第二", "第三"]
    assert translator.warnings == []


def test_mismatched_src_is_reported_but_line_index_wins():
    def handler(request: httpx.Request) -> httpx.Response:
        content = json.dumps(
            {"lines": [{"i": 0, "src": "完全不是这一行", "dst": "第一"}]}, ensure_ascii=False
        )
        return httpx.Response(200, json=_chat_response(content))

    translator = DeepSeekTranslator(api_key="sk-test", client=_client(handler))
    assert translator.translate_lines(["first line"]) == ["第一"]
    assert any("对不上" in warning for warning in translator.warnings)


def test_source_is_kept_when_retry_also_returns_source():
    def handler(request: httpx.Request) -> httpx.Response:
        content = json.dumps({"lines": [{"i": 0, "dst": "HACHIHERY"}]})
        return httpx.Response(200, json=_chat_response(content))

    translator = DeepSeekTranslator(api_key="sk-test", client=_client(handler))
    result = translator.translate_lines(["HACHIHERY"])
    assert result == ["HACHIHERY"]


def test_identifiers_are_not_retried():
    """玩家 ID / 带数字下划线的标识符不去猜，避免无中生有。"""

    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        content = json.dumps({"lines": [{"i": 0, "dst": "AlexLime008"}]})
        return httpx.Response(200, json=_chat_response(content))

    translator = DeepSeekTranslator(api_key="sk-test", client=_client(handler))
    assert translator.translate_lines(["AlexLime008"]) == ["AlexLime008"]
    assert len(calls) == 1, "标识符不应触发二次请求"


def test_looks_like_word_rules():
    assert looks_like_word("HACHIHERY")
    assert looks_like_word("Steel Ingot")
    assert not looks_like_word("AlexLime008")
    assert not looks_like_word("Realistika_")
    assert not looks_like_word("minecraft:stone")
    assert not looks_like_word("12 34")
    assert not looks_like_word("ab")


def test_code_fence_and_glossary():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        fenced = "```json\n" + json.dumps({"lines": [{"i": 0, "dst": "红石"}]}) + "\n```"
        return httpx.Response(200, json=_chat_response(fenced))

    translator = DeepSeekTranslator(
        api_key="sk-test",
        glossary={"Redstone": "红石"},
        client=_client(handler),
    )
    assert translator.translate_lines(["Redstone"]) == ["红石"]
    system_prompt = captured["body"]["messages"][0]["content"]
    assert isinstance(system_prompt, str)
    assert "Redstone=红石" in system_prompt


def test_invalid_json_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_chat_response("不是 JSON"))

    translator = DeepSeekTranslator(api_key="sk-test", client=_client(handler))
    with pytest.raises(TranslationError):
        translator.translate_lines(["Hello"])


def test_http_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    translator = DeepSeekTranslator(api_key="bad", client=_client(handler))
    with pytest.raises(TranslationError) as excinfo:
        translator.translate_lines(["Hello"])
    assert "401" in str(excinfo.value)


def test_missing_api_key_raises():
    with pytest.raises(TranslationError) as excinfo:
        DeepSeekTranslator(api_key="")
    assert "API key" in str(excinfo.value)


def test_empty_input_short_circuits():
    translator = DeepSeekTranslator(api_key="sk-test", client=_client(lambda r: httpx.Response(500)))
    assert translator.translate_lines([]) == []


def test_build_system_prompt_without_glossary():
    assert "JSON" in build_system_prompt(None)
