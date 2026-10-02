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
import org.spongepowered.asm.mixin.injection.Redirect;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * 成书页面翻译（1.20.1 / Yarn）。
 *
 * 1.20.1 和 1.21.1 不一样：`BookScreen$Contents` 是**接口**（1.21.1 才是 record），
 * 所以不能往里注入，改成重定向 `render` 里那次取页调用：
 *   StringVisitable page = this.contents.getPage(this.pageIndex);
 *
 * 另外原版只在"页号变了"时重新折行（cachedPageIndex），译文晚到会一直挂英文，
 * 所以渲染前比一下"这一页该显示的文本"，变了就把 cachedPageIndex 打成 -1 逼它重建。
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
		StringVisitable raw = this.contents.getPage(this.pageIndex);
		if (!(raw instanceof Text text)) {
			return;
		}
		Text translated = TextTranslator.translateMultiline(text, true);
		String shown = (translated == text ? text : translated).getString();
		if (!shown.equals(this.mchanhua$lastPageText)) {
			this.mchanhua$lastPageText = shown;
			this.cachedPageIndex = -1;
		}
	}

	/** 把 render 里那次"取页面文本"换成译文（按行翻，行数与分段不变）。 */
	@Redirect(
			method = "render",
			at = @At(
					value = "INVOKE",
					target = "Lnet/minecraft/client/gui/screen/ingame/BookScreen$Contents;getPage(I)Lnet/minecraft/text/StringVisitable;"
			)
	)
	private StringVisitable mchanhua$translatePage(BookScreen.Contents contents, int index) {
		StringVisitable page = contents.getPage(index);
		if (!(page instanceof Text text)) {
			return page;
		}
		Text translated = TextTranslator.translateMultiline(text, TextTranslator.booksEnabled());
		return translated == text ? text : translated;
	}
}
