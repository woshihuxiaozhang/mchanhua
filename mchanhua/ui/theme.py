"""界面主题：所有颜色、字体、尺寸都从配置来，改 UI 不用动逻辑代码。

配置来源：config.toml 的 [ui] 段（设置界面也能改），或直接编辑配置文件。
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from mchanhua.config import UiConfig


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
