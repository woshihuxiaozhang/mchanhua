# mchanhua 1.20.1（独立工程）

和 `mod-legacy`（1.21.1）是同一套代码的两份拷贝：老版本之间 API 签名有差别，分开建工程各自独立可测。

## 状态

| 项 | 状态 |
|---|---|
| 构建 + 自测（hudtest 29 + configtest 107 + translatetest 75） | ✅ 211 项全绿 |
| 客户端启动 + mod 加载 | ✅ 实测通过（JDK 17，无 mixin 报错） |
| 进游戏逐项功能验证（tooltip / 聊天 / 标题 / HUD / 告示牌 / 名牌 / 悬浮字 / 书页） | ⏳ 待做 |

## 1.20.1 与 1.21.1 的差异（这次踩到的）

| 位置 | 1.21.1 | 1.20.1 |
|---|---|---|
| 物品 tooltip | `getTooltip(Item$TooltipContext, PlayerEntity, TooltipType)` | `getTooltip(PlayerEntity, client.item.TooltipContext)`（两参数） |
| 书页 `Contents` | record，可直接注入 `getPage` | **接口**，不能注入 → 改成 `@Redirect` `render` 里的取页调用 |
| 名牌 | `renderLabelIfPresent(entity, text, matrices, consumers, light, tickDelta)` | **少一个 tickDelta** |
| loader | 0.19.5 可用 | 0.19.5 会让 Loom 1.13.6 重映射报 EnvType 错；又必须 ≥0.16.10（Fabric API 要求）→ 用 **0.16.14** |

## 开发环境额外依赖（老 loader 需要，只影响开发）

`compileOnly sponge-mixin` + `runtimeOnly`：sponge-mixin、asm 全家桶、tiny-mappings-parser、tiny-remapper、access-widener。

## 命令

```bash
.\gradlew.bat build        # 构建 + 自测
.\gradlew.bat runClient    # 进游戏（需要 JDK 17：D:\Tools\jdk-17）
```
