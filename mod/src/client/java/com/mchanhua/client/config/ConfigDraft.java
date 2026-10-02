package com.mchanhua.client.config;

import java.util.ArrayList;
import java.util.List;

/**
 * 设置界面的"草稿"：把输入框里的字符串收拢、检查，再写回 {@link MchanhuaConfig}。
 *
 * 单独抽出来是为了能脱离游戏跑测试（见 ConfigDraftSelfTest）：
 * 数字填错、地址留空、key 前后带空格，这些都不该让游戏出问题，
 * 也不该悄悄把配置写成废值——所以出过什么"兜底"都会以人话返回给界面显示。
 */
public final class ConfigDraft {
	public static final String DEFAULT_BASE_URL = "https://api.deepseek.com";
	public static final String DEFAULT_MODEL = "deepseek-chat";
	public static final String DEFAULT_TARGET_LANGUAGE = "简体中文";

	public static final int AUTO_HIDE_MIN = 0;
	public static final int AUTO_HIDE_MAX = 3600;
	public static final int TIMEOUT_MIN = 5;
	public static final int TIMEOUT_MAX = 300;

	public String apiKey = "";
	public String baseUrl = DEFAULT_BASE_URL;
	public String model = DEFAULT_MODEL;
	public String targetLanguage = DEFAULT_TARGET_LANGUAGE;
	public String autoHideSeconds = "6";
	public String timeoutSeconds = "30";
	public boolean translateTooltips = true;
	public boolean translateChat = true;
	public boolean hudVisible = true;
	public boolean showOriginal = true;

	/** 从现有配置拷一份到草稿（界面上看到的就是当前生效的值）。 */
	public static ConfigDraft from(MchanhuaConfig config) {
		ConfigDraft draft = new ConfigDraft();
		if (config == null) {
			return draft;
		}
		draft.apiKey = config.apiKey == null ? "" : config.apiKey;
		draft.baseUrl = orDefault(config.baseUrl, DEFAULT_BASE_URL);
		draft.model = orDefault(config.model, DEFAULT_MODEL);
		draft.targetLanguage = orDefault(config.targetLanguage, DEFAULT_TARGET_LANGUAGE);
		draft.autoHideSeconds = String.valueOf(config.hudAutoHideSeconds);
		draft.timeoutSeconds = String.valueOf(config.requestTimeoutSeconds);
		draft.translateTooltips = config.translateTooltips;
		draft.translateChat = config.translateChat;
		draft.hudVisible = config.hudVisible;
		draft.showOriginal = config.showOriginal;
		return draft;
	}

	/**
	 * 落地到配置。返回"兜底说明"（正常保存返回空列表）：
	 * 例如「自动隐藏秒数「abc」不是数字，已按 6 处理」，界面直接把这几句显示给用户。
	 */
	public List<String> applyTo(MchanhuaConfig config) {
		List<String> notes = new ArrayList<>();
		if (config == null) {
			return notes;
		}
		config.apiKey = apiKey == null ? "" : apiKey.trim();

		if (isBlank(baseUrl)) {
			config.baseUrl = DEFAULT_BASE_URL;
			notes.add("接口地址是空的，已用默认 " + DEFAULT_BASE_URL);
		} else {
			config.baseUrl = baseUrl.trim();
		}
		if (isBlank(model)) {
			config.model = DEFAULT_MODEL;
			notes.add("模型是空的，已用默认 " + DEFAULT_MODEL);
		} else {
			config.model = model.trim();
		}
		if (isBlank(targetLanguage)) {
			config.targetLanguage = DEFAULT_TARGET_LANGUAGE;
			notes.add("目标语言是空的，已用默认 " + DEFAULT_TARGET_LANGUAGE);
		} else {
			config.targetLanguage = targetLanguage.trim();
		}

		config.hudAutoHideSeconds = number(autoHideSeconds, 6, AUTO_HIDE_MIN, AUTO_HIDE_MAX,
				"自动隐藏秒数", notes);
		config.requestTimeoutSeconds = number(timeoutSeconds, 30, TIMEOUT_MIN, TIMEOUT_MAX,
				"请求超时秒数", notes);

		config.translateTooltips = translateTooltips;
		config.translateChat = translateChat;
		config.hudVisible = hudVisible;
		config.showOriginal = showOriginal;

		if (!config.ready()) {
			notes.add("还没填 API Key，填上才能翻译");
		}
		return notes;
	}

	/** key 在界面上只露头尾，避免录屏/截图时整串泄漏。 */
	public static String maskKey(String key) {
		String text = key == null ? "" : key.trim();
		if (text.isEmpty()) {
			return "（还没填）";
		}
		if (text.length() <= 8) {
			return "•".repeat(text.length());
		}
		return text.substring(0, 5) + "…" + text.substring(text.length() - 4);
	}

	public String maskedKey() {
		return maskKey(apiKey);
	}

	/** 空着就用默认；数字填错或超出范围就兜底，并把原因记进 notes。 */
	public static int number(String text, int fallback, int min, int max,
			String label, List<String> notes) {
		String trimmed = text == null ? "" : text.trim();
		if (trimmed.isEmpty()) {
			return fallback;
		}
		int value;
		try {
			value = Integer.parseInt(trimmed);
		} catch (NumberFormatException e) {
			notes.add(label + "「" + trimmed + "」不是数字，已按 " + fallback + " 处理");
			return fallback;
		}
		if (value < min || value > max) {
			int clamped = Math.max(min, Math.min(max, value));
			notes.add(label + " " + value + " 超出 " + min + "-" + max + "，已按 " + clamped + " 处理");
			return clamped;
		}
		return value;
	}

	public static String orDefault(String value, String fallback) {
		return isBlank(value) ? fallback : value.trim();
	}

	private static boolean isBlank(String value) {
		return value == null || value.trim().isEmpty();
	}
}
