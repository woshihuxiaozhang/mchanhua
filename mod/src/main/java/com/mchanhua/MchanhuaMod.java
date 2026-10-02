package com.mchanhua;

import net.fabricmc.api.ModInitializer;

import net.minecraft.resources.Identifier;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * mchanhua 模组的公共入口。
 *
 * 这一版先只做初始化和日志：真正的翻译逻辑放在客户端侧
 * （{@link com.mchanhua.client.MchanhuaModClient}），
 * 因为要读的是"玩家眼前看到的那点字"，而不是服务端数据。
 */
public class MchanhuaMod implements ModInitializer {
	public static final String MOD_ID = "mchanhua";
	public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

	@Override
	public void onInitialize() {
		LOGGER.info("mchanhua 已加载：屏幕取词翻译的模组版（目标 Minecraft 26.1.2 / Fabric）");
	}

	public static Identifier id(String path) {
		return Identifier.fromNamespaceAndPath(MOD_ID, path);
	}
}
