package com.mchanhua.client;

import com.mchanhua.MchanhuaMod;
import com.mchanhua.client.config.MchanhuaConfig;
import com.mchanhua.client.hud.TranslationHud;
import com.mchanhua.client.translate.TranslationService;
import com.mchanhua.client.translate.TextTranslator;
import com.mojang.blaze3d.platform.InputConstants;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.keymapping.v1.KeyMappingHelper;

import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.resources.Identifier;

import org.lwjgl.glfw.GLFW;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;

/**
 * 客户端入口：热键、读屏幕/游戏内文本、把译文画到界面上，后面都挂在这里。
 *
 * 这一版做了三件事：
 * 1. 悬停物品时翻译 tooltip（{@link TooltipTranslator} + ScreenTooltipMixin）；
 * 2. HUD 小窗显示最近一次翻译（原文 + 译文对照）；
 * 3. 两个热键：H 开关小窗、J 测试一次翻译（用来确认 API Key 通不通）。
 */
public class MchanhuaModClient implements ClientModInitializer {
	public static final Logger LOGGER = LoggerFactory.getLogger("mchanhua-client");

	/** 缓存落盘间隔（tick 数，20 tick ≈ 1 秒）。 */
	private static final int FLUSH_INTERVAL_TICKS = 100;

	private static MchanhuaConfig config;
	private static TranslationService service;
	private static int tickCounter = 0;

	@Override
	public void onInitializeClient() {
		config = MchanhuaConfig.load();
		service = new TranslationService(config);

		TextTranslator.init(config, service);
		TranslationHud.register(config);
		registerKeys();

		ClientTickEvents.END_CLIENT_TICK.register(client -> {
			while (toggleHudKey.consumeClick()) {
				TranslationHud.toggle();
				LOGGER.info("HUD 小窗：{}", TranslationHud.visible() ? "开" : "关");
			}
			while (testKey.consumeClick()) {
				runTestTranslation();
			}
			if (++tickCounter >= FLUSH_INTERVAL_TICKS) {
				tickCounter = 0;
				service.flush();
			}
		});

		LOGGER.info("mchanhua 客户端侧就绪：tooltip 翻译 {}，HUD {}",
				config.translateTooltips ? "开" : "关", config.hudVisible ? "开" : "关");
		if (!config.ready()) {
			LOGGER.warn("还没填 API Key：请编辑 config/mchanhua.json，或直接用桌面版里那份 key");
		}
	}

	private static KeyMapping toggleHudKey;
	private static KeyMapping testKey;

	private static void registerKeys() {
		KeyMapping.Category category = KeyMapping.Category.register(
				Identifier.fromNamespaceAndPath(MchanhuaMod.MOD_ID, "main"));
		toggleHudKey = KeyMappingHelper.registerKeyMapping(new KeyMapping(
				"key.mchanhua.toggle_hud", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_H, category));
		testKey = KeyMappingHelper.registerKeyMapping(new KeyMapping(
				"key.mchanhua.test", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_J, category));
	}

	/** 按 J：拿一段示例物品文本走一遍完整链路（配置 → 请求 → 缓存 → HUD）。 */
	private static void runTestTranslation() {
		if (!config.ready()) {
			LOGGER.warn("没有 API Key，无法测试翻译");
			return;
		}
		List<String> sample = List.of(
				"Steel Ingot",
				"A sturdy ingot of steel. Right-click to place.");
		LOGGER.info("开始测试翻译：{}", sample);
		service.request(sample, translated -> Minecraft.getInstance().execute(() -> {
			TranslationHud.setLast(sample, translated);
			LOGGER.info("测试翻译完成：{}", translated);
		}));
	}
}
