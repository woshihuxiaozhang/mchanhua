"""把 Windows 的标题栏设成浅色。

系统是深色主题时，Tk 窗口默认拿到的是黑标题栏；用户要的是"白色外框"，
所以启动后显式把 DWMWA_USE_IMMERSIVE_DARK_MODE 置 0（不跟随系统深色）。
"""

from __future__ import annotations

import sys


def use_light_title_bar(widget) -> bool:
    """把 widget 所在窗口的标题栏设成浅色；失败时安静返回 False。"""

    if sys.platform != "win32":  # pragma: no cover - 目前只发布 Windows
        return False
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = int(widget.frame(), 16)
        dwm = ctypes.WinDLL("dwmapi", use_last_error=True)
        value = ctypes.c_int(0)                 # 0 = 不用深色标题栏
        for attribute in (20, 19):              # 20 是新系统，19 是旧系统
            dwm.DwmSetWindowAttribute(
                wintypes.HWND(hwnd), attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
        return True
    except Exception:                           # pragma: no cover - 任何异常都不影响使用
        return False
