package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.client.gui.screens.inventory.BookViewScreen;
import net.minecraft.network.chat.Component;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * 成书（书本界面）里的页面文字翻译。
 *
 * {@code BookAccess} 是"打开的书"里页面文本的来源，只被查看界面用；
 * 挂在它这里，原版自己拿到的就是译文，排版（自动折行、页数）全都照旧。
 * 书里的数据不动：这里返回的是新建的 Component。
 */
@Mixin(BookViewScreen.BookAccess.class)
public class BookAccessMixin {

	@Inject(method = "getPage", at = @At("RETURN"), cancellable = true)
	private void mchanhua$translatePage(int page, CallbackInfoReturnable<Component> cir) {
		Component text = cir.getReturnValue();
		if (text == null) {
			return;
		}
		Component translated = TextTranslator.translateMultiline(text, TextTranslator.booksEnabled());
		if (translated != text) {
			cir.setReturnValue(translated);
		}
	}
}
