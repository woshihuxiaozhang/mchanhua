"""配置文件读写。

配置默认放在 %APPDATA%\\mchanhua\\config.toml，也就是仓库之外，
避免 API key 之类的敏感信息被提交进版本库。
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from mchanhua.geometry import Region


class ConfigError(Exception):
    """配置文件不合法。"""


APP_DIR_NAME = "mchanhua"

# 配置结构版本：写进 config.toml 的 [meta] version。
# 旧版本的 exe 不知道这个字段，它保存配置时会把 [meta] 丢掉，
# 所以"文件里没有 [meta]"就等于"这份配置来自旧版本"，需要迁移。
CONFIG_VERSION = 5

# 旧版本用过的热键默认值。一旦发现配置里还是这些老值，就说明它来自旧版本，
# 直接升级成新默认值；用户自己改成别的值的项一律原样保留。
LEGACY_HOTKEYS: dict[str, dict[str, str]] = {
    "translate": {"ctrl+alt+q": "ctrl+alt"},
    "translate_clipboard": {"ctrl+alt+s": "alt+s"},
    "quit": {"ctrl+alt+x": ""},
}

# 旧版本曾经把主窗口撑成整屏（半透明白底盖住桌面，什么都点不到），
# 迁移时把尺寸收回到"小窗"的范围；用户在设置里自己定的尺寸（新版配置）不动。
LEGACY_WINDOW_LIMITS = {"width": (320, 900), "height": (160, 700)}

# v3 的默认高度偏大，会让小窗底下多出一块空白（用户反馈"窗口太高"）。
OLD_DEFAULT_HEIGHT = 235

# 已经不再支持的历史字段：配置文件里残留的就当没看见（不报"未知字段"，也别写回去）
RETIRED_FIELDS = {"ui": {"background_image"}}


def default_config_path() -> Path:
    base = os.environ.get("APPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Roaming")
    return Path(base) / APP_DIR_NAME / "config.toml"


def project_config_path(project_dir: Path | None = None) -> Path:
    """项目目录下的本地配置，放在仓库里方便直接编辑（已被 .gitignore 排除）。"""

    root = project_dir or Path(__file__).resolve().parents[1]
    return Path(root) / "config.local.toml"


@dataclass
class HotkeysConfig:
    translate: str = "ctrl+alt"
    translate_region: str = "alt+/"
    translate_fullscreen: str = "alt+m"
    translate_clipboard: str = "alt+s"
    select_region: str = "alt+v"
    toggle_window: str = "ctrl+alt+w"
    quit: str = ""            # 留空表示不注册退出热键


@dataclass
class CaptureConfig:
    backend: str = "auto"
    monitor: int = 1


@dataclass
class OcrConfig:
    backend: str = "auto"
    language: str = "auto"
    upscale: float = 1.0
    invert: bool = False
    # screen：整屏识别后按选区筛选（保证行完整，默认）
    # padded：只抓选区外扩一圈（快，但横向被切掉的长句补不回来）
    capture_mode: str = "screen"
    # 抓屏前确认画面已经稳定（1 = 不检测直接抓；2~3 = 多抓几帧比较，
    # 免得把还在淡入的提示框翻成半截）
    settle_frames: int = 2
    # 识别前的图像预处理：off / auto / contrast / sharpen / grayscale / binarize
    # auto = 画面发灰（对比度低）时自动增强，否则原样识别
    preprocess: str = "auto"
    # 把被 OCR 切碎的行拼回整句（送翻译之前）
    merge_lines: bool = True


@dataclass
class TranslateConfig:
    provider: str = "deepseek"
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    api_key: str = ""
    timeout: float = 30.0
    temperature: float = 0.0
    cache_enabled: bool = True
    # 让模型额外给一段"整理通顺"的整段译文（把 OCR 切碎的行接回去、调语序）
    humanize: bool = True
    # 目标语言：翻成什么语言（默认简体中文）
    target_language: str = "简体中文"
    # 源语言：auto = 自动识别（本地按字符集判断 + 让模型自己判断），也可以写死"英语""日语"
    source_language: str = "auto"


@dataclass
class UiConfig:
    width: int = 430
    # 最小高度：内容更高就跟着变高，内容更矮不会留空白（v4 起生效）
    height: int = 160
    font_family: str = "Microsoft YaHei UI"
    font_size: int = 13
    opacity: float = 0.90     # 灰色半透明背景（1.0 即完全不透明）
    always_on_top: bool = True
    position: str = "right"
    # ---- 主题（改这里就能换界面风格，不用动代码）----
    background: str = "#FFFFFF"    # 画布：纯白
    panel: str = "#F7F6F3"        # 面板：暖灰（配合半透明即"灰色透明"）
    border: str = "#EAEAEA"       # 结构线：极浅灰
    text: str = "#111111"         # 正文：off-black，不用纯黑
    text_dim: str = "#737069"     # 次级：暖灰（#787774 在白/灰底上只有 4.14:1，不达标）
    accent: str = "#1F6C9F"       # 强调（文字/图标）
    accent_soft: str = "#E1F3FE"  # 强调底色（淡蓝，用于标签）
    button_background: str = "#F7F6F3"
    button_text: str = "#111111"
    button_primary: str = "#111111"       # 主按钮：实心深色 + 白字
    button_primary_text: str = "#FFFFFF"
    source_font_size: int = 11
    result_font_size: int = 15
    line_height: float = 1.5          # 行高倍数（WCAG/排版规范建议正文 1.5 左右）
    padding: int = 8
    button_rows: int = 2


@dataclass
class RegionsConfig:
    """命名区域，坐标一律是物理像素。

    follow_cursor 表示"跟随光标"的相对区域：x/y 是相对光标的偏移，可取负值。
    默认值以光标为中心取一块略大于物品提示框的区域，这样提示框画在光标左侧
    还是右侧都能覆盖到。
    """

    fixed: dict[str, str] = field(default_factory=dict)
    follow_cursor: str | None = "-280,-20,560,440"
    # 参与翻译的区域（按顺序、只留启用的）。停用的区域仍留在 fixed 里，方便随时开回来。
    areas: list[str] = field(default_factory=list)
    # 退出程序就把保存的区域清掉（用户要求：不想留下上次框的区域）
    clear_on_exit: bool = True

    def fixed_region(self, name: str) -> Region | None:
        raw = self.fixed.get(name)
        return Region.parse(raw) if raw else None

    def enabled_areas(self) -> list[tuple[str, Region]]:
        """按顺序取出启用的区域：(名字, 区域)。"""

        result: list[tuple[str, Region]] = []
        for name in self.areas:
            region = self.fixed_region(name)
            if region is not None:
                result.append((name, region))
        return result

    def area_names(self) -> list[str]:
        """所有已保存区域的名字（含停用的），保持 fixed 里的顺序。"""

        return list(self.fixed.keys())

    def next_area_name(self) -> str:
        """给新区域起个不重名的名字：区域1、区域2……"""

        index = 1
        existing = set(self.fixed)
        while f"区域{index}" in existing:
            index += 1
        return f"区域{index}"

    def add_area(self, region: Region, name: str | None = None) -> str | None:
        """保存一个新区域（默认按顺序命名），并把它设为启用。

        已经到上限（MAX_AREAS）时返回 None，让调用方提示用户先删一个。
        """

        if len(self.fixed) >= MAX_AREAS:
            return None
        label = name or self.next_area_name()
        self.fixed[label] = region.to_csv()
        if label not in self.areas:
            self.areas.append(label)
        return label

    def remove_area(self, name: str) -> None:
        self.fixed.pop(name, None)
        self.areas = [item for item in self.areas if item != name]

    def rename_area(self, old: str, new: str) -> str:
        """改名（保留原有顺序与启用状态）。返回最终使用的名字。"""

        new = (new or "").strip()
        if not new or new == old:
            return old
        if new in self.fixed:
            raise ValueError(f"已经有一个叫「{new}」的区域了")
        if old in self.fixed:
            self.fixed[new] = self.fixed.pop(old)
        self.areas = [new if item == old else item for item in self.areas]
        return new

    def set_area_enabled(self, name: str, enabled: bool) -> None:
        if name not in self.fixed:
            return
        if enabled and name not in self.areas:
            self.areas.append(name)
        elif not enabled:
            self.areas = [item for item in self.areas if item != name]

    def custom_region(self) -> Region | None:
        """用户框选并保存下来的自定义选区（v2 的主用选区）。"""

        return self.fixed_region(CUSTOM_REGION_KEY)

    def set_custom_region(self, region: Region) -> None:
        """兼容老接口（"只保存一个选区"）：写成「区域1」并启用它。"""

        self.fixed[FIRST_AREA_NAME] = region.to_csv()
        if FIRST_AREA_NAME not in self.areas:
            self.areas.insert(0, FIRST_AREA_NAME)


CUSTOM_REGION_KEY = "custom"
# 第一个区域的固定名字（老的"自定义选区"迁移过来就叫这个）
FIRST_AREA_NAME = "区域1"
# 最多保存几个区域（用户要求：5 个够用，再多屏幕上也不好点）
MAX_AREAS = 5
# OCR 预处理模式（不要从 ocr.preprocess 模块导入，避免配置层依赖 PIL）
PREPROCESS_MODES = ("off", "auto", "contrast", "sharpen", "grayscale", "binarize")


@dataclass
class Config:
    hotkeys: HotkeysConfig = field(default_factory=HotkeysConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    ocr: OcrConfig = field(default_factory=OcrConfig)
    translate: TranslateConfig = field(default_factory=TranslateConfig)
    ui: UiConfig = field(default_factory=UiConfig)
    regions: RegionsConfig = field(default_factory=RegionsConfig)
    glossary: dict[str, str] = field(default_factory=dict)
    loaded_from: Path | None = field(default=None, compare=False)
    version: int = field(default=CONFIG_VERSION, compare=False)
    migrations: list[str] = field(default_factory=list, compare=False)

    @property
    def resolved_api_key(self) -> str:
        return os.environ.get("MCHANHUA_API_KEY") or self.translate.api_key

    def validate(self) -> None:
        if self.ocr.upscale <= 0:
            raise ConfigError(f"ocr.upscale 必须为正数：{self.ocr.upscale}")
        if self.ocr.capture_mode not in ("screen", "padded"):
            raise ConfigError(f"ocr.capture_mode 只能是 screen 或 padded：{self.ocr.capture_mode}")
        if not 1 <= int(self.ocr.settle_frames) <= 3:
            raise ConfigError(f"ocr.settle_frames 只能是 1~3：{self.ocr.settle_frames}")
        if (self.ocr.preprocess or "").lower() not in PREPROCESS_MODES:
            raise ConfigError(
                f"ocr.preprocess 只能是 {' / '.join(PREPROCESS_MODES)}：{self.ocr.preprocess}"
            )
        if self.translate.temperature < 0:
            raise ConfigError("translate.temperature 不能为负数")
        if not (self.translate.target_language or "").strip():
            raise ConfigError("translate.target_language 不能为空（默认「简体中文」）")
        if self.capture.monitor < 0:
            raise ConfigError("capture.monitor 不能为负数")
        if not 0 < self.ui.opacity <= 1:
            raise ConfigError(f"ui.opacity 应在 (0, 1] 之间：{self.ui.opacity}")
        for name, raw in self.regions.fixed.items():
            try:
                Region.parse(raw)
            except (TypeError, ValueError) as exc:
                raise ConfigError(f"regions.fixed.{name} 不合法：{exc}") from exc
        if self.regions.follow_cursor:
            try:
                Region.parse(self.regions.follow_cursor)
            except (TypeError, ValueError) as exc:
                raise ConfigError(f"regions.follow_cursor 不合法：{exc}") from exc


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] 必须是表（table）")
    return value


def _build(cls: type, data: dict[str, Any], section: str) -> Any:
    allowed = {f for f in cls.__dataclass_fields__}
    retired = RETIRED_FIELDS.get(section, set())
    data = {key: value for key, value in data.items() if key not in retired}
    kwargs = {k: v for k, v in data.items() if k in allowed}
    unexpected = set(data) - allowed
    try:
        instance = cls(**kwargs)
    except TypeError as exc:
        raise ConfigError(f"[{section}] 字段类型不匹配：{exc}") from exc
    if unexpected:
        # 未知字段只提示，不报错，方便配置文件向前兼容。
        print(f"[配置] 忽略 [{section}] 中未知字段：{', '.join(sorted(unexpected))}")
    return instance


def migrate(config: Config, version: int | None) -> list[str]:
    """把旧版本残留的配置修好，返回这次改了哪些项。

    version 为 None 表示文件里没有 [meta]（旧版本写的），按最老版本处理。
    """

    changes: list[str] = []
    if version is None or version < CONFIG_VERSION:
        for field_name, mapping in LEGACY_HOTKEYS.items():
            current = (getattr(config.hotkeys, field_name) or "").strip().lower()
            replacement = mapping.get(current)
            if replacement is not None and replacement != current:
                setattr(config.hotkeys, field_name, replacement)
                changes.append(f"hotkeys.{field_name}: {current} → {replacement or '（留空）'}")
        if int(config.ui.height) == OLD_DEFAULT_HEIGHT:
            config.ui.height = UiConfig.height
            changes.append(f"ui.height: {OLD_DEFAULT_HEIGHT} → {UiConfig.height}（现在高度按内容自适应）")
        for field_name, (low, high) in LEGACY_WINDOW_LIMITS.items():
            current = int(getattr(config.ui, field_name))
            clamped = min(high, max(low, current))
            if clamped != current:
                setattr(config.ui, field_name, clamped)
                changes.append(f"ui.{field_name}: {current} → {clamped}")
        # v4 及更早只有"一个自定义选区"：迁移成第一个区域，别让用户重框
        if not config.regions.areas and config.regions.fixed:
            legacy = config.regions.fixed.pop(CUSTOM_REGION_KEY, None)
            if legacy:
                config.regions.fixed = {FIRST_AREA_NAME: legacy, **config.regions.fixed}
                config.regions.areas = [FIRST_AREA_NAME]
                changes.append(f"选区：把原来的自定义选区变成「{FIRST_AREA_NAME}」（{legacy}）")
    config.version = CONFIG_VERSION
    return changes


def loads(text: str) -> Config:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"TOML 解析失败：{exc}") from exc

    fixed_raw = _section(data, "regions").get("fixed", {}) or {}
    if not isinstance(fixed_raw, dict):
        raise ConfigError("[regions.fixed] 必须是表（table）")

    meta = _section(data, "meta")
    version_raw = meta.get("version")
    version = version_raw if isinstance(version_raw, int) else None

    config = Config(
        hotkeys=_build(HotkeysConfig, _section(data, "hotkeys"), "hotkeys"),
        capture=_build(CaptureConfig, _section(data, "capture"), "capture"),
        ocr=_build(OcrConfig, _section(data, "ocr"), "ocr"),
        translate=_build(TranslateConfig, _section(data, "translate"), "translate"),
        ui=_build(UiConfig, _section(data, "ui"), "ui"),
        regions=RegionsConfig(
            fixed={str(k): str(v) for k, v in fixed_raw.items()},
            follow_cursor=_section(data, "regions").get("follow_cursor"),
            areas=[
                str(item)
                for item in (_section(data, "regions").get("areas") or [])
                if str(item).strip()
            ],
            clear_on_exit=bool(_section(data, "regions").get("clear_on_exit", True)),
        ),
        glossary={str(k): str(v) for k, v in (_section(data, "glossary")).items()},
    )
    config.validate()
    config.migrations = migrate(config, version)
    return config


def resolve_config_path(path: Path | None = None, project_dir: Path | None = None) -> Path:
    """确定实际使用的配置文件：显式指定 > 项目内 config.local.toml > %APPDATA%。"""

    if path is not None:
        return Path(path)
    local = project_config_path(project_dir)
    if local.exists():
        return local
    return default_config_path()


def load_config(path: Path | None = None, project_dir: Path | None = None) -> Config:
    target = resolve_config_path(path, project_dir)
    if not target.exists():
        config = Config()
        config.validate()
        config.loaded_from = target
        return config
    config = loads(target.read_text(encoding="utf-8"))
    config.loaded_from = target
    if config.migrations:
        # 迁移结果立刻落盘：否则下次启动还得再迁一次，日志里会反复出现同样的提示。
        try:
            save_config(config, target)
            print(f"[配置] 已把旧版本配置升级到 v{CONFIG_VERSION}：{'；'.join(config.migrations)}")
        except OSError as exc:  # pragma: no cover - 磁盘只读等极端情况
            print(f"[配置] 旧版本配置升级失败（只影响这次运行）：{exc}")
    return config


def _dump_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{text}"'


def _dump_key(name: str) -> str:
    """TOML 的裸键只允许 ASCII 字母数字和 -_：区域名/词条名带中文时得加引号。"""

    if re.fullmatch(r"[A-Za-z0-9_-]+", name or ""):
        return name
    return _dump_scalar(name)


def dumps(config: Config) -> str:
    """把配置写成 TOML。支持一层表和标量，够用且无额外依赖。"""

    lines: list[str] = []
    lines.append("[meta]")
    lines.append(f"version = {int(config.version)}")
    lines.append("")
    for section in ("hotkeys", "capture", "ocr", "translate", "ui"):
        lines.append(f"[{section}]")
        for key, value in asdict(getattr(config, section)).items():
            lines.append(f"{key} = {_dump_scalar(value)}")
        lines.append("")

    lines.append("[regions]")
    if config.regions.follow_cursor:
        lines.append(f"follow_cursor = {_dump_scalar(config.regions.follow_cursor)}")
    # 参与翻译的区域（有序）；没列进来的区域等于"停用"
    names = ", ".join(_dump_scalar(item) for item in config.regions.areas)
    lines.append(f"areas = [{names}]")
    lines.append(f"clear_on_exit = {_dump_scalar(config.regions.clear_on_exit)}")
    lines.append("")
    lines.append("[regions.fixed]")
    for name, raw in config.regions.fixed.items():
        lines.append(f"{_dump_key(name)} = {_dump_scalar(raw)}")
    lines.append("")

    lines.append("[glossary]")
    for key, value in config.glossary.items():
        lines.append(f"{_dump_key(key)} = {_dump_scalar(value)}")
    lines.append("")
    return "\n".join(lines)


def save_config(config: Config, path: Path | None = None) -> Path:
    # 与 load_config 保持一致：显式路径 > 本次加载的来源 > 默认路径
    target = Path(path) if path else (config.loaded_from or resolve_config_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(dumps(config), encoding="utf-8")
    os.replace(tmp, target)
    return target
