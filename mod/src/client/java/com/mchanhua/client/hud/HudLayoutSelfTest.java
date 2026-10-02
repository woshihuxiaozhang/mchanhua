package com.mchanhua.client.hud;

import java.util.ArrayList;
import java.util.List;

/**
 * HUD 折行自测：不进游戏、不联网，直接跑断言。
 * 用法：.\gradlew.bat hudtest
 *
 * 覆盖用户报的"字幕超出范围"：中文长句必须被折进面板宽度里。
 *
 * 注意：这里的中文一律写成 Java 转义形式，避免源码编码影响断言。
 */
public final class HudLayoutSelfTest {

	/** 假的字体宽度：ASCII 6px，中日韩 9px（跟 Minecraft 默认字体差不多）。 */
	private static final HudTextLayout.WidthOf FAKE_FONT = text -> {
		int width = 0;
		for (int i = 0; i < text.length(); i++) {
			width += text.charAt(i) < 128 ? 6 : 9;
		}
		return width;
	};

	private static final String PANEL_WIDTH_NOTE = "inner width = 260 - 6*2";
	private static final int INNER = 260 - 6 * 2;

	private static int passed = 0;
	private static int failed = 0;

	public static void main(String[] args) {
		// 截图里那条越界的中文长句
		String longChinese = "\u300A\u54C8\u5FB7\u68EE\u914B\u957F\u300B\u662F\u7684\u3002"
				+ "\u4F60\u8981\u627E\u7684\u4E1C\u897F\uFF0C\u6BD4\u4F60\u60F3\u8C61\u7684\u66F4\u8FD1\u3002";
		String longEnglish = "Closer than you think, and the road ahead is long indeed my friend";
		String shortChinese = "\u628A\u9F20\u6807\u653E\u5230\u7269\u54C1\u4E0A\u770B\u8BD1\u6587";

		List<String> wrapped = HudTextLayout.wrap(FAKE_FONT, longChinese, INNER, 3);
		check(!wrapped.isEmpty(), "longChinese 应该折出至少一行");
		check(wrapped.size() <= 3, "longChinese 行数不超过 3，实际 " + wrapped.size());
		for (String line : wrapped) {
			check(FAKE_FONT.width(line) <= INNER,
					"折行后每行都要放得下（" + FAKE_FONT.width(line) + " <= " + INNER + "）：" + line);
		}
		// 放得下就别画省略号
		List<String> fits = HudTextLayout.wrap(FAKE_FONT, shortChinese, INNER, 3);
		check(fits.size() == 1 && fits.get(0).equals(shortChinese), "短句应该原样一行");
		check(!fits.get(0).contains("\u2026"), "短句不该加省略号");

		// 放不下：截断后在最后一行加省略号
		List<String> truncated = HudTextLayout.wrap(FAKE_FONT, longChinese + longChinese, INNER, 1);
		check(truncated.size() == 1, "maxLines=1 只能有一行");
		check(truncated.get(0).endsWith("\u2026"), "被截断的行要以省略号结尾：" + truncated.get(0));
		check(FAKE_FONT.width(truncated.get(0)) <= INNER, "带省略号的行也不能超宽");

		// 英文尽量在空格处断开，不要把单词劈开（拼回去应该和原文一模一样）
		List<String> english = HudTextLayout.wrap(FAKE_FONT, longEnglish, INNER, 3);
		check(english.size() > 1, "长英文应该折成多行，实际 " + english.size());
		for (String line : english) {
			check(FAKE_FONT.width(line) <= INNER, "英文每行也要放得下：" + line);
			check(!line.startsWith(" "), "英文行首不该有空格：" + line);
		}
		check(String.join(" ", english).equals(longEnglish),
				"英文折行不该丢字/劈词，拼回来是：" + String.join(" ", english));

		// wrapAll：多行原文合起来也不超过总行数上限
		List<String> sources = new ArrayList<>();
		sources.add(longEnglish);
		sources.add(longChinese);
		sources.add(longEnglish);
		sources.add(longChinese);
		sources.add("Closer");
		List<String> all = HudTextLayout.wrapAll(FAKE_FONT, sources, INNER, 3);
		check(all.size() <= 3, "wrapAll 总行数不超过 3，实际 " + all.size());
		check(all.get(all.size() - 1).endsWith("\u2026"), "被砍掉的行尾要有省略号");

		// 极端窄：比一个字还窄也不能死循环
		long start = System.nanoTime();
		List<String> narrow = HudTextLayout.wrap(FAKE_FONT, longChinese, 1, 3);
		long costMs = (System.nanoTime() - start) / 1_000_000L;
		check(narrow.size() == 3, "极窄宽度也要按 maxLines 收住，实际 " + narrow.size());
		check(costMs < 1000, "极窄宽度不能卡住（" + costMs + "ms）");
		for (String line : narrow) {
			check(!line.isEmpty(), "不能产出空行");
		}

		// 边界输入
		check(HudTextLayout.wrap(FAKE_FONT, longChinese, INNER, 0).isEmpty(), "maxLines=0 应该返回空");
		check(HudTextLayout.wrap(FAKE_FONT, null, INNER, 3).isEmpty(), "null 应该返回空");
		check(HudTextLayout.wrap(FAKE_FONT, "   ", INNER, 3).isEmpty(), "全空白应该返回空");
		check(HudTextLayout.wrapAll(FAKE_FONT, null, INNER, 3).isEmpty(), "wrapAll(null) 应该返回空");
		check(HudTextLayout.wrapAll(FAKE_FONT, sources, INNER, 0).isEmpty(), "wrapAll maxLines=0 应该返回空");

		// 面板宽度跟着内容走
		check(HudTextLayout.maxLineWidth(FAKE_FONT, english) == HudTextLayout.maxLineWidth(FAKE_FONT, english),
				"maxLineWidth 应该稳定");
		check(HudTextLayout.maxLineWidth(FAKE_FONT, List.of(shortChinese)) == FAKE_FONT.width(shortChinese),
				"maxLineWidth 等于最宽那一行");
		check(HudTextLayout.maxLineWidth(FAKE_FONT, null) == 0, "maxLineWidth(null) 应该是 0");

		System.out.println();
		System.out.println("[hud-layout] 通过 " + passed + "，失败 " + failed + "  (" + PANEL_WIDTH_NOTE + ")");
		if (failed > 0) {
			System.exit(1);
		}
	}

	private static void check(boolean condition, String message) {
		if (condition) {
			passed++;
		} else {
			failed++;
			System.out.println("  [FAIL] " + message);
		}
	}

	private HudLayoutSelfTest() {
	}
}
