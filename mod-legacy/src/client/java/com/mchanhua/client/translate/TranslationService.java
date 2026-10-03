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
 * 翻译调度：后台队列 + 去重 + 缓存 + 节流 + 过期丢弃。
 *
 * 渲染线程只允许"查缓存"，查不到就把请求丢进队列、这一帧先显示原文——
 * 这样悬停物品永远不会卡帧。
 *
 * 队列只给两条线程：一条被卡住（网络半死不活）时另一条还能干活；
 * 排队太久的请求直接跳过（见 maxQueueWaitMs），免得界面被一堆没人看的请求吊住。
 */
public final class TranslationService {
	/** 同一批文本最短请求间隔，免得快速划过物品栏时把额度烧光。 */
	private static final long MIN_REQUEST_INTERVAL_MS = 300;
	/**
	 * 排队最久等多久：超过就当这条过期，直接放行原文。
	 *
	 * 网络不好时悬停物品会堆一堆请求，等排到时鼠标早移开了，翻出来也没人看；
	 * 跳过它们既能让界面不吊着，也能把线程让给真正要看的那条。
	 */
	private static final long DEFAULT_MAX_QUEUE_WAIT_MS = 10_000;

	private final MchanhuaConfig config;
	private final TranslationCache cache = new TranslationCache();
	private final LineTranslator translator;
	private final long maxQueueWaitMs;
	/**
	 * 两条线程而不是一条：万一真有一条被卡住（比如网络半死不活），
	 * 另一条还能继续给玩家翻东西，不至于整局游戏都哑掉。
	 */
	private final ExecutorService pool = Executors.newFixedThreadPool(2, runnable -> {
		Thread thread = new Thread(runnable, "mchanhua-translate-" + THREAD_COUNTER.incrementAndGet());
		thread.setDaemon(true);
		return thread;
	});
	private static final java.util.concurrent.atomic.AtomicInteger THREAD_COUNTER =
			new java.util.concurrent.atomic.AtomicInteger();
	private final Map<String, List<String>> inFlight = new ConcurrentHashMap<>();
	private volatile long lastRequestAt = 0L;

	public TranslationService(MchanhuaConfig config) {
		this(config, new DeepSeekTranslator(), true, DEFAULT_MAX_QUEUE_WAIT_MS);
	}

	/** 给自测用：可以塞一个假的翻译器，也可以不碰磁盘缓存（不依赖 FabricLoader）。 */
	public TranslationService(MchanhuaConfig config, LineTranslator translator, boolean loadCache) {
		this(config, translator, loadCache, DEFAULT_MAX_QUEUE_WAIT_MS);
	}

	public TranslationService(MchanhuaConfig config, LineTranslator translator, boolean loadCache,
			long maxQueueWaitMs) {
		this.config = config;
		this.translator = translator;
		this.maxQueueWaitMs = maxQueueWaitMs;
		if (loadCache) {
			cache.load();
		}
	}

	public static String key(List<String> lines) {
		return String.join("\n", lines);
	}

	/** 缓存里有就直接返回，没有返回 null（渲染线程用）。 */
	public List<String> cached(List<String> lines) {
		// 不能按"条数必须相等"判定：模型常把多行译文塞回一个含换行的字符串，
		// 那是正确结果。对齐交给 TextLines.applyTranslations（先摊平再按行放回）。
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
		long queuedAt = System.currentTimeMillis();
		pool.submit(() -> {
			try {
				if (System.currentTimeMillis() - queuedAt > maxQueueWaitMs) {
					MchanhuaMod.LOGGER.info("翻译排队太久，跳过这次：{}", lines);
					onDone.accept(lines);
					return;
				}
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

	/**
	 * 设置界面用的连通性测试：拿给定配置真打一次接口，成功失败都以一句人话回报。
	 *
	 * 用传进来的 probe 而不是自己的 config，是为了让"只是想试试 key 通不通"不落盘；
	 * 顺便把 401、超时这类原因原样带给用户看，比只写日志强。
	 */
	public void test(MchanhuaConfig probe, Consumer<String> report) {
		// 单独开一条线程：就算翻译队列正被卡住的请求堵着，"测试一下"也要马上给结果
		Thread thread = new Thread(() -> {
			try {
				List<String> out = translator.translate(probe, List.of("Steel Ingot"));
				String first = out.isEmpty() ? "" : out.get(0);
				report.accept("✓ 通了：Steel Ingot → " + first);
			} catch (Exception e) {
				report.accept("✗ 失败：" + e.getMessage());
			}
		}, "mchanhua-selftest");
		thread.setDaemon(true);
		thread.start();
	}
}
