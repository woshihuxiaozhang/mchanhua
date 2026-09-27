"""配置文件读写。

配置默认放在 %APPDATA%\\mchanhua\\config.toml，也就是仓库之外，
避免 API key 之类的敏感信息被提交进版本库。
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from mchanhua.geometry import Region


class ConfigError(Exception):
    """配置文件不合法。"""


APP_DIR_NAME = "mchanhua"


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
    translate: str = "ctrl+alt+q"
    translate_region: str = "alt+/"
    translate_fullscreen: str = "alt+m"
    translate_clipboard: str = "ctrl+alt+s"
    select_region: str = "alt+v"
    toggle_window: str = "ctrl+alt+w"
    quit: str = "ctrl+alt+x"


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


@dataclass
class TranslateConfig:
    provider: str = "deepseek"
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    api_key: str = ""
    timeout: float = 30.0
    temperature: float = 0.0
    cache_enabled: bool = True


@dataclass
class UiConfig:
    width: int = 430
    height: int = 235          # 紧凑：只放译文与原文
    font_family: str = "Microsoft YaHei UI"
    font_size: int = 13
    opacity: float = 0.90     # 灰色半透明背景（1.0 即完全不透明）
    always_on_top: bool = True
    position: str = "right"
    # ---- 主题（改这里就能换界面风格，不用动代码）----
    background: str = "#ffffff"
    panel: str = "#eef0f3"     # 浅灰面板，配合半透明更像"灰色透明"
    text: str = "#17171b"
    text_dim: str = "#5f6470"
    accent: str = "#0a66ff"
    button_background: str = "#e8eaee"
    button_text: str = "#17171b"
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

    def fixed_region(self, name: str) -> Region | None:
        raw = self.fixed.get(name)
        return Region.parse(raw) if raw else None

    def custom_region(self) -> Region | None:
        """用户框选并保存下来的自定义选区（v2 的主用选区）。"""

        return self.fixed_region(CUSTOM_REGION_KEY)

    def set_custom_region(self, region: Region) -> None:
        self.fixed[CUSTOM_REGION_KEY] = region.to_csv()


CUSTOM_REGION_KEY = "custom"


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

    @property
    def resolved_api_key(self) -> str:
        return os.environ.get("MCHANHUA_API_KEY") or self.translate.api_key

    def validate(self) -> None:
        if self.ocr.upscale <= 0:
            raise ConfigError(f"ocr.upscale 必须为正数：{self.ocr.upscale}")
        if self.ocr.capture_mode not in ("screen", "padded"):
            raise ConfigError(f"ocr.capture_mode 只能是 screen 或 padded：{self.ocr.capture_mode}")
        if self.translate.temperature < 0:
            raise ConfigError("translate.temperature 不能为负数")
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


def loads(text: str) -> Config:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"TOML 解析失败：{exc}") from exc

    fixed_raw = _section(data, "regions").get("fixed", {}) or {}
    if not isinstance(fixed_raw, dict):
        raise ConfigError("[regions.fixed] 必须是表（table）")

    config = Config(
        hotkeys=_build(HotkeysConfig, _section(data, "hotkeys"), "hotkeys"),
        capture=_build(CaptureConfig, _section(data, "capture"), "capture"),
        ocr=_build(OcrConfig, _section(data, "ocr"), "ocr"),
        translate=_build(TranslateConfig, _section(data, "translate"), "translate"),
        ui=_build(UiConfig, _section(data, "ui"), "ui"),
        regions=RegionsConfig(
            fixed={str(k): str(v) for k, v in fixed_raw.items()},
            follow_cursor=_section(data, "regions").get("follow_cursor"),
        ),
        glossary={str(k): str(v) for k, v in (_section(data, "glossary")).items()},
    )
    config.validate()
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
    return config


def _dump_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{text}"'


def dumps(config: Config) -> str:
    """把配置写成 TOML。支持一层表和标量，够用且无额外依赖。"""

    lines: list[str] = []
    for section in ("hotkeys", "capture", "ocr", "translate", "ui"):
        lines.append(f"[{section}]")
        for key, value in asdict(getattr(config, section)).items():
            lines.append(f"{key} = {_dump_scalar(value)}")
        lines.append("")

    lines.append("[regions]")
    if config.regions.follow_cursor:
        lines.append(f"follow_cursor = {_dump_scalar(config.regions.follow_cursor)}")
    lines.append("")
    lines.append("[regions.fixed]")
    for name, raw in config.regions.fixed.items():
        lines.append(f"{name} = {_dump_scalar(raw)}")
    lines.append("")

    lines.append("[glossary]")
    for key, value in config.glossary.items():
        lines.append(f"{key} = {_dump_scalar(value)}")
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
