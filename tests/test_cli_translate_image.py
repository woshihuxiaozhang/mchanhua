"""命令行 translate-image 的集成测试：本地假 DeepSeek + 真实 OCR。"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from mchanhua.cli import main
from mchanhua.config import Config, save_config


class FakeDeepSeek(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        content = json.dumps({"lines": [{"i": 0, "dst": "钢锭"}]}, ensure_ascii=False)
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
    server = HTTPServer(("127.0.0.1", 0), FakeDeepSeek)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _sample_image(path: Path) -> Path:
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = ImageFont.truetype(str(font_path), 28) if font_path.exists() else ImageFont.load_default()
    image = Image.new("RGB", (420, 60), (16, 0, 16))
    ImageDraw.Draw(image).text((10, 10), "Steel Ingot", font=font, fill=(255, 255, 255))
    image.save(path)
    return path


def test_translate_image_reports_translation(workdir, fake_server, capsys):
    config = Config()
    config.translate.base_url = fake_server
    config.translate.api_key = "sk-local"
    config.translate.cache_enabled = False
    config.ocr.backend = "rapidocr"
    config_path = save_config(config, workdir / "config.toml")
    image_path = _sample_image(workdir / "shot.png")

    code = main(
        [
            "--config",
            str(config_path),
            "translate-image",
            str(image_path),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "钢锭" in captured.out
    assert "Steel Ingot" in captured.out
    assert "已翻 1 行" in captured.out


def test_translate_image_without_key_prints_source_only(workdir, capsys):
    config = Config()
    config.ocr.backend = "rapidocr"
    config.translate.api_key = ""
    config_path = save_config(config, workdir / "config.toml")
    image_path = _sample_image(workdir / "shot.png")

    code = main(["--config", str(config_path), "translate-image", str(image_path)])
    captured = capsys.readouterr()
    assert code == 0
    assert "未配置 DeepSeek API key" in captured.err
    assert "Steel Ingot" in captured.out
