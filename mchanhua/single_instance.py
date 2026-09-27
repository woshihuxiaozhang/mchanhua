"""单实例锁：避免同时开两个程序导致热键重复触发、日志互相覆盖。"""

from __future__ import annotations

import ctypes
import sys

ERROR_ALREADY_EXISTS = 183


def mutex_name(app: str = "mchanhua") -> str:
    """用固定名字的全局互斥体；测试里可以传不同名字。"""

    return f"Global\\{app}-single-instance"


class SingleInstance:
    """拿不到锁说明已经有一个实例在跑。"""

    def __init__(self, name: str | None = None) -> None:
        self.name = name or mutex_name()
        self._handle = None
        self.already_running = False

    def acquire(self) -> bool:
        if sys.platform != "win32":  # pragma: no cover - 目前只发布 Windows
            return True
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        handle = kernel32.CreateMutexW(None, False, self.name)
        last_error = ctypes.get_last_error()
        if not handle:
            return True          # 拿不到互斥体就不拦，宁可多开也别打不开
        self._handle = handle
        self.already_running = last_error == ERROR_ALREADY_EXISTS
        return not self.already_running

    def release(self) -> None:
        if self._handle and sys.platform == "win32":
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CloseHandle(ctypes.c_void_p(self._handle))
            self._handle = None

    def __enter__(self) -> "SingleInstance":
        self.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()
