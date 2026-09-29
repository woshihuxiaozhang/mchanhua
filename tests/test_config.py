import pytest

from mchanhua.config import (
    CONFIG_VERSION,
    Config,
    ConfigError,
    default_config_path,
    dumps,
    load_config,
    loads,
    migrate,
    project_config_path,
    resolve_config_path,
    save_config,
)
from mchanhua.geometry import Region


# 旧版本（v2 及更早的 exe）写出来的配置文件：没有 [meta]，热键还是老默认值。
LEGACY_TEXT = """
[hotkeys]
translate = "ctrl+alt+q"
translate_region = "alt+/"
translate_fullscreen = "alt+m"
translate_clipboard = "ctrl+alt+s"
select_region = "alt+v"
quit = "ctrl+alt+x"

[translate]
provider = "deepseek"
api_key = "sk-keep-me"

[ui]
background = "#1b1b1f"
"""


def test_defaults_when_file_missing(workdir):
    config = load_config(workdir / "missing.toml")
    assert config.ocr.backend == "auto"
    assert config.translate.model == "deepseek-chat"
    assert config.hotkeys.translate == "ctrl+alt"
    assert config.hotkeys.translate_clipboard == "alt+s"
    assert config.hotkeys.quit == ""      # 默认为空 = 不注册退出热键
    assert config.resolved_api_key == ""


def test_round_trip_preserves_tricky_strings(workdir):
    config = Config()
    config.glossary = {"Redstone": "红石", "quote": 'he said "hi"', "path": r"C:\temp\new"}
    config.regions.fixed = {"tooltip": "100,200,400,300"}
    config.regions.follow_cursor = "-20,-10,420,320"
    config.translate.api_key = "sk-test\nline"

    path = save_config(config, workdir / "config.toml")
    loaded = load_config(path)

    assert loaded.glossary == config.glossary
    assert loaded.regions.fixed == config.regions.fixed
    assert loaded.regions.follow_cursor == config.regions.follow_cursor
    assert loaded.translate.api_key == "sk-test\nline"


def test_glossary_parsed_from_toml():
    text = """
[glossary]
Redstone = "红石"
Netherite = "下界合金"
"""
    config = loads(text)
    assert config.glossary == {"Redstone": "红石", "Netherite": "下界合金"}


def test_unknown_keys_are_ignored():
    config = loads("[ocr]\nbackend = \"windows\"\nfuture_option = 1\n")
    assert config.ocr.backend == "windows"


def test_retired_background_image_key_is_ignored(workdir):
    """自定义背景图功能已经取消：旧配置里残留的那行当没看见，也不会再写回去。"""

    text = '[ui]\nbackground_image = "D:\\\\pics\\\\bg.png"\nopacity = 0.9\n'
    config = loads(text)

    assert config.ui.opacity == 0.9
    assert "background_image" not in dumps(config)


def test_invalid_values_raise():
    with pytest.raises(ConfigError):
        loads("[ocr]\nupscale = 0\n")
    with pytest.raises(ConfigError):
        loads("[ui]\nopacity = 1.5\n")
    with pytest.raises(ConfigError):
        loads("[regions.fixed]\ntooltip = \"not-a-region\"\n")
    with pytest.raises(ConfigError):
        loads("[ocr\nbad toml")


def test_env_var_overrides_api_key(monkeypatch):
    config = Config()
    assert config.resolved_api_key == ""
    monkeypatch.setenv("MCHANHUA_API_KEY", "sk-from-env")
    assert config.resolved_api_key == "sk-from-env"


def test_dumps_is_valid_toml():
    config = Config()
    config.regions.fixed = {"chat": "0,900,800,200"}
    text = dumps(config)
    assert "[hotkeys]" in text
    assert "[regions.fixed]" in text
    assert loads(text).regions.fixed == config.regions.fixed


def test_default_config_path_points_outside_repo():
    path = default_config_path()
    assert path.name == "config.toml"
    assert path.parent.name == "mchanhua"


def test_project_local_config_takes_priority(workdir, monkeypatch):
    monkeypatch.setenv("APPDATA", str(workdir / "appdata"))
    local = project_config_path(workdir)
    assert not local.exists()
    # 没有项目内配置时用 %APPDATA%
    assert resolve_config_path(None, workdir) == default_config_path()

    save_config(Config(), local)
    assert local.exists()
    assert resolve_config_path(None, workdir) == local
    assert load_config(None, workdir).translate.model == "deepseek-chat"


def test_explicit_path_wins(workdir):
    explicit = workdir / "custom.toml"
    save_config(Config(), explicit)
    save_config(Config(), project_config_path(workdir))
    assert resolve_config_path(explicit, workdir) == explicit


def test_save_config_defaults_to_loaded_source(workdir, monkeypatch):
    """不给路径保存时应写回原文件，而不是 %APPDATA%（曾经写错地方）。"""

    monkeypatch.setenv("APPDATA", str(workdir / "appdata"))
    path = save_config(Config(), workdir / "config.local.toml")
    loaded = load_config(path)
    assert loaded.loaded_from == path

    loaded.regions.set_custom_region(Region.parse("1,2,3,4"))
    returned = save_config(loaded)
    assert returned == path
    assert "1,2,3,4" in path.read_text(encoding="utf-8")
    assert not (workdir / "appdata" / "mchanhua" / "config.toml").exists()


# ---- 配置版本迁移：旧 exe 写坏的配置必须自动修好 ----


def test_legacy_hotkeys_are_migrated():
    """旧版本写的配置文件会在加载时升级到新默认热键。"""

    config = loads(LEGACY_TEXT)
    assert config.hotkeys.translate == "ctrl+alt"
    assert config.hotkeys.translate_clipboard == "alt+s"
    assert config.hotkeys.quit == ""          # 新版本不再注册退出热键
    assert config.version == CONFIG_VERSION
    assert config.migrations, "迁移过的配置要能说明改了什么"
    # 与热键无关的内容原样保留
    assert config.translate.api_key == "sk-keep-me"


def test_user_modified_hotkeys_survive_migration():
    """只有"旧默认值"会被改写，用户自己设过的值不动。"""

    config = loads("[hotkeys]\ntranslate = \"alt+t\"\nquit = \"ctrl+shift+q\"\n")
    assert config.hotkeys.translate == "alt+t"
    assert config.hotkeys.quit == "ctrl+shift+q"
    assert config.migrations == []


def test_migration_is_persisted_once(workdir):
    """迁移后立刻落盘并带上 [meta] version，下次启动不再重复迁移。"""

    path = workdir / "config.toml"
    path.write_text(LEGACY_TEXT, encoding="utf-8")

    first = load_config(path)
    assert first.hotkeys.translate == "ctrl+alt"
    text = path.read_text(encoding="utf-8")
    assert "[meta]" in text
    assert f"version = {CONFIG_VERSION}" in text
    assert "ctrl+alt+q" not in text

    again = load_config(path)
    assert again.migrations == []
    assert again.hotkeys.translate == "ctrl+alt"


def test_current_version_is_not_migrated():
    """新版本自己写出来的配置不会再被迁移。"""

    text = dumps(Config())
    assert f"version = {CONFIG_VERSION}" in text
    assert loads(text).migrations == []


def test_migrate_ignores_newer_version():
    config = Config()
    config.hotkeys.translate = "ctrl+alt+q"
    assert migrate(config, CONFIG_VERSION + 1) == []
    assert config.hotkeys.translate == "ctrl+alt+q"


def test_legacy_oversized_window_is_clamped():
    """旧版本会把主窗口撑成整屏（半透明白底盖住桌面）；迁移时必须收回小窗。"""

    config = loads(
        "[hotkeys]\ntranslate = \"ctrl+alt+q\"\n\n[ui]\nwidth = 2560\nheight = 1440\n"
    )
    assert config.ui.width == 900
    assert config.ui.height == 700
    assert any("ui.width" in note for note in config.migrations)


def test_current_version_keeps_user_window_size():
    """新版配置里用户自己定的尺寸（哪怕很大）不该被动手脚。"""

    text = dumps(Config())
    text = text.replace("width = 430", "width = 1200").replace("height = 160", "height = 800")
    assert loads(text).ui.width == 1200
    assert loads(text).ui.height == 800


def test_legacy_default_height_is_migrated():
    """v3 的默认高度 235 会在小窗底部留一块空白；迁移时降到新版默认值。"""

    config = loads("[ui]\nheight = 235\nwidth = 430\n")
    assert config.ui.height == 160
    assert any("ui.height" in note for note in config.migrations)


def test_user_chosen_height_is_kept_when_migrating():
    config = loads("[ui]\nheight = 300\n")
    assert config.ui.height == 300
    assert all("ui.height" not in note for note in config.migrations)


def test_opacity_round_trip(workdir):
    """透明度要能存进配置再读回来。"""

    config = Config()
    config.ui.opacity = 0.85

    path = save_config(config, workdir / "config.toml")
    loaded = load_config(path)

    assert loaded.ui.opacity == 0.85
