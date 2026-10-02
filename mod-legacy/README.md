# mchanhua 老版本线（独立工程）

这是**另一个 mod 工程**：给 Yarn 时代的 Minecraft（先做 1.21.1）用的。
26.x 那条线在仓库的 `mod/` 里，两者独立、互不影响。

## 为什么必须单独开一个工程

26.x 用的是 **Mojang 官方映射**（26.x 已不再发布 Yarn），而 1.21.x 生态是 **Yarn**，名字全都不一样：

| 26.x（官方映射） | 老版本（Yarn） |
|---|---|
| `Minecraft` | `MinecraftClient` |
| `GuiGraphics` / `GuiGraphicsExtractor` | `DrawContext` |
| `ChatComponent` | `ChatHud` |
| `Gui` | `InGameHud` |
| `Button` / `EditBox` | `ButtonWidget` / `TextFieldWidget` |
| `Identifier.fromNamespaceAndPath` | `Identifier.of` |

另外还有个坑：老版 Fabric API 的 access widener 是 intermediary 命名空间，
**Loom 1.14+ 处理不了**（报 `Expected official namespace ... found: intermediary`），
所以这条线用旧插件 id `fabric-loom` + **Loom 1.13.6**（实测能在 Gradle 9.7.1 上跑）。

## 现状

| 部分 | 状态 |
|---|---|
| 核心链路（缓存 / 队列 / 去重 / 逐行挑选 / 配置 / 模型预设） | ✅ 已从 26.x 原样搬来并跑通 |
| 自测（hudtest 29 + configtest 107 + translatetest 75） | ✅ 211 项全绿 |
| 版本层第一批：tooltip（ItemStack + DrawContext）、聊天（ChatHud）、标题/副标题/ActionBar（InGameHud）、HUD 小窗（HudRenderCallback） | ✅ 已移植，游戏里加载成功 |
| 版本层第二批：热键 + 设置界面（K 键面板） | ⏳ |
| 版本层第三批：告示牌 / 实体名牌 / 悬浮字 / 书页 | ⏳ |
| 进游戏逐项实测（JDK 21 已装好） | ⏳ 已确认能启动并加载 mod，待逐项验证功能 |

待移植的代码都放在 `port-todo/`，是从 26.x 那版复制过来的"参考实现"：
按 Yarn 的名字改写一个就搬进 `src/`，并在 `mchanhua.client.mixins.json` 里加一条。

## 这一代 Loom 的三个坑（都已经踩过并解决）

1. **插件 id**：老版本必须用旧的 `fabric-loom`（新 id 只覆盖 Loom 1.14+）。
2. **Mixin 注解**：Loom 1.13 已默认关掉 Mixin 注解处理器，注解 API 要自己加
   （`compileOnly net.fabricmc:sponge-mixin`），重映射交给 Loom 在 remapJar 时做。
3. **dev 启动缺 ASM**：Fabric Loader 在开发环境要 ASM，而这一代 Loom 没带上
   （26.x 那代的 loader 自带），所以 `runtimeOnly` 显式补了 sponge-mixin 与 asm 全家桶。
   这只影响开发环境，打出来的 jar 里不含它们。
4. **Fabric API 必须用 `modImplementation`**：老版发的是 intermediary jar，
   Loom 要把它重映射到 Yarn（26.x 那条线因为 Fabric 已按官方映射发布，`implementation` 也行）。

## 命令

```bash
.\gradlew.bat build          # 构建 + 跑全部自测（当前 211 项）
.\gradlew.bat runClient      # 进游戏实测（1.21.1）
```

移植时的坑与版本号表记在 [docs/移植笔记.md](docs/移植笔记.md)。
