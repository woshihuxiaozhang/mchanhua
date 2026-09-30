# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：onedir，体积大一点但启动快、稳定。

用法：.venv\\Scripts\\python.exe -m PyInstaller --noconfirm --clean mchanhua.spec
产物：dist\\mchanhua\\mchanhua.exe
"""

import sys
from pathlib import Path

import pefile
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules


def conda_extra_binaries():
    """Miniconda 的扩展模块（_ctypes.pyd / _sqlite3.pyd / _ssl.pyd …）依赖 Library\\bin 里的 DLL，
    例如 ffi.dll、sqlite3.dll、libssl-3-x64.dll。PyInstaller 默认不会带上，
    打包后会报 "DLL load failed while importing _ctypes"，所以这里自动把它们补齐。
    """

    base = Path(sys.base_prefix)
    lib_bin = base / "Library" / "bin"
    if not lib_bin.is_dir():
        return []

    wanted: set[str] = set()
    for pyd in (base / "DLLs").glob("*.pyd"):
        try:
            pe = pefile.PE(str(pyd))
            for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []) or []:
                name = entry.dll.decode("ascii", "ignore")
                if (lib_bin / name).exists():
                    wanted.add(name)
        except Exception:  # noqa: BLE001 - 分析失败不影响其它模块
            continue
    return [(str(lib_bin / name), ".") for name in sorted(wanted)]

# OCR 模型（约 13MB）必须随包分发
datas = collect_data_files("rapidocr_onnxruntime")
datas += collect_data_files("customtkinter")      # 主题 json 等资源
# 日语识别模型（识别 + 字典，约 9.3MB）：认假名全靠它（检测仍用默认中英模型）
datas += [
    ("assets/models/japan_rec.onnx", "assets/models"),
    ("assets/models/japan_dict.txt", "assets/models"),
]
binaries = collect_dynamic_libs("onnxruntime") + conda_extra_binaries()

hiddenimports = (
    collect_submodules("winrt")
    + collect_submodules("rapidocr_onnxruntime")   # RapidOCR 用字符串动态导入子模块
    + [
        "cv2",
        "onnxruntime",
        "keyboard",
        "customtkinter",
        "pyclipper",
        "shapely",
        "PIL._tkinter_finder",
    ]
)

a = Analysis(
    ["app_entry.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["matplotlib", "pandas", "scipy", "PyQt5", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="mchanhua",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI 程序，不弹黑窗口
    icon="assets/mchanhua.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="mchanhua",
)
