"""
ClawHermes - QQ 渠道（OneBot/go-cqhttp 协议）
"""
from __future__ import annotations

import logging

from clawhermes.gateway.channels import PlatformAdapter, SendResult

logger = logging.getLogger(__name__)


class QQAdapter(PlatformAdapter):
    """QQ 渠道 — 通过 go-cqhttp (OneBot 协议)"""

    def __init__(self, ws_url: str = "ws://127.0.0.1:6700", token: str = ""):
        self.ws_url = ws_url
        self.token = token

    def send_text(self, chat_id: str, text: str) -> SendResult:
        import httpx
        api_url = self.ws_url.replace("ws://", "http://").rstrip("/")
        if api_url.endswith(":6700"):
            api_url = api_url.replace(":6700", ":5700")
        params = {"user_id": int(chat_id), "message": text}
        endpoint = f"{api_url}/send_private_msg"
        if chat_id.startswith("group_"):
            params = {"group_id": int(chat_id[6:]), "message": text}
            endpoint = f"{api_url}/send_group_msg"
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            resp = httpx.get(endpoint, params=params, headers=headers, timeout=10)
            if resp.is_success and resp.json().get("status") == "ok":
                return SendResult(success=True)
            return SendResult(success=False, error=resp.text)
        except Exception as e:
            return SendResult(success=False, error=str(e))
