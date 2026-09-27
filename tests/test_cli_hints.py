"""不给子命令时应给出友好提示（而不是 argparse 的原始报错）。"""

from mchanhua.cli import main


def test_no_subcommand_prints_hint(capsys):
    code = main([])
    captured = capsys.readouterr()
    assert code == 2
    assert "mchanhua run" in captured.out
    assert "启动.cmd" in captured.out


def test_unknown_subcommand_exits_with_error(capsys):
    import pytest

    with pytest.raises(SystemExit) as excinfo:
        main(["not-a-command"])
    assert excinfo.value.code == 2
