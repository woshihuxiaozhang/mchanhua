package com.mchanhua;

import net.fabricmc.api.ModInitializer;

// Yarn 映射：1.21.x 里 Identifier 在 net.minecraft.util 下
import net.minecraft.util.Identifier;

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
		LOGGER.info("mchanhua 已加载：屏幕取词翻译的模组版（老版本线：Minecraft 1.21.1 / Fabric）");
	}

	public static Identifier id(String path) {
		// Yarn 下是 Identifier.of(ns, path)（官方映射那版叫 fromNamespaceAndPath）
		return Identifier.of(MOD_ID, path);
	}
}
