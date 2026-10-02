package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.client.renderer.blockentity.AbstractSignRenderer;
import net.minecraft.client.renderer.blockentity.state.SignRenderState;
import net.minecraft.client.renderer.feature.ModelFeatureRenderer;
import net.minecraft.network.chat.Component;
import net.minecraft.world.level.block.entity.SignBlockEntity;
import net.minecraft.world.level.block.entity.SignText;
import net.minecraft.world.phys.Vec3;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

import java.util.ArrayList;
import java.util.List;

/**
 * 世界里告示牌的翻译（门禁牌 DISABLE DOOR SECURITY、房间号 CELL 01 这类）。
 *
 * 挂点选在**渲染状态**上而不是文本源头：SignBlockEntity 里的 SignText 是客户端数据，
 * 直接改它有风险（单人存档会被写回、编辑界面里也会变成译文）。
 * 这里只在"这一帧要画什么"的阶段换掉，原文一个字节都不动。
 *
 * 注意 {@link SignText} 是不可变的：setMessage / setColor 都返回新对象，
 * 所以我们用公开构造造一份副本再改，绝不碰方块实体手里那份。
 */
@Mixin(AbstractSignRenderer.class)
public class SignRendererMixin {

	@Inject(
			method = "extractRenderState(Lnet/minecraft/world/level/block/entity/SignBlockEntity;Lnet/minecraft/client/renderer/blockentity/state/SignRenderState;FLnet/minecraft/world/phys/Vec3;Lnet/minecraft/client/renderer/feature/ModelFeatureRenderer$CrumblingOverlay;)V",
			at = @At("TAIL")
	)
	private void mchanhua$translateSign(SignBlockEntity sign, SignRenderState state, float partialTick,
			Vec3 cameraPos, ModelFeatureRenderer.CrumblingOverlay crumbling, CallbackInfo ci) {
		if (!TextTranslator.signsEnabled()) {
			return;
		}
		state.frontText = translate(state.frontText);
		state.backText = translate(state.backText);
	}

	/** 翻一面的 4 行；没有译文可用时原样返回（缓存命中后，下一帧就是中文）。 */
	private static SignText translate(SignText text) {
		if (text == null) {
			return null;
		}
		List<Component> lines = new ArrayList<>(SignText.LINES);
		for (int i = 0; i < SignText.LINES; i++) {
			lines.add(text.getMessage(i, false));
		}
		List<Component> translated = TextTranslator.translateLines(lines, true);
		if (translated == lines) {
			return text;                 // 没得翻（空牌子 / 已经是中文 / 还没翻好）
		}
		SignText copy = new SignText();
		copy = copy.setColor(text.getColor());
		copy = copy.setHasGlowingText(text.hasGlowingText());
		for (int i = 0; i < SignText.LINES; i++) {
			copy = copy.setMessage(i, translated.get(i));
		}
		return copy;
	}
}
