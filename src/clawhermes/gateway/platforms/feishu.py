"""
ClawHermes - 飞书适配器（lark-oapi WebSocket 模式）
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Callable

import lark_oapi as lark

from clawhermes.gateway.channels import PlatformAdapter, MessageEvent, MessageType, SendResult

logger = logging.getLogger(__name__)

# 事件类型常量
EVENT_TYPE_MESSAGE = "im.message.receive_v1"


class FeishuAdapter(PlatformAdapter):
    """飞书适配器 - 支持 WebSocket 长连接"""

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._handler: Callable | None = None
        self._client: lark.Client | None = None
        self._running = False

    def send_text(self, chat_id: str, text: str) -> SendResult:
        """发送文本消息到飞书"""
        if not self._client:
            return SendResult(success=False, error="客户端未初始化")

        try:
            content = json.dumps({"text": text}, ensure_ascii=False)
            resp = self._client.im.v1.message.create(
                lark.im.v1.model.CreateMessageReq(
                    receive_id_type="chat_id",
                    body=lark.im.v1.model.CreateMessageBody(
                        receive_id=chat_id,
                        msg_type="text",
                        content=content,
                    ),
                )
            )
            if resp.success():
                return SendResult(success=True)
            return SendResult(success=False, error=resp.msg)
        except Exception as e:
            return SendResult(success=False, error=str(e))

    def send_image(self, chat_id: str, image_key: str) -> SendResult:
        """发送图片"""
        return SendResult(success=False, error="图片发送未实现")

    def start(self, message_handler: Callable[[MessageEvent], None]):
        """启动 WebSocket 长连接"""
        self._handler = message_handler

        lark.logger.setLevel(logging.WARNING)

        self._running = True

        def _run():
            asyncio.run(self._ws_loop())

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        logger.info("飞书适配器已启动 (app_id=%s)", self.app_id[:15])

    async def _ws_loop(self):
        """WebSocket 长连接 - 使用 lark-oapi 原生 WS 客户端"""
        try:
            # 初始化客户端
            self._client = lark.Client.builder() \
                .app_id(self.app_id) \
                .app_secret(self.app_secret) \
                .build()

            # 注册事件处理器
            handler = lark.EventDispatcherHandler.builder(self.app_id, self.app_secret, self._client)
            # 使用 lark-oapi 的事件系统注册消息事件
            self._client.ws_event_dispatcher.register_event_type(
                EVENT_TYPE_MESSAGE,
                self._handle_message
            )

            # 启动 WS 长连接
            ws_client = lark.ws.Client(
                app_id=self.app_id,
                app_secret=self.app_secret,
            )
            await ws_client.start()
        except Exception as e:
            logger.error("飞书 WS 连接异常: %s", e)

    def _handle_message(self, req):
        """处理收到的消息"""
        data = req if isinstance(req, dict) else {}
        message = data.get("event", {}).get("message", data)
        chat_id = message.get("chat_id", "")
        msg_type = message.get("msg_type", "")
        content_str = message.get("content", "")
        text_content = ""

        if msg_type == "text":
            try:
                content = json.loads(content_str)
                text_content = content.get("text", "")
            except Exception:
                text_content = content_str or ""

        if not text_content:
            return

        event = MessageEvent(
            type=MessageType.TEXT,
            text=text_content,
            chat_id=chat_id,
            platform="feishu",
            raw=message,
        )

        if self._handler:
            self._handler(event)

    def stop(self):
        self._running = False
