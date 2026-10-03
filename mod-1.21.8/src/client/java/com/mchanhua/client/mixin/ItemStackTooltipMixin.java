package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.item.ItemStack;
import net.minecraft.text.Text;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

import java.util.List;

/**
 * tooltip 文本的源头（Yarn 版）：物品的所有 tooltip 行都是这里出来的。
 * 挂这一层能一次覆盖背包、箱子、创造模式以及其他模组的物品界面。
 */
@Mixin(ItemStack.class)
public class ItemStackTooltipMixin {
	@Inject(
			method = "getTooltip(Lnet/minecraft/item/Item$TooltipContext;Lnet/minecraft/entity/player/PlayerEntity;Lnet/minecraft/item/tooltip/TooltipType;)Ljava/util/List;",
			at = @At("RETURN"),
			cancellable = true
	)
	private void mchanhua$translateTooltip(CallbackInfoReturnable<List<Text>> cir) {
		List<Text> lines = cir.getReturnValue();
		if (lines == null || lines.isEmpty()) {
			return;
		}
		List<Text> translated = TextTranslator.translateLines(lines, TextTranslator.tooltipsEnabled());
		if (translated != lines) {
			cir.setReturnValue(translated);
		}
	}
}
