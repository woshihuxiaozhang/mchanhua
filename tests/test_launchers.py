"""启动脚本的冒烟检查：确保双击就能用（自动切目录、用虚拟环境的 Python）。"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_launcher_scripts_exist_and_are_self_contained():
    for name in ("启动.cmd", "检查环境.cmd"):
        script = REPO / name
        assert script.exists(), f"缺少启动脚本：{name}"
        text = script.read_text(encoding="utf-8")
        # 切到脚本所在目录，避免在不同工作目录下运行时 import 失败
        assert 'cd /d "%~dp0"' in text
        # 用项目虚拟环境里的解释器，不依赖 PATH
        assert r".venv\Scripts\python.exe" in text
        assert "pause" in text, "出错时要留住窗口，方便看报错"


def test_run_launcher_calls_module_entrypoint():
    text = (REPO / "启动.cmd").read_text(encoding="utf-8")
    assert "-m mchanhua run" in text


def test_check_launcher_runs_probe():
    text = (REPO / "检查环境.cmd").read_text(encoding="utf-8")
    assert "-m mchanhua probe" in text
    assert "-m mchanhua config-path" in text
