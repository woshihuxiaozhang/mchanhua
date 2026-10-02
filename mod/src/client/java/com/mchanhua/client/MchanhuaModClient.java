package com.mchanhua.client;

import net.fabricmc.api.ClientModInitializer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * 客户端入口：热键、读屏幕/游戏内文本、把译文画到界面上，后面都挂在这里。
 *
 * 目前只做初始化；下一步接翻译管线（先复用桌面版的提示词与术语表）。
 */
public class MchanhuaModClient implements ClientModInitializer {
	public static final Logger LOGGER = LoggerFactory.getLogger("mchanhua-client");

	@Override
	public void onInitializeClient() {
		LOGGER.info("mchanhua 客户端侧就绪：等待接入翻译管线");
	}
}
