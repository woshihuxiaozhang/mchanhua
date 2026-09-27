"""日志与异常钩子测试。"""

import logging

from mchanhua.logging_setup import get_logger, setup_logging


def test_setup_logging_writes_to_file(workdir):
    target = workdir / "mchanhua.log"
    setup_logging(target)
    logger = get_logger()
    logger.info("启动测试 %s", "信息")
    for handler in logger.handlers:
        handler.flush()

    text = target.read_text(encoding="utf-8")
    assert "启动测试 信息" in text
    assert "INFO" in text


def test_exception_hook_records_traceback(workdir):
    import sys

    target = workdir / "mchanhua.log"
    setup_logging(target)
    try:
        raise RuntimeError("模拟启动失败")
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
    for handler in get_logger().handlers:
        handler.flush()

    text = target.read_text(encoding="utf-8")
    assert "未捕获的异常" in text
    assert "模拟启动失败" in text
    assert "RuntimeError" in text


def test_setup_logging_is_idempotent(workdir):
    target = workdir / "mchanhua.log"
    setup_logging(target)
    setup_logging(target)
    logger = get_logger()
    file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1, "重复调用不应叠加文件 handler"
