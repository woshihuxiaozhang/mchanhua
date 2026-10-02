package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.network.chat.Component;
import net.minecraft.world.BossEvent;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * Boss 栏名字（/bossbar 显示的那一条）。
 *
 * 从 getName() 取最省事：不管原版还是地图自定义的 Boss 栏，渲染时都要读这个名字。
 */
@Mixin(BossEvent.class)
public class BossEventMixin {
	@Inject(method = "getName()Lnet/minecraft/network/chat/Component;", at = @At("RETURN"), cancellable = true)
	private void mchanhua$translateName(CallbackInfoReturnable<Component> cir) {
		Component name = cir.getReturnValue();
		if (name == null) {
			return;
		}
		Component translated = TextTranslator.translateLine(name, TextTranslator.enabled());
		if (translated != name) {
			cir.setReturnValue(translated);
		}
	}
}
