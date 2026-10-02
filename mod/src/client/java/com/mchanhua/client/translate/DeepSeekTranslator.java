package com.mchanhua.client.translate;

import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.mchanhua.MchanhuaMod;
import com.mchanhua.client.config.MchanhuaConfig;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

/**
 * OpenAI 兼容的翻译后端（默认 DeepSeek），走纯 JDK 的 HttpClient。
 *
 * 提示词沿用桌面版调好的那一套思路：逐行翻译、口语化、保留情绪、专有名词前后一致、
 * 并且只输出一个 JSON 对象（行号 → 译文），方便按行对齐。
 */
public final class DeepSeekTranslator implements LineTranslator {
	private static final Gson GSON = new Gson();

	private static final String SYSTEM_PROMPT = """
			你是游戏文本的翻译，负责把屏幕上的文本翻译成[[target]]。

			【语气与风格】
			- 译成口语化、自然的[[target]]，像真人在说话，不要翻译腔。
			- 保留原句的情绪：惊讶、紧张、警告、嘲讽、催促都要译出来。
			- 物品名、技能名保持简洁；NPC 台词要短促有力。

			【格式规则】（必须严格遵守）
			1. 逐行翻译，**输出行数与输入完全一致、顺序一致**，不合并、不拆分、不增删。
			2. 只输出一个 JSON 对象：{"lines": [{"i": 0, "dst": "译文"}, ...]}，i 是输入行号（从 0 开始）。
			3. 已经是[[target]]的行、纯数字或纯符号的行，把原文原样放进 dst。
			4. 专有名词（人名、地名、物品名）要一致：优先用[[target]]社区通行译名，没有就音译并固定；
			   人名地名不要按字面意译（The Butcher 这种外号可以意译）。
			5. 输入来自游戏界面，可能有个别字符识别/排版噪音，按最合理的理解翻译。
			""";

	private final HttpClient client = HttpClient.newBuilder()
			.connectTimeout(Duration.ofSeconds(10))
			.build();

	/** 翻译若干行，返回与输入等长的译文列表；失败抛异常，由调用方兜底。 */
	@Override
	public List<String> translate(MchanhuaConfig config, List<String> lines) throws Exception {
		if (lines.isEmpty()) {
			return lines;
		}
		StringBuilder numbered = new StringBuilder();
		for (int i = 0; i < lines.size(); i++) {
			numbered.append(i).append(". ").append(lines.get(i)).append('\n');
		}

		JsonObject system = new JsonObject();
		system.addProperty("role", "system");
		system.addProperty("content", SYSTEM_PROMPT.replace("[[target]]", config.targetLanguage));
		JsonObject user = new JsonObject();
		user.addProperty("role", "user");
		user.addProperty("content", "请翻译下面 " + lines.size() + " 行文本，返回 JSON：\n" + numbered);
		JsonArray messages = new JsonArray();
		messages.add(system);
		messages.add(user);

		JsonObject body = new JsonObject();
		body.addProperty("model", config.model);
		body.addProperty("temperature", 0.0);
		body.add("messages", messages);

		HttpRequest request = HttpRequest.newBuilder()
				.uri(URI.create(endpoint(config.baseUrl)))
				.timeout(Duration.ofSeconds(Math.max(5, config.requestTimeoutSeconds)))
				.header("Content-Type", "application/json")
				.header("Authorization", "Bearer " + config.apiKey)
				.POST(HttpRequest.BodyPublishers.ofString(GSON.toJson(body)))
				.build();

		// 用 sendAsync + 硬超时：早先直接用 send()，网络卡住时线程会一直吊在那儿，
		// 单线程队列就被一个卡死的请求堵死——后面的物品全都翻不出来（用户看到的"有些物品没翻译"）。
		// get(timeout) 保证这条任务一定会还给队列，超时就当失败处理（显示原文，不写缓存）。
		HttpResponse<String> response;
		try {
			response = client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
					.get(Math.max(5, config.requestTimeoutSeconds) + 5L, java.util.concurrent.TimeUnit.SECONDS);
		} catch (java.util.concurrent.TimeoutException e) {
			throw new IllegalStateException("请求超时（超过 " + Math.max(5, config.requestTimeoutSeconds)
					+ " 秒没回应）");
		} catch (java.util.concurrent.ExecutionException e) {
			Throwable cause = e.getCause();
			throw new IllegalStateException("请求失败：" + (cause == null ? e.toString() : cause.toString()));
		}
		if (response.statusCode() != 200) {
			throw new IllegalStateException("翻译服务返回 " + response.statusCode() + "：" + trim(response.body()));
		}
		return parse(response.body(), lines);
	}

	private static String endpoint(String baseUrl) {
		String base = (baseUrl == null || baseUrl.isBlank() ? "https://api.deepseek.com" : baseUrl).trim();
		if (base.endsWith("/")) {
			base = base.substring(0, base.length() - 1);
		}
		if (base.endsWith("/v1") || base.endsWith("/v4")) {
			return base + "/chat/completions";
		}
		return base + "/v1/chat/completions";
	}

	private static List<String> parse(String body, List<String> sources) {
		List<String> result = new ArrayList<>(sources);
		try {
			JsonObject root = GSON.fromJson(body, JsonObject.class);
			String content = root.getAsJsonArray("choices").get(0).getAsJsonObject()
					.getAsJsonObject("message").get("content").getAsString();
			content = stripFence(content);
			JsonObject parsed = GSON.fromJson(content, JsonObject.class);
			JsonArray items = parsed.getAsJsonArray("lines");
			for (int i = 0; i < items.size(); i++) {
				JsonObject item = items.get(i).getAsJsonObject();
				if (!item.has("i") || !item.has("dst")) {
					continue;
				}
				int index = item.get("i").getAsInt();
				String dst = item.get("dst").getAsString();
				if (index >= 0 && index < result.size() && dst != null && !dst.isBlank()) {
					result.set(index, dst);
				}
			}
		} catch (Exception e) {
			MchanhuaMod.LOGGER.warn("解析翻译结果失败：{}", e.toString());
		}
		return result;
	}

	private static String stripFence(String text) {
		String trimmed = text.trim();
		if (trimmed.startsWith("```")) {
			trimmed = trimmed.replaceFirst("^```[a-zA-Z]*\\s*", "");
			trimmed = trimmed.replaceFirst("```$", "").trim();
		}
		return trimmed;
	}

	private static String trim(String text) {
		if (text == null) {
			return "";
		}
		return text.length() > 200 ? text.substring(0, 200) : text;
	}
}
