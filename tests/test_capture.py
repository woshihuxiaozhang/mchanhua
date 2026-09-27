import pytest
from PIL import Image

from mchanhua.capture import Grabber, grab_screen, resolve_region
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
