package com.mchanhua.client.config;

import java.util.ArrayList;
import java.util.List;

/**
 * 设置界面的配置逻辑自测：不进游戏、不联网，只跑断言。
 * 用法：.\gradlew.bat configtest
 *
 * 重点覆盖"手滑"：数字填成字母、地址留空、key 前后带空格、秒数离谱。
 */
public final class ConfigDraftSelfTest {

	private static int passed = 0;
	private static int failed = 0;

	public static void main(String[] args) {
		roundTripKeepsValues();
		blankStringsFallBackToDefaults();
		badNumbersFallBackWithNote();
		numbersAreClampedWithNote();
		emptyNumbersSilentlyUseDefault();
		apiKeyIsTrimmed();
		maskHidesTheMiddleOfTheKey();
		missingKeyIsReported();
		switchesAreCopied();

		System.out.println();
		System.out.println("[config-draft] 通过 " + passed + "，失败 " + failed);
		if (failed > 0) {
			System.exit(1);
		}
	}

	private static void roundTripKeepsValues() {
		MchanhuaConfig source = new MchanhuaConfig();
		source.apiKey = "sk-abcdefghijklmnop";
		source.baseUrl = "https://api.moonshot.cn/v1";
		source.model = "kimi-k2";
		source.targetLanguage = "繁體中文";
		source.hudAutoHideSeconds = 12;
		source.requestTimeoutSeconds = 45;
		source.translateTooltips = false;
		source.translateChat = true;
		source.hudVisible = false;
		source.showOriginal = false;

		MchanhuaConfig target = new MchanhuaConfig();
		List<String> notes = ConfigDraft.from(source).applyTo(target);

		check(notes.isEmpty(), "完整配置往返不该有兜底提示：" + notes);
		check("sk-abcdefghijklmnop".equals(target.apiKey), "apiKey 要一致");
		check("https://api.moonshot.cn/v1".equals(target.baseUrl), "baseUrl 要一致");
		check("kimi-k2".equals(target.model), "model 要一致");
		check("繁體中文".equals(target.targetLanguage), "targetLanguage 要一致");
		check(target.hudAutoHideSeconds == 12, "自动隐藏秒数要一致");
		check(target.requestTimeoutSeconds == 45, "超时秒数要一致");
		check(!target.translateTooltips && target.translateChat, "开关要一致");
		check(!target.hudVisible && !target.showOriginal, "显示开关要一致");
	}

	private static void blankStringsFallBackToDefaults() {
		MchanhuaConfig target = new MchanhuaConfig();
		ConfigDraft draft = new ConfigDraft();
		draft.apiKey = "sk-abcdefghijklmnop";
		draft.baseUrl = "   ";
		draft.model = "";
		draft.targetLanguage = "  ";
		List<String> notes = draft.applyTo(target);

		check(ConfigDraft.DEFAULT_BASE_URL.equals(target.baseUrl), "空地址要用默认地址");
		check(ConfigDraft.DEFAULT_MODEL.equals(target.model), "空模型要用默认模型");
		check(ConfigDraft.DEFAULT_TARGET_LANGUAGE.equals(target.targetLanguage), "空语言要用默认语言");
		check(notes.size() == 3, "三条兜底提示都要说清楚，实际 " + notes);
		check(notes.stream().anyMatch(n -> n.contains("接口地址")), "要有接口地址的提示");
	}

	private static void badNumbersFallBackWithNote() {
		MchanhuaConfig target = new MchanhuaConfig();
		ConfigDraft draft = new ConfigDraft();
		draft.apiKey = "sk-abcdefghijklmnop";
		draft.autoHideSeconds = "abc";
		draft.timeoutSeconds = "三十";
		List<String> notes = draft.applyTo(target);

		check(target.hudAutoHideSeconds == 6, "填了字母就回默认 6，实际 " + target.hudAutoHideSeconds);
		check(target.requestTimeoutSeconds == 30, "填了字母就回默认 30，实际 " + target.requestTimeoutSeconds);
		check(notes.size() == 2, "两条提示，实际 " + notes);
		check(notes.get(0).contains("abc"), "提示里要带上用户填的内容");
	}

	private static void numbersAreClampedWithNote() {
		MchanhuaConfig target = new MchanhuaConfig();
		ConfigDraft draft = new ConfigDraft();
		draft.apiKey = "sk-abcdefghijklmnop";
		draft.autoHideSeconds = "-5";
		draft.timeoutSeconds = "9999";
		List<String> notes = draft.applyTo(target);

		check(target.hudAutoHideSeconds == ConfigDraft.AUTO_HIDE_MIN,
				"负数往下夹到 " + ConfigDraft.AUTO_HIDE_MIN + "，实际 " + target.hudAutoHideSeconds);
		check(target.requestTimeoutSeconds == ConfigDraft.TIMEOUT_MAX,
				"超大值往上夹到 " + ConfigDraft.TIMEOUT_MAX + "，实际 " + target.requestTimeoutSeconds);
		check(notes.size() == 2, "夹取也要给提示，实际 " + notes);
	}

	private static void emptyNumbersSilentlyUseDefault() {
		MchanhuaConfig target = new MchanhuaConfig();
		ConfigDraft draft = new ConfigDraft();
		draft.apiKey = "sk-abcdefghijklmnop";
		draft.autoHideSeconds = "  ";
		draft.timeoutSeconds = "";
		List<String> notes = draft.applyTo(target);

		check(target.hudAutoHideSeconds == 6, "空着就用默认 6");
		check(target.requestTimeoutSeconds == 30, "空着就用默认 30");
		check(notes.isEmpty(), "空着不算错误，不用啰嗦：" + notes);
	}

	private static void apiKeyIsTrimmed() {
		MchanhuaConfig target = new MchanhuaConfig();
		ConfigDraft draft = new ConfigDraft();
		draft.apiKey = "  sk-abcdefghijklmnop  \n";
		draft.applyTo(target);
		check("sk-abcdefghijklmnop".equals(target.apiKey),
				"从网页复制来的 key 常带空格/换行，要自动去掉：" + target.apiKey);
	}

	private static void maskHidesTheMiddleOfTheKey() {
		check("（还没填）".equals(ConfigDraft.maskKey(null)), "null 显示未填");
		check("（还没填）".equals(ConfigDraft.maskKey("   ")), "空白显示未填");
		check("••••".equals(ConfigDraft.maskKey("abcd")), "太短的 key 全打点");
		check("••••••••".equals(ConfigDraft.maskKey("abcdefgh")), "8 位全打点");
		String masked = ConfigDraft.maskKey("sk-abcdefghijklmnop");
		check(masked.startsWith("sk-ab") && masked.endsWith("mnop"), "露头露尾：" + masked);
		check(masked.contains("…"), "中间要省略：" + masked);
		check(!masked.contains("cdefghijkl"), "中间不能泄漏：" + masked);
	}

	private static void missingKeyIsReported() {
		MchanhuaConfig target = new MchanhuaConfig();
		ConfigDraft draft = new ConfigDraft();
		draft.apiKey = "";
		List<String> notes = draft.applyTo(target);
		check(notes.stream().anyMatch(n -> n.contains("API Key")), "没填 key 要提醒：" + notes);
		check(!target.ready(), "没填 key 时 ready() 应该是 false");
	}

	private static void switchesAreCopied() {
		MchanhuaConfig target = new MchanhuaConfig();
		ConfigDraft draft = ConfigDraft.from(target);
		draft.translateTooltips = !draft.translateTooltips;
		draft.translateChat = !draft.translateChat;
		draft.hudVisible = !draft.hudVisible;
		draft.showOriginal = !draft.showOriginal;
		List<String> notes = new ArrayList<>();
		notes.addAll(draft.applyTo(target));

		MchanhuaConfig fresh = new MchanhuaConfig();
		check(target.translateTooltips == !fresh.translateTooltips, "tooltip 开关要被翻转写回");
		check(target.translateChat == !fresh.translateChat, "聊天开关要被翻转写回");
		check(target.hudVisible == !fresh.hudVisible, "HUD 开关要被翻转写回");
		check(target.showOriginal == !fresh.showOriginal, "原文对照开关要被翻转写回");
	}

	private static void check(boolean condition, String message) {
		if (condition) {
			passed++;
		} else {
			failed++;
			System.out.println("  [FAIL] " + message);
		}
	}

	private ConfigDraftSelfTest() {
	}
}
