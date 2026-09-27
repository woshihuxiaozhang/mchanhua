"""控制台输出编码处理。"""

from __future__ import annotations

import sys
import os


def configure_stdio() -> None:
    """让中文在 Windows 控制台正常输出；打包成 GUI 程序后没有控制台，这里兜底。"""

    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
