"""translate-text 命令的测试：本地假 DeepSeek 服务器，不访问外网。"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from mchanhua.cli import main
from mchanhua.config import Config, save_config


class FakeDeepSeek(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        FakeDeepSeek.requests.append(body)
        content = json.dumps(
            {"lines": [{"i": 0, "dst": "机械"}, {"i": 1, "dst": "钢铁"}]}, ensure_ascii=False
        )
        payload = json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args) -> None:
        return None


@pytest.fixture
def fake_server():
    FakeDeepSeek.requests = []
    server = HTTPServer(("127.0.0.1", 0), FakeDeepSeek)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _config_file(workdir, base_url: str):
    config = Config()
    config.translate.base_url = base_url
    config.translate.api_key = "sk-local"
    config.translate.cache_enabled = False
    return save_config(config, workdir / "config.toml")


def test_translate_text_prints_pairs(workdir, fake_server, capsys):
    config_path = _config_file(workdir, fake_server)
    code = main(["--config", str(config_path), "translate-text", "HACHIHERY\nSteel"])
    captured = capsys.readouterr()
    assert code == 0
    assert "机械" in captured.out
    assert "HACHIHERY" in captured.out
    # 中文行不送翻译
    assert FakeDeepSeek.requests and "HACHIHERY" in FakeDeepSeek.requests[0]["messages"][1]["content"]


def test_translate_text_without_key_echoes_input(workdir, capsys):
    config = Config()
    config.translate.api_key = ""
    config_path = save_config(config, workdir / "config.toml")
    code = main(["--config", str(config_path), "translate-text", "Steel Ingot"])
    captured = capsys.readouterr()
    assert code == 0
    assert "Steel Ingot" in captured.out
    assert "未配置" in captured.err


def test_translate_text_empty_input(workdir, capsys):
    config_path = save_config(Config(), workdir / "config.toml")
    code = main(["--config", str(config_path), "translate-text", "   "])
    captured = capsys.readouterr()
    assert code == 2
    assert "没有可翻译的内容" in captured.err
