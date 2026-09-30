"""日语：能不能送去翻译（语言判断）＋ 识别语言怎么选。

注意：这个文件**绝不能真的去建 OCR 引擎**——先初始化 winrt、再 import
rapidocr/onnxruntime 会在部分机器上原生崩溃（access violation）。
所以下面都用替身来验路由逻辑；真正的引擎由 test_ocr_* 那两组测试负责。
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from mchanhua.app import Application
from mchanhua.config import Config
from mchanhua.ocr import (
    OCR_LANGUAGE_CHOICES,
    language_label,
    normalize_ocr_language,
    rapidocr_is_unsafe,
)
from mchanhua.translate.base import should_translate, split_translatable
from tests.fakes import FakeGrabber, FakeOcr, FakeWindow


# ---- 该不该翻译 ----


@pytest.mark.parametrize(
    "text",
    (
        "冒険者よ、よく来たな。",
        "こんにちは",
        "レベルアップ！",
        "HPが回復した",
        "スライムが現れた！",
        "なにか用ですか？",
    ),
)
def test_japanese_lines_are_translated(text):
    """回归：以前只认英文字母，日语（假名）一个字母都没有，整行被跳过。"""

    assert should_translate(text, "简体中文") is True


def test_kanji_only_line_uses_the_batch_hint():
    """纯汉字行分不清中日：同一批里出现过假名就当日语翻，否则当已经是中文。"""

    assert should_translate("冒険者", "简体中文") is False
    assert should_translate("冒険者", "简体中文", batch_has_japanese=True) is True

    mixed = split_translatable(["冒険者よ、よく来たな。", "冒険者"], "简体中文")
    assert [index for index, _ in mixed] == [0, 1]

    chinese = split_translatable(["磁石", "可以放在："], "简体中文")
    assert chinese == []


def test_japanese_target_skips_japanese_but_keeps_foreign_words():
    assert should_translate("こんにちは", "日本語") is False
    assert should_translate("こんにちは World", "日本語") is True


def test_other_languages_still_work():
    assert should_translate("Привет, мир", "简体中文") is True
    assert should_translate("안녕하세요", "简体中文") is True
    assert should_translate("Steel Ingot", "简体中文") is True
    assert should_translate("磁石", "简体中文") is False
    assert should_translate("已将截图保存为1.png", "简体中文") is True
    assert should_translate("1234 / 1234", "简体中文") is False
    assert should_translate("", "简体中文") is False


# ---- 识别语言 ----


def test_normalize_ocr_language():
    assert normalize_ocr_language("") == "auto"
    assert normalize_ocr_language("自动") == "auto"
    assert normalize_ocr_language("日语") == "ja"
    assert normalize_ocr_language("JP") == "ja"
    assert normalize_ocr_language("ja-JP") == "ja"
    assert normalize_ocr_language("韩语") == "ko"
    assert normalize_ocr_language("俄语") == "ru"
    assert normalize_ocr_language("英语") == "en"
    assert normalize_ocr_language("随便什么") == "auto"


def test_language_label():
    assert language_label("auto") == "自动（中英）"
    assert language_label("ja") == "日语"
    assert language_label("zh") == "中文"
    assert {code for code, _label in OCR_LANGUAGE_CHOICES} >= {"auto", "ja", "ko", "ru", "en"}


class _FakeEngine:
    def __init__(self, name, ready=True, **kwargs):
        self.name = name
        self.ready = ready
        self.kwargs = kwargs
        self.warning = ""


def _patch_engines(monkeypatch, rapid_ready=True):
    """把两个后端换成替身（绝不真的加载 winrt / onnxruntime）。"""

    import mchanhua.ocr as ocr

    created: dict = {}

    def fake_rapid(language="auto", upscale=1.0, **options):
        engine = _FakeEngine("rapidocr", rapid_ready, language=language, **options)
        created["rapidocr"] = engine
        return engine

    def fake_windows(language="auto", upscale=1.0, **options):
        engine = _FakeEngine("windows", language == "auto", language=language, **options)
        created["windows"] = engine
        return engine

    monkeypatch.setattr(ocr, "RapidOcr", fake_rapid)
    monkeypatch.setattr(ocr, "WindowsOcr", fake_windows)
    return ocr, created


def test_japanese_uses_the_bundled_model(monkeypatch):
    """日语优先用随包的日语模型（中英模型认不出假名）。"""

    ocr, created = _patch_engines(monkeypatch)

    engine = ocr.create_engine("auto", "ja")

    assert engine.name == "rapidocr"
    assert created["rapidocr"].kwargs["language"] == "ja"
    assert "windows" not in created           # 有模型就不用去碰系统 OCR


def test_japanese_without_any_model_falls_back_to_windows(monkeypatch):
    """模型没带上时才退回系统 OCR 语言包。"""

    ocr, _created = _patch_engines(monkeypatch, rapid_ready=False)

    engine = ocr.create_engine("auto", "ja")

    assert engine.name == "windows"


def test_japanese_with_nothing_available_warns_instead_of_crashing(monkeypatch):
    ocr, _created = _patch_engines(monkeypatch, rapid_ready=False)
    monkeypatch.setattr(ocr, "WindowsOcr", lambda **kwargs: _FakeEngine("windows", False))

    engine = ocr.create_engine("auto", "日语")

    assert engine.ready is False
    assert "OCR 语言包" in engine.warning and "日语" in engine.warning


def test_chinese_still_prefers_rapidocr(monkeypatch):
    ocr, created = _patch_engines(monkeypatch)

    engine = ocr.create_engine("auto", "auto")

    assert engine.name == "rapidocr"
    assert "windows" not in created


def test_windows_fallback_when_rapidocr_missing(monkeypatch):
    ocr, _created = _patch_engines(monkeypatch, rapid_ready=False)

    engine = ocr.create_engine("auto", "auto")

    assert engine.name == "windows"


def test_japanese_model_files_are_bundled():
    """日语识别模型要随程序分发（认假名全靠它）。"""

    from mchanhua.ocr.models import has_model, model_pack, models_dir

    pack = model_pack("ja")
    assert pack is not None and pack.label == "日语"
    assert has_model("ja") is True, f"缺模型文件：{pack.missing()}（目录 {models_dir()}）"
    assert model_pack("ko") is None
    assert has_model("auto") is False


def test_japanese_model_actually_reads_katakana():
    """真跑一遍日语识别：以前中英模型只能认出「の初期」，现在要认出整句。"""

    pytest.importorskip("rapidocr_onnxruntime")
    pytest.importorskip("onnxruntime")
    from PIL import Image, ImageDraw, ImageFont

    from mchanhua.ocr.rapidocr import RapidOcr

    font_path = r"C:\Windows\Fonts\YuGothM.ttc"
    if not Path(font_path).exists():
        pytest.skip("没有日文字体，跳过")  # pragma: no cover

    image = Image.new("RGB", (1000, 90), (18, 40, 60))
    ImageDraw.Draw(image).text(
        (14, 22), "ウィンドウサイズの初期化", font=ImageFont.truetype(font_path, 40),
        fill=(255, 255, 255),
    )

    engine = RapidOcr(language="ja", upscale=1.0)
    result = engine.recognize(image)
    text = " ".join(line.text for line in result.lines)

    assert "ウィンドウ" in text, f"假名还是没认出来：{text!r}"
    assert "初期化" in text


def test_rapidocr_is_not_loaded_after_winrt(monkeypatch):
    """先碰过 winrt 再加载 rapidocr 会崩：这时应当直接改用系统 OCR。"""

    ocr, created = _patch_engines(monkeypatch)
    monkeypatch.setitem(sys.modules, "winrt", types.ModuleType("winrt"))
    monkeypatch.delitem(sys.modules, "onnxruntime", raising=False)

    assert rapidocr_is_unsafe() is True
    assert ocr.create_engine("auto", "auto").name == "windows"
    assert "rapidocr" not in created


def test_rapidocr_guard_raises_instead_of_crashing(monkeypatch):
    """万一还是走到了 rapidocr：给个明确错误，别让进程直接死。"""

    from mchanhua.ocr.base import OcrUnavailable
    from mchanhua.ocr.rapidocr import RapidOcr

    monkeypatch.setitem(sys.modules, "winrt", types.ModuleType("winrt"))
    monkeypatch.delitem(sys.modules, "onnxruntime", raising=False)

    engine = RapidOcr(language="auto", upscale=1.0)
    assert engine.ready is False
    with pytest.raises(OcrUnavailable):
        engine._ensure_engine()


# ---- 控制器：把提醒显示出来 ----


class _WarningOcr(FakeOcr):
    warning = "日语识别包没装喵"
    ready = False
    languages: list[str] = []


class _FakeHotkeys:
    def __init__(self) -> None:
        self.registered: dict[str, str] = {}

    def register(self, action, hotkey, callback) -> None:
        self.registered[action] = hotkey

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


def test_ocr_warning_shows_up_in_the_status():
    app = Application(
        Config(),
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=_WarningOcr(),
        window=FakeWindow(),
    )
    app.hotkeys = _FakeHotkeys()

    assert app.ocr_warning == "日语识别包没装喵"

    app._register_hotkeys()

    status = app.queue.get_nowait()
    assert status[0] == "status" and "日语识别包没装喵" in status[1]


def test_ocr_languages_are_read_from_the_engine():
    class _Ocr(FakeOcr):
        languages = ["zh-Hans-CN", "ja-JP"]

    app = Application(
        Config(),
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=_Ocr(),
        window=FakeWindow(),
    )

    assert app.ocr_languages == ["zh-Hans-CN", "ja-JP"]
