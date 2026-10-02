package com.mchanhua.client.hud;

import com.mchanhua.MchanhuaMod;
import com.mchanhua.client.config.MchanhuaConfig;

import net.fabricmc.fabric.api.client.rendering.v1.hud.HudElement;
import net.fabricmc.fabric.api.client.rendering.v1.hud.HudElementRegistry;
import net.minecraft.client.DeltaTracker;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.Identifier;

import java.util.ArrayList;
import java.util.List;

/**
 * HUD 小窗：在屏幕右上角显示最近一次翻译（译文 + 原文对照）。
 *
 * 和桌面版的小窗是一个思路——不遮挡游戏主画面、只显示这一屏需要看懂的那点字。
 */
public final class TranslationHud implements HudElement {
	private static final int MARGIN = 8;
	private static final int PADDING = 6;
	private static final int LINE_HEIGHT = 10;
	private static final int MAX_WIDTH = 260;
	/** 最多显示几行译文 / 原文（tooltip 那种长文本不会把半个屏幕糊住）。 */
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
		HudElementRegistry.addLast(Identifier.fromNamespaceAndPath(MchanhuaMod.MOD_ID, "translation"), new TranslationHud());
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

	@Override
	public void extractRenderState(GuiGraphicsExtractor graphics, DeltaTracker delta) {
		if (!visible() || hiddenByTimeout()) {
			return;
		}
		Minecraft minecraft = Minecraft.getInstance();
		// 打开背包/箱子这类界面时不画：物品 tooltip 只在这些界面里出现，
		// HUD 挤在右上角会正好压在它上面（用户反馈"挡住翻译"）。
		if (minecraft.screen != null) {
			return;
		}
		String title = "mchanhua";
		int innerWidth = MAX_WIDTH - PADDING * 2;
		List<String> targetLines = new ArrayList<>();
		List<String> sourceLines = new ArrayList<>();

		if (lastTarget.isEmpty()) {
			targetLines.addAll(wrap(minecraft,
					config != null && config.ready()
							? "把鼠标放到物品上看译文"
							: "还没填 API Key：按 K 打开设置",
					innerWidth, MAX_LINES));
		} else {
			targetLines.addAll(wrapAll(minecraft, lastTarget, innerWidth, MAX_LINES));
			if (config == null || config.showOriginal) {
				sourceLines.addAll(wrapAll(minecraft, lastSource, innerWidth, MAX_LINES));
			}
		}

		int contentWidth = minecraft.font.width(title);
		for (String line : targetLines) {
			contentWidth = Math.max(contentWidth, minecraft.font.width(line));
		}
		for (String line : sourceLines) {
			contentWidth = Math.max(contentWidth, minecraft.font.width(line));
		}
		int width = Math.min(MAX_WIDTH, contentWidth + PADDING * 2);
		int height = PADDING * 2 + LINE_HEIGHT * (1 + targetLines.size() + sourceLines.size());
		int x = graphics.guiWidth() - width - MARGIN;
		int y = MARGIN;

		graphics.fill(x - 1, y - 1, x + width + 1, y + height + 1, COLOR_BORDER);
		graphics.fill(x, y, x + width, y + height, COLOR_BACKGROUND);
		graphics.text(minecraft.font, Component.literal(title), x + PADDING, y + PADDING, COLOR_TITLE);

		int lineY = y + PADDING + LINE_HEIGHT;
		for (String line : targetLines) {
			graphics.text(minecraft.font, Component.literal(line), x + PADDING, lineY, COLOR_TARGET);
			lineY += LINE_HEIGHT;
		}
		for (String line : sourceLines) {
			graphics.text(minecraft.font, Component.literal(line), x + PADDING, lineY, COLOR_SOURCE);
			lineY += LINE_HEIGHT;
		}
	}

	private static List<String> wrap(Minecraft minecraft, String line, int maxWidth, int maxLines) {
		return HudTextLayout.wrap(minecraft.font::width, line, maxWidth, maxLines);
	}

	private static List<String> wrapAll(Minecraft minecraft, List<String> lines, int maxWidth, int maxLines) {
		return HudTextLayout.wrapAll(minecraft.font::width, lines, maxWidth, maxLines);
	}
}
