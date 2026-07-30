"""
ClawHermes - 记忆系统
支持多 Provider（ChromaDB / JSON 文件 / SQLite）
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from pathlib import Path

from clawhermes.storage.base import MemoryProvider  # noqa: F401
from clawhermes.types import MemoryItem, MemoryScope
from clawhermes.util.atomic import atomic_write

logger = logging.getLogger(__name__)


class JSONMemoryProvider(MemoryProvider):
    """JSON 文件记忆存储（轻量，零依赖）。

    M5 重构：
    - threading.RLock 保护所有读写，避免并发 save 互相覆盖
    - max_items FIFO 淘汰（按 created_at 升序丢最旧）
    - atomic_write 原子落盘
    """

    def __init__(self, data_dir: str | Path, max_items: int = 1000):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.data_dir / "memory.json"
        self._max_items = max_items
        self._lock = threading.RLock()
        self._items: list[dict] = []
        self._load()

    def _load(self):
        with self._lock:
            if self._file.exists():
                try:
                    self._items = json.loads(self._file.read_text())
                except Exception:
                    self._items = []

    def _save(self):
        with self._lock:
            atomic_write(
                self._file,
                json.dumps(self._items, ensure_ascii=False, indent=2),
            )

    def _evict_if_needed(self):
        """FIFO 淘汰：超过 max_items 时按 created_at 升序丢最旧。"""
        with self._lock:
            if len(self._items) > self._max_items:
                # 按 created_at 升序排序，丢最旧的 (created_at 缺失视为最旧)
                self._items.sort(
                    key=lambda x: x.get("created_at", ""),
                )
                overflow = len(self._items) - self._max_items
                del self._items[:overflow]

    def save(self, item: MemoryItem):
        with self._lock:
            self._items.append({
                "id": item.id,
                "content": item.content,
                "scope": item.scope.value,
                "metadata": item.metadata,
                "created_at": item.created_at.isoformat(),
                "importance": item.importance,
            })
            self._evict_if_needed()
            self._save()

    def search(self, query: str, limit: int = 5) -> list[MemoryItem]:
        """简单的关键词搜索（子串匹配，大小写不敏感）"""
        with self._lock:
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
        with self._lock:
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

    def get_all(self) -> list[MemoryItem]:
        """返回全部记忆（按 created_at 升序）。"""
        with self._lock:
            ordered = sorted(self._items, key=lambda x: x.get("created_at", ""))
            return [
                MemoryItem(
                    content=m["content"],
                    scope=MemoryScope(m["scope"]),
                    importance=m["importance"],
                )
                for m in ordered
            ]


class SQLiteMemoryProvider(MemoryProvider):
    """SQLite 记忆存储（WAL 模式，线程安全，支持 FIFO 淘汰）。

    M5 新增：与 JSONMemoryProvider 同接口，使用 sqlite3 标准库。
    表结构：memories(id TEXT PRIMARY KEY, content TEXT, importance REAL,
                    metadata TEXT, created_at REAL)
    search 使用 LIKE 子串匹配（与 JSON 版本语义一致）。
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS memories (
        id TEXT PRIMARY KEY,
        content TEXT,
        importance REAL,
        metadata TEXT,
        created_at REAL
    );
    CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);
    """

    def __init__(self, data_dir: str | Path, max_items: int = 1000):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self.data_dir / "memory.db"
        self._max_items = max_items
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._connect()

    def _connect(self):
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(self.SCHEMA)
        self._conn.commit()

    def close(self):
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    def _evict_if_needed(self):
        """FIFO 淘汰：超过 max_items 时按 created_at 升序丢最旧。"""
        assert self._conn is not None  # noqa: S101  mypy 类型收窄
        count = self._conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        if count > self._max_items:
            overflow = count - self._max_items
            self._conn.execute(
                "DELETE FROM memories WHERE id IN ("
                "  SELECT id FROM memories ORDER BY created_at ASC LIMIT ?"
                ")",
                (overflow,),
            )

    def save(self, item: MemoryItem):
        with self._lock:
            assert self._conn is not None  # noqa: S101  mypy 类型收窄
            # scope 编码进 metadata，保持表结构与设计一致
            meta = {**item.metadata, "_scope": item.scope.value}
            self._conn.execute(
                "INSERT OR REPLACE INTO memories "
                "(id, content, importance, metadata, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    item.id,
                    item.content,
                    float(item.importance),
                    json.dumps(meta, ensure_ascii=False),
                    item.created_at.timestamp(),
                ),
            )
            self._evict_if_needed()
            self._conn.commit()

    def search(self, query: str, limit: int = 5) -> list[MemoryItem]:
        """LIKE 子串匹配（大小写不敏感），按 importance 降序。"""
        with self._lock:
            assert self._conn is not None  # noqa: S101  mypy 类型收窄
            pattern = f"%{query}%"
            rows = self._conn.execute(
                "SELECT content, importance, metadata FROM memories "
                "WHERE LOWER(content) LIKE LOWER(?) "
                "ORDER BY importance DESC LIMIT ?",
                (pattern, limit),
            ).fetchall()
            return [self._row_to_item(r) for r in rows]

    def get_recent(self, limit: int = 10) -> list[MemoryItem]:
        with self._lock:
            assert self._conn is not None  # noqa: S101  mypy 类型收窄
            rows = self._conn.execute(
                "SELECT content, importance, metadata FROM memories "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._row_to_item(r) for r in rows]

    def get_all(self) -> list[MemoryItem]:
        """返回全部记忆（按 created_at 升序）。"""
        with self._lock:
            assert self._conn is not None  # noqa: S101  mypy 类型收窄
            rows = self._conn.execute(
                "SELECT content, importance, metadata FROM memories "
                "ORDER BY created_at ASC",
            ).fetchall()
            return [self._row_to_item(r) for r in rows]

    @staticmethod
    def _row_to_item(row: tuple) -> MemoryItem:
        """行转 MemoryItem，从 metadata 中还原 scope。"""
        content, importance, meta_json = row
        try:
            meta = json.loads(meta_json) if meta_json else {}
        except Exception:
            meta = {}
        scope_value = meta.pop("_scope", "user") if isinstance(meta, dict) else "user"
        return MemoryItem(
            content=content,
            scope=MemoryScope(scope_value),
            importance=float(importance) if importance is not None else 0.5,
            metadata=meta if isinstance(meta, dict) else {},
        )


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
            except Exception:  # noqa: S110  provider 失败时跳过，best-effort 聚合
                pass
        all_results.sort(key=lambda x: x.importance, reverse=True)
        return all_results[:limit]

    def get_recent(self, limit: int = 10) -> list[MemoryItem]:
        all_items = []
        for p in self._providers:
            try:
                all_items.extend(p.get_recent(limit))
            except Exception:  # noqa: S110  provider 失败时跳过，best-effort 聚合
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
