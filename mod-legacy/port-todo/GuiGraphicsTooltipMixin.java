package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.network.chat.Component;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyVariable;

import java.util.List;

/**
 * tooltip 翻译的统一入口。
 *
 * 26.x 里不管是背包、箱子还是创造物品栏，物品 tooltip 最后都会走
 * {@code GuiGraphicsExtractor.setTooltipForNextFrame(Font, List<Component>, Optional, int, int, Identifier)}。
 * 挂在这一个方法上，比逐个界面挂（Screen.getTooltipFromItem / AbstractContainerScreen…）稳得多——
 * 26.x 的创造物品栏就自己覆盖了 getTooltipFromContainerItem，父类注入根本不会执行。
 */
@Mixin(GuiGraphicsExtractor.class)
public class GuiGraphicsTooltipMixin {
	@ModifyVariable(
			method = "setTooltipForNextFrame(Lnet/minecraft/client/gui/Font;Ljava/util/List;Ljava/util/Optional;IILnet/minecraft/resources/Identifier;)V",
			at = @At("HEAD"),
			argsOnly = true
	)
	private List<Component> mchanhua$translateTooltip(List<Component> lines) {
		if (lines == null || lines.isEmpty()) {
			return lines;
		}
		return TextTranslator.translateLines(lines, TextTranslator.tooltipsEnabled());
	}

	/**
	 * 有些界面（比如创造模式物品栏）只画"物品名"这一行，走的是单 Component 的重载。
	 */
	@ModifyVariable(
			method = "setTooltipForNextFrame(Lnet/minecraft/client/gui/Font;Lnet/minecraft/network/chat/Component;II)V",
			at = @At("HEAD"),
			argsOnly = true
	)
	private Component mchanhua$translateSingleLine(Component line) {
		return TextTranslator.translateLine(line, TextTranslator.tooltipsEnabled());
	}

	@ModifyVariable(
			method = "setTooltipForNextFrame(Lnet/minecraft/client/gui/Font;Lnet/minecraft/network/chat/Component;IILnet/minecraft/resources/Identifier;)V",
			at = @At("HEAD"),
			argsOnly = true
	)
	private Component mchanhua$translateSingleLineStyled(Component line) {
		return TextTranslator.translateLine(line, TextTranslator.tooltipsEnabled());
	}
}
