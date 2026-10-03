package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.block.entity.SignBlockEntity;
import net.minecraft.block.entity.SignText;
import net.minecraft.client.render.block.entity.AbstractSignBlockEntityRenderer;
import net.minecraft.text.Text;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

import java.util.List;

/**
 * 世界里告示牌的翻译（1.21.8 / Yarn）。
 *
 * 1.21.8 已经没有 1.21.1 那个 {@code renderText(..., SignText, ...)} 了：
 * 渲染器直接从方块实体读文本（`SignBlockEntity.getFrontText()/getBackText()`），
 * 所以这里改成重定向这两次调用，返回一份**翻译过的副本**——
 * 方块实体里那份原文一个字节都不动。
 */
@Mixin(AbstractSignBlockEntityRenderer.class)
public class SignRendererMixin {

	@Redirect(
			// 文本是在私有的 render(...) 里读的（公开那个只是转发）
			method = "render(Lnet/minecraft/block/entity/SignBlockEntity;Lnet/minecraft/client/util/math/MatrixStack;Lnet/minecraft/client/render/VertexConsumerProvider;IILnet/minecraft/block/BlockState;Lnet/minecraft/block/AbstractSignBlock;Lnet/minecraft/block/WoodType;Lnet/minecraft/client/model/Model;)V",
			at = @At(value = "INVOKE", target = "Lnet/minecraft/block/entity/SignBlockEntity;getFrontText()Lnet/minecraft/block/entity/SignText;")
	)
	private SignText mchanhua$front(SignBlockEntity sign) {
		return translate(sign.getFrontText());
	}

	@Redirect(
			method = "render(Lnet/minecraft/block/entity/SignBlockEntity;Lnet/minecraft/client/util/math/MatrixStack;Lnet/minecraft/client/render/VertexConsumerProvider;IILnet/minecraft/block/BlockState;Lnet/minecraft/block/AbstractSignBlock;Lnet/minecraft/block/WoodType;Lnet/minecraft/client/model/Model;)V",
			at = @At(value = "INVOKE", target = "Lnet/minecraft/block/entity/SignBlockEntity;getBackText()Lnet/minecraft/block/entity/SignText;")
	)
	private SignText mchanhua$back(SignBlockEntity sign) {
		return translate(sign.getBackText());
	}

	/** 翻一面的四行；没得翻就原样返回。 */
	private static SignText translate(SignText text) {
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
			return text;
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
