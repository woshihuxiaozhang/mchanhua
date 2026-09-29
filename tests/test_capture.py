import pytest
from PIL import Image

from mchanhua.capture import Grabber, frames_similar, grab_screen, resolve_region
from mchanhua.geometry import Region


class FakeGrabber(Grabber):
    name = "fake"

    def __init__(self, monitor: Region, size_hint: tuple[int, int] | None = None) -> None:
        self._monitor = monitor
        self._size_hint = size_hint
        self.requests: list[Region] = []

    def monitors(self) -> list[Region]:
        return [self._monitor]

    def primary_monitor(self) -> Region:
        return self._monitor

    def grab(self, region: Region) -> Image.Image:
        self.requests.append(region)
        size = self._size_hint or (region.width, region.height)
        return Image.new("RGB", size, (0, 0, 0))

    def close(self) -> None:
        return None


def test_resolve_region_uses_full_monitor_by_default():
    monitor = Region(0, 0, 2560, 1440)
    assert resolve_region(None, monitor) == monitor


def test_resolve_region_clamps_partial_overlap():
    monitor = Region(0, 0, 2560, 1440)
    assert resolve_region(Region(-50, -50, 200, 200), monitor).to_csv() == "0,0,150,150"


def test_resolve_region_rejects_fully_outside():
    monitor = Region(0, 0, 2560, 1440)
    with pytest.raises(ValueError):
        resolve_region(Region(3000, 2000, 100, 100), monitor)


def test_grab_screen_passes_clamped_region_and_checks_size():
    monitor = Region(0, 0, 1920, 1080)
    grabber = FakeGrabber(monitor)
    image = grab_screen(grabber, Region(1800, 1000, 400, 400))
    assert grabber.requests == [Region(1800, 1000, 120, 80)]
    assert image.size == (120, 80)


def test_grab_screen_raises_on_size_mismatch():
    monitor = Region(0, 0, 1920, 1080)
    grabber = FakeGrabber(monitor, size_hint=(10, 10))
    with pytest.raises(RuntimeError):
        grab_screen(grabber, Region(0, 0, 100, 100))


def test_screenshot_fixture_round_trip(workdir):
    """确认保存/读取截图这条链路（后面做回归对比要用）。"""

    path = workdir / "shot.png"
    Image.new("RGB", (64, 48), (12, 34, 56)).save(path)
    reopened = Image.open(path)
    assert reopened.size == (64, 48)


# ---- 画面稳定检测（等提示框定住再翻，学 UGTLive 的 settle）----


def test_frames_similar_for_identical_images():
    first = Image.new("RGB", (200, 120), (30, 60, 90))
    second = Image.new("RGB", (200, 120), (30, 60, 90))
    assert frames_similar(first, second) is True


def test_frames_similar_detects_small_change():
    """提示框淡入这种细微变化也要判成"还在变"。"""

    first = Image.new("RGB", (400, 300), (20, 20, 20))
    second = Image.new("RGB", (400, 300), (20, 20, 20))
    # 中间画一块亮色，相当于提示框正在出现
    for x in range(200, 400):
        for y in range(150, 300):
            second.putpixel((x, y), (230, 230, 230))

    assert frames_similar(first, second) is False


def test_frames_similar_handles_size_mismatch():
    assert frames_similar(Image.new("RGB", (10, 10)), Image.new("RGB", (20, 20))) is False
