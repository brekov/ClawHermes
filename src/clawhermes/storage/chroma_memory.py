"""
ClawHermes - ChromaDB 向量记忆存储（语义检索）
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from clawhermes.agent.memory import MemoryProvider
from clawhermes.types import MemoryItem, MemoryScope

logger = logging.getLogger(__name__)


class ChromaMemoryProvider(MemoryProvider):
    """基于 ChromaDB 的向量记忆存储，支持语义搜索"""

    def __init__(self, data_dir: str | Path, collection_name: str = "clawhermes_memory"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        import chromadb
        self._client = chromadb.PersistentClient(path=str(self.data_dir / "chroma"))
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def save(self, item: MemoryItem):
        """保存一条记忆（自动向量化）"""
        doc_id = item.id or uuid.uuid4().hex
        metadata = {
            "scope": item.scope.value,
            "importance": item.importance,
            "created_at": item.created_at.isoformat(),
        }
        metadata.update(item.metadata)

        self._collection.add(
            documents=[item.content],
            metadatas=[metadata],
            ids=[doc_id],
        )

    def search(self, query: str, limit: int = 5) -> list[MemoryItem]:
        """语义搜索相关记忆"""
        results = self._collection.query(
            query_texts=[query],
            n_results=limit,
        )

        items = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                items.append(MemoryItem(
                    content=doc,
                    scope=MemoryScope(meta.get("scope", "user")),
                    importance=float(str(meta.get("importance") or "0.5")),
                    metadata={k: v for k, v in meta.items() if k not in ("scope", "importance", "created_at")},
                ))
        return items

    def get_recent(self, limit: int = 10) -> list[MemoryItem]:
        """获取最近记忆"""
        results = self._collection.get(limit=limit)
        items = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"]):
                meta = results["metadatas"][i] if results["metadatas"] else {}
                items.append(MemoryItem(
                    content=doc,
                    scope=MemoryScope(meta.get("scope", "user")),
                    importance=float(str(meta.get("importance") or "0.5")),
                ))
        return items

    def delete(self, doc_id: str):
        """删除指定记忆"""
        self._collection.delete(ids=[doc_id])

    def count(self) -> int:
        """记忆总数"""
        return self._collection.count()
