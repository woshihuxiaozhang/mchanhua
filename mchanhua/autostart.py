"""开机自启：在「启动」文件夹里放一个启动脚本，登录后自动运行。

不用改注册表、不用额外依赖：就是一个文本文件，用户想关掉直接删掉也行。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

LAUNCHER_NAME = "mchanhua-autostart.cmd"


def startup_dir() -> Path:
    """Windows 的「启动」文件夹（登录后会自动运行里面的东西）。"""

    base = os.environ.get("APPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def launcher_path(directory: Path | None = None) -> Path:
    return (Path(directory) if directory else startup_dir()) / LAUNCHER_NAME


def launch_command() -> str:
    """自启脚本里写什么：打包后直接起 exe，开发时用 pythonw 跑入口脚本。"""

    if getattr(sys, "frozen", False):
        return f'start "" "{Path(sys.executable)}"'
    entry = Path(__file__).resolve().parents[1] / "app_entry.py"
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    runner = pythonw if pythonw.exists() else Path(sys.executable)
    return f'start "" "{runner}" "{entry}"'


def script_text() -> str:
    # 注释只用 ASCII：cmd.exe 按系统代码页读脚本，中文在某些区域设置下会乱码
    return (
        "@echo off\r\n"
        "rem mchanhua autostart - delete this file to disable\r\n"
        f"{launch_command()}\r\n"
    )


def _codec() -> str:
    """cmd.exe 按系统 OEM 代码页读脚本：Windows 上用 mbcs 写更保险。"""

    return "mbcs" if os.name == "nt" else "utf-8"


def is_enabled(directory: Path | None = None) -> bool:
    return launcher_path(directory).exists()


def enable(directory: Path | None = None) -> Path:
    path = launcher_path(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(script_text(), encoding=_codec(), errors="replace")
    return path


def disable(directory: Path | None = None) -> bool:
    """删掉自启脚本；本来就没有就返回 False（不算失败）。"""

    path = launcher_path(directory)
    if not path.exists():
        return False
    path.unlink()
    return True


def set_enabled(enabled: bool, directory: Path | None = None) -> bool:
    """按勾选框设置自启；返回最终是不是开启状态。"""

    if enabled:
        enable(directory)
    else:
        disable(directory)
    return is_enabled(directory)
