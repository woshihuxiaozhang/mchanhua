"""界面主题：所有颜色、字体、尺寸都从配置来，改 UI 不用动逻辑代码。

配置来源：config.toml 的 [ui] 段（设置界面也能改），或直接编辑配置文件。
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from mchanhua.config import UiConfig
from mchanhua.ui.contrast import audit

# 默认浅色主题（自愈时用它覆盖被旧实例写坏的混搭配色）
DEFAULT_LIGHT: dict[str, object] = {
    "background": "#f5f6f8",
    "panel": "#ffffff",
    "text": "#17171b",
    "text_dim": "#5f6470",
    "accent": "#0a66ff",
    "button_background": "#e8eaee",
    "button_text": "#17171b",
    "opacity": 1.0,
}


def heal_theme(config) -> list[str]:
    """配色不达标时恢复默认浅色。返回被修正的问题列表（空表示没问题）。

    旧实例用旧配色保存配置时，会把新版本新增的字段（如 text_dim）与旧背景混搭，
    造出"深底浅字/浅底浅字"这种读不清的配色；这里在启动时自动纠正。
    """

    theme = Theme.from_config(config.ui)
    problems = audit(theme)
    if not problems:
        return []
    for key, value in DEFAULT_LIGHT.items():
        setattr(config.ui, key, value)
    return problems


@dataclass(frozen=True)
class Theme:
    background: str
    panel: str
    text: str
    text_dim: str
    accent: str
    button_background: str
    button_text: str
    font_family: str
    font_size: int
    source_font_size: int
    result_font_size: int
    line_height: float
    padding: int
    opacity: float
    always_on_top: bool
    width: int
    height: int
    position: str

    @classmethod
    def from_config(cls, ui: UiConfig) -> "Theme":
        family = ui.font_family or "Microsoft YaHei UI"
        return cls(
            background=ui.background,
            panel=ui.panel,
            text=ui.text,
            text_dim=ui.text_dim,
            accent=ui.accent,
            button_background=ui.button_background,
            button_text=ui.button_text,
            font_family=family,
            font_size=max(8, int(ui.font_size)),
            source_font_size=max(8, int(ui.source_font_size)),
            result_font_size=max(9, int(ui.result_font_size)),
            line_height=min(2.2, max(1.1, float(getattr(ui, "line_height", 1.5)))),
            padding=max(4, int(ui.padding)),
            opacity=min(1.0, max(0.3, float(ui.opacity))),
            always_on_top=bool(ui.always_on_top),
            width=max(320, int(ui.width)),
            height=max(240, int(ui.height)),
            position=ui.position or "right",
        )

    @property
    def field_names(self) -> list[str]:
        return [field.name for field in fields(self)]
