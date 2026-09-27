# mchanhua

Minecraft 屏幕取词汉化小工具：按热键截取游戏画面的一块区域，本地 OCR 识别英文，
交给 DeepSeek 翻译，在一个置顶小窗里显示译文。只服务自己玩的时候看懂，不生成汉化补丁。

## 安装

```powershell
D:\Tools\Miniconda3\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

（依赖也可直接用 `pip install -e .` 安装。）

## 当前进度

- [x] 区域模型与 DPI 感知（物理像素坐标，避免 125% 缩放导致的偏移）
- [x] 配置文件读写（默认在 `%APPDATA%\mchanhua\config.toml`，仓库外）
- [x] 屏幕采集（mss 后端，Pillow 兜底）
- [x] OCR 后端两个：Windows 自带 OCR、RapidOCR
- [x] OCR 精度测量工具与结论文档（见 `docs/ocr-findings.md`）
- [x] DeepSeek 翻译（JSON 结构化输出、术语表、格式串保护）+ sqlite 缓存
- [x] 小窗界面、全局热键、框选区域

## 使用

```powershell
# 1) 生成配置文件，然后把 DeepSeek API key 填进 [translate] api_key
.\.venv\Scripts\python.exe -m mchanhua config-init

# 2) 启动小窗（默认热键：Ctrl+Alt+Q 取词翻译 / Ctrl+Alt+R 框选区域 / Ctrl+Alt+X 退出）
.\.venv\Scripts\python.exe -m mchanhua run
```

使用流程：把鼠标移到游戏里的物品上 → 按 `Ctrl+Alt+Q` → 小窗显示原文与译文。
默认按"光标周围的区域"取词，如果提示框位置特殊，按 `Ctrl+Alt+R` 拖拽框选一次，
之后一直用这个区域。翻译结果会缓存，同一句话不会重复调用接口。

## 命令行

```powershell
# 环境自检：DPI 模式、显示器、OCR 语言、API key 状态
.\.venv\Scripts\python.exe -m mchanhua probe

# 对已有截图做 OCR（排查识别效果用）
.\.venv\Scripts\python.exe -m mchanhua ocr-image shot.png --json

# 截取屏幕区域并 OCR，同时把截图存下来
.\.venv\Scripts\python.exe -m mchanhua ocr-screen -r 100,200,600,400 --save tmp/shot.png

# 指定 OCR 后端（RapidOCR 在真实游戏文本上明显更准）
.\.venv\Scripts\python.exe -m mchanhua ocr-image shot.png --backend rapidocr

# 生成默认配置文件
.\.venv\Scripts\python.exe -m mchanhua config-init
```

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## 说明

- 所有坐标都是**物理像素**。本机 2560x1440 屏幕在 125% 缩放下会被报告成 2048x1152，
  程序在启动时声明 DPI 感知，避免区域偏移。
- OCR 语言包来自系统：若 `probe` 显示语言缺失，需要在「设置 → 时间和语言 → 语言和区域」
  里为该语言安装「可选功能 → 光学字符识别」。
- 仓库不包含任何 Minecraft 素材；需要真实字体做比对时，从本机安装目录读取。
