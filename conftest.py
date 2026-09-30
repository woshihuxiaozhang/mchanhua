"""全局测试夹具。

不使用 pytest 内置的 tmp_path / basetemp：Codex 沙箱身份与真实用户身份创建的
目录互无权限删除，内置机制在会话开始时会强制清理 basetemp，因而会报
PermissionError。这里改成在仓库 tmp/ 下按进程 + 随机串建目录，清理时忽略错误，
两种身份互不干扰。
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent
TEST_TMP_ROOT = REPO_ROOT / "tmp" / "tests"


@pytest.fixture
def workdir() -> Path:
    path = TEST_TMP_ROOT / f"{uuid.uuid4().hex[:12]}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(autouse=True)
def isolate_tk_roots():
    """每个测试结束后把 Tk 的"默认根"清干净。

    有的测试会自己起一个 tk.Tk()（比如框选遮罩），漏掉一个还活着的根就会成为
    tkinter 的默认根，之后新建窗口里的图片会绑到那个旧解释器上，
    报 `image "pyimageN" doesn't exist`（真实程序只有一个根，不受影响）。
    """

    yield
    try:
        import tkinter
    except ImportError:  # pragma: no cover
        return
    root = getattr(tkinter, "_default_root", None)
    if root is None:
        return
    try:
        root.destroy()
    except Exception:  # pragma: no cover - 已经关掉了
        pass
    tkinter._default_root = None
