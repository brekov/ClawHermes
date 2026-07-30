"""
ClawHermes - 存储层抽象基类
依赖倒置（A3）：将 MemoryProvider ABC 从 agent/memory.py 迁移至 storage/base.py，
使实现层（storage/chroma_memory.py）依赖同层抽象，依赖方向由「实现→业务」修正为「实现→抽象」。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from clawhermes.types import MemoryItem


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
