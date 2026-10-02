# mchanhua · Minecraft 模组版

桌面版（[仓库根目录](../README.md)）靠"看屏幕 + OCR"翻译，任何游戏都能用，但要经过识别这一步。
这个模组走另一条路：**直接读游戏里的文本**（聊天、物品名、tooltip、字幕、Boss Bar、任务书……），
再交给 AI 翻译显示出来——没有 OCR 错字，还能带上"这是物品名还是台词"的上下文。

## 当前状态

**已经能在游戏里翻译了**（26.1.2 + Fabric 实测）：

- 鼠标悬停物品 → tooltip **就地变成中文**（背包、箱子、创造模式物品栏都覆盖）
- 右上角 HUD 小窗显示「译文 + 原文」对照，跟着悬停内容更新
- 热键：`H` 开关 HUD，`J` 测试一次翻译（用来确认 API Key 通不通）

实测截图里的效果：`Oak Slab` → 「橡木台阶」；HUD 里 `金合欢木板 / Acacia Slab`。

配置与缓存都在 `run/config/`（开发）或 `.minecraft/config/`（装进游戏里）：

| 文件 | 内容 |
|---|---|
| `mchanhua.json` | API Key、接口地址、模型、目标语言、tooltip/HUD 开关 |
| `mchanhua-cache.json` | 译文缓存（同一句只翻一次，默认最多 2000 条） |

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
- [ ] 聊天 / 字幕 / Boss Bar / 标题 / 任务书（剧情地图最需要）
- [ ] 术语表与"专有名词一致性"（把桌面版那套搬过来：术语表 + 自动术语表）
- [ ] 配置界面（Cloth Config + ModMenu：API Key、显示模式、翻译源）
- [ ] 显示模式：原文 / 译文 / 双语
- [ ] 兜底：贴图里烤死的英文（地图封面、自制 GUI）仍走 OCR，复用桌面版的识别模型

## 与桌面版的关系

两边共用一套"翻译口味"：提示词模板、术语表、自动术语表、缓存与 OCR 容错。
模组版优先读文本，读不到时才考虑 OCR；桌面版继续负责"任何游戏、任何版本"的兜底。

## 许可

[MIT](../LICENSE)（骨架来自 [FabricMC/fabric-example-mod](https://github.com/FabricMC/fabric-example-mod)，CC0）。
