package com.mchanhua.client.config;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

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
		providerPresetsAreUsable();
		modelCyclingWrapsAround();
		providerCyclingStaysOnKnownOnes();
		localOllamaDoesNotNeedKey();

		System.out.println();
		System.out.println("[config-draft] 通过 " + passed + "，失败 " + failed);
		if (failed > 0) {
			System.exit(1);
		}
	}

	private static void roundTripKeepsValues() {
		MchanhuaConfig source = new MchanhuaConfig();
		source.apiKey = "test-key-0123456789";
		source.baseUrl = "https://api.moonshot.cn/v1";
		source.model = "kimi-k2";
		source.targetLanguage = "繁體中文";
		source.hudAutoHideSeconds = 12;
		source.requestTimeoutSeconds = 45;
		source.translateTooltips = false;
		source.translateChat = true;
		source.translateSigns = false;
		source.translateNametags = false;
		source.translateBooks = false;
		source.hudVisible = false;
		source.showOriginal = false;

		MchanhuaConfig target = new MchanhuaConfig();
		List<String> notes = ConfigDraft.from(source).applyTo(target);

		check(notes.isEmpty(), "完整配置往返不该有兜底提示：" + notes);
		check("test-key-0123456789".equals(target.apiKey), "apiKey 要一致");
		check("https://api.moonshot.cn/v1".equals(target.baseUrl), "baseUrl 要一致");
		check("kimi-k2".equals(target.model), "model 要一致");
		check("繁體中文".equals(target.targetLanguage), "targetLanguage 要一致");
		check(target.hudAutoHideSeconds == 12, "自动隐藏秒数要一致");
		check(target.requestTimeoutSeconds == 45, "超时秒数要一致");
		check(!target.translateTooltips && target.translateChat, "开关要一致");
		check(!target.translateSigns, "告示牌开关要一致");
		check(!target.translateNametags, "悬浮字开关要一致");
		check(!target.translateBooks, "书页开关要一致");
		check(!target.hudVisible && !target.showOriginal, "显示开关要一致");
	}

	private static void blankStringsFallBackToDefaults() {
		MchanhuaConfig target = new MchanhuaConfig();
		ConfigDraft draft = new ConfigDraft();
		draft.apiKey = "test-key-0123456789";
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
		draft.apiKey = "test-key-0123456789";
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
		draft.apiKey = "test-key-0123456789";
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
		draft.apiKey = "test-key-0123456789";
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
		draft.apiKey = "  test-key-0123456789  \n";
		draft.applyTo(target);
		check("test-key-0123456789".equals(target.apiKey),
				"从网页复制来的 key 常带空格/换行，要自动去掉：" + target.apiKey);
	}

	private static void maskHidesTheMiddleOfTheKey() {
		check("（还没填）".equals(ConfigDraft.maskKey(null)), "null 显示未填");
		check("（还没填）".equals(ConfigDraft.maskKey("   ")), "空白显示未填");
		check("••••".equals(ConfigDraft.maskKey("abcd")), "太短的 key 全打点");
		check("••••••••".equals(ConfigDraft.maskKey("abcdefgh")), "8 位全打点");
		String masked = ConfigDraft.maskKey("test-key-0123456789");
		check(masked.startsWith("test-") && masked.endsWith("6789"), "露头露尾：" + masked);
		check(masked.contains("…"), "中间要省略：" + masked);
		check(!masked.contains("key-012345"), "中间不能泄漏：" + masked);
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
		draft.translateSigns = !draft.translateSigns;
		draft.translateNametags = !draft.translateNametags;
		draft.translateBooks = !draft.translateBooks;
		draft.hudVisible = !draft.hudVisible;
		draft.showOriginal = !draft.showOriginal;
		List<String> notes = new ArrayList<>();
		notes.addAll(draft.applyTo(target));

		MchanhuaConfig fresh = new MchanhuaConfig();
		check(target.translateTooltips == !fresh.translateTooltips, "tooltip 开关要被翻转写回");
		check(target.translateChat == !fresh.translateChat, "聊天开关要被翻转写回");
		check(target.translateSigns == !fresh.translateSigns, "告示牌开关要被翻转写回");
		check(target.translateNametags == !fresh.translateNametags, "悬浮字开关要被翻转写回");
		check(target.translateBooks == !fresh.translateBooks, "书页开关要被翻转写回");
		check(target.hudVisible == !fresh.hudVisible, "HUD 开关要被翻转写回");
		check(target.showOriginal == !fresh.showOriginal, "原文对照开关要被翻转写回");
	}

	private static void providerPresetsAreUsable() {
		check(ProviderPresets.all().size() >= 7, "预设里至少要有 7 个条目（含自定义）");
		check("deepseek".equals(ProviderPresets.guess("https://api.deepseek.com").key), "认得出 DeepSeek");
		check("deepseek".equals(ProviderPresets.guess("https://api.deepseek.com/v1/chat/completions").key),
				"带路径也认得出 DeepSeek");
		check("openai".equals(ProviderPresets.guess("https://api.openai.com/v1").key), "认得出 OpenAI");
		check("moonshot".equals(ProviderPresets.guess("https://api.moonshot.cn/v1").key), "认得出 Kimi");
		check("dashscope".equals(
				ProviderPresets.guess("https://dashscope.aliyuncs.com/compatible-mode/v1").key), "认得出通义千问");
		check("zhipu".equals(ProviderPresets.guess("https://open.bigmodel.cn/api/paas/v4").key), "认得出智谱");
		check("siliconflow".equals(ProviderPresets.guess("https://api.siliconflow.cn/v1").key), "认得出硅基流动");
		check("ollama".equals(ProviderPresets.guess("http://localhost:11434/v1").key), "认得出本地 Ollama");
		check(ProviderPresets.isCustom(ProviderPresets.guess("https://我自己的服务器.example.com/v1")),
				"认不出的地址要当自定义");
		check(ProviderPresets.isCustom(ProviderPresets.guess("")), "空地址就是自定义");

		for (ProviderPresets.Preset preset : ProviderPresets.all()) {
			if (ProviderPresets.isCustom(preset)) {
				continue;
			}
			check(!preset.label.isBlank(), "预设要有名字：" + preset.key);
			check(!preset.baseUrl.isBlank(), "预设要有地址：" + preset.key);
			check(!preset.models.isEmpty(), "预设要有可选模型：" + preset.key);
			check(ProviderPresets.guess(preset.baseUrl).key.equals(preset.key),
					"用预设地址要能反推回它自己：" + preset.key);
		}
		check(ProviderPresets.modelsFor("https://api.deepseek.com").contains("deepseek-chat"),
				"DeepSeek 列表里要有 deepseek-chat");
		check(ProviderPresets.modelsFor("https://我自己的服务器.example.com/v1").isEmpty(),
				"自定义服务商不预设模型，交给手填");
	}

	private static void modelCyclingWrapsAround() {
		List<String> models = ProviderPresets.modelsFor("https://api.deepseek.com");
		check(models.size() >= 2, "DeepSeek 至少要有两个模型可切");
		String first = models.get(0);
		check(models.get(1).equals(ProviderPresets.next(models, first)), "点一下要换到第二个");
		check(first.equals(ProviderPresets.next(models, models.get(models.size() - 1))),
				"最后一个的下一轮要回到第一个");
		check(first.equals(ProviderPresets.next(models, "不存在的模型")), "认不出的模型回到第一个");
		check("x".equals(ProviderPresets.next(List.of(), "x")), "空列表原样返回，别崩");
		check("x".equals(ProviderPresets.next(null, "x")), "null 列表原样返回，别崩");
	}

	private static void providerCyclingStaysOnKnownOnes() {
		String baseUrl = "https://api.deepseek.com";
		Set<String> seen = new HashSet<>();
		for (int i = 0; i < ProviderPresets.all().size(); i++) {
			ProviderPresets.Preset preset = ProviderPresets.nextPreset(baseUrl);
			check(!ProviderPresets.isCustom(preset), "循环里不该出现自定义：" + preset.key);
			seen.add(preset.key);
			baseUrl = preset.baseUrl;
		}
		check(seen.contains("deepseek"), "循环要能回到 DeepSeek");
		check(seen.contains("ollama"), "循环要能走到本地 Ollama");
		check(seen.size() >= 6, "循环要覆盖常见服务商，实际 " + seen.size());
	}

	private static void localOllamaDoesNotNeedKey() {
		ConfigDraft draft = new ConfigDraft();
		draft.baseUrl = "http://localhost:11434/v1";
		draft.model = "qwen2.5:7b";
		draft.apiKey = "";
		MchanhuaConfig target = new MchanhuaConfig();
		List<String> notes = draft.applyTo(target);
		check(target.ready(), "本地 Ollama 不填 key 也算配好了");
		check(!ProviderPresets.needsKey(target.baseUrl), "本地服务不需要 key");
		check(notes.stream().noneMatch(note -> note.contains("API Key")),
				"本地服务不该催我填 key：" + notes);

		ConfigDraft remote = new ConfigDraft();
		remote.baseUrl = "https://api.moonshot.cn/v1";
		remote.apiKey = "";
		MchanhuaConfig remoteTarget = new MchanhuaConfig();
		check(remote.applyTo(remoteTarget).stream().anyMatch(note -> note.contains("API Key")),
				"远程服务没填 key 还是要提醒");
		check(!remoteTarget.ready(), "远程服务没 key 就是没配好");
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
