package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.ingame.BookScreen;
import net.minecraft.text.StringVisitable;
import net.minecraft.text.Text;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * 成书（书本界面）页面翻译（老版本线 / Yarn 映射）。
 *
 * 两个挂点：
 * 1. {@code BookScreen$Contents.getPage(int)} —— 页面文本的来源，按行翻再拼回去（行数/分段不变）；
 * 2. {@code BookScreen.render} —— 原版只在"页号变了"时才重新折行（cachedPageIndex），
 *    译文晚到会一直挂英文，所以这里比一下"这一页该显示的文本"，变了就把缓存页号打成 -1 逼它重建。
 */
@Mixin(BookScreen.class)
public class BookScreenMixin {

	@Shadow
	private int pageIndex;

	@Shadow
	private int cachedPageIndex;

	@Shadow
	private BookScreen.Contents contents;

	/** 上一次交给原版折行的文本（含译文）。 */
	@Unique
	private String mchanhua$lastPageText;

	@Inject(method = "render", at = @At("HEAD"))
	private void mchanhua$refreshPageCache(DrawContext context, int mouseX, int mouseY, float delta,
			CallbackInfo ci) {
		if (!TextTranslator.booksEnabled() || this.contents == null) {
			return;
		}
		int count = this.contents.getPageCount();
		if (this.pageIndex < 0 || this.pageIndex >= count) {
			return;
		}
		StringVisitable page = this.contents.getPage(this.pageIndex);   // 已带译文（若有）
		String text = page == null ? "" : page.getString();
		if (!text.equals(this.mchanhua$lastPageText)) {
			this.mchanhua$lastPageText = text;
			this.cachedPageIndex = -1;
		}
	}

}
