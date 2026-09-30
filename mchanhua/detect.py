"""语言判定（纯函数，不联网、不花额度）。

用途：
1. 记日志/状态栏，让人知道这次识别到的是什么语言；
2. 目标语言为"自动"时，判断要不要跳过（识别到的文本已经是目标语言就不翻译）；
3. 将来给 OCR 选引擎语言时也用得上。

只按字符集判断，够用且快——真正精确的语种判断交给翻译模型自己（提示词里要求它先判断再翻）。
"""

from __future__ import annotations

import re

CJK = re.compile(r"[\u4e00-\u9fff]")            # 汉字（中/日共用）
KANA = re.compile(r"[\u3040-\u30ff]")            # 平假名 / 片假名 → 日语
HANGUL = re.compile(r"[\uac00-\ud7af\u1100-\u11ff]")   # 谚文 → 韩语
CYRILLIC = re.compile(r"[\u0400-\u04ff]")        # 西里尔 → 俄语等
ARABIC = re.compile(r"[\u0600-\u06ff]")
THAI = re.compile(r"[\u0e00-\u0e7f]")
LATIN = re.compile(r"[A-Za-z]")

# 返回值统一用这种短标签，配置里可以直接写
NAMES = {
    "ja": "日语",
    "ko": "韩语",
    "zh": "中文",
    "ru": "俄语",
    "ar": "阿拉伯语",
    "th": "泰语",
    "en": "英语",
    "": "未知",
}


def guess_language(text: str) -> str:
    """返回语言代码：ja / ko / zh / ru / ar / th / en / ""（判不出来）。"""

    sample = text or ""
    if not sample.strip():
        return ""
    if KANA.search(sample):
        return "ja"                      # 有假名一定是日语（汉字多也可能是日文）
    if HANGUL.search(sample):
        return "ko"
    if CYRILLIC.search(sample):
        return "ru"
    if ARABIC.search(sample):
        return "ar"
    if THAI.search(sample):
        return "th"
    cjk = len(CJK.findall(sample))
    latin = len(LATIN.findall(sample))
    if cjk and cjk >= latin:
        return "zh"
    if latin:
        return "en"
    if cjk:
        return "zh"
    return ""


def language_name(code: str) -> str:
    return NAMES.get(code or "", "未知")


def is_already_target(text: str, target_language: str) -> bool:
    """粗判这段文字是不是已经是目标语言（用于"别把中文再翻一遍"）。"""

    target = (target_language or "").strip()
    if not target:
        return False
    code = guess_language(text)
    if not code:
        return False
    if "中文" in target or "汉语" in target:
        # 简体/繁体都算中文：已经是中文就不需要再翻
        return code == "zh"
    return language_name(code) in target or code in target.lower()
