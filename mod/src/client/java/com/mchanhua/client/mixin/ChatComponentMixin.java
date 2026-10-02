package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.client.gui.components.ChatComponent;
import net.minecraft.network.chat.Component;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyVariable;

/**
 * 聊天栏翻译：收到的服务器消息、系统提示、玩家发言都会经过这三个入口。
 *
 * 26.x 上原来的 addMessage 拆成了三个方法（客户端系统消息 / 服务端系统消息 / 玩家消息）。
 * 翻的是**本地显示**的文本：不改服务器上的任何东西，也不替玩家发消息。
 */
@Mixin(ChatComponent.class)
public class ChatComponentMixin {
	@ModifyVariable(method = "addClientSystemMessage(Lnet/minecraft/network/chat/Component;)V",
			at = @At("HEAD"), argsOnly = true)
	private Component mchanhua$translateClientSystem(Component message) {
		return TextTranslator.translateLine(message, TextTranslator.chatEnabled());
	}

	@ModifyVariable(method = "addServerSystemMessage(Lnet/minecraft/network/chat/Component;)V",
			at = @At("HEAD"), argsOnly = true)
	private Component mchanhua$translateServerSystem(Component message) {
		return TextTranslator.translateLine(message, TextTranslator.chatEnabled());
	}

	@ModifyVariable(
			method = "addPlayerMessage(Lnet/minecraft/network/chat/Component;Lnet/minecraft/network/chat/MessageSignature;Lnet/minecraft/client/multiplayer/chat/GuiMessageTag;)V",
			at = @At("HEAD"), argsOnly = true)
	private Component mchanhua$translatePlayerMessage(Component message) {
		return TextTranslator.translateLine(message, TextTranslator.chatEnabled());
	}
}
