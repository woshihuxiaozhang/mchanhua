"""翻译前的格式串保护。

Minecraft 文本里大量存在 § 颜色码、%s / %1$s 占位符、{0}、反斜杠转义等。
直接送去翻译很容易被模型吃掉或改坏，所以先替换成哨兵，翻完再还原。
"""

from __future__ import annotations

import re

SENTINEL_PREFIX = "\ue000"
SENTINEL_SUFFIX = "\ue001"

FORMAT_PATTERNS = [
    re.compile(r"§[0-9a-fk-orA-FK-OR]"),       # 颜色/格式码
    re.compile(r"%\d+\$[sd]"),                  # %1$s
    re.compile(r"%[sd]"),                       # %s %d
    re.compile(r"\{\d+\}"),                     # {0}
    re.compile(r"\$\{[^}]*\}"),                 # ${...}
    re.compile(r"\\n|\\t"),                     # 转义换行
]


def protect(text: str) -> tuple[str, list[str]]:
    """把格式串替换成哨兵，返回 (处理后文本, 还原表)。"""

    tokens: list[str] = []

    def replace(match: re.Match[str]) -> str:
        tokens.append(match.group(0))
        return f"{SENTINEL_PREFIX}{len(tokens) - 1}{SENTINEL_SUFFIX}"

    result = text
    for pattern in FORMAT_PATTERNS:
        result = pattern.sub(replace, result)
    return result, tokens


def restore(text: str, tokens: list[str]) -> str:
    """把哨兵还原成原始格式串。"""

    def replace(match: re.Match[str]) -> str:
        index = int(match.group(1))
        if 0 <= index < len(tokens):
            return tokens[index]
        return match.group(0)

    pattern = re.compile(rf"{SENTINEL_PREFIX}(\d+){SENTINEL_SUFFIX}")
    return pattern.sub(replace, text)


def protect_lines(lines: list[str]) -> tuple[list[str], list[list[str]]]:
    protected: list[str] = []
    tables: list[list[str]] = []
    for line in lines:
        masked, tokens = protect(line)
        protected.append(masked)
        tables.append(tokens)
    return protected, tables


def missing_tokens(text: str, tokens: list[str]) -> list[str]:
    """检查译文里哪些格式串丢了（模型偶尔会吃掉哨兵）。"""

    return [token for token in tokens if token not in text]


def strip_leftover_sentinels(text: str) -> str:
    """清掉译文里没还原成功的哨兵，避免把控制字符带到界面上。"""

    pattern = re.compile(rf"{SENTINEL_PREFIX}\d+{SENTINEL_SUFFIX}")
    return pattern.sub("", text)
