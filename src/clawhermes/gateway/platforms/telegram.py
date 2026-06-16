"""
ClawHermes - Telegram 渠道（通过 Bridge 调官方 SDK）
"""
from __future__ import annotations

import logging

from clawhermes.gateway.channels import PlatformAdapter, SendResult

logger = logging.getLogger(__name__)


class TelegramAdapter(PlatformAdapter):
    """Telegram 渠道"""

    def __init__(self, token: str):
        self.token = token
        self._api_base = f"https://api.telegram.org/bot{token}"

    def send_text(self, chat_id: str, text: str) -> SendResult:
        import httpx
        try:
            resp = httpx.post(
                f"{self._api_base}/sendMessage",
                json={"chat_id": chat_id, "text": text},
                timeout=10,
            )
            if resp.is_success:
                return SendResult(success=True)
            return SendResult(success=False, error=resp.text)
        except Exception as e:
            return SendResult(success=False, error=str(e))
