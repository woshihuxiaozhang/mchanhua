"""OpenAI 兼容的翻译后端（DeepSeek / OpenAI / Kimi / 通义 / 智谱 / Ollama 通用）。"""

from __future__ import annotations

import json
import re
from typing import Any, Sequence

import httpx

from mchanhua.translate.base import TranslationError
from mchanhua.translate.placeholders import (
    missing_tokens,
    protect_lines,
    restore,
    strip_leftover_sentinels,
)

PROMPT_VERSION = "v4"

SYSTEM_PROMPT = """你是 Minecraft 模组与整合包的汉化译者，负责把游戏里的英文翻译成简体中文。

【语气与风格】（很重要）
- 译成**口语化、自然**的中文，像真人在说话，不要翻译腔、不要书面语、不要逐字硬译。
- **保留原句的情绪**：惊讶、紧张、警告、嘲讽、催促、感慨、恐惧都要译出来。
- 该用语气词就用（啊、吧、呢、喂、该死、天哪），该用感叹/疑问标点就用（！？……）。
- NPC 台词要短促有力；物品名、技能名保持简洁专业。

【格式规则】（必须严格遵守）
1. 输入是若干行文本，逐行翻译；**输出行数与输入完全一致、顺序一致**，不合并、不拆分、不增删、不加解释。
2. 只输出一个 JSON 对象：{"lines": [{"i": 0, "src": "原行", "dst": "译文"}, ...]}。
   i 是输入行号（从 0 开始），**必须与输入的序号一一对应**；src 原样抄回该行输入，用于核对。
3. 文本里的哨兵字符（\\ue000数字\\ue001）代表格式占位符（颜色码、%s 之类），必须原样保留在译文对应位置，不得翻译、删除或改动。
4. 已经是中文的行、没有实际词义的文本（纯数字、纯符号），把原文原样放进 dst。
5. **输入来自屏幕 OCR，可能有个别字符被认错**（l/I、o/0、w/u、rn/m 混淆，下划线丢失）。
   遇到明显是识别错误的单词，按最接近的常见英文词理解并翻译，不要原样返回英文；
   只有确定是人名、玩家 ID、命令或代码时才保留原文。
6. 使用 Minecraft 中文社区的通行译法。

【风格示例】
- "Durability" → "耐久"
- "Right-click to place" → "右键放置"
- "You shouldn't be here." → "你不该来这儿的。"
- "No way through, unless I stop that leak." → "该死，不把那个漏点堵上就过不去。"
- "What the hell is that?!" → "这到底是什么鬼东西？！"
- "You are one step closer to salvation." → "你离获救又近了一步。"
"""

GLOSSARY_PREFIX = "固定译法（必须遵守）："

CORRECTION_NOTE = """

补充说明：下面这些行是**屏幕 OCR 的结果，可能有字母被认错**（例如 HACHIHERY 其实是 MACHINERY、
TCHNOLOGY 其实是 TECHNOLOGY）。请推断最可能的英文原词并给出中文翻译，不要原样返回英文；
只有确认是人名、玩家 ID、命令或代码时才原样返回。
"""

LETTERS = re.compile(r"[A-Za-z]")
NON_WORD = re.compile(r"[0-9_./\\:@]")


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
        stripped = re.sub(r"```$", "", stripped).strip()
    return stripped


def _normalize_for_check(text: str) -> str:
    """核对 src 用的宽松比较：忽略大小写与空白差异。"""

    return " ".join(text.split()).casefold()


def build_system_prompt(glossary: dict[str, str] | None) -> str:
    if not glossary:
        return SYSTEM_PROMPT
    pairs = "；".join(f"{key}={value}" for key, value in sorted(glossary.items()))
    return f"{SYSTEM_PROMPT}\n\n{GLOSSARY_PREFIX}{pairs}"


def looks_like_word(text: str, min_letters: int = 3) -> bool:
    """判断一行是否像"本该翻出来的英文单词"（用来决定要不要二次纠错）。"""

    stripped = text.strip()
    if len(LETTERS.findall(stripped)) < min_letters:
        return False
    return NON_WORD.search(stripped) is None


class OpenAICompatibleTranslator:
    """任何 OpenAI 兼容服务都能用：只换 base_url 与模型名。"""

    name = "openai-compatible"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        timeout: float = 30.0,
        temperature: float = 0.0,
        glossary: dict[str, str] | None = None,
        client: httpx.Client | None = None,
        provider: str = "custom",
    ) -> None:
        if not base_url:
            raise TranslationError("未配置翻译服务的接口地址（base_url）")
        self.api_key = api_key or ""
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.provider = provider
        self.glossary = dict(glossary or {})
        self.prompt_version = PROMPT_VERSION
        self._client = client or httpx.Client(timeout=timeout)
        self.warnings: list[str] = []

    def _endpoint(self) -> str:
        if self.base_url.endswith(("/v1", "/v4")):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/v1/chat/completions"

    def translate_lines(self, lines: Sequence[str]) -> list[str]:
        if not lines:
            return []
        self.warnings = []
        sources = list(lines)
        result = self._request(sources)

        retry = [
            (index, source)
            for index, (source, target) in enumerate(zip(sources, result))
            if target.strip() == source.strip() and looks_like_word(source)
        ]
        if retry:
            self.warnings.append(f"{len(retry)} 行模型原样返回，已按 OCR 纠错再问一次")
            corrected = self._request([source for _, source in retry], correction=True)
            for (index, _source), target in zip(retry, corrected):
                if target.strip() and target.strip() != sources[index].strip():
                    result[index] = target
        return result

    def _request(self, lines: list[str], correction: bool = False) -> list[str]:
        protected, tables = protect_lines(lines)
        numbered = "\n".join(f"{index}. {text}" for index, text in enumerate(protected))
        system_prompt = build_system_prompt(self.glossary) + (CORRECTION_NOTE if correction else "")

        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"请翻译下面 {len(lines)} 行文本，返回 JSON：\n{numbered}",
                },
            ],
        }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = self._client.post(self._endpoint(), json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise TranslationError(f"请求翻译服务失败：{exc}") from exc

        if response.status_code != 200:
            raise TranslationError(f"翻译服务返回 {response.status_code}：{response.text[:300]}")

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise TranslationError(f"翻译服务响应结构异常：{response.text[:300]}") from exc

        return self._parse(content, lines, tables)

    def _parse(self, content: str, sources: list[str], tables: list[list[str]]) -> list[str]:
        try:
            parsed = json.loads(_strip_code_fence(content))
        except json.JSONDecodeError as exc:
            raise TranslationError(f"无法解析模型返回的 JSON：{content[:300]}") from exc

        items = parsed.get("lines") if isinstance(parsed, dict) else None
        if not isinstance(items, list):
            raise TranslationError(f"模型返回缺少 lines 字段：{content[:300]}")

        result = list(sources)
        seen: set[int] = set()
        mismatched: list[int] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            index = item.get("i")
            target = item.get("dst")
            if not isinstance(index, int) or not isinstance(target, str):
                continue
            if not 0 <= index < len(sources):
                continue
            declared = item.get("src")
            if isinstance(declared, str) and declared.strip():
                # 行号是主键；src 只用于核对，对不上就记警告（防止模型把行错位）
                if _normalize_for_check(declared) != _normalize_for_check(sources[index]):
                    mismatched.append(index)
            result[index] = strip_leftover_sentinels(restore(target, tables[index]))
            seen.add(index)
            lost = missing_tokens(target, tables[index])
            if lost:
                self.warnings.append(f"第 {index} 行丢失格式串：{lost[:3]}")

        missing = [i for i in range(len(sources)) if i not in seen]
        if missing:
            self.warnings.append(f"模型漏翻 {len(missing)} 行，已保留原文：{missing[:5]}")
        if mismatched:
            self.warnings.append(f"{len(mismatched)} 行的原文与行号对不上（已按行号对齐）：{mismatched[:5]}")
        return result
