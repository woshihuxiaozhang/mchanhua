package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.block.entity.SignText;
import net.minecraft.client.render.block.entity.SignBlockEntityRenderer;
import net.minecraft.text.Text;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyVariable;

import java.util.List;

/**
 * 世界里告示牌的翻译（老版本线 / Yarn 映射）。
 *
 * 1.21.1 还没有 26.x 那套 render state，所以挂点是渲染器里真正画字的那个方法：
 * {@code SignBlockEntityRenderer.renderText(BlockPos, SignText, ...)} —— 它拿到的就是牌子某一面的四行文本。
 *
 * 和我们一贯的做法一样：造一份**副本**去画，方块实体里那份原文一个字节都不动。
 */
@Mixin(SignBlockEntityRenderer.class)
public class SignRendererMixin {

	@ModifyVariable(method = "renderText", at = @At("HEAD"), argsOnly = true)
	private SignText mchanhua$translateSign(SignText text) {
		if (text == null || !TextTranslator.signsEnabled()) {
			return text;
		}
		List<Text> lines = List.of(
				text.getMessage(0, false),
				text.getMessage(1, false),
				text.getMessage(2, false),
				text.getMessage(3, false));
		List<Text> translated = TextTranslator.translateLines(lines, true);
		if (translated == lines) {
			return text;                 // 没得翻 / 还没翻好，这一帧照旧
		}
		SignText copy = new SignText();
		copy = copy.withColor(text.getColor());
		copy = copy.withGlowing(text.isGlowing());
		for (int i = 0; i < 4; i++) {
			copy = copy.withMessage(i, translated.get(i));
		}
		return copy;
	}
}
