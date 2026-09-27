"""选区取词：向外多抓一圈 + 只保留选区内的完整行；以及调试落盘。"""

import json

from PIL import Image

from mchanhua.app import Application
from mchanhua.autoregion import (
    capture_padded_and_filter,
    filter_lines_in_region,
    padded_region,
)
from mchanhua.config import Config, load_config, save_config
from mchanhua.debugdump import dump_last_run
from mchanhua.geometry import Region
from mchanhua.ocr.base import OcrLine, OcrResult
from mchanhua.pipeline import run_from_ocr
from tests.fakes import DecodingTranslator, FakeGrabber, FakeWindow, wait_for

MONITOR = Region(0, 0, 2560, 1440)


def _result(lines: list[OcrLine]) -> OcrResult:
    return OcrResult(lines=lines, elapsed_ms=1.0, backend="fake")


# ---- 多抓一圈 ----


def test_padded_region_grows_by_padding():
    assert padded_region(Region(300, 400, 200, 100), MONITOR, pad=80).to_csv() == "220,320,360,260"


def test_padded_region_is_clamped_to_monitor():
    assert padded_region(Region(0, 0, 100, 100), MONITOR, pad=80).to_csv() == "0,0,180,180"
    assert padded_region(Region(2500, 1400, 60, 40), MONITOR, pad=80).to_csv() == "2420,1320,140,120"


# ---- 按选区筛选 ----


def test_filter_keeps_lines_whose_center_is_inside_region():
    capture = Region(100, 100, 400, 300)
    region = Region(200, 200, 100, 50)
    # 屏幕中心 = (100+130+20, 100+115+15) = (250, 230)，落在选区内
    inside = OcrLine("inside", Region(130, 115, 40, 30))
    outside = OcrLine("outside", Region(10, 10, 40, 30))

    filtered = filter_lines_in_region(_result([inside, outside]), capture, region)

    assert [line.text for line in filtered.lines] == ["inside"]
    assert filtered.backend == "fake"


def test_filter_keeps_lines_without_box():
    filtered = filter_lines_in_region(
        _result([OcrLine("no box")]), Region(0, 0, 100, 100), Region(0, 0, 50, 50)
    )
    assert [line.text for line in filtered.lines] == ["no box"]


def test_filter_keeps_long_line_when_region_covers_only_part_of_it():
    """长行的中心点可能在选区外（例如 1800px 宽的行、选区只盖住左半），但重叠够多也要保留。"""

    capture = Region(0, 0, 2000, 400)
    region = Region(0, 100, 900, 60)
    long_line = OcrLine("a very long chat line", Region(0, 105, 1800, 50))

    filtered = filter_lines_in_region(_result([long_line]), capture, region)

    assert [line.text for line in filtered.lines] == ["a very long chat line"]


def test_keeps_whole_line_when_region_is_far_too_small_screen_mode():
    """默认 screen 模式：整屏识别后按选区筛选，选区再小也能拿到完整的一行。"""

    region = Region(300, 300, 200, 40)

    def recognize(image):
        assert image.width == MONITOR.width, "screen 模式应该抓整屏"
        # 一行文字横跨选区左右边界（坐标相对整屏）
        return _result([OcrLine("You shouldn't be here.", Region(250, 305, 400, 30))])

    capture, _image, result = capture_padded_and_filter(
        region,
        MONITOR,
        grab=lambda target: Image.new("RGB", (target.width, target.height)),
        recognize=recognize,
    )

    assert capture == MONITOR
    assert [line.text for line in result.lines] == ["You shouldn't be here."]


def test_padded_mode_still_works_when_configured():
    """配置成 padded 时只抓选区外扩的一圈（快，但横向切掉的长句补不回来）。"""

    region = Region(300, 300, 200, 40)

    def recognize(image):
        # 一行文字横跨选区左右边界（坐标相对抓图）
        return _result([OcrLine("You shouldn't be here.", Region(10, 65, image.width - 20, 30))])

    capture, _image, result = capture_padded_and_filter(
        region,
        MONITOR,
        grab=lambda target: Image.new("RGB", (target.width, target.height)),
        recognize=recognize,
        mode="padded",
    )

    assert capture.to_csv() == "220,220,360,200"
    assert [line.text for line in result.lines] == ["You shouldn't be here."]


def test_capture_padded_and_filter_drops_far_away_lines():
    region = Region(300, 300, 200, 40)

    def recognize(image):
        return _result(
            [
                OcrLine("keep me", Region(10, 65, 200, 30)),
                OcrLine("far away", Region(10, 5, 200, 30)),
            ]
        )

    _capture, _image, result = capture_padded_and_filter(
        region,
        MONITOR,
        grab=lambda target: Image.new("RGB", (target.width, target.height)),
        recognize=recognize,
        mode="padded",
    )

    assert [line.text for line in result.lines] == ["keep me"]


def test_fullscreen_path_uses_monitor_and_does_not_filter():
    capture, _image, result = capture_padded_and_filter(
        None,
        MONITOR,
        grab=lambda target: Image.new("RGB", (target.width, target.height)),
        recognize=lambda image: _result([OcrLine("chat line", Region(5, 5, image.width, 20))]),
    )

    assert capture is None                      # 整屏模式不记抓图区域
    assert [line.text for line in result.lines] == ["chat line"]


# ---- 控制器接线 ----


class _FakeOcr:
    name = "fake-ocr"

    def recognize(self, image):
        return _result([OcrLine("Steel Ingot"), OcrLine("磁石")])


def _app(workdir, ocr):
    config_path = save_config(Config(), workdir / "config.toml")
    config = load_config(config_path)
    return Application(
        config,
        config_path=config_path,
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=ocr,
        window=FakeWindow(),
    )


def test_worker_captures_full_screen_by_default(workdir):
    app = _app(workdir, _FakeOcr())
    app.translator = DecodingTranslator()
    app.config.regions.set_custom_region(Region(300, 400, 500, 300))

    app.perform_translate()
    wait_for(app, "result")

    assert app.grabber.requests[-1].to_csv() == "0,0,2560,1440"


def test_worker_respects_padded_capture_mode(workdir):
    app = _app(workdir, _FakeOcr())
    app.translator = DecodingTranslator()
    app.config.ocr.capture_mode = "padded"
    app.config.regions.set_custom_region(Region(300, 400, 500, 300))

    app.perform_translate()
    wait_for(app, "result")

    assert app.grabber.requests[-1].to_csv() == "220,320,660,460"


# ---- 调试落盘 ----


def test_dump_last_run_writes_capture_and_json(workdir):
    image = Image.new("RGB", (120, 40), (0, 0, 0))
    ocr_result = _result([OcrLine("Hello", Region(2, 2, 60, 20))])
    result = run_from_ocr(ocr_result, DecodingTranslator())

    dump_last_run(image, ocr_result, result, directory=workdir)

    assert (workdir / "last_capture.png").exists()
    payload = json.loads((workdir / "last_result.json").read_text(encoding="utf-8"))
    assert payload["size"] == [120, 40]
    assert payload["lines"][0]["text"] == "Hello"
    assert payload["pairs"] == [{"src": "Hello", "dst": "[olleH]"}]
