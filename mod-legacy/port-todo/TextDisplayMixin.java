package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.Display;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * 世界里"悬浮大字"的翻译——地图作者用 /summon text_display 摆的章节名、任务名
 * （1. The Slaughterhouse 这种）。
 *
 * 踩过的两个坑：
 * 1. 不能挂 {@code getText()}：字节码里它被**存档序列化**调用（addAdditionalSaveData），
 *    挂上去会把译文写进存档。改挂 {@code cacheDisplay} —— 它只服务渲染。
 * 2. 真正画出来的是它产出的 {@code cachedInfo}（按文本切好的行），而这个缓存**只在为 null 时重建**、
 *    不比对文本；所以第一次（还是英文时）建好之后就一直画英文。
 *    于是这里换掉渲染用的文本后，顺手把缓存置空让它按译文重建。
 *
 * 收敛性：换过之后 text 本身就是译文，下一帧不再满足"有得翻"，就不会反复重建了。
 */
@Mixin(targets = "net.minecraft.world.entity.Display$TextDisplay")
public class TextDisplayMixin {

	@Shadow
	private Display.TextDisplay.TextRenderState textRenderState;

	@Shadow
	private Display.TextDisplay.CachedInfo clientDisplayCache;

	@Inject(method = "cacheDisplay", at = @At("HEAD"))
	private void mchanhua$translateDisplayText(
			CallbackInfoReturnable<Display.TextDisplay.CachedInfo> cir) {
		if (!TextTranslator.nametagsEnabled()) {
			return;
		}
		Display.TextDisplay.TextRenderState current = this.textRenderState;
		if (current == null) {
			return;
		}
		Component translated = TextTranslator.translateLine(current.text(), true);
		if (translated == current.text()) {
			return;                    // 没得翻 / 还没翻好，这一帧照旧
		}
		this.textRenderState = new Display.TextDisplay.TextRenderState(translated, current.lineWidth(),
				current.textOpacity(), current.backgroundColor(), current.flags());
		this.clientDisplayCache = null;   // 文本变了，让分行缓存按译文重建
	}
}
