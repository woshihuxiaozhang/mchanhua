"""翻译层的通用接口与纯函数。"""

from __future__ import annotations

import re
from typing import Protocol, Sequence

from mchanhua.detect import ARABIC, CJK, CYRILLIC, HANGUL, KANA, LATIN, THAI


class TranslationError(Exception):
    """翻译失败（网络、鉴权、响应格式等）。"""


class Translator(Protocol):
    name: str

    def translate_lines(self, lines: Sequence[str]) -> list[str]: ...


def set_area_hint(translator, hint: str) -> None:
    """给翻译器挂一条「这批文本来自什么区域」的提示。

    物品区与字幕区要的译法不一样（前者要短、用通用译名；后者要口语化），
    但又不能给 translate_lines 硬加参数——所有测试替身和后端都得跟着改。
    所以挂成一个可选属性：后端愿意用就用，不认识的直接忽略。
    """

    try:
        translator.area_hint = hint or ""
    except AttributeError:  # pragma: no cover - 极少数后端不允许挂属性
        pass


def set_extra_glossary(translator, glossary: dict[str, str] | None) -> None:
    """给翻译器挂一份"临时术语表"（自动学到的专有名词）。

    和用户自己的术语表分开：用户配置里的 [glossary] 优先级更高，
    这里挂上去的只是"这几天又见过的名字"，过期就自动没了。
    """

    try:
        translator.extra_glossary = dict(glossary or {})
    except AttributeError:  # pragma: no cover - 极少数后端不允许挂属性
        pass


CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]")
LETTER_PATTERN = re.compile(r"[A-Za-z]")

# 目标语言没配时按这个来（本项目默认翻成简体中文）
DEFAULT_TARGET_LANGUAGE = "简体中文"


def contains_cjk(text: str) -> bool:
    """是否包含中日韩字符或全角标点。"""

    return bool(CJK_PATTERN.search(text))


def _looks_like_target_language(target: str, kind: str) -> bool:
    """目标语言是不是这一类文字（中文 / 日语…）。"""

    target = (target or "").strip()
    if not target:
        return False
    lowered = target.lower()
    if kind == "zh":
        return (
            "中文" in target
            or "汉语" in target
            or "漢語" in target
            or lowered in ("zh", "zh-cn", "zh-tw", "chinese")
        )
    if kind == "ja":
        return (
            "日语" in target
            or "日文" in target
            or "日本語" in target
            or "日本" in target
            or lowered in ("ja", "jp", "japanese")
        )
    return lowered in (kind,)


def should_translate(
    text: str,
    target_language: str = DEFAULT_TARGET_LANGUAGE,
    min_letters: int = 2,
    batch_has_japanese: bool = False,
) -> bool:
    """判断一行是否需要送去翻译。

    按**文字种类**判断，不按"有没有英文字母"判断：

    - 有假名/谚文/西里尔/阿拉伯/泰文 → 不是目标语言（除非目标就是它），要翻；
    - 汉字：目标不是中文就翻；中英/中日混排（拉丁字母够多）也翻；
      只有汉字、目标又是中文时才跳过（整合包常常已经汉化，别把「磁石」再翻一遍），
      但同一批里只要出现过假名，就把这种"纯汉字行"当日语翻；
    - 纯数字/符号、字母太少的行跳过。

    （以前只认英文字母，结果日语假名行一个字母都没有，整行被跳过 → 日语完全翻不了。）
    """

    stripped = text.strip()
    if not stripped:
        return False

    latin = len(LATIN.findall(stripped))
    kana = bool(KANA.search(stripped))
    foreign = kana or bool(
        HANGUL.search(stripped)
        or CYRILLIC.search(stripped)
        or ARABIC.search(stripped)
        or THAI.search(stripped)
    )
    cjk = bool(CJK.search(stripped))

    if foreign:
        if kana and _looks_like_target_language(target_language, "ja"):
            return latin >= min_letters      # 目标就是日语：纯日语不用翻，混了外文才翻
        return True
    if cjk:
        if not _looks_like_target_language(target_language, "zh"):
            return True                      # 目标不是中文：汉字当然要翻
        if latin >= min_letters:
            return True                      # 中英混排：里面那截外文要翻
        return batch_has_japanese            # 只有汉字：批里有假名就当日语
    return latin >= min_letters


def split_translatable(
    lines: Sequence[str],
    target_language: str = DEFAULT_TARGET_LANGUAGE,
) -> list[tuple[int, str]]:
    """挑出需要翻译的行，返回 (行号, 文本) 列表；其余行由调用方原样保留。"""

    batch_has_japanese = any(KANA.search(line or "") for line in lines)
    return [
        (index, line)
        for index, line in enumerate(lines)
        if should_translate(
            line, target_language, batch_has_japanese=batch_has_japanese
        )
    ]
