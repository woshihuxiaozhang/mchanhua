package com.mchanhua.client.mixin;

import net.minecraft.client.render.VertexConsumerProvider;
import net.minecraft.client.render.entity.EntityRenderer;
import net.minecraft.client.render.entity.state.EntityRenderState;
import net.minecraft.client.util.math.MatrixStack;
import net.minecraft.text.Text;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

/**
 * {@code EntityRenderer.renderLabelIfPresent} 是 protected，外部包直接调不到，
 * 用 Mixin 的 @Invoker 造一个公开桥，供"拦住原文、用译文重画一遍"用。
 *
 * 1.21.8 的签名注意：第一个参数是 **EntityRenderState**（1.21.2 之后渲染器改成状态驱动），
 * 而且没有 tickDelta。
 */
@Mixin(EntityRenderer.class)
public interface EntityRendererInvoker {

	@Invoker("renderLabelIfPresent")
	void mchanhua$renderLabelIfPresent(EntityRenderState state, Text text, MatrixStack matrices,
			VertexConsumerProvider vertexConsumers, int light);
}
