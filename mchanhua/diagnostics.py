"""界面健康检查：主线程卡住时把堆栈写进日志。

"窗口未响应"这种问题光看普通日志很难定位，所以这里做两件事：
1. 界面每次处理事件都记一次心跳；
2. 看门狗线程发现心跳超时，就把所有线程的调用栈 dump 到日志里。
"""

from __future__ import annotations

import faulthandler
import threading
import time
from typing import Callable, TextIO

from mchanhua.logging_setup import get_logger


class UiWatchdog:
    def __init__(
        self,
        stall_seconds: float = 5.0,
        interval: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
        dump: Callable[[], None] | None = None,
    ) -> None:
        self.stall_seconds = stall_seconds
        self.interval = interval
        self._clock = clock
        self._dump = dump
        self._last_beat = clock()
        self._reported = False
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def beat(self) -> None:
        """界面线程每次处理事件时调用。"""

        self._last_beat = self._clock()
        self._reported = False

    def stalled_for(self) -> float | None:
        """返回停滞时长；未超过阈值时返回 None。"""

        elapsed = self._clock() - self._last_beat
        return elapsed if elapsed >= self.stall_seconds else None

    def check_once(self) -> float | None:
        """检查一次；只有首次发现停滞时才记录，避免刷屏。"""

        if self._reported:
            return None
        stalled = self.stalled_for()
        if stalled is None:
            return None
        self._reported = True
        get_logger().error("界面超过 %.1f 秒没有处理事件（疑似卡死），下面是各线程堆栈", stalled)
        if self._dump is not None:
            self._dump()
        return stalled

    def start(self) -> None:
        if self._thread is not None:
            return

        def loop() -> None:
            while not self._stop.wait(self.interval):
                self.check_once()

        self._thread = threading.Thread(target=loop, name="ui-watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None


def make_dump_all_threads(stream: TextIO | None) -> Callable[[], None]:
    """生成一个把全部线程堆栈写进日志文件的回调。"""

    def dump() -> None:
        faulthandler.dump_traceback(file=stream)
        if stream is not None:
            try:
                stream.flush()
            except Exception:
                pass

    return dump
