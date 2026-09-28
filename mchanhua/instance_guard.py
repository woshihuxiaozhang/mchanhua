"""找出（并按用户选择结束）已经在跑的 mchanhua 进程。

背景：程序是"单实例"的，旧实例不退，新版本就抢不到热键——
界面看起来换了，按热键却还是旧行为。控制台被隐藏后，
"已经有实例在运行"这句话也没人看得见，所以这里必须给出可见提示。
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from dataclasses import dataclass

PROCESS_NAME = "mchanhua.exe"

TH32CS_SNAPPROCESS = 0x00000002
PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MAX_PATH = 260

MB_OKCANCEL = 0x00000001
MB_ICONWARNING = 0x00000030
MB_SETFOREGROUND = 0x00010000
MB_TOPMOST = 0x00040000
IDOK = 1


@dataclass(frozen=True)
class Instance:
    pid: int
    exe: str

    @property
    def display(self) -> str:
        return f"PID {self.pid}（{self.exe or '路径未知'}）"


def should_close(entry: Instance, self_pid: int, process_name: str = PROCESS_NAME) -> bool:
    """判断这个进程是不是"该被结束掉的旧实例"：不是自己，且进程名一致。"""

    if entry.pid == self_pid:
        return False
    name = os.path.basename(entry.exe or "").lower()
    if not name:
        return True                     # 同名进程但拿不到路径，按旧实例处理
    return name == process_name.lower()


def describe(instances: list[Instance]) -> str:
    return "；".join(item.display for item in instances) if instances else "（未找到进程信息）"


def list_instances(process_name: str = PROCESS_NAME) -> list[Instance]:
    """列出当前在跑的指定进程。非 Windows 或调用失败时返回空列表。"""

    if sys.platform != "win32":  # pragma: no cover - 目前只发布 Windows
        return []

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * MAX_PATH),
        ]

    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == wintypes.HANDLE(-1).value or not snapshot:
        return []

    found: list[Instance] = []
    try:
        entry = ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(ProcessEntry32W)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return found
        while True:
            if entry.szExeFile.lower() == process_name.lower():
                found.append(Instance(pid=int(entry.th32ProcessID), exe=_image_path(kernel32, entry.th32ProcessID)))
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)
    return found


def _image_path(kernel32, pid: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(MAX_PATH * 2)
        size = wintypes.DWORD(len(buffer))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def terminate(pid: int) -> bool:
    """结束指定进程；失败返回 False（不抛异常，调用方继续走别的分支）。"""

    if sys.platform != "win32":  # pragma: no cover - 目前只发布 Windows
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not handle:
        return False
    try:
        return bool(kernel32.TerminateProcess(handle, 1))
    finally:
        kernel32.CloseHandle(handle)


def confirm_close(instances: list[Instance]) -> bool:
    """弹一个系统提示框问用户要不要结束旧实例；没有窗口/失败时默认不结束。"""

    if sys.platform != "win32":  # pragma: no cover
        return False
    text = (
        "检测到旧的 mchanhua 还在运行，它会占着热键，导致新版本的热键不生效。\n\n"
        f"{describe(instances)}\n\n"
        "点「确定」结束旧实例并启动新版本；点「取消」退出本次启动。"
    )
    flags = MB_OKCANCEL | MB_ICONWARNING | MB_SETFOREGROUND | MB_TOPMOST
    try:
        result = ctypes.WinDLL("user32", use_last_error=True).MessageBoxW(None, text, "mchanhua", flags)
    except OSError:  # pragma: no cover
        return False
    return result == IDOK
