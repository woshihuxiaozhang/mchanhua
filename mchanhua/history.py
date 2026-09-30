"""翻译历史：**只放在内存里**，退出程序就没了，不写磁盘、不占空间。

一次翻译记成一条记录（里面可能有多行原文/译文）：
- 小窗里的时钟按钮展开后看最近 20 条；
- 设置里的「历史翻译」页看全部（内部仍有条数上限，防止挂机太久内存涨不停）。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime

DEFAULT_RECENT = 20
MAX_ENTRIES = 500
EMPTY_TEXT = "还没有翻译记录"


@dataclass(frozen=True)
class HistoryEntry:
    at: datetime
    source: tuple[str, ...]
    target: tuple[str, ...]
    region: str = ""

    @property
    def clock(self) -> str:
        """只要"时:分"。"""

        return self.at.strftime("%H:%M")

    def pairs(self) -> list[tuple[str, str]]:
        return list(zip(self.source, self.target))


class TranslationHistory:
    """内存里的翻译记录（线程安全：工作线程写、界面线程读）。"""

    def __init__(self, capacity: int = MAX_ENTRIES) -> None:
        self.capacity = max(1, int(capacity))
        self._items: list[HistoryEntry] = []
        self._lock = threading.Lock()

    def add(
        self,
        source_lines: list[str] | tuple[str, ...],
        output_lines: list[str] | tuple[str, ...],
        region: str = "",
        at: datetime | None = None,
    ) -> HistoryEntry | None:
        """记一次翻译；空行会被丢掉，全是空行则返回 None（不记）。"""

        pairs = [(src, dst) for src, dst in zip(source_lines, output_lines) if src.strip()]
        if not pairs:
            return None
        entry = HistoryEntry(
            at=at or datetime.now(),
            source=tuple(src for src, _ in pairs),
            target=tuple(dst for _, dst in pairs),
            region=region,
        )
        with self._lock:
            self._items.append(entry)
            if len(self._items) > self.capacity:
                del self._items[: len(self._items) - self.capacity]
        return entry

    def recent(self, count: int = DEFAULT_RECENT) -> list[HistoryEntry]:
        with self._lock:
            return self._items[-max(1, int(count)) :]

    def all(self) -> list[HistoryEntry]:
        with self._lock:
            return list(self._items)

    def clear(self) -> int:
        with self._lock:
            removed = len(self._items)
            self._items.clear()
        return removed

    def amend_last(self, pairs: list[tuple[str, str]]) -> bool:
        """用户手动改过译文：把最近一条记录里的译文换掉（同样只放内存里）。

        返回有没有真的改到（没有记录、或者改完跟原来一样都算没改）。
        """

        fixes = {source: target for source, target in pairs if source}
        if not fixes:
            return False
        with self._lock:
            if not self._items:
                return False
            last = self._items[-1]
            targets = tuple(
                fixes.get(source, target) for source, target in zip(last.source, last.target)
            )
            if targets == last.target:
                return False
            self._items[-1] = HistoryEntry(
                at=last.at, source=last.source, target=targets, region=last.region
            )
            return True

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


def render_entries(entries: list[HistoryEntry], empty_text: str = EMPTY_TEXT) -> str:
    """把记录排成"时间 + 译文 + 原文"的纯文本（小窗与设置共用）。"""

    if not entries:
        return empty_text
    blocks: list[str] = []
    for entry in entries:
        blocks.append(f"[{entry.clock}]")
        for source, target in entry.pairs():
            blocks.append(target)
            blocks.append(f"  ← {source}")
        blocks.append("")
    return "\n".join(blocks).rstrip()
