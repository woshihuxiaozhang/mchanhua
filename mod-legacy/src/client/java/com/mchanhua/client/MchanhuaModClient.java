package com.mchanhua.client;

import com.mchanhua.client.config.MchanhuaConfig;
import com.mchanhua.client.hud.TranslationHud;
import com.mchanhua.client.gui.MchanhuaConfigScreen;
import com.mchanhua.client.translate.TextTranslator;
import com.mchanhua.client.translate.TranslationService;

import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.keybinding.v1.KeyBindingHelper;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.option.KeyBinding;
import net.minecraft.client.util.InputUtil;

import org.lwjgl.glfw.GLFW;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;

/**
 * 老版本线（Yarn 映射 / 1.21.1）的客户端入口。
 *
 * 和 26.x 那版同样的三件事：读配置、挂 HUD 小窗、注册热键。
 * 热键一律走 Yarn 的 KeyBindingHelper + KeyBinding#wasPressed，
 * 并且"打开任何界面时不响应"（不然在聊天里打字会误触发）。
 */
public class MchanhuaModClient implements ClientModInitializer {
	public static final Logger LOGGER = LoggerFactory.getLogger("mchanhua-client");

	/** 缓存落盘间隔（tick 数，20 tick ≈ 1 秒）。 */
	private static final int FLUSH_INTERVAL_TICKS = 100;
	private static final String KEY_CATEGORY = "key.categories.mchanhua.main";

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
			boolean screenOpen = client.currentScreen != null;
			while (toggleHudKey.wasPressed()) {
				if (screenOpen) {
					continue;
				}
				TranslationHud.toggle();
				LOGGER.info("HUD 小窗：{}", TranslationHud.visible() ? "开" : "关");
			}
			while (testKey.wasPressed()) {
				if (screenOpen) {
					continue;
				}
				runTestTranslation();
			}
			while (configKey.wasPressed()) {
				// 设置界面本身就是界面，所以这里不能用 screenOpen 把它挡掉
				if (client.currentScreen == null && client.world != null) {
					LOGGER.info("打开设置界面（热键 K）");
					client.setScreen(new MchanhuaConfigScreen(config, service, null));
				}
			}
			if (++tickCounter >= FLUSH_INTERVAL_TICKS) {
				tickCounter = 0;
				service.flush();
			}
		});

		LOGGER.info("mchanhua（老版本线 1.21.1）客户端就绪：tooltip 翻译 {}，HUD {}",
				config.translateTooltips ? "开" : "关", config.hudVisible ? "开" : "关");
		if (!config.ready()) {
			LOGGER.warn("还没填 API Key：请编辑 config/mchanhua.json");
		}
	}

	private static KeyBinding toggleHudKey;
	private static KeyBinding testKey;
	private static KeyBinding configKey;

	private static void registerKeys() {
		toggleHudKey = KeyBindingHelper.registerKeyBinding(new KeyBinding(
				"key.mchanhua.toggle_hud", InputUtil.Type.KEYSYM, GLFW.GLFW_KEY_H, KEY_CATEGORY));
		testKey = KeyBindingHelper.registerKeyBinding(new KeyBinding(
				"key.mchanhua.test", InputUtil.Type.KEYSYM, GLFW.GLFW_KEY_J, KEY_CATEGORY));
		configKey = KeyBindingHelper.registerKeyBinding(new KeyBinding(
				"key.mchanhua.config", InputUtil.Type.KEYSYM, GLFW.GLFW_KEY_K, KEY_CATEGORY));
	}

	/** 按 J：拿一段示例文本走一遍完整链路（配置 → 请求 → 缓存 → HUD）。 */
	private static void runTestTranslation() {
		if (!config.ready()) {
			LOGGER.warn("没有 API Key，无法测试翻译");
			return;
		}
		List<String> sample = List.of(
				"Steel Ingot",
				"A sturdy ingot of steel. Right-click to place.");
		LOGGER.info("开始测试翻译：{}", sample);
		service.request(sample, translated -> MinecraftClient.getInstance().execute(() -> {
			TranslationHud.setLast(sample, translated);
			LOGGER.info("测试翻译完成：{}", translated);
		}));
	}
}
