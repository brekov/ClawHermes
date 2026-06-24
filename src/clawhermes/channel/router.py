"""
ClawHermes - Channel Router
统一消息路由层，解耦 Gateway 与渠道适配器
"""
from __future__ import annotations

import asyncio
import enum
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from clawhermes.channel.adapter import (
    ChannelManager,
    ChannelMessage,
    ChannelResponse,
    ChannelType,
)
from clawhermes.channel.pairing import DMPairingManager

logger = logging.getLogger(__name__)


class QueueMode(str, enum.Enum):
    STEER = "steer"
    FOLLOWUP = "followup"
    COLLECT = "collect"
    INTERRUPT = "interrupt"


@dataclass
class QueuedMessage:
    message: ChannelMessage
    enqueued_at: float = field(default_factory=time.time)
    mode: QueueMode = QueueMode.STEER


@dataclass
class SessionMapping:
    channel_type: ChannelType
    chat_id: str
    session_id: str
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)


class SessionRouter:
    def __init__(self, idle_timeout_seconds: int = 86400):
        self._mappings: dict[str, SessionMapping] = {}
        self._idle_timeout = idle_timeout_seconds

    def _routing_key(self, channel_type: ChannelType, chat_id: str) -> str:
        return f"{channel_type.value}:{chat_id}"

    def resolve(self, channel_type: ChannelType, chat_id: str) -> str | None:
        key = self._routing_key(channel_type, chat_id)
        mapping = self._mappings.get(key)
        if mapping is None:
            return None
        if time.time() - mapping.last_active > self._idle_timeout:
            del self._mappings[key]
            return None
        return mapping.session_id

    def create(self, channel_type: ChannelType, chat_id: str, session_id: str | None = None) -> str:
        key = self._routing_key(channel_type, chat_id)
        if session_id is None:
            session_id = f"sess_{uuid.uuid4().hex[:12]}"
        self._mappings[key] = SessionMapping(
            channel_type=channel_type,
            chat_id=chat_id,
            session_id=session_id,
        )
        return session_id

    def touch(self, channel_type: ChannelType, chat_id: str) -> None:
        key = self._routing_key(channel_type, chat_id)
        mapping = self._mappings.get(key)
        if mapping:
            mapping.last_active = time.time()

    def remove(self, channel_type: ChannelType, chat_id: str) -> bool:
        key = self._routing_key(channel_type, chat_id)
        if key in self._mappings:
            del self._mappings[key]
            return True
        return False

    def list_mappings(self) -> list[dict[str, Any]]:
        return [
            {
                "channel_type": m.channel_type.value,
                "chat_id": m.chat_id,
                "session_id": m.session_id,
                "last_active": m.last_active,
            }
            for m in self._mappings.values()
        ]

    def cleanup_expired(self) -> int:
        now = time.time()
        expired = [
            k for k, m in self._mappings.items()
            if now - m.last_active > self._idle_timeout
        ]
        for k in expired:
            del self._mappings[k]
        return len(expired)


class ChannelRouter:
    def __init__(
        self,
        channel_manager: ChannelManager,
        session_router: SessionRouter | None = None,
        default_queue_mode: QueueMode = QueueMode.STEER,
        pairing_manager: DMPairingManager | None = None,
    ):
        self._pairing_manager = pairing_manager
        self._channel_manager = channel_manager
        self._session_router = session_router or SessionRouter()
        self._default_queue_mode = default_queue_mode
        self._agent_handler: Callable[..., Any] | None = None
        self._session_creator: Callable[..., str] | None = None
        self._running = False
        self._active_session: str | None = None
        self._active_lock = asyncio.Lock()
        self._queue: list[QueuedMessage] = []
        self._allowlist: set[str] | None = None
        self._collect_buffer: list[ChannelMessage] = []
        self._collect_timer: float | None = None

    def set_agent_handler(self, handler: Callable[..., Any]) -> None:
        self._agent_handler = handler

    def set_session_creator(self, creator: Callable[..., str]) -> None:
        self._session_creator = creator

    def set_allowlist(self, allowlist: set[str] | None) -> None:
        self._allowlist = allowlist

    @property
    def session_router(self) -> SessionRouter:
        return self._session_router

    async def start(self) -> None:
        self._running = True
        await self._channel_manager.start_all()
        self._channel_manager.set_message_handler(self._on_message)
        logger.info("Channel Router started")

    async def stop(self) -> None:
        self._running = False
        await self._channel_manager.stop_all()
        logger.info("Channel Router stopped")

    def _on_message(self, message: ChannelMessage) -> None:
        if not self._running:
            logger.warning("Router not running, dropping message: %s", message.message_id)
            return

        if self._allowlist is not None:
            if message.user.user_id not in self._allowlist:
                logger.info(
                    "User %s not in allowlist, dropping message",
                    message.user.user_id,
                )
                return

        # DM 配对安全检查
        if self._pairing_manager is not None and message.channel_type not in (
            ChannelType.CLI, ChannelType.REST
        ):
            if not self._pairing_manager.is_paired(message.user.user_id):
                logger.warning(
                    "User %s not paired on channel %s, rejecting message",
                    message.user.user_id, message.channel_type.value,
                )
                return

        chat_id = message.metadata.get("chat_id", message.user.user_id)
        session_id = self._session_router.resolve(message.channel_type, chat_id)

        if session_id is None:
            if self._session_creator:
                session_id = self._session_creator()
            else:
                session_id = self._session_router.create(message.channel_type, chat_id)

        self._session_router.touch(message.channel_type, chat_id)

        mode_str = message.metadata.get("queue_mode", self._default_queue_mode.value)
        try:
            mode = QueueMode(mode_str)
        except ValueError:
            mode = self._default_queue_mode

        qm = QueuedMessage(message=message, mode=mode)

        if self._active_session is not None and session_id == self._active_session:
            if mode == QueueMode.INTERRUPT:
                self._queue.clear()
                self._queue.insert(0, qm)
            elif mode == QueueMode.STEER:
                self._queue.append(qm)
            elif mode == QueueMode.FOLLOWUP:
                self._queue.append(qm)
            elif mode == QueueMode.COLLECT:
                self._collect_buffer.append(message)
                if self._collect_timer is None:
                    self._collect_timer = time.time()
                return
        else:
            if mode == QueueMode.COLLECT and self._collect_buffer:
                self._flush_collect_buffer(session_id)
            self._queue.append(qm)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._process_queue())
        except RuntimeError:
            pass

    def _flush_collect_buffer(self, session_id: str) -> None:
        if not self._collect_buffer:
            return
        combined_content = "\n".join(m.content for m in self._collect_buffer)
        first_msg = self._collect_buffer[0]
        merged = ChannelMessage(
            message_id=f"collect_{uuid.uuid4().hex[:8]}",
            channel_type=first_msg.channel_type,
            user=first_msg.user,
            content=combined_content,
            session_id=session_id,
            metadata={**first_msg.metadata, "queue_mode": "steer"},
        )
        self._collect_buffer.clear()
        self._collect_timer = None
        self._queue.append(QueuedMessage(message=merged, mode=QueueMode.STEER))

    async def _process_queue(self) -> None:
        if not self._queue:
            return

        async with self._active_lock:
            if not self._queue:
                return

            qm = self._queue.pop(0)
            message = qm.message
            chat_id = message.metadata.get("chat_id", message.user.user_id)
            session_id = self._session_router.resolve(message.channel_type, chat_id)

            if session_id is None:
                session_id = self._session_router.create(message.channel_type, chat_id)

            self._active_session = session_id

            try:
                if self._agent_handler:
                    result = self._agent_handler(
                        message.content,
                        session_id=session_id,
                    )

                    response = ChannelResponse(
                        content=str(result),
                        session_id=session_id,
                    )

                    adapter = self._channel_manager.get(
                        message.channel_type.value
                    )
                    if adapter:
                        await adapter.send_response(response, message)
            except Exception as e:
                logger.error("Error processing message %s: %s", message.message_id, e)
            finally:
                self._active_session = None

    def route_message(
        self,
        content: str,
        channel_type: ChannelType,
        user_id: str = "rest_user",
        chat_id: str | None = None,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if chat_id is None:
            chat_id = user_id

        resolved_session = self._session_router.resolve(channel_type, chat_id)
        if resolved_session is None:
            if session_id:
                resolved_session = session_id
                self._session_router.create(channel_type, chat_id, session_id=session_id)
            elif self._session_creator:
                resolved_session = self._session_creator()
                self._session_router.create(channel_type, chat_id, session_id=resolved_session)
            else:
                resolved_session = self._session_router.create(channel_type, chat_id)
        self._session_router.touch(channel_type, chat_id)

        if self._agent_handler:
            result = self._agent_handler(content, session_id=resolved_session)
            return str(result)

        return ""

    def get_queue_size(self) -> int:
        return len(self._queue)

    def get_active_session(self) -> str | None:
        return self._active_session

    def list_channels(self) -> list[dict[str, Any]]:
        return self._channel_manager.list_adapters()
