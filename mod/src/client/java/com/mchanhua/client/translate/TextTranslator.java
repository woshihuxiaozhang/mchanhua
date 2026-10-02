package com.mchanhua.client.translate;

import com.mchanhua.MchanhuaMod;
import com.mchanhua.client.config.MchanhuaConfig;

import net.minecraft.client.Minecraft;
import net.minecraft.network.chat.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * 游戏内文本的翻译出口：tooltip、聊天、标题/ActionBar、Boss 栏都走这里。
 *
 * 策略是"先原文、后译文"：第一次遇到某段文本先原样显示并后台请求，
 * 翻好之后（通常一秒内）再遇到就直接显示中文，渲染线程从不等待网络。
 */
public final class TextTranslator {
	private static TranslationService service;
	private static MchanhuaConfig config;
	private static int debugCount = 0;

	private TextTranslator() {
	}

	public static void init(MchanhuaConfig modConfig, TranslationService translationService) {
		config = modConfig;
		service = translationService;
	}

	public static boolean enabled() {
		return config != null && service != null && config.ready();
	}

	public static boolean tooltipsEnabled() {
		return enabled() && config.translateTooltips;
	}

	public static boolean chatEnabled() {
		return enabled() && config.translateChat;
	}

	/** 条件不满足时原样返回（渲染线程安全，不做网络等待）。 */
	public static List<Component> translateLines(List<Component> original, boolean allowed) {
		if (!allowed || original == null || original.isEmpty()) {
			return original;
		}
		List<String> sources = new ArrayList<>(original.size());
		for (Component line : original) {
			sources.add(line.getString());
		}
		if (alreadyTarget(sources)) {
			return original;              // 已经是中文（或上一层已翻过），别再花一次请求
		}
		List<String> cached = service.cached(sources);
		if (cached != null) {
			return rebuild(original, cached);
		}
		if (debugCount < 5) {
			debugCount++;
			MchanhuaMod.LOGGER.info("开始后台翻译：{}", sources);
		}
		service.request(sources, translated -> Minecraft.getInstance().execute(() ->
				com.mchanhua.client.hud.TranslationHud.setLast(sources, translated)));
		return original;
	}

	/** 单行文本（聊天、标题、Boss 栏名都用这个）。 */
	public static Component translateLine(Component line, boolean allowed) {
		if (line == null || !allowed) {
			return line;
		}
		List<Component> translated = translateLines(List.of(line), true);
		return translated.isEmpty() ? line : translated.get(0);
	}

	/** 用译文重建同样行数的 Component，并保留原来那一行的样式（颜色、粗体等）。 */
	private static List<Component> rebuild(List<Component> original, List<String> translated) {
		List<Component> result = new ArrayList<>(original.size());
		for (int i = 0; i < original.size(); i++) {
			if (i < translated.size() && translated.get(i) != null && !translated.get(i).isBlank()) {
				result.add(Component.literal(translated.get(i))
						.withStyle(original.get(i).getStyle()));
			} else {
				result.add(original.get(i));
			}
		}
		return result;
	}

	/** 只要有一行是中文，就认为这批已经翻过了（多层钩子不会重复请求）。 */
	private static boolean alreadyTarget(List<String> lines) {
		for (String line : lines) {
			if (line == null || line.isBlank()) {
				continue;
			}
			for (int i = 0; i < line.length(); i++) {
				char ch = line.charAt(i);
				if (ch >= 0x4E00 && ch <= 0x9FFF) {
					return true;
				}
			}
		}
		return false;
	}
}
