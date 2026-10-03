package com.mchanhua.client.translate;

import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;
import com.mchanhua.MchanhuaMod;

import net.fabricmc.loader.api.FabricLoader;

import java.lang.reflect.Type;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 译文缓存：同一段原文只翻一次（悬浮同一物品不会反复请求）。
 *
 * 内存里是 LRU，落盘成 config/mchanhua-cache.json，和桌面版"同一句只翻一次"是一个思路。
 */
public final class TranslationCache {
	private static final int MAX_ENTRIES = 2000;
	// 值直接存**列表**，不再用 \n 拼成字符串（译文本身可能含换行）
	private static final Type TYPE = new TypeToken<LinkedHashMap<String, List<String>>>() { }.getType();
	private static final Gson GSON = new Gson();

	private final Map<String, List<String>> entries = new LinkedHashMap<>(64, 0.75f, true);
	private boolean dirty = false;

	private static Path file() {
		return FabricLoader.getInstance().getConfigDir().resolve("mchanhua-cache.json");
	}

	public void load() {
		Path path = file();
		if (!Files.exists(path)) {
			return;
		}
		try {
			Map<String, List<String>> loaded =
					GSON.fromJson(Files.readString(path, StandardCharsets.UTF_8), TYPE);
			if (loaded != null) {
				entries.putAll(loaded);
			}
			MchanhuaMod.LOGGER.info("译文缓存已载入：{} 条", entries.size());
		} catch (Exception e) {
			// 旧格式（值是字符串）解析会失败：当空缓存用，重翻一遍更干净
			MchanhuaMod.LOGGER.warn("读取译文缓存失败：{}", e.toString());
		}
	}

	public List<String> get(String key) {
		return entries.get(key);
	}

	public void put(String key, List<String> lines) {
		entries.put(key, List.copyOf(lines));
		dirty = true;
		while (entries.size() > MAX_ENTRIES) {
			String oldest = entries.keySet().iterator().next();
			entries.remove(oldest);
		}
	}

	/** 由后台线程定期调用（不在渲染线程里写盘）。 */
	public void saveIfDirty() {
		if (!dirty) {
			return;
		}
		dirty = false;
		Path path = file();
		try {
			Files.createDirectories(path.getParent());
			Files.writeString(path, GSON.toJson(entries), StandardCharsets.UTF_8);
		} catch (Exception e) {
			MchanhuaMod.LOGGER.warn("保存译文缓存失败：{}", e.toString());
		}
	}
}
