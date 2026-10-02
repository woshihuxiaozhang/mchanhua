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

	private static final int COLOR_BACKGROUND = 0xCC101418;
	private static final int COLOR_BORDER = 0x66FFFFFF;
	private static final int COLOR_TITLE = 0xFF7FB2FF;
	private static final int COLOR_TARGET = 0xFFFFFFFF;
	private static final int COLOR_SOURCE = 0xFF9AA0A6;

	private static volatile List<String> lastSource = List.of();
	private static volatile List<String> lastTarget = List.of();
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
		if (!visible()) {
			return;
		}
		Minecraft minecraft = Minecraft.getInstance();
		List<Component> targetLines = new ArrayList<>();
		List<Component> sourceLines = new ArrayList<>();
		String title = "mchanhua";

		if (lastTarget.isEmpty()) {
			targetLines.add(Component.literal(config != null && config.ready()
					? "把鼠标放到物品上看译文"
					: "还没填 API Key（config/mchanhua.json）"));
		} else {
			for (String line : lastTarget) {
				targetLines.add(Component.literal(line));
			}
			if (config == null || config.showOriginal) {
				for (String line : lastSource) {
					sourceLines.add(Component.literal(line));
				}
			}
		}

		int width = Math.min(MAX_WIDTH, Math.max(minecraft.font.width(title),
				maxWidth(minecraft, targetLines, sourceLines)) + PADDING * 2);
		int height = PADDING * 2 + LINE_HEIGHT * (1 + targetLines.size() + sourceLines.size());
		int x = graphics.guiWidth() - width - MARGIN;
		int y = MARGIN;

		graphics.fill(x - 1, y - 1, x + width + 1, y + height + 1, COLOR_BORDER);
		graphics.fill(x, y, x + width, y + height, COLOR_BACKGROUND);
		graphics.text(minecraft.font, Component.literal(title), x + PADDING, y + PADDING, COLOR_TITLE);

		int lineY = y + PADDING + LINE_HEIGHT;
		for (Component line : targetLines) {
			graphics.text(minecraft.font, line, x + PADDING, lineY, COLOR_TARGET);
			lineY += LINE_HEIGHT;
		}
		for (Component line : sourceLines) {
			graphics.text(minecraft.font, line, x + PADDING, lineY, COLOR_SOURCE);
			lineY += LINE_HEIGHT;
		}
	}

	private static int maxWidth(Minecraft minecraft, List<Component> first, List<Component> second) {
		int width = 0;
		for (Component line : first) {
			width = Math.max(width, minecraft.font.width(line));
		}
		for (Component line : second) {
			width = Math.max(width, minecraft.font.width(line));
		}
		return width;
	}
}
