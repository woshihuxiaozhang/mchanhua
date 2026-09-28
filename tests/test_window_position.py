from mchanhua.config import UiConfig
from mchanhua.ui.window import resolve_position


def test_positions_inside_screen():
    ui = UiConfig(width=400, height=300)
    screen = (2560, 1440)
    for position in ("left", "right", "bottom-right", "bottom-left", "weird"):
        ui.position = position
        x, y = resolve_position(ui, screen)
        assert 0 <= x <= screen[0] - ui.width
        assert 0 <= y <= screen[1] - ui.height


def test_small_screen_never_goes_negative():
    ui = UiConfig(width=400, height=300, position="right")
    x, y = resolve_position(ui, (300, 200))
    assert (x, y) == (0, 24)


def test_size_override_keeps_window_inside_screen():
    """布局实际需要的尺寸比配置宽时，也要贴边摆放、不能顶出屏幕（按钮会被切掉）。"""

    ui = UiConfig(width=430, height=235, position="right")
    width, height = 520, 260
    x, y = resolve_position(ui, (2560, 1440), (width, height))
    assert x == 2560 - width - 24
    assert x + width <= 2560
    assert y + height <= 1440


def test_size_override_on_bottom_right():
    ui = UiConfig(width=430, height=235, position="bottom-right")
    x, y = resolve_position(ui, (1920, 1080), (500, 300))
    assert (x, y) == (1920 - 500 - 24, 1080 - 300 - 24)
