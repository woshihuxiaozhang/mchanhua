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
	// 值直接存**列表**，不再用 \n 拼成字符串：
	// 译文本身就可能含换行，拼起来再拆会把"1 条含换行的译文"误判成"多条"，
	// 之前那个"行数对不上"的守卫就是被这个坑住了（每帧重翻、日志刷屏）。
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
				synchronized (entries) {
					entries.putAll(loaded);
				}
			}
			MchanhuaMod.LOGGER.info("译文缓存已载入：{} 条", entries.size());
		} catch (Exception e) {
			// 旧格式（值是字符串）会在这里解析失败：直接当空缓存用，
			// 反正旧条目里有"整段当一行翻"留下的残缺结果，重翻一遍更干净。
			MchanhuaMod.LOGGER.warn("读取译文缓存失败：{}", e.toString());
		}
	}

	public List<String> get(String key) {
		// 这个 Map 是"按访问顺序"的 LRU，取值本身就会改动顺序；写盘在后台线程，
		// 两者一撞就是 ConcurrentModificationException（用户日志里见过），所以加锁。
		synchronized (entries) {
			return entries.get(key);
		}
	}

	public void put(String key, List<String> lines) {
		synchronized (entries) {
			entries.put(key, List.copyOf(lines));
			dirty = true;
			while (entries.size() > MAX_ENTRIES) {
				String oldest = entries.keySet().iterator().next();
				entries.remove(oldest);
			}
		}
	}

	/** 由后台线程定期调用（不在渲染线程里写盘）。 */
	public void saveIfDirty() {
		if (!dirty) {
			return;
		}
		dirty = false;
		// 先拍个快照再序列化，避免后台写盘时被渲染线程的 get() 改乱顺序
		Map<String, List<String>> snapshot;
		synchronized (entries) {
			snapshot = new LinkedHashMap<>(entries);
		}
		Path path = file();
		try {
			Files.createDirectories(path.getParent());
			Files.writeString(path, GSON.toJson(snapshot), StandardCharsets.UTF_8);
		} catch (Exception e) {
			MchanhuaMod.LOGGER.warn("保存译文缓存失败：{}", e.toString());
		}
	}
}
