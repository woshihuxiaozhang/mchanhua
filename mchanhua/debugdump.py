"""把每次识别/翻译的结果落到 tmp 下，方便排查"翻译不全"这类问题。"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from mchanhua.logging_setup import get_logger


def dump_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "tmp"


def dump_last_run(image: Image.Image | None, ocr_result, result=None, directory: Path | None = None) -> None:
    """写出最后一张截图与识别/翻译结果（覆盖式，方便直接打开看）。"""

    target = Path(directory) if directory else dump_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
        if image is not None:
            image.save(target / "last_capture.png")
        payload = {
            "size": list(image.size) if image is not None else None,
            "ocr_backend": getattr(ocr_result, "backend", None),
            "ocr_ms": round(getattr(ocr_result, "elapsed_ms", 0.0), 1),
            "lines": [
                {
                    "text": line.text,
                    "box": line.box.to_tuple() if line.box else None,
                }
                for line in getattr(ocr_result, "lines", [])
            ],
        }
        if result is not None:
            payload["translate_ms"] = round(result.translate_ms, 1)
            payload["pairs"] = [
                {"src": source, "dst": target_text}
                for source, target_text in result.pairs()
            ]
            payload["warnings"] = list(result.warnings)
        (target / "last_result.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:  # pragma: no cover - 排查用，失败不影响主流程
        get_logger().warning("写出调试文件失败", exc_info=True)
