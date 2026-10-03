package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.client.render.entity.DisplayEntityRenderer;
import net.minecraft.text.Text;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyVariable;

/**
 * 世界里"悬浮大字"的翻译（1.21.8 / Yarn）。
 *
 * 1.21.8 的实体渲染是"状态驱动"的：每帧都会调
 * {@code TextDisplayEntityRenderer.getLines(Text, int)} 把文本切成行再画。
 * 所以直接改这个方法拿到的 **Text 入参**最省事——渲染状态每帧重建，也就没有
 * "译文晚到、缓存不刷新"的问题（1.21.1 那版得手动把缓存置空）。
 *
 * 不能挂 {@code TextDisplayEntity.getText()}：它被存档序列化调用，会把译文写进存档。
 */
@Mixin(DisplayEntityRenderer.TextDisplayEntityRenderer.class)
public class TextDisplayRendererMixin {

	@ModifyVariable(method = "getLines", at = @At("HEAD"), argsOnly = true)
	private Text mchanhua$translateDisplayText(Text text) {
		if (text == null || !TextTranslator.nametagsEnabled()) {
			return text;
		}
		return TextTranslator.translateLine(text, true);
	}
}
