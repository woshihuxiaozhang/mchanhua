package com.mchanhua.client.translate;

import com.mchanhua.MchanhuaMod;
import com.mchanhua.client.config.MchanhuaConfig;

import net.minecraft.client.Minecraft;
import net.minecraft.network.chat.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

/**
 * 游戏内文本的翻译入口：tooltip、聊天、标题/ActionBar、Boss 栏都在这里。
 *
 * 两类文本两条路：
 * - tooltip / Boss 栏这类"一直在那"的：先显示原文，译文回来后就地替换（渲染线程从不等待网络）；
 * - 聊天 / 标题 / ActionBar 这类"一闪而过"的：先按住不显示，翻好再显示一次。
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

	/** 世界里的告示牌要不要翻（走路经过的门禁牌、房间号那些）。 */
	public static boolean signsEnabled() {
		return enabled() && config.translateSigns;
	}

	/** 实体头顶名字 / 世界悬浮字要不要翻（玩家 ID 由调用方跳过）。 */
	public static boolean nametagsEnabled() {
		return enabled() && config.translateNametags;
	}

	/** 书本页面要不要翻。 */
	public static boolean booksEnabled() {
		return enabled() && config.translateBooks;
	}

	/**
	 * 带换行的整页文本（书页）：**按行**翻再拼回去。
	 *
	 * 书页里的 {@code \n} 是作者自己分好的行，行数或顺序一变排版就乱，
	 * 所以这里一行对一行地贴回去（空行原样留着）。
	 * 还没翻好时先把原文交出去，等缓存里有了，下一帧自然就换成译文。
	 */
	public static Component translateMultiline(Component page, boolean allowed) {
		if (page == null || !allowed) {
			return page;
		}
		String raw = page.getString();
		if (raw.isEmpty()) {
			return page;
		}
		List<String> rawLines = List.of(raw.split("\n", -1));
		List<Integer> indices = TextLines.indicesToTranslate(rawLines);
		if (indices.isEmpty()) {
			return page;
		}
		List<String> picked = TextLines.pick(rawLines, indices);
		List<String> cached = service.cached(picked);
		if (cached == null) {
			service.request(picked, translated -> {
				// 结果进缓存就够了，界面下一帧自己会取到
			});
			return page;
		}
		List<String> merged = TextLines.applyTranslations(rawLines, indices, cached);
		return Component.literal(String.join("\n", merged)).withStyle(page.getStyle());
	}

	/** 当前是否正在"把译文放回游戏"的回放里（钩子见到就放行）。 */
	public static boolean isReplaying() {
		return ReplayGuard.active();
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
		List<String> all = new ArrayList<>(original.size());
		for (Component line : original) {
			all.add(line.getString());
		}
		// 逐行挑要翻的：混排 tooltip（物品名英文 + 属性行中文）里中文行留着、英文行照翻。
		// 早先是"整段只要有一行中文就整段跳过"，结果用户看到"有些物品没翻译"。
		List<Integer> indices = TextLines.indicesToTranslate(all);
		if (indices.isEmpty()) {
			return original;
		}
		List<String> sources = TextLines.pick(all, indices);
		List<String> cached = service.cached(sources);
		if (cached != null) {
			return applyTranslation(original, indices, cached);
		}
		if (debugCount < 50) {
			debugCount++;
			MchanhuaMod.LOGGER.info("开始后台翻译：{}", sources);
		}
		service.request(sources, translated -> {
			if (mirrorToHud) {
				Minecraft.getInstance().execute(() ->
						com.mchanhua.client.hud.TranslationHud.setLast(sources, translated));
			}
		});
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
		if (!TextLines.needsTranslation(text)) {
			return line;                 // 本来就是中文，没什么可翻的
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
	 *
	 * **所有回放都必须走 {@link ReplayGuard}**：回放会再进一次钩子，
	 * 不打标记就会"回放→钩子→回放"无限递归，直接把游戏撑爆（PCL 里崩过）。
	 */
	public static void requestLater(Component line, boolean allowed, Consumer<Component> replay) {
		if (line == null || !allowed) {
			ReplayGuard.run(line, replay);
			return;
		}
		Component ready = readyOrNull(line, true);
		if (ready != null) {
			ReplayGuard.run(ready, replay);
			return;
		}
		String source = line.getString();
		service.request(List.of(source), translated -> {
			String text = translated.isEmpty() ? source : translated.get(0);
			Component result = Component.literal(text).withStyle(line.getStyle());
			Minecraft.getInstance().execute(() -> {
				// HUD 里留一份对照（译文 + 原文），因为它会自己收起来，不会一直挡视野
				com.mchanhua.client.hud.TranslationHud.setLast(List.of(source), List.of(text));
				ReplayGuard.run(result, replay);
			});
		});
	}

	/** 把译文按行号放回原列表（没翻的行保持原样、原样式）。 */
	private static List<Component> applyTranslation(List<Component> original, List<Integer> indices,
			List<String> translated) {
		List<String> originals = new ArrayList<>(original.size());
		for (Component line : original) {
			originals.add(line.getString());
		}
		List<String> merged = TextLines.applyTranslations(originals, indices, translated);
		List<Component> result = new ArrayList<>(original.size());
		for (int i = 0; i < original.size(); i++) {
			String text = merged.get(i);
			if (text.equals(originals.get(i))) {
				result.add(original.get(i));      // 没翻的行连样式一起原样留着
			} else {
				result.add(Component.literal(text).withStyle(original.get(i).getStyle()));
			}
		}
		return result;
	}
}
