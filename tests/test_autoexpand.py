"""自动扩边（解决"翻译不全"）与调试落盘的测试。"""

import json

from PIL import Image

from mchanhua.app import Application
from mchanhua.autoregion import capture_with_autoexpand, ocr_score
from mchanhua.config import Config, load_config, save_config
from mchanhua.debugdump import dump_last_run
from mchanhua.geometry import Region
from mchanhua.ocr.base import OcrLine, OcrResult
from mchanhua.pipeline import (
    clipped_directions,
    expand_region_for_clipping,
    run_from_ocr,
)
from tests.fakes import DecodingTranslator, FakeGrabber, FakeWindow, wait_for

MONITOR = Region(0, 0, 2560, 1440)


def _result(lines: list[OcrLine]) -> OcrResult:
    return OcrResult(lines=lines, elapsed_ms=1.0, backend="fake")


# ---- 纯函数 ----


def test_clipped_directions_detects_each_edge():
    size = (200, 100)
    # 右边贴住 200 的边界
    assert clipped_directions(_result([OcrLine("x", Region(10, 10, 190, 20))]), size) == {"right"}
    assert clipped_directions(_result([OcrLine("x", Region(0, 10, 100, 20))]), size) == {"left"}
    assert clipped_directions(_result([OcrLine("x", Region(50, 0, 100, 20))]), size) == {"top"}
    assert clipped_directions(_result([OcrLine("x", Region(50, 80, 100, 20))]), size) == {"bottom"}
    assert clipped_directions(_result([OcrLine("x", Region(50, 40, 100, 20))]), size) == set()
    assert clipped_directions(_result([OcrLine("x", None)]), size) == set()


def test_expand_region_for_clipping_grows_only_requested_edges():
    region = Region(100, 100, 300, 200)
    expanded = expand_region_for_clipping(region, {"right", "bottom"}, MONITOR, step=20)
    assert expanded.to_csv() == "100,100,320,220"
    # 左/上方向：坐标前移、尺寸同步变大
    expanded = expand_region_for_clipping(region, {"left", "top"}, MONITOR, step=20)
    assert expanded.to_csv() == "80,80,320,220"


def test_expand_region_clamps_to_monitor_and_reports_no_change():
    # 已经贴着屏幕左上角，无法再向外扩
    region = Region(0, 0, 300, 200)
    assert expand_region_for_clipping(region, {"left", "top"}, MONITOR, step=20) is None
    # 贴右下角同理
    corner = Region(2360, 1240, 200, 200)
    assert expand_region_for_clipping(corner, {"right", "bottom"}, MONITOR, step=20) is None


def test_run_from_ocr_skips_recognition():
    result = run_from_ocr(_result([OcrLine("Steel Ingot")]), DecodingTranslator())
    assert result.output_lines == ["[tognI leetS]"]
    assert result.ocr_backend == "fake"


# ---- 控制器：自动扩边 ----


class ClippedThenFullOcr:
    """第一次返回"贴住右边缘"的一行，扩边后返回完整的一行。"""

    name = "clipped-fake"

    def __init__(self) -> None:
        self.calls = 0

    def recognize(self, image):
        self.calls += 1
        if self.calls == 1:
            return _result(
                [OcrLine("You are one step", Region(10, 10, image.width - 12, 20))]
            )
        return _result(
            [
                OcrLine(
                    "You are one step closer to salvation",
                    Region(10, 10, max(1, image.width - 40), 20),
                )
            ]
        )


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


def test_worker_auto_expands_region_when_text_touches_edge(workdir):
    app = _app(workdir, ClippedThenFullOcr())
    app.translator = DecodingTranslator()
    app.config.regions.set_custom_region(Region(100, 100, 300, 40))

    app.perform_translate()
    messages = wait_for(app, "result")

    # 第一次抓 300x40，发现文字贴右边 → 扩 28px 后重抓
    assert [region.to_csv() for region in app.grabber.requests] == ["100,100,300,40", "100,100,328,40"]
    result = next(message[1] for message in messages if message[0] == "result")
    assert result.source_lines == ["You are one step closer to salvation"]


def test_worker_does_not_expand_when_text_is_inside(workdir):
    class InsideOcr:
        name = "inside-fake"

        def recognize(self, image):
            return _result([OcrLine("All good here", Region(20, 10, image.width - 60, 20))])

    app = _app(workdir, InsideOcr())
    app.translator = DecodingTranslator()
    app.config.regions.set_custom_region(Region(100, 100, 300, 40))

    app.perform_translate()
    wait_for(app, "result")

    assert len(app.grabber.requests) == 1


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


# ---- 自动扩边的取舍策略 ----


def test_ocr_score_counts_characters():
    assert ocr_score(_result([])) == 0
    assert ocr_score(_result([OcrLine("abc"), OcrLine("de")])) == 5


def test_autoexpand_adopts_better_result():
    def recognize(image):
        if image.width <= 700:
            # 词框贴住右边缘（x + width == 图片宽度），触发扩边
            return _result([OcrLine("rou are one step", Region(5, 5, image.width - 5, 20))])
        return _result([OcrLine("You are one step closer", Region(5, 5, image.width - 5, 20))])

    region, image, result = capture_with_autoexpand(
        Region(0, 0, 700, 50),
        MONITOR,
        grab=lambda target: Image.new("RGB", (target.width, target.height)),
        recognize=recognize,
    )

    assert region.to_csv() == "0,0,728,50"          # 向右扩了 28px
    assert result.lines[0].text == "You are one step closer"


def test_autoexpand_keeps_original_when_result_gets_worse():
    """模糊文字扩边后往往更差，这时必须保持原样，否则会越弄越糟。"""

    def recognize(image):
        if image.width <= 700:
            return _result([OcrLine("rou are one step clos", Region(5, 5, image.width - 5, 20))])
        return _result([OcrLine("Ster.", Region(5, 5, image.width - 5, 20))])

    region, image, result = capture_with_autoexpand(
        Region(0, 0, 700, 50),
        MONITOR,
        grab=lambda target: Image.new("RGB", (target.width, target.height)),
        recognize=recognize,
    )

    assert region.to_csv() == "0,0,700,50"
    assert image.size == (700, 50)
    assert result.lines[0].text == "rou are one step clos"


def test_autoexpand_skips_when_text_is_inside():
    calls: list[int] = []

    def recognize(image):
        calls.append(image.width)
        return _result([OcrLine("All good", Region(20, 10, image.width - 60, 20))])

    region, _image, _ocr = capture_with_autoexpand(
        Region(0, 0, 700, 50),
        MONITOR,
        grab=lambda target: Image.new("RGB", (target.width, target.height)),
        recognize=recognize,
    )

    assert calls == [700]
    assert region.to_csv() == "0,0,700,50"


def test_autoexpand_stops_at_screen_edge():
    """整屏识别时文字本来就贴着屏幕边，不应反复扩边。"""

    calls: list[int] = []

    def recognize(image):
        calls.append(image.width)
        return _result([OcrLine("edge text", Region(0, 0, image.width, 20))])

    region, _image, _ocr = capture_with_autoexpand(
        None,
        MONITOR,
        grab=lambda target: Image.new("RGB", (target.width, target.height)),
        recognize=recognize,
    )

    assert calls == [MONITOR.width]
    assert region == MONITOR
