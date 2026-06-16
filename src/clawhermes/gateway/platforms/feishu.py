"""
ClawHermes - 飞书渠道（通过 Bridge 长连接调官方 Node SDK）
"""
from __future__ import annotations

import json
import logging

from clawhermes.gateway.channels import PlatformAdapter, SendResult

logger = logging.getLogger(__name__)


class FeishuAdapter(PlatformAdapter):
    """飞书渠道 — 通过 Bridge 调用官方 SDK"""

    def __init__(self, app_id: str = "", app_secret: str = ""):
        self.app_id = app_id
        self.app_secret = app_secret

    def send_text(self, chat_id: str, text: str) -> SendResult:
        try:
            from clawhermes.gateway.bridge import get_bridge
            bridge = get_bridge()
            if bridge.alive:
                result = bridge.send("feishu", chat_id, text)
                if not result.get("error"):
                    return SendResult(success=True)
        except Exception:
            pass
        # 回退 Python SDK
        return self._send_python(chat_id, text)

    def _send_python(self, chat_id: str, text: str) -> SendResult:
        try:
            import lark_oapi as lark
            client = lark.Client.builder().app_id(self.app_id).app_secret(self.app_secret).build()
            resp = client.im.v1.message.create(
                lark.im.v1.model.CreateMessageReq(
                    receive_id_type="chat_id",
                    body=lark.im.v1.model.CreateMessageBody(
                        receive_id=chat_id, msg_type="text",
                        content=json.dumps({"text": text}, ensure_ascii=False),
                    ),
                )
            )
            if resp.success():
                return SendResult(success=True)
            return SendResult(success=False, error=resp.msg)
        except ImportError:
            return SendResult(success=False, error="需要 lark-oapi（pip install lark-oapi）")
        except Exception as e:
            return SendResult(success=False, error=str(e))
