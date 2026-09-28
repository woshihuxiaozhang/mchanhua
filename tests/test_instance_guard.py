"""旧实例检测：单实例锁失效时，新版本要能看见并清掉旧进程。"""

import os

from mchanhua import instance_guard
from mchanhua.instance_guard import Instance, describe, should_close


def test_should_close_skips_self():
    me = Instance(pid=os.getpid(), exe=r"C:\x\mchanhua.exe")
    assert should_close(me, os.getpid()) is False


def test_should_close_matches_by_process_name():
    other = Instance(pid=4242, exe=r"C:\Users\a\AppData\Local\Programs\mchanhua\mchanhua.exe")
    assert should_close(other, os.getpid()) is True


def test_should_close_keeps_other_programs():
    other = Instance(pid=4242, exe=r"C:\Windows\explorer.exe")
    assert should_close(other, os.getpid()) is False


def test_should_close_handles_missing_path():
    """拿不到路径时按旧实例处理：宁可提示一次，也别让旧实例默默占着热键。"""

    assert should_close(Instance(pid=1, exe=""), os.getpid()) is True


def test_describe_is_human_readable():
    text = describe([Instance(pid=7, exe=r"C:\app\mchanhua.exe")])
    assert "7" in text and "mchanhua.exe" in text
    assert describe([]) == "（未找到进程信息）"


def test_list_instances_never_raises():
    """枚举进程在任何环境下都不能把启动流程搞崩。"""

    assert isinstance(instance_guard.list_instances(), list)


def test_terminate_reports_failure_instead_of_raising():
    # pid 0 永远不是真实进程（Idle），OpenProcess 会失败
    assert instance_guard.terminate(0) is False
