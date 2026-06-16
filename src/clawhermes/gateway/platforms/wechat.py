"""
ClawHermes - 个人微信渠道（通过 Bridge 调官方 Node SDK）
"""
from __future__ import annotations

import logging
import json

from clawhermes.gateway.channels import PlatformAdapter, SendResult

logger = logging.getLogger(__name__)


class WeChatAdapter(PlatformAdapter):
    """个人微信渠道 — 通过 Bridge 长连接调用官方 SDK"""

    def __init__(self, bot_token: str = ""):
        self.bot_token = bot_token

    def send_text(self, chat_id: str, text: str) -> SendResult:
        try:
            from clawhermes.gateway.bridge import get_bridge
            bridge = get_bridge()
            if bridge.alive:
                result = bridge.send("weixin", chat_id, text)
                if not result.get("error"):
                    return SendResult(success=True)
        except Exception:
            pass
        # 回退直连
        return self._send_direct(chat_id, text)

    def _send_direct(self, chat_id: str, text: str) -> SendResult:
        if not self.bot_token:
            return SendResult(success=False, error="bot_token 未配置")
        import httpx
        try:
            resp = httpx.post(
                "https://ilinkai.weixin.qq.com/ilink/bot/send_message",
                json={"bot_token": self.bot_token, "to_userid": chat_id,
                       "msg_type": "text", "content": text},
                timeout=10,
            )
            return SendResult(success=True)
        except Exception as e:
            return SendResult(success=False, error=str(e))
