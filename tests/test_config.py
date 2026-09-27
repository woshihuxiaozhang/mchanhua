import pytest

from mchanhua.config import (
    Config,
    ConfigError,
    default_config_path,
    dumps,
    load_config,
    loads,
    save_config,
)


def test_defaults_when_file_missing(workdir):
    config = load_config(workdir / "missing.toml")
    assert config.ocr.backend == "auto"
    assert config.translate.model == "deepseek-chat"
    assert config.hotkeys.translate == "ctrl+alt+q"
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
