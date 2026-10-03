package com.mchanhua.client.translate;

import java.util.ArrayList;
import java.util.List;

/**
 * 判断哪些文本"需要翻译"。
 *
 * 踩过的坑（用户报"有些物品没有翻译"）：原来只要整段里**任意一行**含中文就整段跳过，
 * 结果混排 tooltip 全被漏掉——
 * 物品名是地图自带的英文（Cleaver / Elevator Parts），属性行却是游戏自己的中文（"在主手时："）。
 * 现在改成**逐行**判断：中文行留着，英文行照翻。
 */
public final class TextLines {

	private TextLines() {
	}

	/** 这一行要不要送翻译：有拉丁字母/日文假名/韩文才要；纯中文、纯数字符号不用。 */
	public static boolean needsTranslation(String line) {
		if (line == null || line.isBlank()) {
			return false;
		}
		for (int i = 0; i < line.length(); i++) {
			char ch = line.charAt(i);
			if ((ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z')) {
				return true;
			}
			if (ch >= 0x3040 && ch <= 0x30FF) {          // 平假名 / 片假名
				return true;
			}
			if (ch >= 0xAC00 && ch <= 0xD7AF) {          // 谚文
				return true;
			}
		}
		return false;
	}

	/** 需要翻译的行号（其余行原样保留）。 */
	public static List<Integer> indicesToTranslate(List<String> lines) {
		List<Integer> indices = new ArrayList<>();
		if (lines == null) {
			return indices;
		}
		for (int i = 0; i < lines.size(); i++) {
			if (needsTranslation(lines.get(i))) {
				indices.add(i);
			}
		}
		return indices;
	}

	/** 按行号取出要翻译的文本。 */
	public static List<String> pick(List<String> lines, List<Integer> indices) {
		List<String> picked = new ArrayList<>();
		if (lines == null || indices == null) {
			return picked;
		}
		for (int index : indices) {
			if (index >= 0 && index < lines.size()) {
				picked.add(lines.get(index));
			}
		}
		return picked;
	}

	/**
	 * 把译文按行号放回原列表：没翻的行保持原样，译文为空的那几行也不动（宁可显示原文）。
	 *
	 * 这一步最容易出"串行"问题（译文贴到别的行上），所以单独抽出来测。
	 */
	public static List<String> applyTranslations(List<String> lines, List<Integer> indices,
			List<String> translated) {
		List<String> result = new ArrayList<>(lines);
		if (indices == null || translated == null) {
			return result;
		}
		List<String> values = flatten(translated, indices.size());
		for (int k = 0; k < indices.size() && k < values.size(); k++) {
			String text = values.get(k);
			if (text == null || text.isBlank()) {
				continue;
			}
			int index = indices.get(k);
			if (index >= 0 && index < result.size()) {
				result.set(index, text);
			}
		}
		return result;
	}

	/** 模型有时把一个含换行的字符串当成多行译文回（先摊平再按行放回）。 */
	private static List<String> flatten(List<String> translated, int expected) {
		if (translated.size() == expected) {
			return translated;
		}
		List<String> flat = new ArrayList<>();
		for (String value : translated) {
			if (value == null) {
				flat.add(null);
				continue;
			}
			for (String piece : value.split("\n", -1)) {
				flat.add(piece);
			}
		}
		return flat.size() == expected ? flat : translated;
	}
}
