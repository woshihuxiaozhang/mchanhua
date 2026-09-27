"""翻译结果缓存（sqlite）。

同一句话只翻一次：按「模型 + 提示词版本 + 原文」哈希做主键。
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path


def cache_key(source: str, model: str, prompt_version: str) -> str:
    digest = hashlib.sha256(f"{model}\x00{prompt_version}\x00{source}".encode("utf-8"))
    return digest.hexdigest()


class TranslationCache:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS translations (
                key TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        self._connection.commit()

    def get(self, source: str, model: str, prompt_version: str) -> str | None:
        row = self._connection.execute(
            "SELECT target FROM translations WHERE key = ?",
            (cache_key(source, model, prompt_version),),
        ).fetchone()
        return row[0] if row else None

    def put(self, source: str, target: str, model: str, prompt_version: str) -> None:
        self._connection.execute(
            "INSERT OR REPLACE INTO translations (key, source, target, model, prompt_version)"
            " VALUES (?, ?, ?, ?, ?)",
            (cache_key(source, model, prompt_version), source, target, model, prompt_version),
        )
        self._connection.commit()

    def count(self) -> int:
        return int(self._connection.execute("SELECT COUNT(*) FROM translations").fetchone()[0])

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "TranslationCache":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

