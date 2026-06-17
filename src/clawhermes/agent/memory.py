"""
ClawHermes - 记忆系统
支持多 Provider（ChromaDB / JSON 文件）
"""
from __future__ import annotations

import json
import logging
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from clawhermes.types import MemoryItem, MemoryScope

logger = logging.getLogger(__name__)


class MemoryProvider(ABC):
    """记忆提供者抽象"""

    @abstractmethod
    def save(self, item: MemoryItem):
        """保存一条记忆"""

    @abstractmethod
    def search(self, query: str, limit: int = 5) -> list[MemoryItem]:
        """搜索相关记忆"""

    @abstractmethod
    def get_recent(self, limit: int = 10) -> list[MemoryItem]:
        """获取最近记忆"""


class JSONMemoryProvider(MemoryProvider):
    """JSON 文件记忆存储（轻量，零依赖）"""

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.data_dir / "memory.json"
        self._items: list[dict] = []
        self._load()

    def _load(self):
        if self._file.exists():
            try:
                self._items = json.loads(self._file.read_text())
            except Exception:
                self._items = []

    def _save(self):
        self._file.write_text(json.dumps(self._items, ensure_ascii=False, indent=2))

    def save(self, item: MemoryItem):
        self._items.append({
            "id": item.id,
            "content": item.content,
            "scope": item.scope.value,
            "metadata": item.metadata,
            "created_at": item.created_at.isoformat(),
            "importance": item.importance,
        })
        self._save()

    def search(self, query: str, limit: int = 5) -> list[MemoryItem]:
        """简单的关键词搜索"""
        query_lower = query.lower()
        matched = [
            item for item in self._items
            if query_lower in item["content"].lower()
        ]
        matched.sort(key=lambda x: x["importance"], reverse=True)
        return [
            MemoryItem(
                content=m["content"],
                scope=MemoryScope(m["scope"]),
                importance=m["importance"],
            )
            for m in matched[:limit]
        ]

    def get_recent(self, limit: int = 10) -> list[MemoryItem]:
        recent = sorted(
            self._items,
            key=lambda x: x.get("created_at", ""),
            reverse=True,
        )[:limit]
        return [
            MemoryItem(
                content=m["content"],
                scope=MemoryScope(m["scope"]),
                importance=m["importance"],
            )
            for m in recent
        ]


class MemoryManager:
    """记忆管理器 - 协调多 Provider"""

    def __init__(self):
        self._providers: list[MemoryProvider] = []

    def add_provider(self, provider: MemoryProvider):
        self._providers.append(provider)

    def save(self, content: str, scope: MemoryScope = MemoryScope.USER, importance: float = 0.5):
        """保存记忆到所有 provider"""
        item = MemoryItem(
            id=uuid.uuid4().hex,
            content=content,
            scope=scope,
            importance=importance,
        )
        for p in self._providers:
            try:
                p.save(item)
            except Exception as e:
                logger.warning(f"Memory save failed: {e}")

    def search(self, query: str, limit: int = 5) -> list[MemoryItem]:
        """从所有 provider 搜索并合并"""
        all_results = []
        for p in self._providers:
            try:
                all_results.extend(p.search(query, limit))
            except Exception:
                pass
        all_results.sort(key=lambda x: x.importance, reverse=True)
        return all_results[:limit]

    def get_recent(self, limit: int = 10) -> list[MemoryItem]:
        all_items = []
        for p in self._providers:
            try:
                all_items.extend(p.get_recent(limit))
            except Exception:
                pass
        return all_items[:limit]

    def snapshot(self, query: str | None = None) -> str:
        """生成记忆快照文本（供 VolatileLayer 使用）"""
        if query:
            items = self.search(query, limit=3)
        else:
            items = self.get_recent(limit=5)

        if not items:
            return ""

        lines = []
        for item in items:
            lines.append(f"- {item.content}")
        return "\n".join(lines)
