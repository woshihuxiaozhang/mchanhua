"""v2 需求：自定义选区（持久化）、Alt+/ 选区翻译、Alt+m 全屏翻译。"""

from pathlib import Path

import pytest

from mchanhua.app import FULLSCREEN_MAX_LINES, Application
from mchanhua.config import Config, load_config, save_config
from mchanhua.geometry import Region
from tests.fakes import DecodingTranslator, FakeGrabber, FakeOcr, FakeWindow, wait_for


# ---- 配置层 ----


def test_default_hotkeys_include_v2_entries():
    config = Config()
    assert config.hotkeys.translate_region == "alt+/"
    assert config.hotkeys.translate_fullscreen == "alt+m"


def test_custom_region_round_trip(workdir: Path):
    config = Config()
    config.regions.set_custom_region(Region(120, 240, 600, 400))
    path = save_config(config, workdir / "config.toml")

    loaded = load_config(path)
    assert loaded.regions.custom_region().to_csv() == "120,240,600,400"
    assert "custom" in path.read_text(encoding="utf-8")


def test_custom_region_missing_returns_none():
    assert Config().regions.custom_region() is None


# ---- 控制器 ----


def _app(workdir: Path, **kwargs) -> Application:
    config = Config()
    config_path = save_config(config, workdir / "config.toml")
    config = load_config(config_path)
    return Application(
        config,
        config_path=config_path,
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=FakeOcr(),
        window=FakeWindow(),
        **kwargs,
    )


def test_translate_uses_saved_custom_region(workdir: Path):
    """需求 1：取词用自定义选区，而不是跟随光标。"""

    app = _app(workdir)
    app.config.regions.set_custom_region(Region(300, 400, 500, 300))
    app.perform_translate()
    wait_for(app, "result")

    assert app.grabber.requests[-1].to_csv() == "300,400,500,300"


def test_translate_falls_back_to_cursor_region_when_no_custom(workdir: Path):
    app = _app(workdir)
    app.perform_translate()
    wait_for(app, "result")

    # 逻辑 (1024,576) → 物理 (1280,720)，再加默认偏移 -280,-20
    assert app.grabber.requests[-1].to_csv() == "1000,700,560,440"


def test_fullscreen_translate_covers_whole_monitor(workdir: Path):
    """需求 3：Alt+m 全屏翻译。"""

    app = _app(workdir)
    app.config.regions.set_custom_region(Region(300, 400, 500, 300))
    app.translator = DecodingTranslator()
    app.perform_translate_fullscreen()
    messages = wait_for(app, "result")

    assert app.grabber.requests[-1].to_csv() == "0,0,2560,1440"
    result = next(message[1] for message in messages if message[0] == "result")
    assert result.translated_count == 1        # 只有英文行被翻译


def test_select_region_saves_custom_region_to_config_file(workdir: Path, monkeypatch):
    """需求 1 的后半句：框选后要把选区记下来（重启仍在）。"""

    app = _app(workdir)
    monkeypatch.setattr("mchanhua.app.pick_region", lambda monitor, parent: Region(11, 22, 333, 444))

    app.perform_select_region()

    assert app.config.regions.custom_region().to_csv() == "11,22,333,444"
    text = Path(app.config_path).read_text(encoding="utf-8")
    assert 'custom = "11,22,333,444"' in text
    assert any("已保存自定义选区" in status for status in app.window.statuses)


def test_select_region_cancel_keeps_previous(workdir: Path, monkeypatch):
    app = _app(workdir)
    app.config.regions.set_custom_region(Region(1, 2, 3, 4))
    monkeypatch.setattr("mchanhua.app.pick_region", lambda monitor, parent: None)

    app.perform_select_region()

    assert app.config.regions.custom_region().to_csv() == "1,2,3,4"
    assert any("已取消框选" in status for status in app.window.statuses)


class _RecordingHotkeys:
    def __init__(self) -> None:
        self.bindings: list[tuple[str, str]] = []

    def register(self, action: str, hotkey: str, callback) -> None:
        self.bindings.append((action, hotkey))

    def stop(self) -> None:
        pass


def test_hotkey_registration_covers_v2_actions(workdir: Path):
    app = _app(workdir)
    app.hotkeys = _RecordingHotkeys()

    app._register_hotkeys()

    registered = dict(app.hotkeys.bindings)
    assert registered["翻译自定义选区"] == "alt+/"
    assert registered["全屏翻译"] == "alt+m"
    assert len(app.hotkeys.bindings) == 6


def test_fullscreen_line_cap():
    assert FULLSCREEN_MAX_LINES > 0
