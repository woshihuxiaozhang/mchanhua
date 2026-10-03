package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.client.gui.screen.ingame.BookScreen;
import net.minecraft.text.StringVisitable;
import net.minecraft.text.Text;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * 书页文本来源（老版本线 / Yarn 映射）：按行翻再拼回去，行数与分段不变。
 * 1.21.1 里 {@code BookScreen$Contents} 是个 record，方法有实体，可以直接注入。
 */
@Mixin(BookScreen.Contents.class)
public class BookContentsMixin {

	@Inject(method = "getPage", at = @At("RETURN"), cancellable = true)
	private void mchanhua$translatePage(int index, CallbackInfoReturnable<StringVisitable> cir) {
		StringVisitable page = cir.getReturnValue();
		if (!(page instanceof Text text)) {
			return;
		}
		Text translated = TextTranslator.translateMultiline(text, TextTranslator.booksEnabled());
		if (translated != text) {
			cir.setReturnValue(translated);
		}
	}
}
