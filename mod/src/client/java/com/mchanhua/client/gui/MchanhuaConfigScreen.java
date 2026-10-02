package com.mchanhua.client.gui;

import com.mchanhua.client.config.ConfigDraft;
import com.mchanhua.client.config.MchanhuaConfig;
import com.mchanhua.client.config.ProviderPresets;
import com.mchanhua.client.hud.HudTextLayout;
import com.mchanhua.client.translate.TranslationService;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.input.KeyEvent;
import net.minecraft.network.chat.Component;

import org.lwjgl.glfw.GLFW;

import java.util.ArrayList;
import java.util.List;

/**
 * 游戏里填 API Key 的设置界面（原版控件手搓，不依赖 Cloth Config / ModMenu）。
 *
 * 为什么手搓：多装一个前置模组对玩家是负担，而这里要的东西很少——
 * 几个输入框 + 几个开关 + 一个「测试一下」按钮，原版控件完全够用。
 *
 * 热键 K 打开（见 MchanhuaModClient）。值先落在 ConfigDraft 上，
 * 由它做兜底与提示，再写回 config/mchanhua.json。
 *
 * 尺寸注意：Screen 的 width/height 是 **GUI 缩放后**的单位，默认窗口（854x480 + 自动缩放）
 * 只有 427x240 那么大，所以面板必须自己算高度，不能写死——第一版就是写死了 318 高，
 * 结果按钮整排被切到屏幕外。
 */
public final class MchanhuaConfigScreen extends Screen {
	private static final int MAX_PANEL_W = 340;
	private static final int LABEL_COL = 112;
	private static final int ROWS = 7;

	private static final int COLOR_PANEL = 0xF0121720;
	private static final int COLOR_BORDER = 0x70FFFFFF;
	private static final int COLOR_TITLE = 0xFFFFFFFF;
	private static final int COLOR_LABEL = 0xFF9AA4B2;
	private static final int COLOR_OK = 0xFF6BD98A;
	private static final int COLOR_WARN = 0xFFFFC46B;
	private static final int COLOR_BAD = 0xFFFF8A8A;

	private static final String HINT_READY = "填完点「保存」；key 只存本地 config/mchanhua.json";
	private static final String HINT_NO_KEY = "还没填 API Key：点「测试一下」就知道通没通";

	private final MchanhuaConfig config;
	private final TranslationService service;
	private final Screen parent;
	private final ConfigDraft draft;
	private final List<String> notes = new ArrayList<>();

	private String status;
	private int statusColor = COLOR_LABEL;
	private boolean testing = false;
	private boolean maskKey = true;

	private EditBox keyBox;
	private EditBox urlBox;
	private EditBox modelBox;
	private EditBox langBox;
	private EditBox hideBox;
	private EditBox timeoutBox;
	private Button providerButton;
	private Button modelButton;
	private Button urlModeButton;
	private Button modelModeButton;

	/** true = 接口地址/模型用手填，false = 用可选列表。 */
	private boolean customUrl;
	private boolean customModel;

	private int panelLeft;
	private int panelTop;
	private int panelW;
	private int panelH;
	private int rowH;
	private int widgetH;
	private int fieldX;
	private int fieldW;

	public MchanhuaConfigScreen(MchanhuaConfig config, TranslationService service, Screen parent) {
		super(Component.literal("mchanhua 设置"));
		this.config = config;
		this.service = service;
		this.parent = parent;
		this.draft = ConfigDraft.from(config);
		this.status = config != null && config.ready() ? HINT_READY : HINT_NO_KEY;
	}

	@Override
	protected void init() {
		super.init();
		panelW = Math.min(MAX_PANEL_W, Math.max(220, width - 20));
		// 行高跟着屏幕高度收：小窗口挤一点，大窗口松一点，总之不许溢出
		rowH = Math.max(16, Math.min(26, (height - 104) / ROWS));
		widgetH = Math.max(14, Math.min(20, rowH - 2));

		int fixed = 28 + 8 + widgetH + 6 + 20 + 8;
		panelH = fixed + ROWS * rowH;
		panelLeft = (width - panelW) / 2;
		panelTop = Math.max(4, (height - panelH) / 2);
		fieldX = panelLeft + LABEL_COL;
		fieldW = Math.max(80, panelW - LABEL_COL - 14);

		int keyFieldW = Math.max(60, fieldW - 56);
		keyBox = field(fieldX, row(0), keyFieldW, 200, "sk-...（粘进去就行）");
		keyBox.setValue(draft.apiKey);
		keyBox.addFormatter((text, cursor) ->
				Component.literal(maskKey ? "•".repeat(text.length()) : text).getVisualOrderText());
		addRenderableWidget(Button.builder(Component.literal(maskKey ? "显示" : "隐藏"), button -> {
			maskKey = !maskKey;
			button.setMessage(Component.literal(maskKey ? "显示" : "隐藏"));
		}).bounds(fieldX + fieldW - 52, row(0), 52, widgetH).build());

		urlBox = field(fieldX, row(1), fieldW - 56, 200, ConfigDraft.DEFAULT_BASE_URL);
		urlBox.setValue(draft.baseUrl);
		providerButton = addRenderableWidget(Button.builder(
						Component.literal(ProviderPresets.labelOf(draft.baseUrl)), button -> {
							applyProvider(ProviderPresets.nextPreset(currentBaseUrl()));
						})
				.bounds(fieldX, row(1), fieldW - 56, widgetH)
				.tooltip(Tooltip.create(Component.literal("点一下换下一个服务商（接口地址和默认模型一起换）")))
				.build());
		urlModeButton = addRenderableWidget(Button.builder(Component.literal("手填"), button -> {
			customUrl = !customUrl;
			syncProviderRow();
		}).bounds(fieldX + fieldW - 52, row(1), 52, widgetH)
				.tooltip(Tooltip.create(Component.literal("认不出的服务商就在这里手填接口地址")))
				.build());

		modelBox = field(fieldX, row(2), fieldW - 56, 100, ConfigDraft.DEFAULT_MODEL);
		modelBox.setValue(draft.model);
		modelButton = addRenderableWidget(Button.builder(Component.literal(draft.model), button -> {
					List<String> models = ProviderPresets.modelsFor(currentBaseUrl());
					setModel(ProviderPresets.next(models, draft.model));
				})
				.bounds(fieldX, row(2), fieldW - 56, widgetH)
				.tooltip(Tooltip.create(Component.literal("点一下换下一个模型")))
				.build());
		modelModeButton = addRenderableWidget(Button.builder(Component.literal("手填"), button -> {
			customModel = !customModel;
			syncModelRow();
		}).bounds(fieldX + fieldW - 52, row(2), 52, widgetH)
				.tooltip(Tooltip.create(Component.literal("列表里没有的模型就手填")))
				.build());

		langBox = field(fieldX, row(3), fieldW, 40, ConfigDraft.DEFAULT_TARGET_LANGUAGE);
		langBox.setValue(draft.targetLanguage);

		// 开关排成三列，标签取短的（完整含义放在悬停提示里），一排能放下三个
		int toggleW = Math.max(48, (fieldW - 8) / 3);
		int step = toggleW + 4;
		toggle(fieldX, row(4), toggleW, () -> draft.translateTooltips,
				value -> draft.translateTooltips = value, this::tipLabel,
				"悬停物品时的说明文字（tooltip）");
		toggle(fieldX + step, row(4), toggleW, () -> draft.translateChat,
				value -> draft.translateChat = value, this::chatLabel,
				"聊天栏里收到的消息");
		toggle(fieldX + step * 2, row(4), toggleW, () -> draft.translateSigns,
				value -> draft.translateSigns = value, this::signLabel,
				"世界里的告示牌（门禁牌、房间号这些）");
		toggle(fieldX, row(5), toggleW, () -> draft.hudVisible,
				value -> draft.hudVisible = value, this::hudLabel,
				"右上角的翻译小窗（热键 H 也能开关）");
		toggle(fieldX + step, row(5), toggleW, () -> draft.showOriginal,
				value -> draft.showOriginal = value, this::sourceLabel,
				"HUD 里要不要连原文一起显示");
		toggle(fieldX + step * 2, row(5), toggleW, () -> draft.translateNametags,
				value -> draft.translateNametags = value, this::nameLabel,
				"实体头顶的名字和世界里的悬浮大字（玩家 ID 不翻）");

		int numberW = Math.min(52, (fieldW - 8) / 2);
		hideBox = field(fieldX, row(6), numberW, 5, "6");
		hideBox.setValue(draft.autoHideSeconds);
		timeoutBox = field(fieldX + fieldW - numberW, row(6), numberW, 5, "30");
		timeoutBox.setValue(draft.timeoutSeconds);

		int buttonsY = panelTop + 28 + ROWS * rowH + 8;
		int buttonW = Math.max(60, (panelW - 28 - 8) / 3);
		addRenderableWidget(Button.builder(Component.literal("保存"), button -> save())
				.bounds(panelLeft + 14, buttonsY, buttonW, widgetH).build());
		addRenderableWidget(Button.builder(Component.literal("测试一下"), button -> test())
				.bounds(panelLeft + 18 + buttonW, buttonsY, buttonW, widgetH).build());
		addRenderableWidget(Button.builder(Component.literal("保存并关闭"), button -> {
			save();
			onClose();
		}).bounds(panelLeft + 22 + buttonW * 2, buttonsY, buttonW, widgetH).build());

		customUrl = ProviderPresets.isCustom(ProviderPresets.guess(draft.baseUrl));
		customModel = !ProviderPresets.modelsFor(draft.baseUrl).contains(draft.model);
		syncProviderRow();
		syncModelRow();
	}

	/** 以输入框里的地址为准（列表模式下两者是同步的）。 */
	private String currentBaseUrl() {
		return customUrl ? urlBox.getValue() : draft.baseUrl;
	}

	private void setModel(String model) {
		if (model == null || model.isBlank()) {
			return;
		}
		draft.model = model;
		modelBox.setValue(model);
		modelButton.setMessage(Component.literal(model));
	}

	/** 换服务商：地址和默认模型一起换，免得拿 A 家的模型去请求 B 家。 */
	private void applyProvider(ProviderPresets.Preset preset) {
		draft.baseUrl = preset.baseUrl;
		urlBox.setValue(preset.baseUrl);
		providerButton.setMessage(Component.literal(preset.label));
		if (!preset.models.contains(draft.model)) {
			setModel(preset.defaultModel());
		}
		customModel = preset.models.isEmpty();
		syncModelRow();
	}

	/** 接口地址行：列表模式显示服务商按钮，手填模式显示输入框。 */
	private void syncProviderRow() {
		urlBox.visible = customUrl;
		urlBox.active = customUrl;
		providerButton.visible = !customUrl;
		providerButton.active = !customUrl;
		urlModeButton.setMessage(Component.literal(customUrl ? "列表" : "手填"));
		if (customUrl) {
			urlBox.setValue(draft.baseUrl);
		} else {
			ProviderPresets.Preset preset = ProviderPresets.guess(draft.baseUrl);
			if (ProviderPresets.isCustom(preset)) {
				applyProvider(ProviderPresets.all().get(0));
			} else {
				providerButton.setMessage(Component.literal(preset.label));
			}
		}
	}

	/** 模型行：列表模式显示模型按钮，手填模式显示输入框。 */
	private void syncModelRow() {
		modelBox.visible = customModel;
		modelBox.active = customModel;
		modelButton.visible = !customModel;
		modelButton.active = !customModel;
		modelModeButton.setMessage(Component.literal(customModel ? "列表" : "手填"));
		if (customModel) {
			modelBox.setValue(draft.model);
			return;
		}
		List<String> models = ProviderPresets.modelsFor(customUrl ? urlBox.getValue() : draft.baseUrl);
		if (models.isEmpty()) {
			customModel = true;          // 认不出的服务商只能手填
			syncModelRow();
			return;
		}
		if (!models.contains(draft.model)) {
			setModel(models.get(0));
		} else {
			modelButton.setMessage(Component.literal(draft.model));
		}
	}

	private int row(int index) {
		return panelTop + 28 + index * rowH;
	}

	private EditBox field(int x, int y, int width, int maxLength, String hint) {
		EditBox box = new EditBox(font, x, y, width, widgetH, Component.literal(hint));
		box.setMaxLength(maxLength);
		box.setHint(Component.literal(hint));
		return addRenderableWidget(box);
	}

	/** 开关按钮：点一下翻转并刷新自己的标签，免得看不出现在是什么状态。 */
	private void toggle(int x, int y, int width, java.util.function.BooleanSupplier get,
			java.util.function.Consumer<Boolean> set, java.util.function.Supplier<String> label,
			String tooltip) {
		addRenderableWidget(Button.builder(Component.literal(label.get()), self -> {
			set.accept(!get.getAsBoolean());
			self.setMessage(Component.literal(label.get()));
		}).bounds(x, y, width, widgetH).tooltip(Tooltip.create(Component.literal(tooltip))).build());
	}

	private String tipLabel() {
		return "提示：" + onOff(draft.translateTooltips);
	}

	private String chatLabel() {
		return "聊天：" + onOff(draft.translateChat);
	}

	private String signLabel() {
		return "牌子：" + onOff(draft.translateSigns);
	}

	private String nameLabel() {
		return "名字：" + onOff(draft.translateNametags);
	}

	private String hudLabel() {
		return "HUD：" + onOff(draft.hudVisible);
	}

	private String sourceLabel() {
		return "原文：" + onOff(draft.showOriginal);
	}

	private static String onOff(boolean value) {
		return value ? "开" : "关";
	}

	/** 把输入框里的最新内容收进草稿（保存/测试之前都先做这一步）。 */
	private void pullFromBoxes() {
		draft.apiKey = keyBox.getValue();
		draft.baseUrl = urlBox.getValue();
		draft.model = modelBox.getValue();
		draft.targetLanguage = langBox.getValue();
		draft.autoHideSeconds = hideBox.getValue();
		draft.timeoutSeconds = timeoutBox.getValue();
	}

	private void save() {
		pullFromBoxes();
		notes.clear();
		notes.addAll(draft.applyTo(config));
		config.save();
		if (notes.isEmpty()) {
			status = "✓ 已保存到 config/mchanhua.json";
			statusColor = COLOR_OK;
		} else {
			status = String.join("；", notes);
			statusColor = config.ready() ? COLOR_WARN : COLOR_BAD;
		}
	}

	/**
	 * 用输入框里的**临时值**真打一次接口，不写文件——
	 * 免得"只是想看看 key 通不通"就把还没敲完的配置落盘了。
	 */
	private void test() {
		if (testing) {
			return;
		}
		pullFromBoxes();
		MchanhuaConfig probe = new MchanhuaConfig();
		draft.applyTo(probe);
		testing = true;
		status = "正在打一次请求…（用框里现在的值，不写文件）";
		statusColor = COLOR_LABEL;
		service.test(probe, message -> Minecraft.getInstance().execute(() -> {
			testing = false;
			statusColor = message.startsWith("✗") ? COLOR_BAD : COLOR_OK;
			status = message;
		}));
	}

	@Override
	public boolean keyPressed(KeyEvent event) {
		if (event.key() == GLFW.GLFW_KEY_ENTER || event.key() == GLFW.GLFW_KEY_KP_ENTER) {
			save();
			return true;
		}
		return super.keyPressed(event);
	}

	@Override
	public void onClose() {
		Minecraft.getInstance().setScreen(parent);
	}

	@Override
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float partialTick) {
		// 这里千万不要再调 extractBackground：上层 extractRenderStateWithTooltipAndSubtitles
		// 已经先画过背景了，再画一次会撞上原版的 "Can only blur once per frame" 直接崩游戏。
		graphics.fill(panelLeft - 1, panelTop - 1, panelLeft + panelW + 1, panelTop + panelH + 1, COLOR_BORDER);
		graphics.fill(panelLeft, panelTop, panelLeft + panelW, panelTop + panelH, COLOR_PANEL);
		graphics.centeredText(font, title, width / 2, panelTop + 8, COLOR_TITLE);

		label(graphics, "API Key", row(0));
		label(graphics, "接口地址", row(1));
		label(graphics, "模型", row(2));
		label(graphics, "目标语言", row(3));
		label(graphics, "翻译开关", row(4));
		label(graphics, "显示", row(5));
		label(graphics, "秒数", row(6));

		if (fieldW >= 190) {
			graphics.text(font, "0=常显", fieldX + 58, row(6) + (widgetH - 8) / 2, COLOR_LABEL);
			graphics.text(font, "超时", fieldX + fieldW - 52 - 34, row(6) + (widgetH - 8) / 2, COLOR_LABEL);
		}

		super.extractRenderState(graphics, mouseX, mouseY, partialTick);

		int statusY = panelTop + 28 + ROWS * rowH + 8 + widgetH + 6;
		List<String> lines = HudTextLayout.wrap(font::width, status, panelW - 28, 2);
		for (int i = 0; i < lines.size(); i++) {
			graphics.text(font, lines.get(i), panelLeft + 14, statusY + i * 10, statusColor);
		}
	}

	private void label(GuiGraphicsExtractor graphics, String text, int y) {
		graphics.text(font, text, panelLeft + 14, y + (widgetH - 8) / 2, COLOR_LABEL);
	}
}
