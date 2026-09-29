"""程序图标：脚本能跑、ico 里各尺寸齐全（任务栏/快捷方式都用它）。"""

import importlib.util
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
ICON = REPO / "assets" / "mchanhua.ico"
PREVIEW = REPO / "assets" / "mchanhua.png"


def _load_make_icon():
    spec = importlib.util.spec_from_file_location("make_icon", REPO / "tools" / "make_icon.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_make_icon_script_regenerates_icon():
    module = _load_make_icon()

    assert module.main() == 0
    assert ICON.exists() and PREVIEW.exists()

    icon = Image.open(ICON)
    assert icon.size == (256, 256)          # ico 里最大那张
    assert icon.mode == "RGBA"
    assert module.SIZES[0] == 16            # 小尺寸也要有，任务栏才清楚


def test_icon_render_is_deterministic():
    module = _load_make_icon()

    assert module.render(64).tobytes() == module.render(64).tobytes()
