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

