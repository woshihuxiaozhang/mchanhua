package com.mchanhua.client.translate;

import com.mchanhua.MchanhuaMod;
import com.mchanhua.client.config.MchanhuaConfig;

import net.minecraft.client.MinecraftClient;
import net.minecraft.text.Text;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

/**
 * 游戏内文本的翻译入口（老版本线 / Yarn 映射版）。
 *
 * 和 26.x 那版逻辑完全一样，只是名字换了：Component → Text、Minecraft → MinecraftClient。
 * 两类文本两条路：
 * - tooltip / Boss 栏这类"一直在那"的：先显示原文，译文回来后就地替换；
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

	/** 世界里的告示牌要不要翻。 */
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

	/** 当前是否正在"把译文放回游戏"的回放里（钩子见到就放行）。 */
	public static boolean isReplaying() {
		return ReplayGuard.active();
	}

	/** 条件不满足时原样返回（渲染线程安全，不做网络等待）。 */
	public static List<Text> translateLines(List<Text> original, boolean allowed) {
		return translateLines(original, allowed, false);
	}

	/**
	 * @param mirrorToHud 翻好后是否也丢进 HUD 小窗。
	 *                    tooltip 本身就是就地翻译的，再叠一层 HUD 只会挡视野，所以传 false。
	 */
	public static List<Text> translateLines(List<Text> original, boolean allowed, boolean mirrorToHud) {
		if (!allowed || original == null || original.isEmpty()) {
			return original;
		}
		List<String> all = new ArrayList<>(original.size());
		for (Text line : original) {
			all.add(line.getString());
		}
		// 逐行挑要翻的：混排 tooltip（英文物品名 + 游戏自带的中文属性行）里中文行留着、英文行照翻
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
				MinecraftClient.getInstance().execute(() ->
						com.mchanhua.client.hud.TranslationHud.setLast(sources, translated));
			}
		});
		return original;
	}

	/** 单行文本（聊天、标题、Boss 栏名都用这个）。 */
	public static Text translateLine(Text line, boolean allowed) {
		return translateLine(line, allowed, false);
	}

	public static Text translateLine(Text line, boolean allowed, boolean mirrorToHud) {
		if (line == null || !allowed) {
			return line;
		}
		// 单组件也可能是一整屏多行文本（地图把规则塞进一个悬浮大字/名牌就是这种），
		// 这种必须按行拆开翻再拼回，否则模型会把中间几行合并、屏幕上只剩一行。
		if (line.getString().indexOf('\n') >= 0) {
			return translateMultiline(line, true);
		}
		List<Text> translated = translateLines(List.of(line), true, mirrorToHud);
		return translated.isEmpty() ? line : translated.get(0);
	}

	/** 已经翻好的行（缓存命中）就返回译文，否则返回 null——给"翻好再显示"的文本用。 */
	public static Text readyOrNull(Text line, boolean allowed) {
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
		return Text.literal(cached.get(0)).setStyle(line.getStyle());
	}

	/**
	 * 翻这句话，翻好后用译文回调（回调在**渲染线程**）。
	 *
	 * **所有回放都必须走 {@link ReplayGuard}**：回放会再进一次钩子，
	 * 不打标记就会"回放→钩子→回放"无限递归（26.x 那版就因此崩过）。
	 */
	public static void requestLater(Text line, boolean allowed, Consumer<Text> replay) {
		if (line == null || !allowed) {
			ReplayGuard.run(line, replay);
			return;
		}
		// 多行文本（地图常把一整屏规则塞进一个 title）必须**按行**翻：
		// 整块发过去模型会把中间几行合并/吃掉（用户报过"翻译后只剩首尾两行"）。
		if (line.getString().indexOf('\n') >= 0) {
			requestMultilineLater(line, replay);
			return;
		}
		Text ready = readyOrNull(line, true);
		if (ready != null) {
			ReplayGuard.run(ready, replay);
			return;
		}
		String source = line.getString();
		service.request(List.of(source), translated -> {
			String text = translated.isEmpty() ? source : translated.get(0);
			Text result = Text.literal(text).setStyle(line.getStyle());
			MinecraftClient.getInstance().execute(() -> {
				com.mchanhua.client.hud.TranslationHud.setLast(List.of(source), List.of(text));
				ReplayGuard.run(result, replay);
			});
		});
	}

	/**
	 * 多行文本的"翻好再显示"：按 {@code \n} 拆行 → 逐行翻 → 按原行数拼回去。
	 * 行数、分段都不会变，模型少给哪行就保留哪行的原文。
	 */
	private static void requestMultilineLater(Text text, Consumer<Text> replay) {
		String raw = text.getString();
		List<String> rawLines = List.of(raw.split("\n", -1));
		List<Integer> indices = TextLines.indicesToTranslate(rawLines);
		if (indices.isEmpty()) {
			ReplayGuard.run(text, replay);
			return;
		}
		List<String> picked = TextLines.pick(rawLines, indices);
		List<String> cached = service.cached(picked);
		if (cached != null) {
			ReplayGuard.run(rebuildMultiline(text, rawLines, indices, cached), replay);
			return;
		}
		service.request(picked, translated -> {
			Text result = rebuildMultiline(text, rawLines, indices, translated);
			MinecraftClient.getInstance().execute(() -> {
				com.mchanhua.client.hud.TranslationHud.setLast(picked, translated);
				ReplayGuard.run(result, replay);
			});
		});
	}

	private static Text rebuildMultiline(Text original, List<String> rawLines,
			List<Integer> indices, List<String> translated) {
		List<String> merged = TextLines.applyTranslations(rawLines, indices, translated);
		return Text.literal(String.join("\n", merged)).setStyle(original.getStyle());
	}

	/**
	 * 带换行的整页文本（书页）：**按行**翻再拼回去，行数与分段不变。
	 */
	public static Text translateMultiline(Text page, boolean allowed) {
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
		return Text.literal(String.join("\n", merged)).setStyle(page.getStyle());
	}

	/** 把译文按行号放回原列表（没翻的行保持原样、原样式）。 */
	private static List<Text> applyTranslation(List<Text> original, List<Integer> indices,
			List<String> translated) {
		List<String> originals = new ArrayList<>(original.size());
		for (Text line : original) {
			originals.add(line.getString());
		}
		List<String> merged = TextLines.applyTranslations(originals, indices, translated);
		List<Text> result = new ArrayList<>(original.size());
		for (int i = 0; i < original.size(); i++) {
			String text = merged.get(i);
			if (text.equals(originals.get(i))) {
				result.add(original.get(i));      // 没翻的行连样式一起原样留着
			} else {
				result.add(Text.literal(text).setStyle(original.get(i).getStyle()));
			}
		}
		return result;
	}
}
