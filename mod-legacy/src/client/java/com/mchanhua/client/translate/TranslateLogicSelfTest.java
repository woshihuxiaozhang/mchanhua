package com.mchanhua.client.translate;

import java.util.List;
import java.util.ArrayList;
import com.mchanhua.client.config.MchanhuaConfig;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;

/**
 * 翻译链路里两处"纯逻辑"的自测：不进游戏、不联网，只跑断言。
 * 用法：.\gradlew.bat translatetest
 *
 * 对应两个真实事故：
 * 1. ActionBar 同步回放没打防重入标记 → 无限递归 → StackOverflowError（PCL 里直接崩游戏）；
 * 2. 混排 tooltip 整段跳过 → "有些物品没有翻译"（Cleaver 这种英文物品名 + 中文属性行）。
 */
public final class TranslateLogicSelfTest {

	private static int passed = 0;
	private static int failed = 0;

	public static void main(String[] args) {
		replayGuardMarksDuringRun();
		replayGuardNestsAndUnwinds();
		replayGuardRestoresAfterException();
		replayDoesNotRecurseForever();
		withoutGuardItBlowsTheStack();
		hungRequestDoesNotBlockOthers();
		failedRequestFallsBackToOriginal();
		settingsTestReportsBothWays();
		staleQueuedRequestIsSkipped();
		englishNeedsTranslation();
		chineseDoesNotNeedTranslation();
		mixedTooltipOnlyTranslatesEnglishLines();
		pickKeepsOrderAndSkipsBadIndices();
		translationGoesBackToTheRightLine();
		signLinesOnlyTranslateTheTextOnes();
		bookPageKeepsItsLineBreaks();
		multilineTranslationInOneEntryIsFlattened();

		System.out.println();
		System.out.println("[translate-logic] 通过 " + passed + "，失败 " + failed);
		if (failed > 0) {
			System.exit(1);
		}
	}

	private static void replayGuardMarksDuringRun() {
		check(!ReplayGuard.active(), "一开始不该是回放状态");
		ReplayGuard.run("x", text -> check(ReplayGuard.active(), "回放中 active() 要是 true"));
		check(!ReplayGuard.active(), "回放结束要还原成 false");
	}

	private static void replayGuardNestsAndUnwinds() {
		ReplayGuard.run("outer", outer -> {
			ReplayGuard.run("inner", inner -> check(ReplayGuard.active(), "嵌套里仍然是 true"));
			check(ReplayGuard.active(), "内层结束后外层还是 true");
		});
		check(!ReplayGuard.active(), "全部结束要回到 false");
	}

	private static void replayGuardRestoresAfterException() {
		try {
			ReplayGuard.run("boom", text -> {
				throw new IllegalStateException("模拟回放炸了");
			});
		} catch (IllegalStateException expected) {
			// 就是要它抛
		}
		check(!ReplayGuard.active(), "回放抛异常也必须把标记清掉，否则后面所有翻译都不干活了");
	}

	/**
	 * 复刻崩溃现场：钩子拦住原文 → 同步回放 → 又进钩子。
	 * 打了标记的话，钩子第二次看到 active() 就放行，只跑一轮。
	 */
	private static void replayDoesNotRecurseForever() {
		int[] hookSeen = {0};
		int[] bodyRan = {0};
		Consumer<String> setOverlayMessage = new Consumer<>() {
			@Override
			public void accept(String text) {
				hookSeen[0]++;
				if (ReplayGuard.active()) {
					bodyRan[0]++;        // 钩子放行，原方法真正执行
					return;
				}
				ReplayGuard.run(text, this);   // 同步回放（老代码这里没打标记）
			}
		};
		ReplayGuard.run("你好世界", setOverlayMessage);
		check(hookSeen[0] == 1, "同步回放时钩子只该看到 1 次，实际 " + hookSeen[0]);
		check(bodyRan[0] == 1, "原方法要被放行 1 次，实际 " + bodyRan[0]);
	}

	/**
	 * 反证：不放防重入标记的话就会"回放→钩子→回放"，栈直接爆掉——
	 * 这正是用户在 PCL 里遇到的那次崩溃。这里刻意复现并接住它，
	 * 免得以后有人"顺手"把标记去掉又踩一遍。
	 */
	private static void withoutGuardItBlowsTheStack() {
		int[] calls = {0};
		Consumer<String> unguarded = new Consumer<>() {
			@Override
			public void accept(String text) {
				calls[0]++;
				accept(text);          // 没有标记的回放：只能一直套下去
			}
		};
		boolean overflowed = false;
		try {
			unguarded.accept("你好世界");
		} catch (StackOverflowError expected) {
			overflowed = true;
		}
		check(overflowed, "没有防重入标记的回放应该会栈溢出（说明标记是必需的）");
		check(calls[0] > 100, "确实递归了很多层，实际 " + calls[0]);
	}

	private static void englishNeedsTranslation() {
		check(TextLines.needsTranslation("Cleaver"), "英文物品名要翻");
		check(TextLines.needsTranslation("Elevator Parts"), "英文短语要翻");
		check(TextLines.needsTranslation("Technician 著"), "中英混排也要翻（不能整行跳过）");
		check(TextLines.needsTranslation("Steel Ingot"), "英文单词要翻");
		check(TextLines.needsTranslation("こんにちは"), "日文假名要翻");
		check(TextLines.needsTranslation("안녕하세요"), "韩文要翻");
	}

	private static void chineseDoesNotNeedTranslation() {
		check(!TextLines.needsTranslation("在主手时："), "中文属性行不用翻");
		check(!TextLines.needsTranslation("4 攻击伤害"), "中文+数字不用翻");
		check(!TextLines.needsTranslation("1.6 攻击速度"), "中文+小数不用翻");
		check(!TextLines.needsTranslation(""), "空行不用翻");
		check(!TextLines.needsTranslation("   "), "空白不用翻");
		check(!TextLines.needsTranslation(null), "null 不用翻");
		check(!TextLines.needsTranslation("…… —— ！"), "纯符号不用翻");
		check(!TextLines.needsTranslation("12345"), "纯数字不用翻");
	}

	private static void mixedTooltipOnlyTranslatesEnglishLines() {
		// 用户截图里的那种 tooltip：英文物品名 + 游戏自带的中文属性行
		List<String> tooltip = List.of("Cleaver", "在主手时：", "4 攻击伤害", "1.6 攻击速度");
		List<Integer> indices = TextLines.indicesToTranslate(tooltip);
		check(indices.equals(List.of(0)), "混排 tooltip 只该翻第 0 行，实际 " + indices);
		check(TextLines.pick(tooltip, indices).equals(List.of("Cleaver")), "取出来的就是物品名");

		check(TextLines.indicesToTranslate(List.of("皮帽", "在主手时：")).isEmpty(),
				"全中文 tooltip 一行都不用翻");
		check(TextLines.indicesToTranslate(List.of("Elevator Parts", "Technician 著")).equals(List.of(0, 1)),
				"两行都要翻时行号要都对");
		check(TextLines.indicesToTranslate(null).isEmpty(), "null 列表要安全返回空");
		check(TextLines.indicesToTranslate(List.of()).isEmpty(), "空列表要安全返回空");
	}

	private static void pickKeepsOrderAndSkipsBadIndices() {
		List<String> lines = List.of("a", "b", "c");
		check(TextLines.pick(lines, List.of(2, 0)).equals(List.of("c", "a")), "按给的行号顺序取");
		check(TextLines.pick(lines, List.of(9)).isEmpty(), "越界的行号直接跳过");
		check(TextLines.pick(lines, List.of(-1, 1)).equals(List.of("b")), "负数行号跳过");
		check(TextLines.pick(null, List.of(0)).isEmpty(), "null 列表安全");
		check(TextLines.pick(lines, null).isEmpty(), "null 行号安全");
	}

	/** 译文要贴回原来那一行，别串行；没翻的行原样保留。 */
	private static void translationGoesBackToTheRightLine() {
		List<String> tooltip = List.of("Cleaver", "在主手时：", "4 攻击伤害");
		List<Integer> indices = TextLines.indicesToTranslate(tooltip);
		check(indices.equals(List.of(0)), "只有物品名要翻");
		List<String> merged = TextLines.applyTranslations(tooltip, indices, List.of("劈刀"));
		check(merged.equals(List.of("劈刀", "在主手时：", "4 攻击伤害")),
				"只替换第 0 行，中文字段原样，实际 " + merged);
		check(merged.size() == tooltip.size(), "行数不能变（行数变了 tooltip 会错位）");

		// 两行要翻的情况
		List<String> two = List.of("Elevator Parts", "by Technician", "皮帽");
		List<Integer> twoIndices = TextLines.indicesToTranslate(two);
		check(twoIndices.equals(List.of(0, 1)), "前两行要翻，第三行已经是中文，实际 " + twoIndices);
		List<String> twoMerged = TextLines.applyTranslations(two, twoIndices, List.of("电梯零件", "作者：技师"));
		check(twoMerged.equals(List.of("电梯零件", "作者：技师", "皮帽")),
				"两行都要贴回原位，实际 " + twoMerged);

		// 模型某一行动返回空：那一行保留原文，别变成空白
		List<String> blank = TextLines.applyTranslations(tooltip, indices, List.of(""));
		check(blank.equals(tooltip), "译文为空就保留原文，实际 " + blank);

		// 返回值数量不对（模型少给一行）也不能崩
		List<String> fewer = TextLines.applyTranslations(two, twoIndices, List.of("电梯零件"));
		check(fewer.equals(List.of("电梯零件", "by Technician", "皮帽")),
				"少给一行就只替换给到的那行，实际 " + fewer);

		check(TextLines.applyTranslations(tooltip, null, List.of("x")).equals(tooltip), "null 行号不动原文");
		check(TextLines.applyTranslations(tooltip, indices, null).equals(tooltip), "null 译文不动原文");
		check(TextLines.applyTranslations(List.of(), List.of(0), List.of("x")).isEmpty(), "空列表安全");
	}

	/**
	 * 一个请求卡死不能把整条队列堵住——这是 jstack 抓出来的真实现场：
	 * 单线程队列 + 不带硬超时的 HTTP，一个卡住的请求之后所有物品都翻不出来。
	 */
	private static void hungRequestDoesNotBlockOthers() {
		MchanhuaConfig config = new MchanhuaConfig();
		config.apiKey = "sk-selftest";
		CountDownLatch hungStarted = new CountDownLatch(1);
		LineTranslator fake = (cfg, lines) -> {
			if (lines.contains("HANG")) {
				hungStarted.countDown();
				Thread.sleep(8000);              // 假装这条请求半死不活
				return lines;
			}
			return translateAll(lines);
		};
		TranslationService service = new TranslationService(config, fake, false);
		service.request(List.of("HANG"), done -> { });
		boolean started = await(hungStarted);
		check(started, "卡死的那条请求要真的开始执行（测试前提）");

		CountDownLatch fastDone = new CountDownLatch(1);
		AtomicReference<List<String>> got = new AtomicReference<>();
		long start = System.nanoTime();
		service.request(List.of("Hello"), done -> {
			got.set(done);
			fastDone.countDown();
		});
		boolean finished = await(fastDone);
		long costMs = (System.nanoTime() - start) / 1_000_000L;
		check(finished, "卡死一个请求后，后面的请求还是要能拿到结果");
		check(costMs < 3000, "不能等卡死那条结束才轮到，实际 " + costMs + "ms");
		check(got.get() != null && !got.get().isEmpty() && got.get().get(0).contains("Hello"),
				"第二次请求要拿到译文，实际 " + got.get());
	}

	/** 翻译失败时回调原文，界面上宁可显示原文，也不能空着。 */
	private static void failedRequestFallsBackToOriginal() {
		MchanhuaConfig config = new MchanhuaConfig();
		config.apiKey = "sk-selftest";
		LineTranslator failing = (cfg, lines) -> {
			throw new IllegalStateException("模拟接口 401");
		};
		TranslationService service = new TranslationService(config, failing, false);
		CountDownLatch latch = new CountDownLatch(1);
		AtomicReference<List<String>> got = new AtomicReference<>();
		service.request(List.of("Steel Ingot"), done -> {
			got.set(done);
			latch.countDown();
		});
		check(await(latch), "失败也要回调，不能把界面晾着");
		check(got.get() != null && got.get().equals(List.of("Steel Ingot")),
				"失败时回原文，实际 " + got.get());
	}

	/** 设置界面「测试一下」按钮：成功给 ✓，失败给 ✗ 加原因。 */
	private static void settingsTestReportsBothWays() {
		MchanhuaConfig config = new MchanhuaConfig();
		config.apiKey = "sk-selftest";

		TranslationService ok = new TranslationService(config,
				(cfg, lines) -> translateAll(lines), false);
		AtomicReference<String> okMessage = new AtomicReference<>();
		CountDownLatch okLatch = new CountDownLatch(1);
		ok.test(config, message -> {
			okMessage.set(message);
			okLatch.countDown();
		});
		check(await(okLatch), "测试按钮要回调");
		check(okMessage.get() != null && okMessage.get().startsWith("✓"),
				"通了要有 ✓ 和译文，实际 " + okMessage.get());

		TranslationService bad = new TranslationService(config, (cfg, lines) -> {
			throw new IllegalStateException("401 Unauthorized");
		}, false);
		AtomicReference<String> badMessage = new AtomicReference<>();
		CountDownLatch badLatch = new CountDownLatch(1);
		bad.test(config, message -> {
			badMessage.set(message);
			badLatch.countDown();
		});
		check(await(badLatch), "失败也要回调");
		check(badMessage.get() != null && badMessage.get().startsWith("✗")
						&& badMessage.get().contains("401"),
				"失败要带上原因，实际 " + badMessage.get());
	}

	/**
	 * 排队等太久的请求直接跳过、回原文——不然网络一卡，界面会吊好几分钟，
	 * 而且等轮到时鼠标早就移开了，翻出来也没人看。
	 */
	private static void staleQueuedRequestIsSkipped() {
		MchanhuaConfig config = new MchanhuaConfig();
		config.apiKey = "sk-selftest";
		CountDownLatch bothStarted = new CountDownLatch(2);
		LineTranslator slow = (cfg, lines) -> {
			bothStarted.countDown();
			Thread.sleep(1500);              // 两条线程都被占住
			return translateAll(lines);
		};
		// 队列最长等 100ms，方便测试
		TranslationService service = new TranslationService(config, slow, false, 100);
		service.request(List.of("A"), done -> { });
		service.request(List.of("B"), done -> { });
		check(await(bothStarted), "前提：两条线程都要开始干活");

		CountDownLatch done = new CountDownLatch(1);
		AtomicReference<List<String>> got = new AtomicReference<>();
		service.request(List.of("C"), lines -> {
			got.set(lines);
			done.countDown();
		});
		check(await(done), "排队的请求也要有回调，不能一直挂着");
		check(got.get() != null && got.get().equals(List.of("C")),
				"排队超时后就跳过（回原文），实际 " + got.get());
	}

	/**
	 * 告示牌固定是 4 行，空白行得原样留着占位——
	 * 少一行整块牌子的排版都会变，所以这块单独测。
	 */
	private static void signLinesOnlyTranslateTheTextOnes() {
		// 用户截图里那种牌子：两行字，后面两行是空的
		List<String> sign = List.of("DISABLE", "DOOR SECURITY", "", "");
		List<Integer> indices = TextLines.indicesToTranslate(sign);
		check(indices.equals(List.of(0, 1)), "只翻有字的两行，空行不翻，实际 " + indices);
		List<String> merged = TextLines.applyTranslations(sign, indices, List.of("解除", "门禁"));
		check(merged.equals(List.of("解除", "门禁", "", "")), "空行要原样保留，实际 " + merged);
		check(merged.size() == 4, "牌子还是 4 行（行数变了排版就乱了）");

		// 房间号那种
		List<String> cell = List.of("CELL 01", "", "", "");
		List<Integer> cellIndices = TextLines.indicesToTranslate(cell);
		check(cellIndices.equals(List.of(0)), "只有第一行有字");
		check(TextLines.applyTranslations(cell, cellIndices, List.of("一号牢房"))
						.equals(List.of("一号牢房", "", "", "")),
				"只换第一行，其余三行空着");

		// 已经是中文的牌子（地图作者写的中文）不该再翻
		check(TextLines.indicesToTranslate(List.of("禁止通行", "", "", "")).isEmpty(),
				"中文牌子一行都不用翻");

		// 整块空牌子
		check(TextLines.indicesToTranslate(List.of("", "", "", "")).isEmpty(), "空牌子安全返回空");
	}

	/**
	 * 书页：作者用 \n 手动分好行，翻完必须**行数一样**，否则整页排版就乱了。
	 * 这里复刻 TextTranslator.translateMultiline 的拆分/贴回/拼接流程。
	 */
	private static void bookPageKeepsItsLineBreaks() {
		String page = "The Detention Sector\nhad remained out of reach.\n\nCrazled had always\nbeen a difficult man.";
		List<String> rawLines = List.of(page.split("\n", -1));
		check(rawLines.size() == 5, "按 \\n 拆出来 5 行，实际 " + rawLines.size());
		check(rawLines.get(2).isEmpty(), "第三行是空行（作者分段），要原样保留");

		List<Integer> indices = TextLines.indicesToTranslate(rawLines);
		check(indices.equals(List.of(0, 1, 3, 4)), "只翻有英文的四行，空行跳过，实际 " + indices);
		List<String> picked = TextLines.pick(rawLines, indices);
		check(picked.size() == 4, "送出去 4 行");

		List<String> merged = TextLines.applyTranslations(rawLines, indices,
				List.of("拘留区", "已经有一段时间够不着了。", "克雷兹德一向", "是个难打交道的人。"));
		String joined = String.join("\n", merged);
		check(merged.size() == rawLines.size(), "行数必须一样");
		check(joined.split("\n", -1).length == 5, "拼回去还是 5 行");
		check(joined.contains("\n\n"), "空行还在（分段没被吃掉）");
		check(joined.startsWith("拘留区\n已经有一段时间够不着了。\n\n克雷兹德一向"),
				"顺序要对上，实际 " + joined.replace("\n", "\\n"));

		// 已经是中文的书页不用翻
		String chinese = "第一行\n\n第二行";
		check(TextLines.indicesToTranslate(List.of(chinese.split("\n", -1))).isEmpty(),
				"中文书页一行都不用翻");
	}

	/**
	 * 模型有时把几行译文塞回一个含换行的字符串（请求 4 条、回来 1 条但含 3 个换行）。
	 * 必须先摊平再按行放回，否则只有第一行被替换、其余像"翻译丢了"（用户实测）。
	 */
	private static void multilineTranslationInOneEntryIsFlattened() {
		List<String> rules = List.of("--- RULES ---", "1. Play on adventure mode",
				"2. Do not switch to peaceful mode", "3. Stick together");
		List<Integer> indices = TextLines.indicesToTranslate(rules);
		check(indices.size() == 4, "四行都要翻，实际 " + indices);

		List<String> merged = TextLines.applyTranslations(rules, indices,
				List.of("--- 规则 ---\n1. 用冒险模式游玩\n2. 不要切到和平模式\n3. 全程待在一起"));
		check(merged.equals(List.of("--- 规则 ---", "1. 用冒险模式游玩",
						"2. 不要切到和平模式", "3. 全程待在一起")),
				"含换行的单条译文要摊平后按行放回，实际 " + merged);

		check(TextLines.applyTranslations(rules, indices, List.of("A", "B", "C", "D"))
						.equals(List.of("A", "B", "C", "D")),
				"一行对一条时照常替换");
	}

	private static List<String> translateAll(List<String> lines) {
		List<String> out = new ArrayList<>();
		for (String line : lines) {
			out.add("【译】" + line);
		}
		return out;
	}

	private static boolean await(CountDownLatch latch) {
		try {
			return latch.await(5, TimeUnit.SECONDS);
		} catch (InterruptedException e) {
			Thread.currentThread().interrupt();
			return false;
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

	private TranslateLogicSelfTest() {
	}
}
