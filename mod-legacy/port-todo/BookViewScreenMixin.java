package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.screens.inventory.BookViewScreen;
import net.minecraft.network.chat.Component;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * 书页缓存的重建开关。
 *
 * 原版只在"当前页号变了"时才重新折行（{@code cachedPage != currentPage}），
 * 所以译文姗姗来迟时，屏幕上会一直挂着第一次折好的英文——和悬浮字是同一个坑。
 * 这里每帧比一下"这一页现在该显示的文本"，变了就把页号打成 -1 骗原版重建一次，
 * 文本稳定之后就不再动了。
 */
@Mixin(BookViewScreen.class)
public class BookViewScreenMixin {

	@Shadow
	private BookViewScreen.BookAccess bookAccess;

	@Shadow
	private int currentPage;

	@Shadow
	private int cachedPage;

	/** 上一次交给原版折行的文本（含译文）。 */
	@Unique
	private String mchanhua$lastSplitText;

	@Inject(
			method = "extractRenderState(Lnet/minecraft/client/gui/GuiGraphicsExtractor;IIF)V",
			at = @At("HEAD")
	)
	private void mchanhua$refreshPageCache(GuiGraphicsExtractor graphics, int mouseX, int mouseY,
			float partialTick, CallbackInfo ci) {
		if (this.bookAccess == null || !TextTranslator.booksEnabled()) {
			return;
		}
		if (this.currentPage < 0 || this.currentPage >= this.bookAccess.getPageCount()) {
			return;
		}
		Component page = this.bookAccess.getPage(this.currentPage);   // 已经带上译文（若有）
		String text = page == null ? "" : page.getString();
		if (!text.equals(this.mchanhua$lastSplitText)) {
			this.mchanhua$lastSplitText = text;
			this.cachedPage = -1;
		}
	}
}
