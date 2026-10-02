package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.ReplayGuard;
import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.client.render.VertexConsumerProvider;
import net.minecraft.client.render.entity.EntityRenderer;
import net.minecraft.client.util.math.MatrixStack;
import net.minecraft.entity.Entity;
import net.minecraft.entity.player.PlayerEntity;
import net.minecraft.text.Text;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * 实体头顶名字的翻译（老版本线 / Yarn 映射）。
 *
 * 1.21.1 里名字牌走 {@code EntityRenderer.renderLabelIfPresent(entity, text, ...)}：
 * 我们先按缓存把文本换掉，换成功就拦住这一次、用译文重新画一遍——回放必须打 ReplayGuard 标记，
 * 否则"回放→钩子→回放"会无限递归。
 *
 * **玩家 ID 不翻**：那是昵称不是游戏文本。
 */
@Mixin(EntityRenderer.class)
public class EntityNameTagMixin {

	@Inject(method = "renderLabelIfPresent", at = @At("HEAD"), cancellable = true)
	private void mchanhua$translateLabel(Entity entity, Text text, MatrixStack matrices,
			VertexConsumerProvider vertexConsumers, int light, CallbackInfo ci) {
		if (text == null || entity instanceof PlayerEntity || !TextTranslator.nametagsEnabled()
				|| TextTranslator.isReplaying()) {
			return;
		}
		Text translated = TextTranslator.translateLine(text, true);
		if (translated == text) {
			return;                      // 没得翻 / 还没翻好，这一帧照旧画原文
		}
		ci.cancel();
		// 1.21.1 的 EntityRenderer 只有一个类型参数（T extends Entity），
		// 而且 renderLabelIfPresent 是 protected，所以走 @Invoker 造的公开桥
		ReplayGuard.run(translated, value -> ((EntityRendererInvoker) (Object) this)
				.mchanhua$renderLabelIfPresent(entity, value, matrices, vertexConsumers, light));
	}
}
