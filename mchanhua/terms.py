"""自动术语表：模型翻译时顺手认出的专有名词（人名、地名、物品名…）。

为什么要有它：同一个名字散在不同批次里，模型可能给出不同译法（米迦勒 / 迈卡尔），
读起来就乱了。翻译时让模型把本批的专有名词一并交回来（返回 JSON 的 terms 字段），
这里攒起来，下一批请求自动带上——同一个名字从此固定用同一种译法。

**只在本机留一天**：超过 ttl_hours（默认 24 小时）没用到的字样自动清掉，
文件在空了以后直接删除，绝不会越攒越大。想立刻清空可以在设置里点一下。
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from mchanhua.logging_setup import get_logger
from mchanhua.paths import app_dir

DEFAULT_TTL_HOURS = 24.0
MAX_ENTRIES = 200          # 一天之内也用不到这么多，兜底防止文件膨胀
TERMS_FILE_NAME = "terms.json"
FORMAT_VERSION = 1


def default_terms_path() -> Path:
    return app_dir() / TERMS_FILE_NAME


def term_key(text: str) -> str:
    """去空白 + 统一小写：同一个名字的多种写法算同一条。"""

    return " ".join((text or "").split()).casefold()


@dataclass(frozen=True)
class LearnedTerm:
    source: str
    target: str
    at: datetime
    hits: int = 1


class TermStore:
    """线程安全（工作线程写、界面线程读）的自动术语表。"""

    def __init__(
        self,
        path: Path | None = None,
        ttl_hours: float = DEFAULT_TTL_HOURS,
        max_entries: int = MAX_ENTRIES,
    ) -> None:
        self.path = Path(path) if path else default_terms_path()
        self.ttl_hours = max(0.0, float(ttl_hours))
        self.max_entries = max(1, int(max_entries))
        self._items: dict[str, LearnedTerm] = {}
        self._lock = threading.Lock()

    # ---- 读写 ----
    def load(self, now: datetime | None = None) -> int:
        """从磁盘读回来，顺手清掉过期的；返回清掉了几条。"""

        now = now or datetime.now()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return 0
        except (OSError, ValueError):
            get_logger().warning("自动术语表读不出来，当作空的：%s", self.path, exc_info=True)
            return 0
        entries = raw.get("entries") if isinstance(raw, dict) else None
        if not isinstance(entries, list):
            return 0
        loaded: dict[str, LearnedTerm] = {}
        for item in entries:
            term = _parse_term(item)
            if term is not None:
                loaded.setdefault(term_key(term.source), term)
        with self._lock:
            self._items = loaded
        return self.prune(now)

    def save(self, now: datetime | None = None) -> int:
        """落盘（先清过期）；一条都不剩就把文件删掉，返回清掉了几条。"""

        now = now or datetime.now()
        dropped = self.prune(now)
        with self._lock:
            items = list(self._items.values())
        try:
            if not items:
                self.path.unlink(missing_ok=True)
                return dropped
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": FORMAT_VERSION,
                "entries": [
                    {
                        "src": term.source,
                        "dst": term.target,
                        "at": term.at.isoformat(timespec="seconds"),
                        "hits": term.hits,
                    }
                    for term in items
                ],
            }
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:  # pragma: no cover - 磁盘异常不该影响翻译
            get_logger().warning("自动术语表写盘失败：%s", self.path, exc_info=True)
        return dropped

    # ---- 增删查 ----
    def remember(self, source: str, target: str, now: datetime | None = None) -> bool:
        """记一个新词。

        已经记过的（同一个原名）保持**第一次**的译法不动——一致性比"后来可能更好"重要；
        想改就自己改译文（手动修正会写进正式的术语表，优先级比这里高）。
        返回是不是新加的。
        """

        text = " ".join((source or "").split())
        translated = " ".join((target or "").split())
        if not text or not translated or term_key(text) == term_key(translated):
            return False
        key = term_key(text)
        now = now or datetime.now()
        with self._lock:
            existing = self._items.get(key)
            if existing is not None:
                if existing.target == translated:
                    self._items[key] = LearnedTerm(
                        source=existing.source, target=existing.target, at=now,
                        hits=existing.hits + 1,
                    )
                else:
                    # 同一个名字出现别的译法：仍按第一次的来，只把时间刷新
                    self._items[key] = LearnedTerm(
                        source=existing.source, target=existing.target, at=existing.at,
                        hits=existing.hits,
                    )
                return False
            self._items[key] = LearnedTerm(source=text, target=translated, at=now)
        return True

    def merge(self, pairs, now: datetime | None = None) -> int:
        """把一批 (原文, 译名) 记下来，返回新加了几条。"""

        added = 0
        for source, target in pairs or ():
            if self.remember(source, target, now):
                added += 1
        return added

    def prune(self, now: datetime | None = None) -> int:
        """清掉过期的（默认 24 小时没用到就丢），并兜住条数上限。"""

        now = now or datetime.now()
        deadline = now - timedelta(hours=self.ttl_hours)
        dropped = 0
        with self._lock:
            for key, term in list(self._items.items()):
                if term.at < deadline:
                    del self._items[key]
                    dropped += 1
            if len(self._items) > self.max_entries:
                ordered = sorted(self._items.items(), key=lambda item: item[1].at, reverse=True)
                for key, _term in ordered[self.max_entries :]:
                    del self._items[key]
                    dropped += 1
        return dropped

    def active(self) -> dict[str, str]:
        """当前还有效的词：{原文: 译名}（拿去注入提示词）。"""

        with self._lock:
            return {term.source: term.target for term in self._items.values()}

    def entries(self) -> list[LearnedTerm]:
        with self._lock:
            return sorted(self._items.values(), key=lambda term: term.at, reverse=True)

    def clear(self) -> int:
        """全部清掉（并删掉文件），返回清掉了几条。"""

        with self._lock:
            removed = len(self._items)
            self._items.clear()
        try:
            self.path.unlink(missing_ok=True)
        except OSError:  # pragma: no cover
            get_logger().warning("删除自动术语表文件失败：%s", self.path, exc_info=True)
        return removed

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


def _parse_term(item) -> LearnedTerm | None:
    if not isinstance(item, dict):
        return None
    source = str(item.get("src") or "").strip()
    target = str(item.get("dst") or "").strip()
    if not source or not target:
        return None
    raw_at = item.get("at")
    try:
        at = datetime.fromisoformat(str(raw_at))
    except (TypeError, ValueError):
        at = datetime.now()
    try:
        hits = max(1, int(item.get("hits", 1)))
    except (TypeError, ValueError):
        hits = 1
    return LearnedTerm(source=source, target=target, at=at, hits=hits)
