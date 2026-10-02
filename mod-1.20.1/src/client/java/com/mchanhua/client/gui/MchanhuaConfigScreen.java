package com.mchanhua.client.gui;

import com.mchanhua.client.config.ConfigDraft;
import com.mchanhua.client.config.MchanhuaConfig;
import com.mchanhua.client.config.ProviderPresets;
import com.mchanhua.client.hud.HudTextLayout;
import com.mchanhua.client.translate.TranslationService;

import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.DrawContext;
import net.minecraft.client.gui.screen.Screen;
import net.minecraft.client.gui.tooltip.Tooltip;
import net.minecraft.client.gui.widget.ButtonWidget;
import net.minecraft.client.gui.widget.TextFieldWidget;
import net.minecraft.text.Text;

import org.lwjgl.glfw.GLFW;

import java.util.ArrayList;
import java.util.List;

/**
 * 游戏里填 API Key 的设置界面（老版本线 / Yarn 映射版）。
 *
 * 和 26.x 那版是同一套布局与逻辑，只是名字换了：
 * Button→ButtonWidget、EditBox→TextFieldWidget、GuiGraphicsExtractor→DrawContext、
 * addRenderableWidget→addDrawableChild、addFormatter→setRenderTextProvider、setHint→setPlaceholder。
 *
 * 注意：1.21.1 的 {@code Screen.render} 自己会画背景，所以我们**不能**再画一次。
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

	private TextFieldWidget keyBox;
	private TextFieldWidget urlBox;
	private TextFieldWidget modelBox;
	private TextFieldWidget langBox;
	private TextFieldWidget hideBox;
	private TextFieldWidget timeoutBox;
	private ButtonWidget providerButton;
	private ButtonWidget modelButton;
	private ButtonWidget urlModeButton;
	private ButtonWidget modelModeButton;

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
		super(Text.literal("mchanhua 设置"));
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
		keyBox.setText(draft.apiKey);
		keyBox.setRenderTextProvider((text, firstCharacterIndex) ->
				Text.literal(maskKey ? "•".repeat(text.length()) : text).asOrderedText());
		addDrawableChild(ButtonWidget.builder(Text.literal(maskKey ? "显示" : "隐藏"), button -> {
			maskKey = !maskKey;
			button.setMessage(Text.literal(maskKey ? "显示" : "隐藏"));
		}).dimensions(fieldX + fieldW - 52, row(0), 52, widgetH).build());

		urlBox = field(fieldX, row(1), fieldW - 56, 200, ConfigDraft.DEFAULT_BASE_URL);
		urlBox.setText(draft.baseUrl);
		providerButton = addDrawableChild(ButtonWidget.builder(
						Text.literal(ProviderPresets.labelOf(draft.baseUrl)), button ->
								applyProvider(ProviderPresets.nextPreset(currentBaseUrl())))
				.dimensions(fieldX, row(1), fieldW - 56, widgetH)
				.tooltip(Tooltip.of(Text.literal("点一下换下一个服务商（接口地址和默认模型一起换）")))
				.build());
		urlModeButton = addDrawableChild(ButtonWidget.builder(Text.literal("手填"), button -> {
			customUrl = !customUrl;
			syncProviderRow();
		}).dimensions(fieldX + fieldW - 52, row(1), 52, widgetH)
				.tooltip(Tooltip.of(Text.literal("认不出的服务商就在这里手填接口地址")))
				.build());

		modelBox = field(fieldX, row(2), fieldW - 56, 100, ConfigDraft.DEFAULT_MODEL);
		modelBox.setText(draft.model);
		modelButton = addDrawableChild(ButtonWidget.builder(Text.literal(draft.model), button -> {
					List<String> models = ProviderPresets.modelsFor(currentBaseUrl());
					setModel(ProviderPresets.next(models, draft.model));
				})
				.dimensions(fieldX, row(2), fieldW - 56, widgetH)
				.tooltip(Tooltip.of(Text.literal("点一下换下一个模型")))
				.build());
		modelModeButton = addDrawableChild(ButtonWidget.builder(Text.literal("手填"), button -> {
			customModel = !customModel;
			syncModelRow();
		}).dimensions(fieldX + fieldW - 52, row(2), 52, widgetH)
				.tooltip(Tooltip.of(Text.literal("列表里没有的模型就手填")))
				.build());

		langBox = field(fieldX, row(3), fieldW, 40, ConfigDraft.DEFAULT_TARGET_LANGUAGE);
		langBox.setText(draft.targetLanguage);

		int toggleW = Math.max(38, (fieldW - 12) / 4);
		int step = toggleW + 4;
		int rowA = row(4);
		int rowB = row(5);
		toggle(fieldX, rowA, toggleW, () -> draft.translateTooltips,
				value -> draft.translateTooltips = value, this::tipLabel,
				"悬停物品时的说明文字（tooltip）");
		toggle(fieldX + step, rowA, toggleW, () -> draft.translateChat,
				value -> draft.translateChat = value, this::chatLabel,
				"聊天栏里收到的消息");
		toggle(fieldX + step * 2, rowA, toggleW, () -> draft.translateSigns,
				value -> draft.translateSigns = value, this::signLabel,
				"世界里的告示牌（这条线还没接）");
		toggle(fieldX + step * 3, rowA, toggleW, () -> draft.translateNametags,
				value -> draft.translateNametags = value, this::nameLabel,
				"实体头顶名字和悬浮大字（这条线还没接）");
		toggle(fieldX, rowB, toggleW, () -> draft.translateBooks,
				value -> draft.translateBooks = value, this::bookLabel,
				"书本页面文字（这条线还没接）");
		toggle(fieldX + step, rowB, toggleW, () -> draft.hudVisible,
				value -> draft.hudVisible = value, this::hudLabel,
				"右上角的翻译小窗（热键 H 也能开关）");
		toggle(fieldX + step * 2, rowB, toggleW, () -> draft.showOriginal,
				value -> draft.showOriginal = value, this::sourceLabel,
				"HUD 里要不要连原文一起显示");

		int numberW = Math.min(52, (fieldW - 8) / 2);
		hideBox = field(fieldX, row(6), numberW, 5, "6");
		hideBox.setText(draft.autoHideSeconds);
		timeoutBox = field(fieldX + fieldW - numberW, row(6), numberW, 5, "30");
		timeoutBox.setText(draft.timeoutSeconds);

		int buttonsY = panelTop + 28 + ROWS * rowH + 8;
		int buttonW = Math.max(60, (panelW - 28 - 8) / 3);
		addDrawableChild(ButtonWidget.builder(Text.literal("保存"), button -> save())
				.dimensions(panelLeft + 14, buttonsY, buttonW, widgetH).build());
		addDrawableChild(ButtonWidget.builder(Text.literal("测试一下"), button -> test())
				.dimensions(panelLeft + 18 + buttonW, buttonsY, buttonW, widgetH).build());
		addDrawableChild(ButtonWidget.builder(Text.literal("保存并关闭"), button -> {
			save();
			close();
		}).dimensions(panelLeft + 22 + buttonW * 2, buttonsY, buttonW, widgetH).build());

		customUrl = ProviderPresets.isCustom(ProviderPresets.guess(draft.baseUrl));
		customModel = !ProviderPresets.modelsFor(draft.baseUrl).contains(draft.model);
		syncProviderRow();
		syncModelRow();
	}

	private int row(int index) {
		return panelTop + 28 + index * rowH;
	}

	private TextFieldWidget field(int x, int y, int width, int maxLength, String hint) {
		TextFieldWidget box = new TextFieldWidget(textRenderer, x, y, width, widgetH, Text.literal(hint));
		box.setMaxLength(maxLength);
		box.setPlaceholder(Text.literal(hint));
		return addDrawableChild(box);
	}

	private void toggle(int x, int y, int width, java.util.function.BooleanSupplier get,
			java.util.function.Consumer<Boolean> set, java.util.function.Supplier<String> label,
			String tooltip) {
		addDrawableChild(ButtonWidget.builder(Text.literal(label.get()), self -> {
			set.accept(!get.getAsBoolean());
			self.setMessage(Text.literal(label.get()));
		}).dimensions(x, y, width, widgetH).tooltip(Tooltip.of(Text.literal(tooltip))).build());
	}

	private String tipLabel() {
		return "提示:" + onOff(draft.translateTooltips);
	}

	private String chatLabel() {
		return "聊天:" + onOff(draft.translateChat);
	}

	private String signLabel() {
		return "牌子:" + onOff(draft.translateSigns);
	}

	private String nameLabel() {
		return "名字:" + onOff(draft.translateNametags);
	}

	private String bookLabel() {
		return "书本:" + onOff(draft.translateBooks);
	}

	private String hudLabel() {
		return "HUD:" + onOff(draft.hudVisible);
	}

	private String sourceLabel() {
		return "原文:" + onOff(draft.showOriginal);
	}

	private static String onOff(boolean value) {
		return value ? "开" : "关";
	}

	/** 以输入框里的地址为准（列表模式下两者是同步的）。 */
	private String currentBaseUrl() {
		return customUrl ? urlBox.getText() : draft.baseUrl;
	}

	private void setModel(String model) {
		if (model == null || model.isBlank()) {
			return;
		}
		draft.model = model;
		modelBox.setText(model);
		modelButton.setMessage(Text.literal(model));
	}

	/** 换服务商：地址和默认模型一起换，免得拿 A 家的模型去请求 B 家。 */
	private void applyProvider(ProviderPresets.Preset preset) {
		draft.baseUrl = preset.baseUrl;
		urlBox.setText(preset.baseUrl);
		providerButton.setMessage(Text.literal(preset.label));
		if (!preset.models.contains(draft.model)) {
			setModel(preset.defaultModel());
		}
		customModel = preset.models.isEmpty();
		syncModelRow();
	}

	private void syncProviderRow() {
		urlBox.visible = customUrl;
		urlBox.active = customUrl;
		providerButton.visible = !customUrl;
		providerButton.active = !customUrl;
		urlModeButton.setMessage(Text.literal(customUrl ? "列表" : "手填"));
		if (customUrl) {
			urlBox.setText(draft.baseUrl);
		} else {
			ProviderPresets.Preset preset = ProviderPresets.guess(draft.baseUrl);
			if (ProviderPresets.isCustom(preset)) {
				applyProvider(ProviderPresets.all().get(0));
			} else {
				providerButton.setMessage(Text.literal(preset.label));
			}
		}
	}

	private void syncModelRow() {
		modelBox.visible = customModel;
		modelBox.active = customModel;
		modelButton.visible = !customModel;
		modelButton.active = !customModel;
		modelModeButton.setMessage(Text.literal(customModel ? "列表" : "手填"));
		if (customModel) {
			modelBox.setText(draft.model);
			return;
		}
		List<String> models = ProviderPresets.modelsFor(customUrl ? urlBox.getText() : draft.baseUrl);
		if (models.isEmpty()) {
			customModel = true;          // 认不出的服务商只能手填
			syncModelRow();
			return;
		}
		if (!models.contains(draft.model)) {
			setModel(models.get(0));
		} else {
			modelButton.setMessage(Text.literal(draft.model));
		}
	}

	/** 把输入框里的最新内容收进草稿（保存/测试之前都先做这一步）。 */
	private void pullFromBoxes() {
		draft.apiKey = keyBox.getText();
		draft.baseUrl = urlBox.getText();
		draft.model = modelBox.getText();
		draft.targetLanguage = langBox.getText();
		draft.autoHideSeconds = hideBox.getText();
		draft.timeoutSeconds = timeoutBox.getText();
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
		service.test(probe, message -> MinecraftClient.getInstance().execute(() -> {
			testing = false;
			statusColor = message.startsWith("✗") ? COLOR_BAD : COLOR_OK;
			status = message;
		}));
	}

	@Override
	public boolean keyPressed(int keyCode, int scanCode, int modifiers) {
		if (keyCode == GLFW.GLFW_KEY_ENTER || keyCode == GLFW.GLFW_KEY_KP_ENTER) {
			save();
			return true;
		}
		return super.keyPressed(keyCode, scanCode, modifiers);
	}

	@Override
	public void close() {
		MinecraftClient.getInstance().setScreen(parent);
	}

	@Override
	public void render(DrawContext context, int mouseX, int mouseY, float delta) {
		// 注意：不要再调 renderBackground——上层 Screen.render 已经画过了
		context.fill(panelLeft - 1, panelTop - 1, panelLeft + panelW + 1, panelTop + panelH + 1, COLOR_BORDER);
		context.fill(panelLeft, panelTop, panelLeft + panelW, panelTop + panelH, COLOR_PANEL);
		Text title = getTitle();
		context.drawText(textRenderer, title, width / 2 - textRenderer.getWidth(title) / 2, panelTop + 8,
				COLOR_TITLE, false);

		label(context, "API Key", row(0));
		label(context, "接口地址", row(1));
		label(context, "模型", row(2));
		label(context, "目标语言", row(3));
		label(context, "翻译开关", row(4));
		label(context, "显示", row(5));
		label(context, "秒数", row(6));

		if (fieldW >= 190) {
			context.drawText(textRenderer, "0=常显", fieldX + 58, row(6) + (widgetH - 8) / 2, COLOR_LABEL, false);
			context.drawText(textRenderer, "超时", fieldX + fieldW - 52 - 34, row(6) + (widgetH - 8) / 2,
					COLOR_LABEL, false);
		}

		super.render(context, mouseX, mouseY, delta);

		int statusY = panelTop + 28 + ROWS * rowH + 8 + widgetH + 6;
		List<String> lines = HudTextLayout.wrap(textRenderer::getWidth, status, panelW - 28, 2);
		for (int i = 0; i < lines.size(); i++) {
			context.drawText(textRenderer, lines.get(i), panelLeft + 14, statusY + i * 10, statusColor, false);
		}
	}

	private void label(DrawContext context, String text, int y) {
		context.drawText(textRenderer, text, panelLeft + 14, y + (widgetH - 8) / 2, COLOR_LABEL, false);
	}
}
