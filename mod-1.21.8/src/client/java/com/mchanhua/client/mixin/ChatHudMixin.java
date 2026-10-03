package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.client.gui.hud.ChatHud;
import net.minecraft.client.gui.hud.MessageIndicator;
import net.minecraft.network.message.MessageSignatureData;
import net.minecraft.text.Text;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * 聊天栏翻译（Yarn 版）。
 *
 * 翻的是**本地显示**的文本：不改服务器上的任何东西，也不替玩家发言。
 * 聊天是"一闪而过"的：这里先按住这条消息，等译文回来再显示（不会先闪一句英文）。
 */
@Mixin(ChatHud.class)
public class ChatHudMixin {
	@Inject(method = "addMessage(Lnet/minecraft/text/Text;)V", at = @At("HEAD"), cancellable = true)
	private void mchanhua$translateSimple(Text message, CallbackInfo ci) {
		if (!TextTranslator.chatEnabled() || TextTranslator.isReplaying()) {
			return;
		}
		TextTranslator.requestLater(message, true,
				translated -> ((ChatHud) (Object) this).addMessage(translated));
		ci.cancel();
	}

	@Inject(
			method = "addMessage(Lnet/minecraft/text/Text;Lnet/minecraft/network/message/MessageSignatureData;Lnet/minecraft/client/gui/hud/MessageIndicator;)V",
			at = @At("HEAD"),
			cancellable = true
	)
	private void mchanhua$translateSigned(Text message, MessageSignatureData signature,
			MessageIndicator indicator, CallbackInfo ci) {
		if (!TextTranslator.chatEnabled() || TextTranslator.isReplaying()) {
			return;
		}
		TextTranslator.requestLater(message, true, translated ->
				((ChatHud) (Object) this).addMessage(translated, signature, indicator));
		ci.cancel();
	}
}
