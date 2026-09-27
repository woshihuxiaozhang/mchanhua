"""打包入口：双击 exe 直接启动取词小窗；带参数时按命令行参数执行。"""

from __future__ import annotations

import multiprocessing
import sys
import traceback


def _write_crash_log() -> None:
    """打包后没有控制台，启动失败必须落盘，否则完全看不到原因。"""

    try:
        from mchanhua.paths import ensure_dir, log_dir

        path = ensure_dir(log_dir()) / "startup-error.log"
        path.write_text(traceback.format_exc(), encoding="utf-8")
    except Exception:  # pragma: no cover - 连日志都写不了就只能放弃
        pass


def run() -> int:
    multiprocessing.freeze_support()          # 打包后 spawn 子进程需要
    try:
        from mchanhua.cli import main

        return main(sys.argv[1:] or ["run"])
    except BaseException:
        _write_crash_log()
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
