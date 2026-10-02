package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.client.gui.hud.InGameHud;
import net.minecraft.text.Text;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * 屏幕上的大标题、副标题、以及物品上方那行 ActionBar 提示（Yarn 版）。
 *
 * 地图常用 /title、/subtitle、/actionbar 显示台词。它们也是"一闪而过"的，
 * 所以同样先按住、等译文回来再显示一次。
 */
@Mixin(InGameHud.class)
public class InGameHudMixin {
	@Inject(method = "setTitle(Lnet/minecraft/text/Text;)V", at = @At("HEAD"), cancellable = true)
	private void mchanhua$translateTitle(Text text, CallbackInfo ci) {
		if (!TextTranslator.enabled() || TextTranslator.isReplaying()) {
			return;
		}
		TextTranslator.requestLater(text, true,
				translated -> ((InGameHud) (Object) this).setTitle(translated));
		ci.cancel();
	}

	@Inject(method = "setSubtitle(Lnet/minecraft/text/Text;)V", at = @At("HEAD"), cancellable = true)
	private void mchanhua$translateSubtitle(Text text, CallbackInfo ci) {
		if (!TextTranslator.enabled() || TextTranslator.isReplaying()) {
			return;
		}
		TextTranslator.requestLater(text, true,
				translated -> ((InGameHud) (Object) this).setSubtitle(translated));
		ci.cancel();
	}

	@Inject(method = "setOverlayMessage(Lnet/minecraft/text/Text;Z)V", at = @At("HEAD"), cancellable = true)
	private void mchanhua$translateOverlay(Text text, boolean animate, CallbackInfo ci) {
		if (!TextTranslator.enabled() || TextTranslator.isReplaying()) {
			return;
		}
		TextTranslator.requestLater(text, true,
				translated -> ((InGameHud) (Object) this).setOverlayMessage(translated, animate));
		ci.cancel();
	}
}
