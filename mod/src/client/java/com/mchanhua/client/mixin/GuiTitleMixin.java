package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.client.gui.Gui;
import net.minecraft.network.chat.Component;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyVariable;

/**
 * 屏幕上的大字标题、副标题、以及物品栏上方的 ActionBar 提示。
 *
 * 剧情地图常用 /title、/subtitle、/actionbar 显示台词与任务提示，这里一次全接上。
 */
@Mixin(Gui.class)
public class GuiTitleMixin {
	@ModifyVariable(method = "setTitle(Lnet/minecraft/network/chat/Component;)V",
			at = @At("HEAD"), argsOnly = true)
	private Component mchanhua$translateTitle(Component text) {
		return TextTranslator.translateLine(text, TextTranslator.enabled());
	}

	@ModifyVariable(method = "setSubtitle(Lnet/minecraft/network/chat/Component;)V",
			at = @At("HEAD"), argsOnly = true)
	private Component mchanhua$translateSubtitle(Component text) {
		return TextTranslator.translateLine(text, TextTranslator.enabled());
	}

	@ModifyVariable(method = "setOverlayMessage(Lnet/minecraft/network/chat/Component;Z)V",
			at = @At("HEAD"), argsOnly = true)
	private Component mchanhua$translateOverlay(Component text) {
		return TextTranslator.translateLine(text, TextTranslator.enabled());
	}
}
