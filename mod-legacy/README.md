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
| 版本层（tooltip / 聊天 / 标题 / 告示牌 / 名牌 / 悬浮字 / 书页 / HUD / 设置界面） | ⏳ 待按 Yarn 名字改写 |
| 进游戏实测 | ⏳ 待版本层接完后做（本机 JDK 21 已装好） |

待移植的代码都放在 `port-todo/`，是从 26.x 那版复制过来的"参考实现"：
按 Yarn 的名字改写一个就搬进 `src/`，并在 `mchanhua.client.mixins.json` 里加一条。

## 命令

```bash
.\gradlew.bat build          # 构建 + 跑全部自测（当前 211 项）
.\gradlew.bat runClient      # 进游戏实测（1.21.1）
```

移植时的坑与版本号表记在 [docs/移植笔记.md](docs/移植笔记.md)。
