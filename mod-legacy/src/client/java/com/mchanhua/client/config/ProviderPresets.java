package com.mchanhua.client.config;

import java.util.ArrayList;
import java.util.List;

/**
 * 预设服务商与模型清单——和桌面版 {@code mchanhua/translate/providers.py} 保持一致，
 * 两边填的东西能互相照搬。
 *
 * 为什么要按服务商分组：模型名是"绑在服务商身上"的。拿 deepseek-chat 去请求
 * api.moonshot.cn 只会返回 404/模型不存在，所以设置界面里选服务商时会顺带把
 * 接口地址和默认模型一起换掉。
 */
public final class ProviderPresets {

	/** 一个服务商：显示名 + 接口地址 + 默认模型 + 该服务商下可选的模型。 */
	public static final class Preset {
		public final String key;
		public final String label;
		public final String baseUrl;
		public final List<String> models;

		Preset(String key, String label, String baseUrl, String... models) {
			this.key = key;
			this.label = label;
			this.baseUrl = baseUrl;
			this.models = List.of(models);
		}

		public String defaultModel() {
			return models.isEmpty() ? "" : models.get(0);
		}

		/** 本地服务不用 key（Ollama 之类）。 */
		public boolean needsKey() {
			return !isLocal(baseUrl);
		}

		@Override
		public String toString() {
			return label;
		}
	}

	private static final String CUSTOM_KEY = "custom";

	private static final List<Preset> PRESETS = List.of(
			new Preset("deepseek", "DeepSeek（推荐）", "https://api.deepseek.com",
					"deepseek-chat", "deepseek-reasoner"),
			new Preset("openai", "OpenAI", "https://api.openai.com/v1",
					"gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"),
			new Preset("moonshot", "月之暗面 Kimi", "https://api.moonshot.cn/v1",
					"moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k", "kimi-k2-0905-preview"),
			new Preset("dashscope", "通义千问（百炼）", "https://dashscope.aliyuncs.com/compatible-mode/v1",
					"qwen-plus", "qwen-max", "qwen-turbo", "qwen-long"),
			new Preset("zhipu", "智谱 GLM", "https://open.bigmodel.cn/api/paas/v4",
					"glm-4-flash", "glm-4-air", "glm-4-plus"),
			new Preset("siliconflow", "硅基流动 SiliconFlow", "https://api.siliconflow.cn/v1",
					"Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3"),
			new Preset("ollama", "本地 Ollama（不用 key）", "http://localhost:11434/v1",
					"qwen2.5:7b", "llama3.1:8b", "deepseek-r1:7b"));

	/** 认不出来的地址就走这个：不预设模型，让用户自己填。 */
	private static final Preset CUSTOM = new Preset(CUSTOM_KEY, "自定义（OpenAI 兼容）", "");

	private ProviderPresets() {
	}

	public static List<Preset> all() {
		List<Preset> list = new ArrayList<>(PRESETS);
		list.add(CUSTOM);
		return List.copyOf(list);
	}

	/** 认不出来的预设（自定义）。 */
	public static Preset custom() {
		return CUSTOM;
	}

	public static boolean isCustom(Preset preset) {
		return preset == null || CUSTOM_KEY.equals(preset.key);
	}

	/** 按接口地址反推是哪家；认不出来返回自定义。 */
	public static Preset guess(String baseUrl) {
		String url = baseUrl == null ? "" : baseUrl.trim().toLowerCase();
		if (url.isEmpty()) {
			return CUSTOM;
		}
		for (Preset preset : PRESETS) {
			String base = preset.baseUrl.toLowerCase();
			while (base.endsWith("/")) {
				base = base.substring(0, base.length() - 1);
			}
			if (!base.isEmpty() && (url.equals(base) || url.startsWith(base + "/") || url.contains(base))) {
				return preset;
			}
		}
		if (isLocal(url)) {
			return PRESETS.get(PRESETS.size() - 1);   // 换了个本地端口也当成 Ollama
		}
		return CUSTOM;
	}

	/** 这家可选哪些模型（自定义返回空列表）。 */
	public static List<String> modelsFor(String baseUrl) {
		return guess(baseUrl).models;
	}

	/** 界面按钮上显示的服务商名。 */
	public static String labelOf(String baseUrl) {
		return guess(baseUrl).label;
	}

	/** 这个地址要不要填 key（本地服务不用）。 */
	public static boolean needsKey(String baseUrl) {
		return guess(baseUrl).needsKey();
	}

	public static boolean isLocal(String baseUrl) {
		String url = baseUrl == null ? "" : baseUrl.toLowerCase();
		return url.contains("localhost") || url.contains("127.0.0.1") || url.contains("://0.0.0.0");
	}

	/** 循环取下一个（列表为空或找不到当前项就回第一个）。 */
	public static String next(List<String> values, String current) {
		if (values == null || values.isEmpty()) {
			return current;
		}
		int index = values.indexOf(current);
		return values.get((index + 1) % values.size());
	}

	/** 顺次切到下一个服务商（自定义不参与循环，想用它点「手填」）。 */
	public static Preset nextPreset(String baseUrl) {
		Preset current = guess(baseUrl);
		int index = -1;
		for (int i = 0; i < PRESETS.size(); i++) {
			if (PRESETS.get(i).key.equals(current.key)) {
				index = i;
			}
		}
		return PRESETS.get((index + 1) % PRESETS.size());
	}
}
