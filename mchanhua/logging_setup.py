"""日志：把关键步骤和未捕获异常写到文件，便于排查"启动不了 / 卡死"。"""

from __future__ import annotations

import logging
import sys
import tempfile
import threading
from pathlib import Path

LOGGER_NAME = "mchanhua"


def project_log_path() -> Path:
    """优先写到项目目录的 tmp/ 下，不可写时退回系统临时目录。"""

    root = Path(__file__).resolve().parents[1] / "tmp"
    try:
        root.mkdir(parents=True, exist_ok=True)
        return root / "mchanhua.log"
    except OSError:
        return Path(tempfile.gettempdir()) / "mchanhua.log"


def _install_exception_hooks(logger: logging.Logger) -> None:
    def handle(exc_type, exc_value, exc_tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            return
        logger.error("未捕获的异常", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = handle

    def handle_thread(args: threading.ExceptHookArgs) -> None:
        logger.error(
            "后台线程未捕获的异常（%s）",
            args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = handle_thread


def setup_logging(path: Path | None = None, level: int = logging.INFO) -> Path:
    target = Path(path) if path else project_log_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(target, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    logger.propagate = False
    _install_exception_hooks(logger)
    return target


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
