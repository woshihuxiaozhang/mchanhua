package com.mchanhua.client;

import net.fabricmc.api.ClientModInitializer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * 老版本线的客户端入口。
 *
 * 现在是"骨架 + 日志"：核心翻译链路（缓存 / 队列 / 逐行挑选 / 配置）已经从 26.x 那版原样搬过来了，
 * 接下来要按 Yarn 的名字把版本层（tooltip / 聊天 / 标题 / 告示牌 / 悬浮字 / 书页 / HUD / 设置界面）
 * 逐个接上——那就是 `port-todo/` 里列的那几个文件。
 */
public class MchanhuaModClient implements ClientModInitializer {
	public static final Logger LOGGER = LoggerFactory.getLogger("mchanhua-client");

	@Override
	public void onInitializeClient() {
		LOGGER.info("mchanhua（老版本线）客户端就绪：核心链路已就位，版本层移植中");
	}
}
