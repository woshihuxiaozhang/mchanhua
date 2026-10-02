package com.mchanhua.client.translate;

import com.mchanhua.client.config.MchanhuaConfig;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 翻译链路自测（不进游戏也能验证）：读取桌面版的 API Key，翻一段物品文本。
 *
 * 用法：{@code .\gradlew.bat selftest}
 *
 * 存在的意义：改提示词或换服务商时，先在这里确认"请求能发出去、返回能解析"，
 * 再去游戏里试，能少走很多弯路。
 */
public final class TranslatorSelfTest {
	private static final Pattern API_KEY = Pattern.compile("api_key\\s*=\\s*\"([^\"]*)\"");
	private static final Pattern BASE_URL = Pattern.compile("base_url\\s*=\\s*\"([^\"]*)\"");
	private static final Pattern MODEL = Pattern.compile("model\\s*=\\s*\"([^\"]*)\"");

	private TranslatorSelfTest() {
	}

	public static void main(String[] args) throws Exception {
		MchanhuaConfig config = fromDesktopConfig();
		List<String> sample = List.of(
				"Steel Ingot",
				"A sturdy ingot of steel.",
				"Mychael reached the Blackwood Gate before dawn.");

		long started = System.currentTimeMillis();
		List<String> translated = new DeepSeekTranslator().translate(config, sample);
		long elapsed = System.currentTimeMillis() - started;

		StringBuilder report = new StringBuilder();
		report.append("服务商：").append(config.baseUrl).append(" / ").append(config.model).append('\n');
		report.append("耗时  ：").append(elapsed).append(" ms\n");
		report.append("原文  ：").append(sample).append('\n');
		report.append("译文  ：").append(translated).append('\n');
		System.out.print(report);

		// 控制台在中文 Windows 上会按 GBK 转一遍，所以同时写一份 UTF-8 结果文件
		Path out = Path.of("build", "selftest-result.txt");
		Files.createDirectories(out.getParent());
		Files.writeString(out, report.toString(), StandardCharsets.UTF_8);
		System.out.println("结果文件：" + out.toAbsolutePath());

		if (translated.equals(sample)) {
			System.out.println("⚠ 译文和原文一样，检查 API Key / 网络");
			System.exit(2);
		}
	}

	/** 从桌面版的 config.toml 里读 key（用正则，避免为一个小工具引入 TOML 依赖）。 */
	private static MchanhuaConfig fromDesktopConfig() throws Exception {
		MchanhuaConfig config = new MchanhuaConfig();
		Path path = Path.of(System.getenv("APPDATA"), "mchanhua", "config.toml");
		if (Files.exists(path)) {
			String text = Files.readString(path, StandardCharsets.UTF_8);
			config.apiKey = firstGroup(API_KEY, text, "");
			config.baseUrl = firstGroup(BASE_URL, text, config.baseUrl);
			config.model = firstGroup(MODEL, text, config.model);
		}
		if (config.apiKey.isBlank()) {
			System.out.println("没读到 API Key（" + path + "），也无法自测");
			System.exit(1);
		}
		return config;
	}

	private static String firstGroup(Pattern pattern, String text, String fallback) {
		Matcher matcher = pattern.matcher(text);
		return matcher.find() ? matcher.group(1) : fallback;
	}
}
