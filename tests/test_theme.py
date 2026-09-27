"""主题测试：界面样式完全由配置决定（改配置即可换 UI）。"""

from mchanhua.config import Config, UiConfig, load_config, save_config
from mchanhua.ui.theme import Theme


def test_theme_takes_colors_from_config():
    ui = UiConfig(background="#000000", panel="#111111", text="#ffffff", accent="#ff0000")
    theme = Theme.from_config(ui)

    assert theme.background == "#000000"
    assert theme.panel == "#111111"
    assert theme.text == "#ffffff"
    assert theme.accent == "#ff0000"


def test_theme_clamps_unreasonable_values():
    ui = UiConfig(opacity=2.0, width=100, height=100, font_size=4, result_font_size=4, padding=1)
    theme = Theme.from_config(ui)

    assert theme.opacity == 1.0
    assert (theme.width, theme.height) == (320, 240)
    assert theme.font_size >= 8
    assert theme.result_font_size >= 9
    assert theme.padding >= 4


def test_theme_follows_config_file_edits(workdir):
    config = Config()
    config.ui.accent = "#00ff00"
    config.ui.result_font_size = 22
    path = save_config(config, workdir / "config.toml")

    loaded = load_config(path)
    theme = Theme.from_config(loaded.ui)

    assert theme.accent == "#00ff00"
    assert theme.result_font_size == 22


def test_theme_has_all_expected_fields():
    names = Theme.from_config(UiConfig()).field_names
    for field in ("background", "panel", "text", "accent", "font_family", "padding", "opacity"):
        assert field in names
