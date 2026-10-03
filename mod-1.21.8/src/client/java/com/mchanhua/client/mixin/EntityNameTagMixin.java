package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.ReplayGuard;
import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.client.render.VertexConsumerProvider;
import net.minecraft.client.render.entity.EntityRenderer;
import net.minecraft.client.render.entity.state.EntityRenderState;
import net.minecraft.client.render.entity.state.PlayerEntityRenderState;
import net.minecraft.client.util.math.MatrixStack;
import net.minecraft.text.Text;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * 实体头顶名字的翻译（1.21.8 / Yarn）。
 *
 * 1.21.2 之后渲染器改成"状态驱动"：名字牌走
 * {@code renderLabelIfPresent(EntityRenderState, Text, ...)}，玩家身份靠
 * {@code PlayerEntityRenderState} 判断（玩家 ID 是昵称，不翻）。
 *
 * 换成功就拦住这一次、用译文重画一遍；回放必须打 ReplayGuard 标记，否则会无限递归。
 */
@Mixin(EntityRenderer.class)
public class EntityNameTagMixin {

	@Inject(method = "renderLabelIfPresent", at = @At("HEAD"), cancellable = true)
	private void mchanhua$translateLabel(EntityRenderState state, Text text, MatrixStack matrices,
			VertexConsumerProvider vertexConsumers, int light, CallbackInfo ci) {
		if (text == null || state instanceof PlayerEntityRenderState || !TextTranslator.nametagsEnabled()
				|| TextTranslator.isReplaying()) {
			return;
		}
		Text translated = TextTranslator.translateLine(text, true);
		if (translated == text) {
			return;                      // 没得翻 / 还没翻好，这一帧照旧画原文
		}
		ci.cancel();
		// renderLabelIfPresent 是 protected，走 @Invoker 造的公开桥
		ReplayGuard.run(translated, value -> ((EntityRendererInvoker) (Object) this)
				.mchanhua$renderLabelIfPresent(state, value, matrices, vertexConsumers, light));
	}
}
