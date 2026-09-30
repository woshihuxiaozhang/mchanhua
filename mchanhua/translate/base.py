"""翻译层的通用接口与纯函数。"""

from __future__ import annotations

import re
from typing import Protocol, Sequence


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


CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]")
LETTER_PATTERN = re.compile(r"[A-Za-z]")


def contains_cjk(text: str) -> bool:
    """是否包含中日韩字符或全角标点。"""

    return bool(CJK_PATTERN.search(text))


def should_translate(text: str, min_letters: int = 2) -> bool:
    """判断一行是否需要送去翻译。

    规则：只要行里有像样数量的英文字母就翻，纯数字/符号行跳过。

    **为什么不再"见中文就跳过"**：OCR 经常把系统提示、截图通知和英文台词接到一行里
    （例如「You are one step closer to ... in已将截图保存为1.png」），
    以前遇到中文就整行不翻，结果半截英文永远翻不出来（用户反馈的 bug）。
    整行都已经汉化的行本来就没有字母，自然会被下面的字母数筛掉，不会白花请求。
    """

    stripped = text.strip()
    if not stripped:
        return False
    return len(LETTER_PATTERN.findall(stripped)) >= min_letters


def split_translatable(lines: Sequence[str]) -> list[tuple[int, str]]:
    """挑出需要翻译的行，返回 (行号, 文本) 列表；其余行由调用方原样保留。"""

    return [(index, line) for index, line in enumerate(lines) if should_translate(line)]
