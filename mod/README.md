# mchanhua · Minecraft 模组版

桌面版（[仓库根目录](../README.md)）靠"看屏幕 + OCR"翻译，任何游戏都能用，但要经过识别这一步。
这个模组走另一条路：**直接读游戏里的文本**（聊天、物品名、tooltip、字幕、Boss Bar、任务书……），
再交给 AI 翻译显示出来——没有 OCR 错字，还能带上"这是物品名还是台词"的上下文。

## 当前状态

**已经能在游戏里翻译了**（26.1.2 + Fabric 实测）：

- 鼠标悬停物品 → tooltip **就地变成中文**（背包、箱子、创造模式物品栏都覆盖）
- **聊天栏**：收到的服务器消息、系统提示、玩家发言（可在配置里单独关掉，见下）
- **标题 / 副标题 / ActionBar**（剧情地图的 /title、/subtitle、/actionbar）
- **Boss 栏名字**（/bossbar）
- 右上角 HUD 小窗显示「译文 + 原文」对照，跟着悬停内容更新
- 热键：`H` 开关 HUD，`J` 测试一次翻译（用来确认 API Key 通不通）
- **热键 `K` 打开设置界面**：API Key、接口地址、模型、目标语言、几个开关都在游戏里改，不用去翻 JSON

### 游戏里怎么填 Key（按 `K`）

按 `K` 弹出设置面板（原版控件手搓，不需要装 Cloth Config / ModMenu 这类前置）：

- **API Key**：直接粘进输入框，默认打码显示，点「显示」才露明文
- **服务商（接口地址行）**：点一下换下一家 —— DeepSeek / OpenAI / Kimi / 通义千问 / 智谱 GLM / 硅基流动 / 本地 Ollama，
  换服务商会**连接口地址和默认模型一起换**（拿 A 家的模型名去请求 B 家只会 404）；认不出的服务商点「手填」自己输地址
- **模型**：点一下在该服务商的可用模型之间循环（DeepSeek 是 `deepseek-chat` / `deepseek-reasoner`，
  OpenAI 是 `gpt-4o-mini` / `gpt-4o` / `gpt-4.1-mini` …）；列表里没有的点「手填」直接输模型名
- **目标语言**：写进提示词，默认「简体中文」
- **本地 Ollama**：地址填 `http://localhost:11434/v1` 时**不用填 key**，也不会再提示你填
- **测试一下**：拿**输入框里现在的值**真打一次请求，结果直接显示在面板底部
  （`✓ 通了：Steel Ingot → 钢锭` / `✗ 失败：401 ...`）；只测不写文件
- **保存 / 保存并关闭**：写回 `config/mchanhua.json`，立刻生效
- 数字填错、地址留空都会兜底并在底部用中文说清楚（例如「自动隐藏秒数「abc」不是数字，已按 6 处理」）
- 面板按 GUI 缩放自适应高度，默认窗口（427x240 GUI 单位）也不会被切掉

实测效果（真实地图 Project Elek）：物品 `Leather Cap` → 「皮帽 / 已染色 / 装备于头部时：+1 护甲」，
原文在 HUD 里对照显示；创造物品栏里 `Oak Slab` → 「橡木台阶」。

### 文本"什么时候"变中文

游戏里的文本分两种，处理方式不一样：

| 类型 | 例子 | 做法 |
|---|---|---|
| **一直在的** | 物品 tooltip、Boss 栏 | **就地替换**：第一次先显示原文并后台翻译，翻好后再遇到就是中文 |
| **一闪而过的** | 聊天、标题、副标题、ActionBar | **翻好再显示**：先按住这条，等译文回来（约 1 秒）再显示，绝不先闪一句英文又消失 |

几个"别慌"的说明：

- tooltip 需要一次网络往返：**第一次悬停先显示原文，1~2 秒后变中文**，之后就吃缓存、瞬间出译文
- 混排 tooltip（英文物品名 + 游戏自带的中文属性行）只翻英文那几行，中文行原样保留
- 网络卡住时不会一直吊着：「测试一下」会给出 `✗ 失败：请求超时…`；悬停堆积的请求会被判过期直接跳过，不会把界面堵死

### HUD 小窗的规矩（都是为了不挡视野）

- **打开任何界面（背包/箱子）时不画**——物品 tooltip 只在界面里出现，HUD 压上去会正好挡住它
- 最近一次翻译过去 `hudAutoHideSeconds`（默认 6 秒）没更新就自动收起
- 最多显示 3 行译文 + 3 行原文；**按像素宽度自动折行**（中文一个字≈英文两倍宽，按字数截断会撑破面板），放不下的末尾补「…」
- 面板宽度跟着内容走（上限 260px），译文/原文都用游戏字体的真实宽度排版，不会顶出屏幕右边
- **打开任何界面（聊天框、背包、设置…）时热键都不生效**——不然在聊天里打字，句子里带个 `h` 就把 HUD 关了
- **不再重复显示 tooltip 的译文**（tooltip 已经就地翻译了，再叠一层纯属挡视野）；HUD 只留聊天/标题这类对照

配置与缓存都在 `run/config/`（开发）或 `.minecraft/config/`（装进游戏里）：

| 文件 | 内容 |
|---|---|
| `mchanhua.json` | API Key、接口地址、模型、目标语言、tooltip / 聊天 / HUD 开关 |
| `mchanhua-cache.json` | 译文缓存（同一句只翻一次，默认最多 2000 条） |

> **关于聊天翻译**：多人的服务器上，打开它就等于把聊天内容发给第三方翻译服务，
> 有些服务器不允许。所以它是单独的开关（`mchanhua.json` 里 `translateChat`），
> 而且只翻**本地显示**的文本——不改服务器数据、不代替玩家发言。

## 版本信息

| 项目 | 值 |
|---|---|
| 目标版本 | Minecraft **26.1.2** |
| 加载器 | Fabric Loader **0.19.5** |
| 依赖 | Fabric API **0.155.3+26.1.2** |
| Loom | 1.18-SNAPSHOT |
| Java | **25**（MC 26.x 要求；本机用的是 `D:\Tools\jdk-25`） |
| 映射 | 官方映射（Yarn 在 26.x 已不再发布，官方模板也已去掉 `mappings` 声明） |
| 渲染 | 26.x 的绘制入口已改名：`GuiGraphics` → `GuiGraphicsExtractor`；HUD 用 Fabric 的 `HudElementRegistry` |

只有客户端侧逻辑：`environment: client`，不会装到服务器上，也不改存档。

## 构建与运行

```bash
cd mod
.\gradlew.bat build          # 产物：build/libs/mchanhua-mod-<版本>.jar
.\gradlew.bat runClient      # 直接启动一个带本模组的客户端（开发用）
.\gradlew.bat selftest       # 不进游戏，直接用 API Key 翻一段样例（验证提示词/网络）
```

第一次构建会下载 Gradle、Minecraft 与依赖，需要几分钟。要求 JDK 25 作为 Gradle 的 JVM
（本机已在 `%USERPROFILE%\.gradle\gradle.properties` 里指向 `D:\Tools\jdk-25`）。

## 实现要点（26.x 踩过的坑）

- **tooltip 的钩子有两层**：文本源头是 `ItemStack.getTooltipLines(...)`，界面层是
  `GuiGraphicsExtractor.setTooltipForNextFrame(...)`（有的界面只画物品名，走单 Component 重载）。
  只挂 `Screen.getTooltipFromItem` 是不够的：创造模式物品栏自己覆盖了
  `getTooltipFromContainerItem`，父类注入根本不会执行。
- **`@ModifyVariable` 不能挂在 RETURN 上**（返回值不在局部变量表里，会
  `InvalidImplicitDiscriminatorException` 直接崩游戏），改返回值要用 `@Inject` + `CallbackInfoReturnable`。
- **HUD 只在世界里渲染**，标题界面看不到；**键位也只在没有打开界面时生效**（`KeyboardHandler` 会把按键先给当前 Screen）。
- 第一次接入时踩的坑：翻好的文本如果再次进入钩子会被重复请求，所以 `TooltipTranslator` 里加了
  "已经是中文就跳过"的保护。

## 路线图

- [x] **tooltip 就地翻译**（背包 / 箱子 / 创造模式）
- [x] **HUD 小窗**（译文 + 原文对照，热键开关）
- [x] 异步翻译 + 去重 + 缓存 + 节流（单线程队列，不卡帧）
- [x] **聊天 / 标题 / 副标题 / ActionBar / Boss 栏**（剧情地图的主力文本）
- [ ] 任务书 / 模组界面（FTB Quests 这类要按 mod 适配，暂时没法通用挂钩）
- [ ] 原版成书的书页、告示牌（走屏幕上的文本渲染，需要单独评估性能）
- [ ] 术语表与"专有名词一致性"（把桌面版那套搬过来：术语表 + 自动术语表）
- [x] **游戏内设置界面（热键 `K`）**：API Key / 接口地址 / 模型 / 目标语言 / 开关 / 连通性测试；原版控件手搓，不用装 Cloth Config、ModMenu 这类前置
- [ ] 显示模式：原文 / 译文 / 双语
- [ ] 兜底：贴图里烤死的英文（地图封面、自制 GUI）仍走 OCR，复用桌面版的识别模型

## 与桌面版的关系

两边共用一套"翻译口味"：提示词模板、术语表、自动术语表、缓存与 OCR 容错。
模组版优先读文本，读不到时才考虑 OCR；桌面版继续负责"任何游戏、任何版本"的兜底。

## 许可

[MIT](../LICENSE)（骨架来自 [FabricMC/fabric-example-mod](https://github.com/FabricMC/fabric-example-mod)，CC0）。
