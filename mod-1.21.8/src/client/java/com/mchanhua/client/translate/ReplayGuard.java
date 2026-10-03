package com.mchanhua.client.translate;

import java.util.function.Consumer;

/**
 * 防重入标记：记录"现在我正在把译文放回游戏"。
 *
 * 为什么必须有：钩子（setTitle / setOverlayMessage / addMessage…）都是"拦住原文 → 翻好 → 再调一次原方法把译文放进去"。
 * 第二次调用又会被同一个钩子看到，所以钩子靠 {@link #active()} 判断"这次是我自己放的，放行"。
 *
 * 踩过的坑（PCL 里直接崩游戏，StackOverflowError）：早先只有异步那条路径打了标记，
 * "已经是中文 / 命中缓存"这两条**同步**回放路径忘了打，于是：
 * 回放 → 钩子 → 回放 → 钩子……栈直接爆掉。所以现在所有回放都必须走 {@link #run}。
 *
 * 用 ThreadLocal 计数而不是布尔量：回放里还可能嵌套回放，退出时要准确还原。
 */
public final class ReplayGuard {
	private static final ThreadLocal<Integer> DEPTH = ThreadLocal.withInitial(() -> 0);

	private ReplayGuard() {
	}

	public static boolean active() {
		return DEPTH.get() > 0;
	}

	/** 打上标记后执行回放；就算回放抛异常也会把标记还原。 */
	public static <T> void run(T value, Consumer<T> action) {
		int depth = DEPTH.get();
		DEPTH.set(depth + 1);
		try {
			action.accept(value);
		} finally {
			if (depth <= 0) {
				DEPTH.remove();
			} else {
				DEPTH.set(depth);
			}
		}
	}
}
