from PIL import Image

from mchanhua.ocr.base import OcrLine, OcrResult
from mchanhua.pipeline import PipelineResult, render_pairs, run_pipeline


class FakeOcr:
    name = "fake"

    def __init__(self, lines: list[str], elapsed_ms: float = 12.0) -> None:
        self._lines = lines
        self._elapsed = elapsed_ms

    def recognize(self, image: Image.Image) -> OcrResult:
        return OcrResult(
            lines=[OcrLine(text=text) for text in self._lines],
            elapsed_ms=self._elapsed,
            backend=self.name,
        )


class FakeTranslator:
    name = "fake"
    warnings: list[str] = []

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def translate_lines(self, lines):
        self.calls.append(list(lines))
        return [f"【{text}】" for text in lines]


def _image() -> Image.Image:
    return Image.new("RGB", (10, 10))


def test_pipeline_translates_only_english_lines():
    ocr = FakeOcr(["Switch", "可以放在：", "Durability 1234", "磁石"])
    translator = FakeTranslator()

    result = run_pipeline(_image(), ocr, translator)

    assert translator.calls == [["Switch", "Durability 1234"]]
    assert result.output_lines == ["【Switch】", "可以放在：", "【Durability 1234】", "磁石"]
    assert result.translated_count == 2
    assert result.ocr_ms == 12.0
    assert result.translate_ms >= 0


def test_pipeline_without_translator_returns_source():
    ocr = FakeOcr(["Steel Ingot"])
    result = run_pipeline(_image(), ocr, None)
    assert result.output_lines == ["Steel Ingot"]
    assert result.translated_count == 0


def test_pipeline_reports_ocr_early_for_ui():
    seen: list[tuple[list[str], float]] = []
    ocr = FakeOcr(["Steel Ingot", "Durability"])
    run_pipeline(_image(), ocr, FakeTranslator(), on_ocr=lambda lines, ms: seen.append((lines, ms)))
    assert seen == [(["Steel Ingot", "Durability"], 12.0)]


def test_pipeline_warns_when_nothing_to_translate():
    ocr = FakeOcr(["可以放在：", "磁石"])
    result = run_pipeline(_image(), ocr, FakeTranslator())
    assert result.warnings and "没有需要翻译的行" in result.warnings[0]


def test_pipeline_warns_when_model_returns_source():
    class IdentityTranslator:
        name = "identity"
        warnings: list[str] = []

        def translate_lines(self, lines):
            return list(lines)

    result = run_pipeline(_image(), FakeOcr(["Steel Ingot"]), IdentityTranslator())
    assert any("疑似未翻译" in warning for warning in result.warnings)


def test_render_pairs_skips_unchanged_lines():
    result = PipelineResult(
        source_lines=["Switch", "可以放在："],
        output_lines=["开关", "可以放在："],
    )
    rendered = render_pairs(result)
    assert "开关\nSwitch" in rendered
    assert "可以放在：" in rendered
    assert rendered.count("可以放在：") == 1

