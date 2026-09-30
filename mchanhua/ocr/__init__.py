"""OCR 后端。"""

from __future__ import annotations

import sys

from mchanhua.ocr.base import OcrEngine, OcrLine, OcrResult, OcrUnavailable, group_words_into_lines
from mchanhua.ocr.rapidocr import RapidOcr
from mchanhua.ocr.windows import WindowsOcr

__all__ = [
    "OCR_LANGUAGE_CHOICES",
    "OcrEngine",
    "OcrLine",
    "OcrResult",
    "OcrUnavailable",
    "RapidOcr",
    "WindowsOcr",
    "create_engine",
    "group_words_into_lines",
    "language_label",
    "normalize_ocr_language",
    "windows_ocr_languages",
]

# 识别语言。rapidocr 1.2.3 自带的是中英模型（不认假名），
# 所以日语/韩语/俄语这些只能走 Windows 自带的 OCR 语言包。
OCR_LANGUAGE_CHOICES = (
    ("auto", "自动（中英）"),
    ("ja", "日语"),
    ("ko", "韩语"),
    ("ru", "俄语"),
    ("en", "英语"),
)

# 这些语言 rapidocr 的中英模型认不了，必须优先用 Windows OCR
WINDOWS_FIRST_LANGUAGES = {"ja", "ko", "ru", "ar", "th"}

_LANGUAGE_ALIASES = {
    "": "auto",
    "auto": "auto",
    "自动": "auto",
    "自动识别": "auto",
    "ja": "ja",
    "jp": "ja",
    "japanese": "ja",
    "日语": "ja",
    "日文": "ja",
    "ko": "ko",
    "korean": "ko",
    "韩语": "ko",
    "한국어": "ko",
    "ru": "ru",
    "russian": "ru",
    "俄语": "ru",
    "en": "en",
    "english": "en",
    "英语": "en",
    "zh": "zh",
    "ch": "zh",
    "中文": "zh",
}


def normalize_ocr_language(value: str | None) -> str:
    """把配置里写的识别语言收拾成短代码（auto / ja / ko / ru / en / zh）。"""

    text = (value or "").strip()
    lowered = text.lower()
    if lowered in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[lowered]
    for prefix in ("ja", "ko", "ru", "en", "zh"):
        if lowered.startswith(prefix):
            return prefix
    return "auto"


def language_label(value: str | None) -> str:
    code = normalize_ocr_language(value)
    for key, label in OCR_LANGUAGE_CHOICES:
        if key == code:
            return label
    if code == "zh":
        return "中文"
    return code


def windows_ocr_languages() -> list[str]:
    """本机 Windows OCR 装了哪些语言。

    只有**已经加载过 winrt**（也就是这次真的在用系统 OCR）时才去查：在部分机器上
    先初始化 winrt、再 import rapidocr/onnxruntime 会原生崩溃（access violation）。
    平时用 rapidocr 识别中英时这里直接返回空表，界面上写成"未知"就好。
    """

    if not _winrt_loaded():
        return []
    try:
        from mchanhua.ocr.windows import available_languages

        return available_languages()
    except Exception:  # pragma: no cover - 系统没装/查询失败
        return []


def _winrt_loaded() -> bool:
    return any(name == "winrt" or name.startswith("winrt.") for name in sys.modules)


def rapidocr_is_unsafe() -> bool:
    """现在再 import rapidocr 会不会把进程搞崩。

    某些机器（含本机）上：先初始化 winrt（系统 OCR），再 import
    onnxruntime/opencv（rapidocr 的依赖）会触发原生 access violation。
    已经 import 过 onnxruntime 就没问题（顺序固定下来了）。
    """

    return _winrt_loaded() and "onnxruntime" not in sys.modules


def _language_missing_warning(code: str) -> str:
    available = windows_ocr_languages()
    names = "、".join(available) if available else "未知"
    return (
        f"「{language_label(code)}」暂时认不了喵：没有随包的识别模型，系统里也没装对应的"
        f" OCR 语言包（本机可用：{names}）。装法：Windows 设置 → 时间和语言 → 语言和区域 → "
        f"添加「{language_label(code)}」→ 在它的语言选项里勾上「光学字符识别」，"
        "然后回来把「识别语言」选成它就好。"
    )


def create_engine(
    backend: str = "auto",
    language: str = "auto",
    upscale: float = 1.0,
    **options,
) -> OcrEngine:
    """创建 OCR 引擎。

    auto 表示质量优先：能用 RapidOCR 就用它（实测在真实游戏文本上比系统 OCR 准得多），
    没装再退回 Windows 自带 OCR。额外参数（例如 invert）会透传给具体后端。

   """

    wanted = normalize_ocr_language(language)
    if backend == "windows":
        try:
            return WindowsOcr(language=wanted, upscale=upscale, **options)
        except OcrUnavailable:
            raise
    if backend == "rapidocr":
        engine = RapidOcr(language=wanted, upscale=upscale, **options)
        if engine.ready:
            if wanted in WINDOWS_FIRST_LANGUAGES:
                # 用户点名要用 rapidocr：只能中英，先提醒一句
                engine.warning = _language_missing_warning(wanted)
            return engine
        engine._ensure_engine()
    if backend == "auto" and wanted in WINDOWS_FIRST_LANGUAGES:
        # 日语/韩语/俄语：中英模型认不了。
        # 顺序很重要：先试 rapidocr（有随包的日语模型就用它，质量也更好），
        # 不行再退回 Windows 语言包。**反过来（先 winrt 再 import onnxruntime）
        # 在部分机器上会原生崩溃**，所以绝不能先建 WindowsOcr。
        engine = RapidOcr(language=wanted, upscale=upscale, **options)
        if engine.ready:
            return engine
        windows = WindowsOcr(language=wanted, upscale=upscale, **options)
        if windows.ready:
            return windows
        windows.warning = _language_missing_warning(wanted)
        return windows
    if backend == "auto":
        if rapidocr_is_unsafe():
            # 本进程已经碰过 winrt：这时再去加载 rapidocr 会崩，直接用系统 OCR
            return WindowsOcr(language=wanted, upscale=upscale, **options)
        engine = RapidOcr(language=wanted, upscale=upscale, **options)
        if engine.ready:
            return engine
        return WindowsOcr(language=wanted, upscale=upscale, **options)
    raise OcrUnavailable(f"未知的 OCR 后端：{backend}")
