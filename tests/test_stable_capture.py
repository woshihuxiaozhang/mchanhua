"""抓屏时的"等画面稳定"逻辑，以及翻译请求的网络重试。"""

import httpx
import pytest
from PIL import Image

from mchanhua.app import Application
from mchanhua.config import Config
from mchanhua.geometry import Region
from mchanhua.ocr.base import OcrLine, OcrResult
from mchanhua.translate.base import TranslationError
from mchanhua.translate.openai_compat import OpenAICompatibleTranslator
from tests.fakes import DecodingTranslator, FakeOcr, FakeWindow


class _ScriptedGrabber:
    """按脚本一帧一帧返回图片，用来模拟"画面还在变 → 定住"。"""

    name = "scripted"

    def __init__(self, frames: list[Image.Image]) -> None:
        self.frames = frames
        self.calls = 0

    def monitors(self):
        return [Region(0, 0, 800, 600)]

    def primary_monitor(self):
        return Region(0, 0, 800, 600)

    def grab(self, region):
        index = min(self.calls, len(self.frames) - 1)
        self.calls += 1
        return self.frames[index].copy()

    def close(self):
        return None


def _frame(color, box=None) -> Image.Image:
    image = Image.new("RGB", (800, 600), color)
    if box is not None:
        for x in range(box[0], box[2]):
            for y in range(box[1], box[3]):
                image.putpixel((x, y), (240, 240, 240))
    return image


def _app(grabber, ocr=None) -> Application:
    return Application(
        Config(),
        use_hotkeys=False,
        grabber=grabber,
        ocr=ocr or FakeOcr(),
        window=FakeWindow(),
    )


def test_grab_keeps_capturing_until_screen_settles():
    """画面还在变（提示框淡入）就再抓一帧，定住之后用最新那帧。"""

    changing = _frame((20, 20, 20))
    settled = _frame((20, 20, 20), box=(100, 100, 300, 250))
    grabber = _ScriptedGrabber([changing, settled, settled])
    app = _app(grabber)

    _capture, image = app._grab_image(None)

    assert grabber.calls == 2                    # 第二帧和第一帧不一样 → 再抓一次
    assert image.getpixel((200, 200)) == (240, 240, 240)   # 用的是稳定下来的那帧


def test_grab_stops_at_two_frames_when_stable():
    stable = _frame((30, 30, 30))
    grabber = _ScriptedGrabber([stable, stable, stable])
    app = _app(grabber)

    app._grab_image(None)

    assert grabber.calls == 2                    # 两帧一样就够了，不多拍


def test_settle_frames_can_be_turned_off():
    """settle_frames = 1 时只抓一帧（追求最快）。"""

    stable = _frame((30, 30, 30))
    grabber = _ScriptedGrabber([stable, stable])
    app = _app(grabber)
    app.config.ocr.settle_frames = 1

    app._grab_image(None)

    assert grabber.calls == 1


def test_settle_frames_must_be_within_range():
    from mchanhua.config import ConfigError

    config = Config()
    config.ocr.settle_frames = 0
    with pytest.raises(ConfigError):
        config.validate()


# ---- 翻译请求的网络重试 ----


class _FlakyClient:
    """前几次连接失败，之后成功。"""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    def post(self, url, json=None, headers=None):  # noqa: A002 - 与 httpx 一致
        self.calls += 1
        if self.calls <= self.failures:
            raise httpx.ConnectError("目标计算机积极拒绝")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"lines": [{"i": 0, "src": "Steel Ingot", "dst": "钢锭"}]}'}}]},
        )


def test_translation_retries_network_failures():
    client = _FlakyClient(failures=2)
    translator = OpenAICompatibleTranslator(client=client, retry_attempts=3, retry_backoff=0)

    result = translator.translate_lines(["Steel Ingot"])

    assert result == ["钢锭"]
    assert client.calls == 3
    assert any("重试" in warning for warning in translator.warnings)


def test_translation_reports_error_after_retries_exhausted():
    client = _FlakyClient(failures=99)
    translator = OpenAICompatibleTranslator(client=client, retry_attempts=2, retry_backoff=0)

    with pytest.raises(TranslationError) as excinfo:
        translator.translate_lines(["Steel Ingot"])

    assert client.calls == 2                     # 重试次数用满
    assert "请求翻译服务失败" in str(excinfo.value)
