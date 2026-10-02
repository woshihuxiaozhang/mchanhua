package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.client.renderer.entity.EntityRenderer;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * 实体头顶名字的翻译（地图里 NPC 的 Norman、任务目标名这类）。
 *
 * 挂的是渲染层（{@link EntityRenderer} 是客户端类，服务端不会加载），
 * 所以改的只是"这一帧画什么"，实体的自定义名字数据不受影响。
 *
 * **玩家 ID 不翻**：那是昵称不是游戏文本，把别人的名字改成中文既奇怪又会白白烧请求。
 */
@Mixin(EntityRenderer.class)
public class EntityNameTagMixin {

	@Inject(method = "getNameTag", at = @At("RETURN"), cancellable = true)
	private void mchanhua$translateNameTag(Entity entity, CallbackInfoReturnable<Component> cir) {
		Component name = cir.getReturnValue();
		if (name == null || entity instanceof Player || !TextTranslator.nametagsEnabled()) {
			return;
		}
		Component translated = TextTranslator.translateLine(name, true);
		if (translated != name) {
			cir.setReturnValue(translated);
		}
	}
}
