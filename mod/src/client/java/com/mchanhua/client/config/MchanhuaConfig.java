package com.mchanhua.client.config;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.mchanhua.MchanhuaMod;

import net.fabricmc.loader.api.FabricLoader;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/** 模组配置：一个 JSON 文件，第一次运行自动生成。 */
public final class MchanhuaConfig {
	private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

	/** 翻译服务（与桌面版一致，默认 DeepSeek）。 */
	public String baseUrl = "https://api.deepseek.com";
	public String model = "deepseek-chat";
	public String apiKey = "";
	/** 目标语言，写进提示词。 */
	public String targetLanguage = "简体中文";

	/** 悬停物品时自动翻译 tooltip。 */
	public boolean translateTooltips = true;
	/** HUD 小窗是否显示（也可以按热键开关）。 */
	public boolean hudVisible = true;
	/** HUD 里是否带上原文。 */
	public boolean showOriginal = true;
	/** 单次请求超时（秒）。 */
	public int requestTimeoutSeconds = 30;

	private static Path file() {
		return FabricLoader.getInstance().getConfigDir().resolve("mchanhua.json");
	}

	public static MchanhuaConfig load() {
		Path path = file();
		if (Files.exists(path)) {
			try {
				MchanhuaConfig config = GSON.fromJson(Files.readString(path, StandardCharsets.UTF_8), MchanhuaConfig.class);
				if (config != null) {
					return config;
				}
			} catch (Exception e) {
				MchanhuaMod.LOGGER.warn("读取配置失败，改用默认配置：{}", e.toString());
			}
		}
		MchanhuaConfig config = new MchanhuaConfig();
		config.save();
		MchanhuaMod.LOGGER.info("已生成配置文件：{}（把 API Key 填进去就能翻译了）", path);
		return config;
	}

	public void save() {
		Path path = file();
		try {
			Files.createDirectories(path.getParent());
			Files.writeString(path, GSON.toJson(this), StandardCharsets.UTF_8);
		} catch (IOException e) {
			MchanhuaMod.LOGGER.warn("保存配置失败：{}", e.toString());
		}
	}

	public boolean ready() {
		return apiKey != null && !apiKey.isBlank();
	}
}
