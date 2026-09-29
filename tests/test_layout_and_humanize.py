"""遮罩提示白框、数字键删区域、横向/纵向自适应排版、AI 整段整理。"""

import pytest

tk = pytest.importorskip("tkinter")

from mchanhua.app import Application  # noqa: E402
from mchanhua.config import Config, load_config, save_config  # noqa: E402
from mchanhua.geometry import Region  # noqa: E402
from mchanhua.pipeline import PipelineResult, run_from_ocr  # noqa: E402
from mchanhua.ocr.base import OcrLine, OcrResult  # noqa: E402
from mchanhua.translate.openai_compat import (  # noqa: E402
    HUMANIZE_NOTE,
    OpenAICompatibleTranslator,
)
from mchanhua.ui.region_picker import RegionPicker  # noqa: E402
from mchanhua.ui.window import ResultWindow  # noqa: E402
from tests.fakes import DecodingTranslator, FakeGrabber, FakeOcr, FakeWindow  # noqa: E402

SCREEN = Region(0, 0, 2560, 1440)


def _root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover
        pytest.skip(f"没有可用的图形环境：{exc}")
    root.withdraw()
    return root


# ---- 遮罩提示白框 ----


def test_hint_has_white_backdrop():
    root = _root()
    picker = RegionPicker(SCREEN, root)
    try:
        picker._set_hint()
        # 提示是独立的不透明小窗；每条提示是一个白底 + 实线边框的小标签
        assert picker.hint_root.winfo_exists()
        chips = picker._hint_labels
        assert chips, "提示应该拆成一个个小标签"
        for chip in chips:
            assert chip.cget("bg").lower() == "#ffffff"      # 不透明白底
            assert int(chip.cget("bd")) >= 1                 # 不透明边框
            assert str(chip.cget("relief")) == "solid"
            assert chip.cget("text")
    finally:
        picker.close()
        root.destroy()


# ---- 数字键删掉指定区域 ----


def test_number_key_removes_that_area():
    removed: list[int] = []
    shown: list[tuple[str, Region]] = [
        ("区域1", Region(10, 10, 100, 50)),
        ("区域2", Region(200, 60, 100, 50)),
    ]
    root = _root()
    picker = RegionPicker(SCREEN, root)
    try:
        picker.existing = shown
        picker.on_accept = lambda region: None
        picker.on_remove_index = removed.append

        picker.handle_key("2")

        assert removed == [2]               # 按 2 删第 2 个
    finally:
        picker.close()
        root.destroy()


def test_number_key_hint_is_shown():
    root = _root()
    picker = RegionPicker(
        SCREEN, root, on_accept=lambda region: None,
        on_remove=lambda: None, on_remove_index=lambda index: None,
    )
    try:
        text = " ".join(picker.hint_texts())
        assert "数字键 1~9" in text
    finally:
        picker.close()
        root.destroy()


# ---- 横向拉长左右并排 / 纵向拉宽上下排列 ----


def _window():
    try:
        window = ResultWindow(Config())
    except tk.TclError as exc:  # pragma: no cover
        pytest.skip(f"没有可用的图形环境：{exc}")
    window.show_result(PipelineResult(source_lines=["a"], output_lines=["甲"]))
    return window


def test_wide_window_puts_texts_side_by_side():
    window = _window()
    try:
        window.root.geometry("900x220")
        window.root.update()
        window._apply_layout()
        window.root.update_idletasks()

        assert window._side_by_side is True
        assert window.target.pack_info()["side"] == "left"
        assert window.source_area.pack_info()["side"] == "left"
    finally:
        window.root.destroy()


def test_tall_window_keeps_texts_stacked():
    window = _window()
    try:
        window.root.geometry("400x600")
        window.root.update()
        window._apply_layout()
        window.root.update_idletasks()

        assert window._side_by_side is False
        assert window.target.pack_info()["side"] == "top"
        assert window.source_area.pack_info()["side"] == "top"
    finally:
        window.root.destroy()


def test_layout_switches_back_and_forth():
    window = _window()
    try:
        window.root.geometry("900x220")
        window.root.update()
        window._apply_layout()
        assert window._side_by_side is True

        window.root.geometry("420x620")
        window.root.update()
        window._apply_layout()
        assert window._side_by_side is False
    finally:
        window.root.destroy()


# ---- AI 整段整理 ----


def test_humanize_prompt_is_optional():
    with_note = OpenAICompatibleTranslator(humanize=True)
    without = OpenAICompatibleTranslator(humanize=False)

    assert with_note.humanize is True
    assert without.humanize is False
    assert "paragraph" in HUMANIZE_NOTE


def test_paragraph_is_parsed_from_model_reply():
    class _Client:
        def post(self, url, json=None, headers=None):  # noqa: A002
            import httpx

            return httpx.Response(200, json={"choices": [{"message": {"content": (
                '{"paragraph": "钢锭和红石粉都拿到了。",'
                ' "lines": [{"i": 0, "src": "Steel Ingot", "dst": "钢锭"},'
                ' {"i": 1, "src": "Redstone Dust", "dst": "红石粉"}]}'
            )}}]})

    translator = OpenAICompatibleTranslator(client=_Client(), retry_attempts=1)
    result = translator.translate_lines(["Steel Ingot", "Redstone Dust"])

    assert result == ["钢锭", "红石粉"]
    assert translator.last_paragraph == "钢锭和红石粉都拿到了。"


def test_pipeline_carries_paragraph():
    class _Translator:
        name = "fake"
        warnings: list[str] = []
        last_paragraph = "整理后的整段。"

        def translate_lines(self, lines):
            return [f"[{text}]" for text in lines]

    ocr = OcrResult(lines=[OcrLine(text="Steel Ingot")], elapsed_ms=1.0, backend="fake")
    result = run_from_ocr(ocr, _Translator())

    assert result.paragraph == "整理后的整段。"


def test_window_shows_paragraph_on_top():
    window = _window()
    try:
        window.show_result(
            PipelineResult(
                source_lines=["Steel Ingot"], output_lines=["钢锭"],
                line_areas=["区域1"], paragraph="整理后的整段。",
            )
        )
        window.root.update_idletasks()

        translated = window.target.get("1.0", "end").strip().splitlines()
        assert translated[0] == "整理后的整段。"          # 整理版在最上面
        assert "钢锭" in translated                      # 逐行译文仍在下面可核对
        assert "已整理成段" in window.status_text()
    finally:
        window.root.destroy()


def test_humanize_setting_round_trip(workdir):
    config = Config()
    config.translate.humanize = False
    path = save_config(config, workdir / "config.toml")

    assert load_config(path).translate.humanize is False
