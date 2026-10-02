package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.client.gui.Gui;
import net.minecraft.network.chat.Component;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * 屏幕上的大字标题、副标题、以及物品栏上方的 ActionBar 提示。
 *
 * 剧情地图常用 /title、/subtitle、/actionbar 显示台词与任务提示，这里一次全接上。
 * 这些文字也是"一闪而过"的，所以同样按住等译文，再重新显示一次。
 */
@Mixin(Gui.class)
public class GuiTitleMixin {
	@Inject(method = "setTitle(Lnet/minecraft/network/chat/Component;)V",
			at = @At("HEAD"), cancellable = true)
	private void mchanhua$translateTitle(Component text, CallbackInfo ci) {
		if (!TextTranslator.enabled() || TextTranslator.isReplaying()) {
			return;
		}
		TextTranslator.requestLater(text, true,
				translated -> ((Gui) (Object) this).setTitle(translated));
		ci.cancel();
	}

	@Inject(method = "setSubtitle(Lnet/minecraft/network/chat/Component;)V",
			at = @At("HEAD"), cancellable = true)
	private void mchanhua$translateSubtitle(Component text, CallbackInfo ci) {
		if (!TextTranslator.enabled() || TextTranslator.isReplaying()) {
			return;
		}
		TextTranslator.requestLater(text, true,
				translated -> ((Gui) (Object) this).setSubtitle(translated));
		ci.cancel();
	}

	@Inject(method = "setOverlayMessage(Lnet/minecraft/network/chat/Component;Z)V",
			at = @At("HEAD"), cancellable = true)
	private void mchanhua$translateOverlay(Component text, boolean animate, CallbackInfo ci) {
		if (!TextTranslator.enabled() || TextTranslator.isReplaying()) {
			return;
		}
		TextTranslator.requestLater(text, true,
				translated -> ((Gui) (Object) this).setOverlayMessage(translated, animate));
		ci.cancel();
	}
}
