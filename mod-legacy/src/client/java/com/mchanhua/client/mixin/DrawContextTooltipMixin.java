package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.client.gui.DrawContext;
import net.minecraft.text.Text;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyVariable;

import java.util.List;

/**
 * tooltip 翻译的统一入口（Yarn 版）：1.21.x 里所有物品 tooltip 最后都会走
 * {@code DrawContext.drawTooltip(TextRenderer, List, Optional, int, int)}。
 * 挂这一个方法比逐个界面挂稳得多。
 */
@Mixin(DrawContext.class)
public class DrawContextTooltipMixin {
	@ModifyVariable(
			method = "drawTooltip(Lnet/minecraft/client/font/TextRenderer;Ljava/util/List;Ljava/util/Optional;II)V",
			at = @At("HEAD"),
			argsOnly = true
	)
	private List<Text> mchanhua$translateTooltip(List<Text> lines) {
		if (lines == null || lines.isEmpty()) {
			return lines;
		}
		return TextTranslator.translateLines(lines, TextTranslator.tooltipsEnabled());
	}

	/** 有些界面只画"物品名"这一行，走的是单 Text 重载。 */
	@ModifyVariable(
			method = "drawTooltip(Lnet/minecraft/client/font/TextRenderer;Lnet/minecraft/text/Text;II)V",
			at = @At("HEAD"),
			argsOnly = true
	)
	private Text mchanhua$translateSingleLine(Text line) {
		return TextTranslator.translateLine(line, TextTranslator.tooltipsEnabled());
	}
}
