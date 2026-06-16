"""
ClawHermes - 渠道抽象层
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    TEXT = "text"
    COMMAND = "command"


@dataclass
class MessageEvent:
    type: MessageType = MessageType.TEXT
    text: str = ""
    chat_id: str = ""
    user_id: str = ""
    platform: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class SendResult:
    success: bool = False
    message_id: str = ""
    error: str = ""


class PlatformAdapter(ABC):
    """消息渠道适配器抽象"""

    @abstractmethod
    def send_text(self, chat_id: str, text: str) -> SendResult:
        ...

    def start(self, message_handler: Callable[[MessageEvent], None] | None = None):
        """启动监听（默认空实现，需要监听的消息渠道覆写此方法）"""
        pass

    def stop(self):
        pass


class GatewayManager:
    """网关管理器"""

    def __init__(self, agent_callback: Callable | None = None):
        self._adapters: dict[str, PlatformAdapter] = {}
        self._agent_callback = agent_callback

    def register(self, name: str, adapter: PlatformAdapter):
        self._adapters[name] = adapter

    def get(self, name: str) -> PlatformAdapter | None:
        return self._adapters.get(name)

    def start_all(self):
        for name, adapter in self._adapters.items():
            try:
                adapter.start()
                logger.info("渠道已启动: %s", name)
            except Exception as e:
                logger.error("渠道启动失败 %s: %s", name, e)

    def stop_all(self):
        for adapter in self._adapters.values():
            try:
                adapter.stop()
            except Exception:
                pass

    def list(self) -> list[str]:
        return list(self._adapters.keys())
