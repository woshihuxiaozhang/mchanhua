"""OpenAI 兼容的翻译后端（DeepSeek / OpenAI / Kimi / 通义 / 智谱 / Ollama 通用）。"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Sequence

import httpx

from mchanhua.translate.base import TranslationError
from mchanhua.logging_setup import get_logger
from mchanhua.translate.placeholders import (
    missing_tokens,
    protect_lines,
    restore,
    strip_leftover_sentinels,
)

PROMPT_VERSION = "v6"

# 提示词模板：语言对由配置决定（源语言默认"自动识别"），所以这里用占位符
SYSTEM_PROMPT = """你是游戏文本的翻译，负责把屏幕上的 [[source]]翻译成[[target]]。

【语气与风格】（很重要）
- 译成**口语化、自然**的[[target]]，像真人在说话，不要翻译腔、不要书面语、不要逐字硬译。
- **保留原句的情绪**：惊讶、紧张、警告、嘲讽、催促、感慨、恐惧都要译出来。
- 该用语气词就用（啊、吧、呢、喂……），该用感叹/疑问标点就用（？！……）。
- NPC 台词要短促有力；物品名、技能名保持简洁专业。

【格式规则】（必须严格遵守）
1. 输入是若干行文本，逐行翻译；**输出行数与输入完全一致、顺序一致**，不合并、不拆分、不增删、不加解释。
2. 只输出一个 JSON 对象：{"lines": [{"i": 0, "src": "原行", "dst": "译文"}, ...]}。
   i 是输入行号（从 0 开始），**必须与输入的序号一一对应**；src 原样抄回该行输入，用于核对。
3. 文本里的哨兵字符（\\ue000数字\\ue001）代表格式占位符（颜色码、%s 之类），必须原样保留在译文对应位置，不得翻译、删除或改动。
4. 已经是[[target]]的行、没有实际词义的文本（纯数字、纯符号），把原文原样放进 dst。
5. **输入来自屏幕 OCR，可能有个别字符被认错**（l/I、o/0、w/u、rn/m 混淆，下划线丢失，汉字/假名也可能认错）。
   遇到明显是识别错误的单词，按最接近的常见英文词理解并翻译，不要原样返回英文；
   只有确定是人名、玩家 ID、命令或代码时才保留原文。
6. 如果内容是 Minecraft 相关（物品、方块、生物、界面），使用[[target]]社区里通行的译法。
7. 如果下面给了【整段整理】要求，就再补一个 paragraph 字段（整段通顺译文）。

【风格示例】
- 语气要像真人在说话，保留情绪；不要逐字硬译，也不要把语气词都抹掉。
"""

# 源语言"自动识别"时插进提示词的一段说明
AUTO_SOURCE_NOTE = """输入语言**不固定**：可能是英语、日语、韩语、俄语等任何一种，
请你**先自己判断每段文字是什么语言**，再翻译；同一批里混着多种语言也要各自正确处理。
"""

TARGET_LANGUAGE_DEFAULT = "简体中文"

GLOSSARY_PREFIX = "固定译法（必须遵守）："

# 追加在提示词末尾：让模型额外给一段"整理通顺"的整段译文
HUMANIZE_NOTE = """

【整段整理】（paragraph 字段）
- 屏幕 OCR 经常把一句话切成好几行，或者混进无关的碎片。请把它们**整理成自然通顺的整段中文**：
  被切断的句子接回去、语序按中文习惯调整、明显的 OCR 噪音（乱码、重复片段）可以去掉。
- **只能整理，不许加戏**：不得增加原文没有的信息，也不能漏掉有意义的内容。
- 如果这些行本来就是清单式的短条目（物品名、按钮名），保持简短罗列就好，别硬凑成句子。
- 输出仍是同一个 JSON 对象，多一个 paragraph 字段：{"paragraph": "……", "lines": [...]}。
"""

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


def build_system_prompt(
    glossary: dict[str, str] | None,
    target_language: str = TARGET_LANGUAGE_DEFAULT,
    source_language: str = "auto",
) -> str:
    """按当前语言设置生成系统提示词：源语言默认"自动识别"，只固定目标语言。"""

    target = (target_language or TARGET_LANGUAGE_DEFAULT).strip()
    source = (source_language or "auto").strip()
    if source.lower() in ("auto", "", "自动", "自动识别"):
        source_hint = ""
    else:
        source_hint = f"{source}"
    # 用 replace 而不是 str.format：提示词里有的是字面花括号（JSON 示例），
    # format 会把它们当占位符直接报 KeyError
    prompt = SYSTEM_PROMPT.replace("[[source]]", source_hint).replace("[[target]]", target)
    if not source_hint:
        prompt = f"{prompt}\n【源语言】\n{AUTO_SOURCE_NOTE}"
    if not glossary:
        return prompt
    pairs = "；".join(f"{key}={value}" for key, value in sorted(glossary.items()))
    return f"{prompt}\n\n{GLOSSARY_PREFIX}{pairs}"


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
        humanize: bool = True,
        target_language: str = TARGET_LANGUAGE_DEFAULT,
        source_language: str = "auto",
        retry_attempts: int = 3,
        retry_backoff: float = 0.6,
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
        self.humanize = bool(humanize)
        self.target_language = (target_language or TARGET_LANGUAGE_DEFAULT).strip()
        self.source_language = (source_language or "auto").strip()
        self.last_paragraph = ""          # 上一步"整理成段"的结果（没有就是空）
        self._client = client or httpx.Client(timeout=timeout)
        self.retry_attempts = max(1, int(retry_attempts))
        self.retry_backoff = max(0.0, float(retry_backoff))
        self.warnings: list[str] = []

    def _endpoint(self) -> str:
        if self.base_url.endswith(("/v1", "/v4")):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/v1/chat/completions"

    def translate_lines(self, lines: Sequence[str]) -> list[str]:
        if not lines:
            return []
        self.warnings = []
        self.last_paragraph = ""
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
        system_prompt = build_system_prompt(
            self.glossary, self.target_language, self.source_language
        )
        # 区域类型提示（物品区 / 字幕区…）：由 pipeline 按区域挂上来，没有就不加
        area_hint = (getattr(self, "area_hint", "") or "").strip()
        if area_hint:
            system_prompt += f"\n\n【这一批文本的特点】\n{area_hint}"
        if self.humanize and not correction:
            system_prompt += HUMANIZE_NOTE
        if correction:
            system_prompt += CORRECTION_NOTE

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
            response = self._post_with_retry(payload, headers)
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

    def _post_with_retry(self, payload: dict[str, Any], headers: dict[str, str]):
        """网络抖动（连接失败、超时）时自动重试几次——同类工具都是这么做的。

        这类错误通常几秒内就恢复，直接抛给用户等于白按一次热键。
        服务端明确返回的状态码（4xx/5xx）不算网络抖动，交给上层报错。
        """

        last_error: Exception | None = None
        for attempt in range(self.retry_attempts):
            try:
                return self._client.post(self._endpoint(), json=payload, headers=headers)
            except httpx.TransportError as exc:      # 含连接失败与超时
                last_error = exc
                if attempt + 1 >= self.retry_attempts:
                    break
                delay = self.retry_backoff * (2 ** attempt)
                self.warnings.append(f"网络异常，{delay:.1f} 秒后重试：{exc}")
                get_logger().warning(
                    "翻译请求失败，%.1f 秒后重试（第 %d 次）：%s", delay, attempt + 1, exc
                )
                time.sleep(delay)
        assert last_error is not None
        raise last_error

    def _parse(self, content: str, sources: list[str], tables: list[list[str]]) -> list[str]:
        try:
            parsed = json.loads(_strip_code_fence(content))
        except json.JSONDecodeError as exc:
            raise TranslationError(f"无法解析模型返回的 JSON：{content[:300]}") from exc

        items = parsed.get("lines") if isinstance(parsed, dict) else None
        if not isinstance(items, list):
            raise TranslationError(f"模型返回缺少 lines 字段：{content[:300]}")

        if isinstance(parsed, dict):
            paragraph = parsed.get("paragraph")
            if isinstance(paragraph, str) and paragraph.strip():
                self.last_paragraph = paragraph.strip()      # 模型顺手给的"整理成段"版本

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
