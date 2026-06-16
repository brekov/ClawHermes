"""
ClawHermes - QQ 适配器（OneBot 协议 / go-cqhttp）
"""
from __future__ import annotations

import json
import logging
from typing import Callable

from clawhermes.gateway.channels import PlatformAdapter, MessageEvent, MessageType, SendResult

logger = logging.getLogger(__name__)


class QQAdapter(PlatformAdapter):
    """QQ 适配器 - 通过 OneBot 协议连接 go-cqhttp"""

    def __init__(self, ws_url: str = "ws://127.0.0.1:6700", token: str = ""):
        """
        :param ws_url: go-cqhttp WebSocket 地址
        :param token: 访问令牌
        """
        self.ws_url = ws_url
        self.token = token
        self._handler: Callable | None = None
        self._running = False
        self._ws = None

    def send_text(self, chat_id: str, text: str) -> SendResult:
        """发送消息（通过 HTTP API）"""
        import httpx

        # 判断是群还是私聊
        api_url = self.ws_url.replace("ws://", "http://").rstrip("/")
        if api_url.endswith(":6700"):
            api_url = api_url.replace(":6700", ":5700")  # HTTP 默认 5700 端口

        params = {"user_id": int(chat_id), "message": text}
        endpoint = f"{api_url}/send_private_msg"

        # 如果 chat_id 含 group_ 前缀则为群消息
        if chat_id.startswith("group_"):
            params = {"group_id": int(chat_id[6:]), "message": text}
            endpoint = f"{api_url}/send_group_msg"

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            resp = httpx.get(endpoint, params=params, headers=headers, timeout=10)
            if resp.is_success:
                data = resp.json()
                if data.get("status") == "ok":
                    return SendResult(success=True)
                return SendResult(success=False, error=data.get("msg", ""))
            return SendResult(success=False, error=resp.text)
        except httpx.ConnectError:
            return SendResult(success=False, error=f"无法连接到 go-cqhttp ({self.ws_url})")
        except Exception as e:
            return SendResult(success=False, error=str(e))

    def start(self, message_handler: Callable[[MessageEvent], None]):
        """启动 WebSocket 监听"""
        self._handler = message_handler
        self._running = True

        import asyncio
        import threading

        async def _listen():
            import websockets
            async with websockets.connect(self.ws_url) as ws:
                logger.info("QQ (OneBot) 已连接: %s", self.ws_url)
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                        self._process_onebot_event(data)
                    except Exception as e:
                        logger.warning("QQ 消息解析失败: %s", e)

        def _run():
            import asyncio
            asyncio.run(_listen())

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        logger.info("QQ 适配器已启动: %s", self.ws_url)

    def _process_onebot_event(self, data: dict):
        """处理 OneBot 事件"""
        post_type = data.get("post_type", "")

        if post_type == "message":
            msg_type = data.get("message_type", "")
            user_id = str(data.get("user_id", ""))
            raw_message = data.get("raw_message", data.get("message", ""))

            # 提取纯文本
            text = ""
            if isinstance(raw_message, str):
                text = raw_message
            elif isinstance(raw_message, list):
                for seg in raw_message:
                    if seg.get("type") == "text":
                        text += seg.get("data", {}).get("text", "")

            if not text:
                return

            chat_id = user_id
            if msg_type == "group":
                group_id = data.get("group_id", "")
                chat_id = f"group_{group_id}"

            event = MessageEvent(
                type=MessageType.TEXT,
                text=text,
                chat_id=chat_id,
                user_id=user_id,
                platform="qq",
                raw=data,
            )

            if self._handler:
                self._handler(event)

    def stop(self):
        self._running = False
