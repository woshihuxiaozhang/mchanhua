"""随包分发的多语言识别模型（目前是日语）。

自带的 rapidocr 只有中英模型，认不出假名（"ウィンドウサイズの初期化" 会认成 "の初期"）。
这里放一份 PP-OCRv4 的日语识别模型 + 多语言检测模型 + 字典，
设置里把「识别语言」选成日语就能用，不必去装 Windows 的 OCR 语言包。

模型来自 RapidOCR 发布的 ONNX 模型（PP-OCRv4 japan / multi det），
放在 `assets/models/` 下随程序一起分发（约 12MB）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mchanhua.paths import resource_dir

MODELS_SUBDIR = Path("assets") / "models"


def models_dir() -> Path:
    """模型目录：打包后在解包目录里，开发时在项目目录里。"""

    return resource_dir() / MODELS_SUBDIR


@dataclass(frozen=True)
class ModelPack:
    language: str
    label: str
    detector: Path | None      # 检测模型；None = 用默认的中英检测模型
    recognizer: Path
    keys: Path

    def files(self) -> list[Path]:
        return [path for path in (self.detector, self.recognizer, self.keys) if path]

    def missing(self) -> list[str]:
        return [path.name for path in self.files() if not path.exists()]

    @property
    def available(self) -> bool:
        return not self.missing()


def model_pack(language: str | None) -> ModelPack | None:
    """这种识别语言有没有随包的模型（没有就返回 None）。"""

    code = (language or "").strip().lower()
    if code != "ja":
        return None
    directory = models_dir()
    return ModelPack(
        language="ja",
        label="日语",
        # 检测（找文字框）继续用默认的中英模型：实测在游戏截图上比多语言检测更稳
        # （多语言检测会把一行切碎甚至丢掉开头几个字）
        detector=None,
        recognizer=directory / "japan_rec.onnx",
        keys=directory / "japan_dict.txt",
    )


def has_model(language: str | None) -> bool:
    pack = model_pack(language)
    return bool(pack and pack.available)
