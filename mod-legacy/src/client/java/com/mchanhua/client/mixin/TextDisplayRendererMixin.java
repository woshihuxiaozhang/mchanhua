package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.client.render.entity.DisplayEntityRenderer;
import net.minecraft.entity.decoration.DisplayEntity;
import net.minecraft.text.Text;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * 世界里"悬浮大字"的翻译（老版本线 / Yarn 映射）。
 *
 * 地图作者用 /summon text_display 摆的章节名、任务名（1. The Slaughterhouse 这种）都走这里。
 *
 * 为什么不挂 {@code TextDisplayEntity.getText()}：它**被存档序列化调用**（writeCustomDataToNbt），
 * 挂上去会把译文写进存档。所以改挂渲染器拿数据的 {@code getData(...)}，只动画面用的那份 Data。
 * Data 是 record，重建一个把 text 换掉即可。
 */
@Mixin(DisplayEntityRenderer.TextDisplayEntityRenderer.class)
public class TextDisplayRendererMixin {

	@Inject(method = "getData", at = @At("RETURN"), cancellable = true)
	private void mchanhua$translateDisplay(DisplayEntity.TextDisplayEntity entity,
			CallbackInfoReturnable<DisplayEntity.TextDisplayEntity.Data> cir) {
		if (!TextTranslator.nametagsEnabled()) {
			return;
		}
		DisplayEntity.TextDisplayEntity.Data data = cir.getReturnValue();
		if (data == null) {
			return;
		}
		Text translated = TextTranslator.translateLine(data.text(), true);
		if (translated == data.text()) {
			return;                      // 没得翻 / 还没翻好，这一帧照旧
		}
		cir.setReturnValue(new DisplayEntity.TextDisplayEntity.Data(translated, data.lineWidth(),
				data.textOpacity(), data.backgroundColor(), data.flags()));
	}
}
