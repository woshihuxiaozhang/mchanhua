"""走真实 HTTP socket 的集成测试：用本地假服务器验证请求拼装、响应解析与缓存。

不访问外网，也不需要 API key，但会把 URL、鉴权头、请求体真正发出去一次。
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from mchanhua.config import TranslateConfig
from mchanhua.translate import CachingTranslator, create_translator


class FakeDeepSeek(BaseHTTPRequestHandler):
    requests: list[dict] = []
    reply: dict = {"lines": [{"i": 0, "dst": "钢锭"}, {"i": 1, "dst": "耐久 100"}]}

    def do_POST(self) -> None:  # noqa: N802 - http.server 要求的方法名
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        FakeDeepSeek.requests.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "body": body,
            }
        )
        content = json.dumps(FakeDeepSeek.reply, ensure_ascii=False)
        payload = json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args) -> None:  # 静音
        return None


@pytest.fixture
def fake_server():
    FakeDeepSeek.requests = []
    server = HTTPServer(("127.0.0.1", 0), FakeDeepSeek)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_translator_talks_to_openai_compatible_endpoint(fake_server, workdir):
    config = TranslateConfig(base_url=fake_server, model="deepseek-chat", api_key="sk-local")
    translator = create_translator(config, api_key="sk-local", cache_path=workdir / "cache.sqlite")
    assert isinstance(translator, CachingTranslator)

    result = translator.translate_lines(["Steel Ingot", "Durability 100"])

    assert result == ["钢锭", "耐久 100"]
    assert len(FakeDeepSeek.requests) == 1
    request = FakeDeepSeek.requests[0]
    assert request["path"] == "/v1/chat/completions"
    assert request["authorization"] == "Bearer sk-local"
    assert request["body"]["model"] == "deepseek-chat"
    assert request["body"]["response_format"] == {"type": "json_object"}
    user_content = request["body"]["messages"][1]["content"]
    assert "Steel Ingot" in user_content


def test_second_call_hits_cache_without_network(fake_server, workdir):
    config = TranslateConfig(base_url=fake_server, api_key="sk-local")
    translator = create_translator(config, api_key="sk-local", cache_path=workdir / "cache.sqlite")
    translator.translate_lines(["Steel Ingot", "Durability 100"])
    translator.translate_lines(["Steel Ingot", "Durability 100"])

    assert len(FakeDeepSeek.requests) == 1, "第二次应完全命中缓存"
    assert translator.hits == 2


def test_cache_disabled_always_calls_api(fake_server, workdir):
    config = TranslateConfig(base_url=fake_server, api_key="sk-local", cache_enabled=False)
    translator = create_translator(config, api_key="sk-local", cache_path=workdir / "cache.sqlite")
    translator.translate_lines(["Steel Ingot"])
    translator.translate_lines(["Steel Ingot"])
    assert len(FakeDeepSeek.requests) == 2


def test_builtin_glossary_is_sent_and_user_override_wins(fake_server, workdir):
    config = TranslateConfig(base_url=fake_server, api_key="sk-local", cache_enabled=False)
    translator = create_translator(
        config,
        api_key="sk-local",
        cache_path=workdir / "cache.sqlite",
        glossary={"Redstone": "红石粉（自定义）"},
    )
    translator.translate_lines(["Redstone"])

    system_prompt = FakeDeepSeek.requests[-1]["body"]["messages"][0]["content"]
    assert "Redstone=红石粉（自定义）" in system_prompt   # 用户配置覆盖内置
    assert "Netherite=下界合金" in system_prompt          # 内置术语仍然生效
