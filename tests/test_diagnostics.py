"""看门狗逻辑测试（用假时钟，不依赖线程）。"""

from mchanhua.diagnostics import UiWatchdog


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_watchdog_reports_stall_once():
    clock = FakeClock()
    dumps: list[int] = []
    watchdog = UiWatchdog(stall_seconds=5.0, clock=clock, dump=lambda: dumps.append(1))

    clock.advance(1.0)
    assert watchdog.check_once() is None      # 未超时
    clock.advance(10.0)
    assert watchdog.check_once() is not None  # 超时，报一次
    assert watchdog.check_once() is None      # 不重复刷屏
    assert dumps == [1]


def test_beat_resets_stall_detection():
    clock = FakeClock()
    watchdog = UiWatchdog(stall_seconds=5.0, clock=clock, dump=lambda: None)
    clock.advance(4.0)
    watchdog.beat()
    clock.advance(4.0)
    assert watchdog.check_once() is None
    clock.advance(2.0)
    assert watchdog.check_once() is not None
