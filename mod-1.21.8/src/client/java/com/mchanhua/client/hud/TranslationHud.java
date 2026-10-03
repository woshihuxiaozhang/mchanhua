package com.mchanhua.client.hud;

import com.mchanhua.client.config.MchanhuaConfig;

import net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.DrawContext;

import java.util.ArrayList;
import java.util.List;

/**
 * HUD 小窗（老版本线 / Yarn 映射版）：右上角显示最近一次翻译（译文 + 原文对照）。
 *
 * 26.x 那版走的是 Fabric 的 HudElementRegistry + GuiGraphicsExtractor；
 * 这一版走老的 {@link HudRenderCallback} + {@link DrawContext}（1.21.1 只有这个）。
 * 排版逻辑仍然复用 HudTextLayout（纯逻辑，和版本无关）。
 */
public final class TranslationHud {
	private static final int MARGIN = 8;
	private static final int PADDING = 6;
	private static final int LINE_HEIGHT = 10;
	private static final int MAX_WIDTH = 260;
	/** 最多显示几行译文 / 原文 */
	private static final int MAX_LINES = 3;

	private static final int COLOR_BACKGROUND = 0xCC101418;
	private static final int COLOR_BORDER = 0x66FFFFFF;
	private static final int COLOR_TITLE = 0xFF7FB2FF;
	private static final int COLOR_TARGET = 0xFFFFFFFF;
	private static final int COLOR_SOURCE = 0xFF9AA0A6;

	private static volatile List<String> lastSource = List.of();
	private static volatile List<String> lastTarget = List.of();
	private static volatile long lastUpdateAt = 0L;
	private static MchanhuaConfig config;

	private TranslationHud() {
	}

	public static void register(MchanhuaConfig modConfig) {
		config = modConfig;
		HudRenderCallback.EVENT.register((context, tickCounter) -> render(context));
	}

	public static void setLast(List<String> source, List<String> target) {
		lastSource = List.copyOf(source);
		lastTarget = List.copyOf(target);
		lastUpdateAt = System.currentTimeMillis();
	}

	/** 超过配置的时间没更新就自动收起（0 = 一直显示）。 */
	private static boolean hiddenByTimeout() {
		int seconds = config == null ? 6 : config.hudAutoHideSeconds;
		if (seconds <= 0 || lastUpdateAt == 0L) {
			return false;
		}
		return System.currentTimeMillis() - lastUpdateAt > seconds * 1000L;
	}

	public static void toggle() {
		if (config != null) {
			config.hudVisible = !config.hudVisible;
			config.save();
		}
	}

	public static boolean visible() {
		return config == null || config.hudVisible;
	}

	private static void render(DrawContext context) {
		if (!visible() || hiddenByTimeout()) {
			return;
		}
		MinecraftClient client = MinecraftClient.getInstance();
		// 打开背包/箱子这类界面时不画：物品 tooltip 只在这些界面里出现，压在它上面会挡视线
		if (client.currentScreen != null) {
			return;
		}
		String title = "mchanhua";
		int innerWidth = MAX_WIDTH - PADDING * 2;
		List<String> targetLines = new ArrayList<>();
		List<String> sourceLines = new ArrayList<>();

		if (lastTarget.isEmpty()) {
			targetLines.addAll(wrap(client,
					config != null && config.ready()
							? "把鼠标放到物品上看译文"
							: "还没填 API Key（config/mchanhua.json）",
					innerWidth, MAX_LINES));
		} else {
			targetLines.addAll(wrapAll(client, lastTarget, innerWidth, MAX_LINES));
			if (config == null || config.showOriginal) {
				sourceLines.addAll(wrapAll(client, lastSource, innerWidth, MAX_LINES));
			}
		}

		int contentWidth = client.textRenderer.getWidth(title);
		for (String line : targetLines) {
			contentWidth = Math.max(contentWidth, client.textRenderer.getWidth(line));
		}
		for (String line : sourceLines) {
			contentWidth = Math.max(contentWidth, client.textRenderer.getWidth(line));
		}
		int width = Math.min(MAX_WIDTH, contentWidth + PADDING * 2);
		int height = PADDING * 2 + LINE_HEIGHT * (1 + targetLines.size() + sourceLines.size());
		int x = context.getScaledWindowWidth() - width - MARGIN;
		int y = MARGIN;

		context.fill(x - 1, y - 1, x + width + 1, y + height + 1, COLOR_BORDER);
		context.fill(x, y, x + width, y + height, COLOR_BACKGROUND);
		context.drawText(client.textRenderer, title, x + PADDING, y + PADDING, COLOR_TITLE, false);

		int lineY = y + PADDING + LINE_HEIGHT;
		for (String line : targetLines) {
			context.drawText(client.textRenderer, line, x + PADDING, lineY, COLOR_TARGET, false);
			lineY += LINE_HEIGHT;
		}
		for (String line : sourceLines) {
			context.drawText(client.textRenderer, line, x + PADDING, lineY, COLOR_SOURCE, false);
			lineY += LINE_HEIGHT;
		}
	}

	private static List<String> wrap(MinecraftClient client, String line, int maxWidth, int maxLines) {
		return HudTextLayout.wrap(client.textRenderer::getWidth, line, maxWidth, maxLines);
	}

	private static List<String> wrapAll(MinecraftClient client, List<String> lines, int maxWidth,
			int maxLines) {
		return HudTextLayout.wrapAll(client.textRenderer::getWidth, lines, maxWidth, maxLines);
	}
}
