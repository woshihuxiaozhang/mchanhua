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
	/**
	 * 翻译聊天栏里收到的消息。
	 *
	 * 注意：多人服务器上，这等于把聊天内容发给第三方翻译服务，
	 * 有些服务器不允许这么做，所以这个开关单独拿出来，随时可以关。
	 */
	public boolean translateChat = true;
	/**
	 * 翻译世界里的告示牌文字（渲染状态层面替换，不动存档数据、也不动编辑界面）。
	 *
	 * 默认开：地图里的门禁牌、房间号（DISABLE DOOR SECURITY / CELL 01）这类基本都靠它。
	 */
	public boolean translateSigns = true;
	/**
	 * 实体头顶的名字、以及地图用 text_display 摆的悬浮大字（章节名、任务名）。
	 *
	 * 玩家自己的游戏 ID 不翻（那是昵称）。同样只在渲染层动手，实体数据不变。
	 */
	public boolean translateNametags = true;
	/** HUD 小窗是否显示（也可以按热键开关）。 */
	public boolean hudVisible = true;
	/** HUD 里是否带上原文。 */
	public boolean showOriginal = true;
	/** HUD 显示多少秒后自动收起（0 = 一直显示）。挡视野的话就调小。 */
	public int hudAutoHideSeconds = 6;
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
		// 本地 Ollama 之类的服务不需要 key，别把它误判成"没配好"
		return (apiKey != null && !apiKey.isBlank()) || !ProviderPresets.needsKey(baseUrl);
	}
}
