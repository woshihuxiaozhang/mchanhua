# 屏幕 OCR 可行性测量（含数据）

目标：判断"截取游戏画面 → OCR → 翻译"这条路在 Minecraft 上是否可行，以及瓶颈到底在哪。

## 方法

- 样例图像用 `tools/make_sample.py` 生成：字体纹理**直接取自本机客户端 jar**（`assets/minecraft/textures/font/ascii.png`、
  `unicode_page_00.png`），按 Minecraft 的方式绘制（阴影为原色 1/4、偏移 1px），再按 GUI 缩放做整数倍最近邻放大。
- 度量用 `tools/measure_ocr.py`，指标是 CER（字符错误率 = 编辑距离 / 参照文本长度），越低越好。
- 两个 OCR 引擎：
  - **Windows OCR**（`Windows.Media.Ocr`，本机只有 `zh-Hans-CN` 语言包）
  - **RapidOCR**（PP-OCR ONNX 模型，中文+英文训练）

注意：样例是合成的，不是真实截图；但字体纹理和绘制规则来自游戏本身，用于横向比较足够。

## 结果

### 1. 默认位图字体（ascii.png，8x8 像素字形）

| GUI 缩放 | Windows OCR (CER) | RapidOCR (CER) |
|---|---|---|
| x2 | 0.876 | 0.897 |
| x3 | 0.969 | 0.887 |
| x4 | 0.866 | 0.897 |

识别样例（`Steel Ingot / A sturdy ingot of steel / Right-click to place / Durability 1234 / 1234 / Requires level 30`）：

```
3T L )NGOT        ← Windows OCR
3TEEL HGOT        ← RapidOCR
2IGHT CLICK TO FLACE
$LFEILITT
2EOUIRES LEVEL
```

### 2. Unifont（游戏里 `forceUnicodeFont:true` 的效果，16x16 像素字形）

| GUI 缩放 | Windows OCR (CER) |
|---|---|
| x2 | 0.907 |
| x3 | 1.000 |

### 3. 防锯齿 TTF 字体（模拟"把游戏字体换成 TTF 的资源包"）

| TTF 字号（GUI 缩放 x2 后的实际像素） | Windows OCR (CER) | RapidOCR (CER) |
|---|---|---|
| 10px（20px） | 0.722 / 0.320（放大 2 倍后） | 0.268 |
| 12px（24px） | 0.165 | 0.175 |
| 14px（28px） | **0.062** | **0.072** |
| 18px（36px） | 0.062 | 0.309 |

### 4. 耗时（同一台机器，1280x400 左右的区域）

| 引擎 | 单帧耗时 |
|---|---|
| Windows OCR | 15~40 ms |
| RapidOCR | 165~460 ms |

## 真实截图测量（26.1.2 实例，2560x1441，GUI 缩放自动）

用玩家实际游戏截图测的，比合成样例更可信。

| 画面内容 | 引擎 | CER | 观察 |
|---|---|---|---|
| `Objective: Stop the gas leak`（白+红大字） | RapidOCR | **0.036** | 只有冒号丢失 |
| 同上 | Windows OCR | 0.214 | 红色文字识别失败 |
| 物品 tooltip（`Switch` / `可以放在：` / `磁石`） | RapidOCR | ≈0.05 | 3 行仅 1 字错（w→u），中文全对 |
| 告示牌玩家名（密集小字） | RapidOCR | 0.171 | 下划线丢失、`008`→`68` |
| 同上 | Windows OCR | 0.424 | `FreedomDeath`→`FrudomOeath` |
| 剧情字幕（大字但带灰阶模糊） | RapidOCR | 0.395 | `You managed to escape`→`Ytohgahid tirescape` |
| 同上 | Windows OCR | 0.697 | 几乎不可用 |
| 聊天栏（小字 + 半透明背景） | RapidOCR | 英文碎片化 | 英文拆成 `Prison...fron`、`Biutcfer.`；**中文行完全正确** |

放大观察字形后确认了原因：

- tooltip 的字形是**锐利的整数倍像素放大**（纯色块 + 深色阴影），OCR 表现好。
- 剧情字幕的字形带**灰阶过渡**（动画淡入淡出导致 alpha 混合，或非整数倍缩放），OCR 明显变差。
- 聊天栏文字更小，英文被拆碎，但中文（unifont 16px 放大）反而识别正确。

即便做了二值化或对比度拉伸，字幕的 CER 也只从 0.395 降到 0.382，说明问题不在对比度而在字形本身。

**实际规律：文字越大越锐利，识别越准。** 物品 tooltip、目标提示这类大字界面可用；聊天栏小字和带动画淡入的剧情字幕不可靠。

## 结论

1. **瓶颈是字体，不是 OCR 引擎。** 两个引擎在正常 TTF 文本上都很好（工程里的单元测试用 Arial 渲染，相似度 >0.9），
   但在 Minecraft 的像素字体上 CER 高达 0.87~1.00，属于不可用。
2. `forceUnicodeFont:true`（Unifont）同样救不了，甚至更差。
3. **一旦文字是防锯齿 TTF 且实际高度 ≥ 约 28px，CER 降到 6% 左右**，这条路才成立。
4. 速度上 Windows OCR 完胜（20ms vs 200ms），RapidOCR 只有在系统 OCR 不可用或需要中文识别时才值得启用。
5. 真实截图的结论要温和一些：**大字清晰的界面（tooltip、目标提示）RapidOCR 可达 CER 0.04~0.05，实用**；
   小字与动画文字（聊天栏、剧情字幕）不可靠。RapidOCR 在这类真实游戏文本上明显强于 Windows OCR。

## 可选路线

| 路线 | 文字准确率 | 代价 |
|---|---|---|
| 屏幕 OCR + 默认字体 | 不可用（CER ≥0.85） | — |
| 屏幕 OCR + TTF 字体资源包 | 可用（CER ≈6%），再叠加词典模糊匹配可接近准确 | 需要装一个字体资源包，游戏字体外观改变 |
| 运行时取词（小 mod 把悬停文本送出来） | 100%（拿到的是原始字符串） | 需要按 MC 版本/加载器各写一套 mod |

词典模糊匹配的价值：OCR 的 6% 错误率可以通过"与已知原文集合做最近邻匹配"进一步消除，
因为模组的英文原文可以离线从 jar 里提取出来做候选集。
