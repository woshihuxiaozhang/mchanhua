package com.mchanhua.client.tooltip;

import com.mchanhua.MchanhuaMod;
import com.mchanhua.client.config.MchanhuaConfig;
import com.mchanhua.client.hud.TranslationHud;
import com.mchanhua.client.translate.TranslationService;

import net.minecraft.client.Minecraft;
import net.minecraft.network.chat.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * tooltip 翻译：把 {@code List<Component>} 里的文本查缓存 / 发请求，再拼回同样行数的 Component。
 *
 * 策略是"先原文、后译文"：第一次悬停显示原文并后台请求，翻好之后（通常一秒内）
 * 再悬停同一物品就直接显示中文，不卡帧。
 */
public final class TooltipTranslator {
	private static TranslationService service;
	private static MchanhuaConfig config;
	private static int debugCount = 0;

	private TooltipTranslator() {
	}

	public static void init(MchanhuaConfig modConfig, TranslationService translationService) {
		config = modConfig;
		service = translationService;
	}

	public static boolean active() {
		return config != null && service != null && config.translateTooltips && config.ready();
	}

	/**
	 * 把 tooltip 行翻成目标语言；没准备好就原样返回（渲染线程安全，不做网络等待）。
	 */
	public static List<Component> translate(List<Component> original) {
		if (!active() || original == null || original.isEmpty()) {
			return original;
		}
		List<String> sources = new ArrayList<>(original.size());
		for (Component line : original) {
			sources.add(line.getString());
		}
		if (alreadyChinese(sources)) {
			return original;              // 已经是中文了（或上一层已经翻过），别再花一次请求
		}
		List<String> cached = service.cached(sources);
		if (cached != null) {
			return rebuild(original, cached);
		}
		if (debugCount < 5) {
			debugCount++;
			MchanhuaMod.LOGGER.info("tooltip 命中，开始后台翻译：{}", sources);
		}
		service.request(sources, translated -> Minecraft.getInstance().execute(() -> {
			TranslationHud.setLast(sources, translated);
		}));
		return original;
	}

	/** 单行 tooltip（有些界面只画物品名）。 */
	public static Component translateComponent(Component line) {
		if (line == null || !active()) {
			return line;
		}
		List<Component> translated = translate(List.of(line));
		return translated.isEmpty() ? line : translated.get(0);
	}

	/** 只要有一行是中文，就认为这批已经翻过了（避免两层钩子重复请求）。 */
	private static boolean alreadyChinese(List<String> lines) {
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

	/** 用译文重建同样行数的 Component（行数不一致时补回原文，保证显示不串行）。 */
	private static List<Component> rebuild(List<Component> original, List<String> translated) {
		List<Component> result = new ArrayList<>(original.size());
		for (int i = 0; i < original.size(); i++) {
			if (i < translated.size() && translated.get(i) != null && !translated.get(i).isBlank()) {
				result.add(Component.literal(translated.get(i)));
			} else {
				result.add(original.get(i));
			}
		}
		return result;
	}
}
