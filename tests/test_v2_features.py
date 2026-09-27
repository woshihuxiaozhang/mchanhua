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

    # 默认 screen 模式：整屏识别，再按选区筛选要翻译的行
    assert app.grabber.requests[-1].to_csv() == "0,0,2560,1440"


def test_translate_falls_back_to_cursor_region_when_no_custom(workdir: Path):
    app = _app(workdir)
    app.perform_translate()
    wait_for(app, "result")

    assert app.grabber.requests[-1].to_csv() == "0,0,2560,1440"


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
        self.started = False

    def register(self, action: str, hotkey: str, callback) -> None:
        self.bindings.append((action, hotkey))

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        pass


def test_hotkey_registration_covers_v2_actions(workdir: Path):
    app = _app(workdir)
    app.hotkeys = _RecordingHotkeys()

    app._register_hotkeys()

    registered = dict(app.hotkeys.bindings)
    assert registered["翻译自定义选区"] == app.config.hotkeys.translate
    assert registered["框选并翻译"] == "alt+/"
    assert registered["全屏翻译"] == "alt+m"
    assert len(app.hotkeys.bindings) == 5      # 退出热键默认为空，不注册
    assert app.hotkeys.started


def test_fullscreen_line_cap():
    assert FULLSCREEN_MAX_LINES > 0


def test_select_and_translate_uses_new_region_without_saving(workdir: Path, monkeypatch):
    """Alt+/：用新框的选区翻译，但**不保存**，避免覆盖 Alt+V 设定的选区。"""

    app = _app(workdir)
    app.translator = DecodingTranslator()
    app.config.regions.set_custom_region(Region(1, 2, 3, 4))   # 已有 Alt+V 设定的选区
    monkeypatch.setattr("mchanhua.app.pick_region", lambda monitor, parent: Region(50, 60, 400, 300))

    app.perform_select_and_translate()
    messages = wait_for(app, "result")

    # 默认 screen 模式：整屏识别，按本次框的选区筛选
    assert app.grabber.requests[-1].to_csv() == "0,0,2560,1440"
    assert any(message[0] == "result" for message in messages)
    # 原来的自定义选区不受影响，配置文件里也不会写入这次临时选区
    assert app.config.regions.custom_region().to_csv() == "1,2,3,4"
    assert "50,60,400,300" not in Path(app.config_path).read_text(encoding="utf-8")


def test_select_and_translate_cancel_does_not_translate(workdir: Path, monkeypatch):
    app = _app(workdir)
    monkeypatch.setattr("mchanhua.app.pick_region", lambda monitor, parent: None)

    app.perform_select_and_translate()

    assert app.grabber.requests == []
    assert any("已取消框选" in status for status in app.window.statuses)


def test_select_region_only_does_not_translate(workdir: Path, monkeypatch):
    """Alt+V 只框选保存，不触发翻译；之后再按 Ctrl+Alt 才翻译。"""

    app = _app(workdir)
    monkeypatch.setattr("mchanhua.app.pick_region", lambda monitor, parent: Region(7, 8, 90, 100))

    app.perform_select_region()
    assert app.grabber.requests == []
    assert app.config.regions.custom_region().to_csv() == "7,8,90,100"

    app.perform_translate()          # 等价于按 Ctrl+Alt
    wait_for(app, "result")
    assert app.grabber.requests[-1].to_csv() == "0,0,2560,1440"
