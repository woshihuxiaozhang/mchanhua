import json

import httpx
import pytest

from mchanhua.translate.base import TranslationError
from mchanhua.translate.deepseek import DeepSeekTranslator, build_system_prompt


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


def test_translate_lines_restores_placeholders_and_reports_missing_lines():
    def handler(request: httpx.Request) -> httpx.Response:
        content = json.dumps({"lines": [{"i": 0, "dst": "耐久 \ue0000\ue001"}]})
        return httpx.Response(200, json=_chat_response(content))

    translator = DeepSeekTranslator(api_key="sk-test", client=_client(handler))
    result = translator.translate_lines(["Durability §a", "Second line"])

    assert result[0] == "耐久 §a"
    assert result[1] == "Second line"          # 漏翻的行保留原文
    assert any("漏翻" in warning for warning in translator.warnings)


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
