package com.mchanhua.client.translate;

import com.mchanhua.MchanhuaMod;
import com.mchanhua.client.config.MchanhuaConfig;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.function.Consumer;

/**
 * 翻译调度：单线程后台队列 + 去重 + 缓存 + 节流。
 *
 * 渲染线程只允许"查缓存"，查不到就把请求丢进队列、这一帧先显示原文——
 * 这样悬停物品永远不会卡帧。
 */
public final class TranslationService {
	/** 同一批文本最短请求间隔，免得快速划过物品栏时把额度烧光。 */
	private static final long MIN_REQUEST_INTERVAL_MS = 300;

	private final MchanhuaConfig config;
	private final TranslationCache cache = new TranslationCache();
	private final DeepSeekTranslator translator = new DeepSeekTranslator();
	private final ExecutorService pool = Executors.newSingleThreadExecutor(runnable -> {
		Thread thread = new Thread(runnable, "mchanhua-translate");
		thread.setDaemon(true);
		return thread;
	});
	private final Map<String, List<String>> inFlight = new ConcurrentHashMap<>();
	private volatile long lastRequestAt = 0L;

	public TranslationService(MchanhuaConfig config) {
		this.config = config;
		cache.load();
	}

	public static String key(List<String> lines) {
		return String.join("\n", lines);
	}

	/** 缓存里有就直接返回，没有返回 null（渲染线程用）。 */
	public List<String> cached(List<String> lines) {
		return cache.get(key(lines));
	}

	/**
	 * 请求翻译（异步）。onDone 在**后台线程**执行，调用方自己决定怎么切回渲染线程。
	 *
	 * 翻译失败时也会回调一次（用原文），免得"等翻译"的调用方把内容弄丢。
	 */
	public void request(List<String> lines, Consumer<List<String>> onDone) {
		String cacheKey = key(lines);
		List<String> hit = cache.get(cacheKey);
		if (hit != null) {
			onDone.accept(hit);
			return;
		}
		if (inFlight.putIfAbsent(cacheKey, lines) != null) {
			return;                       // 同一段已经在翻了，别重复发
		}
		pool.submit(() -> {
			try {
				long wait = MIN_REQUEST_INTERVAL_MS - (System.currentTimeMillis() - lastRequestAt);
				if (wait > 0) {
					Thread.sleep(wait);
				}
				lastRequestAt = System.currentTimeMillis();
				List<String> translated = translator.translate(config, lines);
				cache.put(cacheKey, translated);
				onDone.accept(translated);
			} catch (Exception e) {
				MchanhuaMod.LOGGER.warn("翻译失败：{}", e.toString());
				onDone.accept(lines);          // 失败就用原文显示，别让这句话消失
			} finally {
				inFlight.remove(cacheKey);
			}
		});
	}

	/** 定期落盘（由客户端 tick 调用，内部只在缓存变化时才写）。 */
	public void flush() {
		pool.submit(cache::saveIfDirty);
	}
}
