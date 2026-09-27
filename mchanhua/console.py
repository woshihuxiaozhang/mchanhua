"""控制台输出编码处理。"""

from __future__ import annotations

import sys


def configure_stdio() -> None:
    """让中文（以及 OCR 可能吐出的任意字符）在 Windows 控制台正常输出。"""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

