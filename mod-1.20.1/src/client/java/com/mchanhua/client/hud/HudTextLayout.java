package com.mchanhua.client.hud;

import java.util.ArrayList;
import java.util.List;

/**
 * HUD 文本排版：把一行文字按**像素宽度**折成多行，超过行数上限就加省略号。
 *
 * 为什么不按字符数截断：中文/日文一个字差不多是英文的两倍宽，
 * 按字符数截断会让中文长句撑破面板（用户报的"超出范围"）。
 *
 * 这里不依赖 Minecraft 类，方便自测（见 HudLayoutSelfTest）。
 */
public final class HudTextLayout {

	/** 量文字宽度（游戏里传 minecraft.font::width）。 */
	@FunctionalInterface
	public interface WidthOf {
		int width(String text);
	}

	private HudTextLayout() {
	}

	/**
	 * 单行折行。maxLines <= 0 时返回空列表；放不下的部分丢掉并在最后一行加省略号。
	 * 即使 maxWidth 比一个字还窄也保证会前进（不会死循环）。
	 */
	public static List<String> wrap(WidthOf widthOf, String line, int maxWidth, int maxLines) {
		List<String> out = new ArrayList<>();
		if (maxLines <= 0) {
			return out;
		}
		int limit = Math.max(1, maxWidth);
		String remaining = line == null ? "" : line.strip();
		while (!remaining.isEmpty() && out.size() < maxLines) {
			if (widthOf.width(remaining) <= limit) {
				out.add(remaining);
				remaining = "";
				break;
			}
			int cut = remaining.length();
			while (cut > 1 && widthOf.width(remaining.substring(0, cut)) > limit) {
				cut--;
			}
			int space = remaining.lastIndexOf(' ', cut);
			if (space > cut / 2) {
				cut = space; // 英文尽量在空格处断开
			}
			out.add(remaining.substring(0, cut).strip());
			remaining = remaining.substring(cut).strip();
		}
		if (!remaining.isEmpty()) {
			markTruncated(widthOf, out, limit);
		}
		return out;
	}

	/** 多行文本逐行折行，**总**行数不超过 maxLines（被截断就在末尾加省略号）。 */
	public static List<String> wrapAll(WidthOf widthOf, List<String> lines, int maxWidth, int maxLines) {
		List<String> out = new ArrayList<>();
		if (lines == null || maxLines <= 0) {
			return out;
		}
		int limit = Math.max(1, maxWidth);
		for (String line : lines) {
			if (out.size() >= maxLines) {
				markTruncated(widthOf, out, limit);
				break;
			}
			out.addAll(wrap(widthOf, line, limit, maxLines - out.size()));
		}
		return out;
	}

	/** 最宽一行的像素宽度（让面板跟着内容变宽）。 */
	public static int maxLineWidth(WidthOf widthOf, List<String> lines) {
		int width = 0;
		if (lines == null) {
			return width;
		}
		for (String line : lines) {
			width = Math.max(width, widthOf.width(line));
		}
		return width;
	}

	/**
	 * 在最后一行加省略号，表示"后面还有，但没地方画了"。
	 * 省略号本身也占宽度，所以先把最后一行裁到 limit - 省略号宽，避免补上省略号反而超出面板。
	 */
	private static void markTruncated(WidthOf widthOf, List<String> lines, int limit) {
		if (lines.isEmpty()) {
			return;
		}
		int last = lines.size() - 1;
		String ellipsis = "…";
		int available = limit - widthOf.width(ellipsis);
		String text = lines.get(last);
		int cut = text.length();
		while (cut > 0 && widthOf.width(text.substring(0, cut)) > available) {
			cut--;
		}
		lines.set(last, (cut <= 0 ? "" : text.substring(0, cut).strip()) + ellipsis);
	}
}
