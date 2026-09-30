"""首次使用向导 + 开机自启。"""

from __future__ import annotations

from pathlib import Path

import pytest

from mchanhua import autostart
from mchanhua.app import Application
from mchanhua.config import Config, dumps, load_config, loads, save_config
from mchanhua.translate.providers import PRESETS
from tests.fakes import FakeGrabber, FakeOcr, FakeWindow


# ---- 开机自启 ----


def test_autostart_enable_and_disable(workdir: Path):
    directory = workdir / "Startup"

    assert autostart.is_enabled(directory) is False
    path = autostart.enable(directory)

    assert path.exists() and path.name == autostart.LAUNCHER_NAME
    assert autostart.is_enabled(directory) is True
    text = path.read_text(encoding="utf-8", errors="replace")
    assert text.startswith("@echo off")
    assert 'start ""' in text

    assert autostart.disable(directory) is True
    assert autostart.is_enabled(directory) is False
    assert autostart.disable(directory) is False        # 本来没有也不算失败


def test_autostart_set_enabled_is_idempotent(workdir: Path):
    directory = workdir / "Startup"

    assert autostart.set_enabled(True, directory) is True
    assert autostart.set_enabled(True, directory) is True
    assert autostart.set_enabled(False, directory) is False
    assert autostart.set_enabled(False, directory) is False


def test_autostart_launcher_points_at_this_program():
    command = autostart.launch_command()
    assert 'start ""' in command
    assert "app_entry.py" in command or "mchanhua" in command.lower()


# ---- 配置：向导走完没有 ----


def test_setup_done_round_trip(workdir: Path):
    config = Config()
    assert config.setup_done is False

    config.setup_done = True
    path = save_config(config, workdir / "config.toml")

    assert "setup_done = true" in dumps(config)
    assert load_config(path).setup_done is True


def test_setup_done_defaults_to_false_for_old_configs():
    assert loads("[hotkeys]\ntranslate = \"ctrl+alt\"\n").setup_done is False


# ---- 什么时候弹向导 ----


def _app(workdir: Path | None = None) -> Application:
    config = Config()
    if workdir is not None:
        path = save_config(config, workdir / "config.toml")
        config = load_config(path)
    return Application(
        config,
        config_path=config.loaded_from,
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=FakeOcr(),
        window=FakeWindow(),
    )


def test_wizard_shows_only_on_first_run_without_a_key(workdir: Path):
    app = _app(workdir)

    assert app.should_show_wizard() is True         # 第一次、还没填 key

    app.config.translate.api_key = "sk-填过了"
    assert app.should_show_wizard() is False        # 有 key 就别烦人家

    app.config.translate.api_key = ""
    app.config.setup_done = True
    assert app.should_show_wizard() is False        # 向导走过（或跳过过）


def test_request_open_wizard_enqueues_one_shot_callable(workdir: Path):
    app = _app(workdir)

    app.request_open_wizard()

    kind, payload = app.queue.get_nowait()
    assert kind == "call"
    assert callable(payload)


# ---- 向导界面 ----


tk = pytest.importorskip("tkinter")


def _wizard(config: Config, on_done=None, monkeypatch=None):
    import mchanhua.ui.wizard as wizard_module

    if monkeypatch is not None:
        # 测试里绝不能往真实的「启动」文件夹里写东西
        recorded: dict = {}
        monkeypatch.setattr(
            wizard_module.autostart, "set_enabled",
            lambda enabled, directory=None: recorded.setdefault("enabled", enabled),
        )
        monkeypatch.setattr(wizard_module.autostart, "is_enabled", lambda directory=None: False)
    else:  # pragma: no cover
        recorded = {}

    last: Exception | None = None
    for _ in range(2):
        try:
            return wizard_module.SetupWizard(config, on_done=on_done), recorded
        except tk.TclError as exc:
            last = exc
    pytest.skip(f"没有可用的图形环境：{last}")  # pragma: no cover


def test_wizard_has_three_steps(workdir: Path):
    config = load_config(save_config(Config(), workdir / "config.toml"))
    wizard, _recorded = _wizard(config)
    try:
        assert len(wizard._pages) == 3
        assert "欢迎" in wizard.step_label.cget("text")

        wizard.next()
        assert wizard.step == 1 and "API Key" in wizard.step_label.cget("text")
        wizard.next()
        assert wizard.step == 2 and wizard.next_button.cget("text") == "完成"

        wizard.back()
        assert wizard.step == 1
        wizard.back()
        assert wizard.step == 0
        assert wizard.back_button.cget("state") == "disabled"
    finally:
        _destroy(wizard)


def _destroy(wizard) -> None:
    try:
        wizard.root.destroy()
    except Exception:  # pragma: no cover - finish() 里已经销毁过
        pass


def test_wizard_finish_saves_key_and_setup_done(workdir: Path, monkeypatch):
    path = save_config(Config(), workdir / "config.toml")
    config = load_config(path)
    done: list[Config] = []
    wizard, recorded = _wizard(config, on_done=done.append, monkeypatch=monkeypatch)
    try:
        wizard._show_step(2)
        wizard._vars["api_key"].set("sk-wizard")
        wizard._vars["autostart"].set(True)

        wizard.next()                     # 最后一步的「下一步」= 完成

        assert recorded["enabled"] is True
        assert done == [config]
        assert config.setup_done is True
        assert config.translate.api_key == "sk-wizard"
        assert config.translate.provider in {preset.key for preset in PRESETS}
        reloaded = load_config(path)
        assert reloaded.setup_done is True and reloaded.translate.api_key == "sk-wizard"
    finally:
        _destroy(wizard)


def test_wizard_skip_marks_setup_done_without_touching_the_key(workdir: Path, monkeypatch):
    path = save_config(Config(), workdir / "config.toml")
    config = load_config(path)
    done: list[Config] = []
    wizard, _recorded = _wizard(config, on_done=done.append, monkeypatch=monkeypatch)
    try:
        wizard.skip()

        assert done == []
        assert config.setup_done is True
        assert load_config(path).setup_done is True
    finally:
        _destroy(wizard)


# ---- 设置里的「使用向导」 ----


def test_settings_footer_can_reopen_the_wizard():
    from mchanhua.ui.settings_window import SettingsWindow

    opened: list[str] = []
    try:
        window = SettingsWindow(Config(), on_open_wizard=lambda: opened.append("wizard"))
    except tk.TclError as exc:  # pragma: no cover
        pytest.skip(f"没有可用的图形环境：{exc}")
    texts = _all_texts(window.card)
    assert "使用向导" in texts

    window.open_wizard()

    assert opened == ["wizard"]


def test_wizard_opens_as_a_child_of_the_main_window():
    """实际用法：挂在主窗口下当模态子窗口（和设置窗口一样）。"""

    import mchanhua.ui.wizard as wizard_module
    from mchanhua.ui.window import ResultWindow

    try:
        main = ResultWindow(Config())
    except tk.TclError as exc:  # pragma: no cover
        pytest.skip(f"没有可用的图形环境：{exc}")
    try:
        wizard = wizard_module.SetupWizard(Config(), parent=main.root)
        wizard.root.update_idletasks()

        assert wizard.root.winfo_exists()
        assert wizard.root.winfo_toplevel() is not main.root
        wizard.root.destroy()
    finally:
        main.root.destroy()


def _all_texts(widget) -> list[str]:
    found: list[str] = []
    for child in widget.winfo_children():
        try:
            text = child.cget("text")
        except Exception:
            text = None
        if text:
            found.append(str(text))
        found.extend(_all_texts(child))
    return found
