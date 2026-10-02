package com.mchanhua.client.mixin;

import com.mchanhua.client.translate.TextTranslator;

import net.minecraft.network.chat.Component;
import net.minecraft.world.item.ItemStack;

import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

import java.util.List;

/**
 * tooltip 文本的源头：物品的所有 tooltip 行都是这里出来的。
 *
 * 挂这一层能一次覆盖背包、箱子、创造模式、以及其他模组的物品界面；
 * 界面层再挂一层是为了那些"只画物品名"的重载（它们不走完整列表）。
 * 两层都命中时不会重复花钱：已经是中文的文本会被直接跳过（见 TooltipTranslator）。
 */
@Mixin(ItemStack.class)
public class ItemStackTooltipMixin {
	@Inject(
			method = "getTooltipLines(Lnet/minecraft/world/item/Item$TooltipContext;Lnet/minecraft/world/entity/player/Player;Lnet/minecraft/world/item/TooltipFlag;)Ljava/util/List;",
			at = @At("RETURN"),
			cancellable = true
	)
	private void mchanhua$translateTooltipLines(CallbackInfoReturnable<List<Component>> cir) {
		List<Component> lines = cir.getReturnValue();
		if (lines == null || lines.isEmpty()) {
			return;
		}
		List<Component> translated = TextTranslator.translateLines(lines, TextTranslator.tooltipsEnabled());
		if (translated != lines) {
			cir.setReturnValue(translated);
		}
	}
}
