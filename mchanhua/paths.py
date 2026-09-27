"""统一管理路径：打包成 exe 之后没有"项目目录"，所有可写数据都放 %APPDATA%。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "mchanhua"


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包出来的 exe 里。"""

    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """可写数据目录：配置、日志、缓存、调试文件都放这里。"""

    override = os.environ.get("MCHANHUA_HOME")
    if override:
        # 显式指定目录时按原样使用（打包测试、绿色版会用）
        return Path(override)
    base = os.environ.get("APPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Roaming")
    return Path(base) / APP_DIR_NAME


def flatpak_safe(path: Path) -> Path:
    return Path(path)


def log_dir() -> Path:
    return app_dir() / "logs"


def debug_dir() -> Path:
    return app_dir() / "debug"


def cache_path() -> Path:
    return app_dir() / "cache.sqlite"


def resource_dir() -> Path:
    """只读资源目录：打包后是解包目录，开发时是项目根目录。"""

    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
