"""DeepSeek 翻译后端（OpenAI 兼容接口）。"""

from __future__ import annotations

import json
import re
from typing import Any, Sequence

import httpx

from mchanhua.translate.base import TranslationError
from mchanhua.translate.placeholders import missing_tokens, protect_lines, restore

PROMPT_VERSION = "v2"

SYSTEM_PROMPT = """你是 Minecraft 模组与整合包的中英翻译译者，负责把游戏界面文本翻译成简体中文。

严格遵守以下规则：
1. 输入是若干行独立文本，逐行翻译，**输出行数与输入完全一致**，不合并、不拆分、不增删行、不添加解释。
2. 只输出一个 JSON 对象，格式为：{"lines": [{"i": 0, "dst": "译文"}, ...]}，其中 i 是输入行号（从 0 开始）。
3. 文本中的哨兵字符（\\ue000数字\\ue001）代表格式占位符（颜色码、%s 之类），必须原样保留在译文对应位置，不得翻译、删除或改动。
4. 已经是中文、或没有实际词义的文本（纯数字、纯符号），把原文原样放进 dst。
5. 使用 Minecraft 中文社区的通行译法，保持简洁，不要加句号之外的额外标点。
6. **输入来自屏幕 OCR，可能有个别字符识别错误**（例如 l/I、o/0、w/u、rn/m 混淆，下划线丢失）。
   遇到明显是识别错误的英文单词时，请按最接近的常见英文单词理解并翻译（例如 "Suitch" 应理解为 "Switch"），
   不要原样返回；只有确定是无法翻译的标识符（命令、代码、玩家 ID）才保留原文。

译文风格示例：
- "Durability" → "耐久"
- "Right-click to place" → "右键放置"
- "You are one step closer to salvation." → "你离获救又近了一步。"
"""

GLOSSARY_PREFIX = "固定译法（必须遵守）："


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
        stripped = re.sub(r"```$", "", stripped).strip()
    return stripped


def build_system_prompt(glossary: dict[str, str] | None) -> str:
    if not glossary:
        return SYSTEM_PROMPT
    pairs = "；".join(f"{key}={value}" for key, value in sorted(glossary.items()))
    return f"{SYSTEM_PROMPT}\n\n{GLOSSARY_PREFIX}{pairs}"


class DeepSeekTranslator:
    name = "deepseek"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        timeout: float = 30.0,
        temperature: float = 0.0,
        glossary: dict[str, str] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise TranslationError(
                "未配置 DeepSeek API key。请在 %APPDATA%\\mchanhua\\config.toml 的 "
                "[translate] api_key 里填写，或设置环境变量 MCHANHUA_API_KEY。"
            )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.glossary = dict(glossary or {})
        self.prompt_version = PROMPT_VERSION
        self._client = client or httpx.Client(timeout=timeout)
        self.warnings: list[str] = []

    def _endpoint(self) -> str:
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/v1/chat/completions"

    def translate_lines(self, lines: Sequence[str]) -> list[str]:
        if not lines:
            return []
        self.warnings = []
        protected, tables = protect_lines(list(lines))
        numbered = "\n".join(f"{index}. {text}" for index, text in enumerate(protected))

        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": build_system_prompt(self.glossary)},
                {
                    "role": "user",
                    "content": f"请翻译下面 {len(lines)} 行文本，返回 JSON：\n{numbered}",
                },
            ],
        }

        try:
            response = self._client.post(
                self._endpoint(),
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        except httpx.HTTPError as exc:
            raise TranslationError(f"请求 DeepSeek 失败：{exc}") from exc

        if response.status_code != 200:
            raise TranslationError(
                f"DeepSeek 返回 {response.status_code}：{response.text[:300]}"
            )

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise TranslationError(f"DeepSeek 响应结构异常：{response.text[:300]}") from exc

        return self._parse(content, list(lines), tables)

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
        for item in items:
            if not isinstance(item, dict):
                continue
            index = item.get("i")
            target = item.get("dst")
            if not isinstance(index, int) or not isinstance(target, str):
                continue
            if not 0 <= index < len(sources):
                continue
            result[index] = restore(target, tables[index])
            seen.add(index)
            lost = missing_tokens(target, tables[index])
            if lost:
                self.warnings.append(f"第 {index} 行丢失格式串：{lost[:3]}")

        missing = [i for i in range(len(sources)) if i not in seen]
        if missing:
            self.warnings.append(f"模型漏翻 {len(missing)} 行，已保留原文：{missing[:5]}")
        return result
