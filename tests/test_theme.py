"""主题测试：界面样式完全由配置决定（改配置即可换 UI）。"""

from mchanhua.config import Config, UiConfig, load_config, save_config
from mchanhua.ui.contrast import audit
from mchanhua.ui.theme import Theme, heal_theme, unreadable_reasons


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


# ---- 主题自愈：只救"看不见"的配色，不动用户能看清的主题 ----


def test_default_palette_passes_its_own_audit():
    """默认配色必须自己达标，否则每次启动都会"自愈"一次、白写一遍配置。"""

    assert audit(Theme.from_config(UiConfig())) == []
    assert heal_theme(Config()) == []


def test_broken_theme_is_healed_to_default_light():
    """旧实例混搭出来的"深底黑字"必须拉回默认浅色。"""

    config = Config()
    config.ui.background = "#1b1b1f"
    config.ui.text = "#111111"

    reasons = heal_theme(config)
    assert reasons, "读不清的配色要给出理由（写进日志）"
    assert config.ui.background == "#FFFFFF"
    assert config.ui.text == "#111111"
    assert unreadable_reasons(Theme.from_config(config.ui)) == []


def test_user_dark_theme_is_kept():
    """用户自己挑的深色主题只要看得清就保留，不能因为不到 4.5:1 就删掉。"""

    config = Config()
    config.ui.background = "#1B1B1F"
    config.ui.panel = "#232329"
    config.ui.text = "#F2F2F2"
    config.ui.text_dim = "#B4B4BE"

    assert heal_theme(config) == []
    assert config.ui.background == "#1B1B1F"
