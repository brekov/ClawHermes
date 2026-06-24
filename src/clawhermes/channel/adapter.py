"""
ClawHermes - Channel Adapter SDK
标准化渠道适配器接口，让任何人都能为 ClawHermes 写渠道适配器
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from clawhermes.agent.exceptions import ClawHermesError

logger = logging.getLogger(__name__)


class ChannelError(ClawHermesError):
    """渠道相关异常"""


class ChannelConnectionError(ChannelError):
    """渠道连接失败"""


class ChannelMessageError(ChannelError):
    """渠道消息处理失败"""


class ChannelType(str, Enum):
    CLI = "cli"
    REST = "rest"
    WEBSOCKET = "websocket"
    SLACK = "slack"
    DISCORD = "discord"
    FEISHU = "feishu"
    WECHAT = "wechat"
    QQ = "qq"
    TELEGRAM = "telegram"
    CUSTOM = "custom"


@dataclass
class ChannelUser:
    user_id: str
    display_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChannelMessage:
    message_id: str
    channel_type: ChannelType
    user: ChannelUser
    content: str
    session_id: str = ""
    reply_to: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


    def to_response(self, content: str, session_id: str = "") -> "ChannelResponse":
        """从消息创建对应的响应对象"""
        return ChannelResponse(
            content=content,
            session_id=session_id or self.session_id,
            metadata={},
        )


@dataclass
class ChannelResponse:
    content: str
    session_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ChannelAdapter(ABC):
    """
    渠道适配器抽象基类

    任何渠道（CLI/REST/WebSocket/Slack/Discord/飞书等）
    都需要实现这个接口来接入 ClawHermes
    """

    def __init__(self, channel_type: ChannelType, config: dict[str, Any] | None = None):
        self.channel_type = channel_type
        self.config = config or {}
        self._on_message: Callable[[ChannelMessage], None] | None = None
        self._running = False

    @abstractmethod
    async def start(self) -> None:
        """启动渠道监听"""

    @abstractmethod
    async def stop(self) -> None:
        """停止渠道监听"""

    @abstractmethod
    async def send_response(self, response: ChannelResponse, original: ChannelMessage) -> None:
        """向渠道发送响应"""

    @abstractmethod
    async def get_user_info(self, user_id: str) -> ChannelUser | None:
        """获取用户信息"""

    def on_message(self, handler: Callable[[ChannelMessage], None]) -> None:
        """注册消息处理器"""
        self._on_message = handler

    def _dispatch_message(self, message: ChannelMessage) -> None:
        """内部方法：将消息分发给处理器"""
        if self._on_message:
            try:
                self._on_message(message)
            except Exception as e:
                logger.error("Channel message handler error: %s", e)

    @property
    def is_running(self) -> bool:
        return self._running


class CLIAdapter(ChannelAdapter):
    """命令行渠道适配器"""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(ChannelType.CLI, config)
        self._user = ChannelUser(user_id="cli_user", display_name="CLI User")

    async def start(self) -> None:
        self._running = True
        logger.info("CLI Adapter started")

    async def stop(self) -> None:
        self._running = False
        logger.info("CLI Adapter stopped")

    async def send_response(self, response: ChannelResponse, original: ChannelMessage) -> None:
        print(response.content)

    async def get_user_info(self, user_id: str) -> ChannelUser | None:
        return self._user

    def receive_message(self, content: str, session_id: str = "") -> ChannelMessage:
        """CLI 专用：手动输入消息"""
        msg = ChannelMessage(
            message_id=f"cli_{id(content)}",
            channel_type=ChannelType.CLI,
            user=self._user,
            content=content,
            session_id=session_id,
        )
        self._dispatch_message(msg)
        return msg


class RESTAdapter(ChannelAdapter):
    """REST API 渠道适配器（与 Gateway 集成）"""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(ChannelType.REST, config)
        self._pending_responses: dict[str, asyncio.Future[ChannelResponse]] = {}

    async def start(self) -> None:
        self._running = True
        logger.info("REST Adapter started")

    async def stop(self) -> None:
        self._running = False
        for fut in self._pending_responses.values():
            if not fut.done():
                fut.cancel()
        self._pending_responses.clear()
        logger.info("REST Adapter stopped")

    async def send_response(self, response: ChannelResponse, original: ChannelMessage) -> None:
        fut = self._pending_responses.pop(original.message_id, None)
        if fut and not fut.done():
            fut.set_result(response)

    async def get_user_info(self, user_id: str) -> ChannelUser | None:
        return ChannelUser(user_id=user_id, display_name=f"REST User ({user_id})")

    async def handle_request(self, content: str, user_id: str = "rest_user",
                             session_id: str = "") -> ChannelResponse:
        """REST 专用：处理 HTTP 请求并等待响应"""
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[ChannelResponse] = loop.create_future()

        msg = ChannelMessage(
            message_id=f"rest_{id(fut)}",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id=user_id),
            content=content,
            session_id=session_id,
        )
        self._pending_responses[msg.message_id] = fut
        self._dispatch_message(msg)

        return await asyncio.wait_for(fut, timeout=self.config.get("timeout", 120))


class WebSocketAdapter(ChannelAdapter):
    """WebSocket 渠道适配器"""

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(ChannelType.WEBSOCKET, config)
        self._connections: dict[str, Any] = {}

    async def start(self) -> None:
        self._running = True
        logger.info("WebSocket Adapter started")

    async def stop(self) -> None:
        self._running = False
        self._connections.clear()
        logger.info("WebSocket Adapter stopped")

    async def send_response(self, response: ChannelResponse, original: ChannelMessage) -> None:
        conn = self._connections.get(original.user.user_id)
        if conn and hasattr(conn, "send"):
            await conn.send(response.content)

    async def get_user_info(self, user_id: str) -> ChannelUser | None:
        return ChannelUser(user_id=user_id, display_name=f"WS User ({user_id[:8]})")

    def register_connection(self, user_id: str, websocket: Any) -> None:
        """注册 WebSocket 连接"""
        self._connections[user_id] = websocket

    def unregister_connection(self, user_id: str) -> None:
        """注销 WebSocket 连接"""
        self._connections.pop(user_id, None)

    def receive_message(self, content: str, user_id: str,
                        session_id: str = "") -> ChannelMessage:
        """WebSocket 专用：接收消息"""
        msg = ChannelMessage(
            message_id=f"ws_{id(content)}",
            channel_type=ChannelType.WEBSOCKET,
            user=ChannelUser(user_id=user_id),
            content=content,
            session_id=session_id,
        )
        self._dispatch_message(msg)
        return msg


class ChannelManager:
    """渠道管理器：统一管理所有渠道适配器"""

    def __init__(self):
        self._adapters: dict[str, ChannelAdapter] = {}

    def register(self, name: str, adapter: ChannelAdapter) -> None:
        self._adapters[name] = adapter
        logger.info("Channel registered: %s (%s)", name, adapter.channel_type.value)

    def unregister(self, name: str) -> None:
        adapter = self._adapters.pop(name, None)
        if adapter:
            logger.info("Channel unregistered: %s", name)

    def get(self, name: str) -> ChannelAdapter | None:
        return self._adapters.get(name)

    def list_adapters(self) -> list[dict[str, Any]]:
        return [
            {"name": n, "type": a.channel_type.value, "running": str(a.is_running)}
            for n, a in self._adapters.items()
        ]

    async def start_all(self) -> None:
        for name, adapter in self._adapters.items():
            try:
                await adapter.start()
            except Exception as e:
                logger.error("Failed to start channel %s: %s", name, e)

    async def stop_all(self) -> None:
        for name, adapter in self._adapters.items():
            try:
                await adapter.stop()
            except Exception as e:
                logger.error("Failed to stop channel %s: %s", name, e)

    def set_message_handler(self, handler: Callable[[ChannelMessage], None]) -> None:
        """为所有渠道设置统一消息处理器"""
        for adapter in self._adapters.values():
            adapter.on_message(handler)
