"""
ClawHermes - 多渠道消息网关
统一 PlatformAdapter 抽象 + Telegram/Webhook 适配器
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    TEXT = "text"
    COMMAND = "command"
    PHOTO = "photo"
    AUDIO = "audio"
    DOCUMENT = "document"


@dataclass
class MessageEvent:
    """统一消息事件"""
    type: MessageType
    text: str = ""
    chat_id: str = ""
    user_id: str = ""
    platform: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class SendResult:
    """发送结果"""
    success: bool
    message_id: str = ""
    error: str = ""


class PlatformAdapter(ABC):
    """消息渠道适配器抽象"""

    @abstractmethod
    def send_text(self, chat_id: str, text: str) -> SendResult:
        """发送文本消息"""

    @abstractmethod
    def start(self, message_handler: Callable[[MessageEvent], None]):
        """启动监听"""

    @abstractmethod
    def stop(self):
        """停止监听"""


class TelegramAdapter(PlatformAdapter):
    """Telegram Bot 适配器"""

    def __init__(self, token: str):
        self.token = token
        self._api_base = f"https://api.telegram.org/bot{token}"
        self._handler: Callable | None = None
        self._running = False
        self._last_update_id = 0

    def send_text(self, chat_id: str, text: str) -> SendResult:
        import httpx
        try:
            resp = httpx.post(
                f"{self._api_base}/sendMessage",
                json={"chat_id": chat_id, "text": text},
                timeout=10,
            )
            if resp.is_success:
                data = resp.json()
                return SendResult(
                    success=True,
                    message_id=str(data.get("result", {}).get("message_id", "")),
                )
            return SendResult(success=False, error=resp.text)
        except Exception as e:
            return SendResult(success=False, error=str(e))

    def start(self, message_handler: Callable[[MessageEvent], None]):
        self._handler = message_handler
        self._running = True
        import threading
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("Telegram 适配器已启动")

    def stop(self):
        self._running = False

    def _poll_loop(self):
        import httpx
        import time

        while self._running:
            try:
                resp = httpx.get(
                    f"{self._api_base}/getUpdates",
                    params={
                        "offset": self._last_update_id + 1,
                        "timeout": 30,
                    },
                    timeout=35,
                )
                if resp.is_success:
                    data = resp.json()
                    for update in data.get("result", []):
                        self._last_update_id = update["update_id"]
                        self._process_update(update)
            except Exception as e:
                logger.warning("Telegram poll error: %s", e)
                time.sleep(5)

    def _process_update(self, update: dict):
        msg = update.get("message", {})
        chat_id = str(msg.get("chat", {}).get("id", ""))
        text = msg.get("text", "")

        if not chat_id or not text:
            return

        event = MessageEvent(
            type=MessageType.TEXT,
            text=text,
            chat_id=chat_id,
            user_id=str(msg.get("from", {}).get("id", "")),
            platform="telegram",
            raw=msg,
        )

        if text.startswith("/"):
            event.type = MessageType.COMMAND

        if self._handler:
            self._handler(event)


class WebhookAdapter(PlatformAdapter):
    """通用 Webhook 适配器（供微信/飞书等调用）"""

    def __init__(self):
        self._handler: Callable | None = None
        self._messages: list[dict] = []

    def send_text(self, chat_id: str, text: str) -> SendResult:
        return SendResult(success=True, message_id="webhook")

    def start(self, message_handler: Callable[[MessageEvent], None]):
        self._handler = message_handler

    def stop(self):
        pass

    def receive(self, platform: str, chat_id: str, text: str, user_id: str = ""):
        """外部调用此方法注入消息"""
        event = MessageEvent(
            type=MessageType.TEXT,
            text=text,
            chat_id=chat_id,
            user_id=user_id,
            platform=platform,
        )
        if self._handler:
            self._handler(event)


class GatewayManager:
    """网关管理器 - 管理所有渠道适配器"""

    def __init__(self, agent_callback: Callable[[str, str], str] | None = None):
        self._adapters: dict[str, PlatformAdapter] = {}
        self._agent_callback = agent_callback

    def register(self, name: str, adapter: PlatformAdapter):
        """注册渠道"""
        self._adapters[name] = adapter
        logger.info("渠道已注册: %s (%s)", name, type(adapter).__name__)

    def start_all(self):
        """启动所有渠道"""
        def handler(event: MessageEvent):
            self._on_message(event)

        for name, adapter in self._adapters.items():
            try:
                adapter.start(handler)
                logger.info("渠道已启动: %s", name)
            except Exception as e:
                logger.error("渠道启动失败 %s: %s", name, e)

    def stop_all(self):
        for adapter in self._adapters.values():
            try:
                adapter.stop()
            except Exception:
                pass

    def broadcast(self, text: str):
        """向所有渠道广播消息"""
        for name, adapter in self._adapters.items():
            try:
                adapter.send_text("0", text)
            except Exception as e:
                logger.warning("广播失败 %s: %s", name, e)

    def _on_message(self, event: MessageEvent):
        """收到消息时的处理"""
        if not self._agent_callback:
            logger.warning("收到消息但未设置 agent_callback: %s", event.text[:50])
            return

        try:
            response = self._agent_callback(event.text, event.chat_id)
            adapter = self._adapters.get(event.platform)
            if adapter:
                adapter.send_text(event.chat_id, response)
        except Exception as e:
            logger.error("消息处理失败: %s", e)
