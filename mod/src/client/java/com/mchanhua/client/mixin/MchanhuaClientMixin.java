package com.mchanhua.client.mixin;

import com.mchanhua.MchanhuaMod;

import net.minecraft.client.Minecraft;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * 最小可用的客户端 Mixin：确认 Mixin 链路在 26.1.2 上能正常工作。
 *
 * 真正要挂的钩子（聊天、tooltip、字幕、Boss Bar 等）在下一步接翻译管线时再加，
 * 那时候类名/方法名以反编译出来的源码为准（Yarn 映射 26.x 已不再发布，现在用的是官方映射）。
 */
@Mixin(Minecraft.class)
public class MchanhuaClientMixin {
	@Inject(at = @At("HEAD"), method = "run")
	private void init(CallbackInfo info) {
		MchanhuaMod.LOGGER.info("mchanhua 客户端 Mixin 生效（Minecraft.run 头部）");
	}
}
