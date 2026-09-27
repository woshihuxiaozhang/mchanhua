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
