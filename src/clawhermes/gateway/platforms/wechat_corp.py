"""
ClawHermes - 企业微信渠道
"""
from __future__ import annotations

import json
import logging

from clawhermes.gateway.channels import PlatformAdapter, SendResult

logger = logging.getLogger(__name__)


class WeChatCorpAdapter(PlatformAdapter):
    """企业微信渠道"""

    def __init__(self, corp_id: str = "", corp_secret: str = "", agent_id: int = 0):
        self.corp_id = corp_id
        self.corp_secret = corp_secret
        self.agent_id = agent_id
        self._token = ""

    def _get_token(self) -> str:
        if self._token:
            return self._token
        import httpx
        try:
            resp = httpx.get(
                "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                params={"corpid": self.corp_id, "corpsecret": self.corp_secret},
                timeout=10,
            )
            if resp.is_success:
                self._token = resp.json().get("access_token", "")
        except Exception:
            pass
        return self._token

    def send_text(self, chat_id: str, text: str) -> SendResult:
        token = self._get_token()
        if not token:
            return SendResult(success=False, error="获取 token 失败")
        import httpx
        try:
            resp = httpx.post(
                f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}",
                json={"touser": chat_id, "msgtype": "text", "agentid": self.agent_id,
                       "text": {"content": text}},
                timeout=10,
            )
            if resp.is_success and resp.json().get("errcode") == 0:
                return SendResult(success=True)
            return SendResult(success=False, error=resp.text)
        except Exception as e:
            return SendResult(success=False, error=str(e))
