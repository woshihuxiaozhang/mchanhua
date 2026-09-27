"""路径与单实例锁的测试。"""

from pathlib import Path

from mchanhua.paths import app_dir, cache_path, debug_dir, is_frozen, log_dir, resource_dir
from mchanhua.single_instance import SingleInstance, mutex_name


def test_app_dir_follows_appdata(monkeypatch, workdir):
    monkeypatch.setenv("APPDATA", str(workdir / "roaming"))
    assert app_dir() == workdir / "roaming" / "mchanhua"
    assert log_dir() == app_dir() / "logs"
    assert debug_dir() == app_dir() / "debug"
    assert cache_path().name == "cache.sqlite"


def test_mchanhua_home_overrides(monkeypatch, workdir):
    monkeypatch.setenv("MCHANHUA_HOME", str(workdir / "custom"))
    assert app_dir() == Path(workdir / "custom")


def test_resource_dir_in_source_mode():
    assert not is_frozen()
    assert (resource_dir() / "mchanhua").is_dir()


def test_single_instance_detects_second_acquire():
    name = mutex_name("mchanhua-test-" + str(id(object())))
    first = SingleInstance(name)
    assert first.acquire() is True
    assert first.already_running is False

    second = SingleInstance(name)
    assert second.acquire() is False
    assert second.already_running is True

    second.release()
    first.release()
