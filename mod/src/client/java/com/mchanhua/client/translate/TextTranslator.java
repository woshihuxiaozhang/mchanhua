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
	/** 正在"用译文重新显示"时置位：避免同一条文本被自己的钩子再次拦下来。 */
	private static final ThreadLocal<Boolean> REPLAYING = ThreadLocal.withInitial(() -> Boolean.FALSE);

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

	/** 当前是否正处在"补显示译文"的回放里（钩子见到就放行）。 */
	public static boolean isReplaying() {
		return REPLAYING.get();
	}

	/** 条件不满足时原样返回（渲染线程安全，不做网络等待）。 */
	public static List<Component> translateLines(List<Component> original, boolean allowed) {
		return translateLines(original, allowed, false);
	}

	/**
	 * @param mirrorToHud 翻好后是否也丢进 HUD 小窗。
	 *                    tooltip 本身就是就地翻译的，再叠一层 HUD 只会挡视野，所以传 false。
	 */
	public static List<Component> translateLines(List<Component> original, boolean allowed,
			boolean mirrorToHud) {
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
		service.request(sources, translated -> Minecraft.getInstance().execute(() -> {
			if (mirrorToHud) {
				com.mchanhua.client.hud.TranslationHud.setLast(sources, translated);
			}
		}));
		return original;
	}

	/** 单行文本（聊天、标题、Boss 栏名都用这个）。 */
	public static Component translateLine(Component line, boolean allowed) {
		return translateLine(line, allowed, false);
	}

	public static Component translateLine(Component line, boolean allowed, boolean mirrorToHud) {
		if (line == null || !allowed) {
			return line;
		}
		List<Component> translated = translateLines(List.of(line), true, mirrorToHud);
		return translated.isEmpty() ? line : translated.get(0);
	}

	/** 已经翻好的行（缓存命中）就返回译文，否则返回 null——给"翻好再显示"的文本用。 */
	public static Component readyOrNull(Component line, boolean allowed) {
		if (line == null || !allowed) {
			return line;
		}
		String text = line.getString();
		if (alreadyTarget(List.of(text))) {
			return line;
		}
		List<String> cached = service.cached(List.of(text));
		if (cached == null || cached.isEmpty()) {
			return null;
		}
		return Component.literal(cached.get(0)).withStyle(line.getStyle());
	}

	/**
	 * 翻这句话，翻好后用译文回调（回调在**渲染线程**）。
	 *
	 * 用于"一闪而过"的文本：聊天、标题、ActionBar。它们显示时间很短，
	 * 若按"先原文后替换"的做法，等翻译回来时字幕早没了——所以这里先按住不显示，
	 * 翻好（或失败）再拿译文重新显示一次。
	 */
	public static void requestLater(Component line, boolean allowed, java.util.function.Consumer<Component> replay) {
		if (line == null || !allowed) {
			replay.accept(line);
			return;
		}
		Component ready = readyOrNull(line, true);
		if (ready != null) {
			replay.accept(ready);
			return;
		}
		String source = line.getString();
		service.request(List.of(source), translated -> {
			String text = translated.isEmpty() ? source : translated.get(0);
			Component result = Component.literal(text).withStyle(line.getStyle());
			Minecraft.getInstance().execute(() -> {
				// HUD 里留一份对照（译文 + 原文），因为它会自己收起来，不会一直挡视野
				com.mchanhua.client.hud.TranslationHud.setLast(List.of(source), List.of(text));
				REPLAYING.set(true);
				try {
					replay.accept(result);
				} finally {
					REPLAYING.set(false);
				}
			});
		});
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
