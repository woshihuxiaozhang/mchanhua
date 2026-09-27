"""可选的翻译服务（都是 OpenAI 兼容接口）。

DeepSeek、OpenAI、Kimi、通义、智谱、硅基流动、Ollama 都用同一套 chat/completions 协议，
区别只在 base_url 与模型名，所以一个实现就能全支持。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderPreset:
    key: str
    label: str
    base_url: str
    model: str
    needs_key: bool = True
    note: str = ""


PRESETS: tuple[ProviderPreset, ...] = (
    ProviderPreset("deepseek", "DeepSeek（推荐）", "https://api.deepseek.com", "deepseek-chat"),
    ProviderPreset("openai", "OpenAI", "https://api.openai.com/v1", "gpt-4o-mini"),
    ProviderPreset("moonshot", "月之暗面 Kimi", "https://api.moonshot.cn/v1", "moonshot-v1-8k"),
    ProviderPreset(
        "dashscope",
        "通义千问（阿里云）",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "qwen-plus",
    ),
    ProviderPreset("zhipu", "智谱 GLM", "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash"),
    ProviderPreset(
        "siliconflow",
        "硅基流动 SiliconFlow",
        "https://api.siliconflow.cn/v1",
        "Qwen/Qwen2.5-7B-Instruct",
    ),
    ProviderPreset(
        "ollama",
        "Ollama 本地模型（免 key）",
        "http://localhost:11434/v1",
        "qwen2.5:7b",
        needs_key=False,
        note="需要先在本机跑起 Ollama",
    ),
    ProviderPreset("custom", "自定义（OpenAI 兼容）", "", "", note="自己填接口地址与模型名"),
)

PRESET_BY_KEY = {preset.key: preset for preset in PRESETS}


def find_preset(key: str | None) -> ProviderPreset | None:
    return PRESET_BY_KEY.get((key or "").strip().lower())


def guess_provider(base_url: str, model: str = "") -> str:
    """根据 base_url 反推是哪家服务，用于设置界面回显。"""

    url = (base_url or "").lower()
    for preset in PRESETS:
        if preset.key != "custom" and preset.base_url and preset.base_url.lower().rstrip("/") in url:
            return preset.key
    if "localhost" in url or "127.0.0.1" in url:
        return "ollama"
    return "custom"
