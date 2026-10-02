package com.mchanhua.client.translate;

import com.mchanhua.client.config.MchanhuaConfig;

import java.util.List;

/**
 * 一次"把这几行翻成中文"的调用，抽成接口是为了能脱离网络测试
 * （比如验证"某个请求卡死时，后面的请求还能不能照常发"）。
 */
public interface LineTranslator {
	List<String> translate(MchanhuaConfig config, List<String> lines) throws Exception;
}
