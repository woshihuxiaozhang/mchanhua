"""翻译层的通用接口与纯函数。"""

from __future__ import annotations

import re
from typing import Protocol, Sequence


class TranslationError(Exception):
    """翻译失败（网络、鉴权、响应格式等）。"""


class Translator(Protocol):
    name: str

    def translate_lines(self, lines: Sequence[str]) -> list[str]: ...


CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]")
LETTER_PATTERN = re.compile(r"[A-Za-z]")


def contains_cjk(text: str) -> bool:
    """是否包含中日韩字符或全角标点。"""

    return bool(CJK_PATTERN.search(text))


def should_translate(text: str, min_letters: int = 2) -> bool:
    """判断一行是否需要送去翻译。

    规则：已经含中文的行原样保留（整合包往往已有部分汉化，避免"磁石"被再翻一次），
    纯数字/符号行没有翻译价值，字母太少的行也跳过。
    """

    stripped = text.strip()
    if not stripped:
        return False
    if contains_cjk(stripped):
        return False
    return len(LETTER_PATTERN.findall(stripped)) >= min_letters


def split_translatable(lines: Sequence[str]) -> list[tuple[int, str]]:
    """挑出需要翻译的行，返回 (行号, 文本) 列表；其余行由调用方原样保留。"""

    return [(index, line) for index, line in enumerate(lines) if should_translate(line)]
