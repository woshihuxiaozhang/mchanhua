package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.client.gui.components.ChatComponent;
import net.minecraft.network.chat.Component;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * 聊天栏翻译：收到的服务器消息、系统提示、玩家发言都会经过这三个入口。
 *
 * 26.x 上原来的 addMessage 拆成了三个方法（客户端系统消息 / 服务端系统消息 / 玩家消息）。
 * 翻的是**本地显示**的文本：不改服务器上的任何东西，也不替玩家发消息。
 *
 * 聊天是一闪而过的：这里先按住这条消息，等译文回来再显示（不会先闪一句英文）。
 */
@Mixin(ChatComponent.class)
public class ChatComponentMixin {
	@Inject(method = "addClientSystemMessage(Lnet/minecraft/network/chat/Component;)V",
			at = @At("HEAD"), cancellable = true)
	private void mchanhua$translateClientSystem(Component message, CallbackInfo ci) {
		if (!TextTranslator.chatEnabled() || TextTranslator.isReplaying()) {
			return;
		}
		TextTranslator.requestLater(message, true,
				translated -> ((ChatComponent) (Object) this).addClientSystemMessage(translated));
		ci.cancel();
	}

	@Inject(method = "addServerSystemMessage(Lnet/minecraft/network/chat/Component;)V",
			at = @At("HEAD"), cancellable = true)
	private void mchanhua$translateServerSystem(Component message, CallbackInfo ci) {
		if (!TextTranslator.chatEnabled() || TextTranslator.isReplaying()) {
			return;
		}
		TextTranslator.requestLater(message, true,
				translated -> ((ChatComponent) (Object) this).addServerSystemMessage(translated));
		ci.cancel();
	}

	@Inject(
			method = "addPlayerMessage(Lnet/minecraft/network/chat/Component;Lnet/minecraft/network/chat/MessageSignature;Lnet/minecraft/client/multiplayer/chat/GuiMessageTag;)V",
			at = @At("HEAD"), cancellable = true)
	private void mchanhua$translatePlayerMessage(Component message,
			net.minecraft.network.chat.MessageSignature signature,
			net.minecraft.client.multiplayer.chat.GuiMessageTag tag, CallbackInfo ci) {
		if (!TextTranslator.chatEnabled() || TextTranslator.isReplaying()) {
			return;
		}
		TextTranslator.requestLater(message, true, translated ->
				((ChatComponent) (Object) this).addPlayerMessage(translated, signature, tag));
		ci.cancel();
	}
}
