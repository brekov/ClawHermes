"""
ClawHermes - 微信适配器（企业微信/公众号）
"""
from __future__ import annotations

import json
import logging
from typing import Callable

from clawhermes.gateway.channels import PlatformAdapter, MessageEvent, MessageType, SendResult

logger = logging.getLogger(__name__)


class WeChatAdapter(PlatformAdapter):
    """微信适配器 - 支持企业微信（WeCom）"""

    def __init__(self, corp_id: str = "", corp_secret: str = "", agent_id: int = 0,
                 bot_token: str = ""):
        """
        微信适配器，支持两种认证方式:
        1. 企业微信应用: corp_id + corp_secret + agent_id
        2. 扫码登录: bot_token（通过 clawhermes gateway setup 扫码获取）
        """
        self.corp_id = corp_id
        self.corp_secret = corp_secret
        self.agent_id = agent_id
        self.bot_token = bot_token
        self._handler: Callable | None = None
        self._running = False
        self._token = ""

    def send_text(self, chat_id: str, text: str) -> SendResult:
        """发送文本消息"""
        # 优先通过 Bridge 调用官方 Node SDK
        try:
            from clawhermes.gateway.bridge import get_bridge
            bridge = get_bridge()
            health = bridge.health()
            if health.get("status") == "ok" and health.get("weixin"):
                result = bridge.send("weixin", chat_id, text)
                if not result.get("error"):
                    return SendResult(success=True)
                logger.warning("Bridge 发送失败，回退直连: %s", result.get("error"))
        except Exception:
            pass

        # 回退到直连 ilink API
        if self.bot_token:
            return self._send_via_bot(chat_id, text)
        return self._send_via_corp(chat_id, text)

    def _send_via_bot(self, chat_id: str, text: str) -> SendResult:
        """通过 bot_token 发送（Ilio 协议）"""
        import httpx
        try:
            resp = httpx.post(
                "https://ilinkai.weixin.qq.com/ilink/bot/send_message",
                json={
                    "bot_token": self.bot_token,
                    "to_userid": chat_id,
                    "msg_type": "text",
                    "content": json.dumps({"text": text}, ensure_ascii=False),
                },
                timeout=10,
            )
            if resp.is_success:
                return SendResult(success=True)
            return SendResult(success=False, error=resp.text)
        except Exception as e:
            return SendResult(success=False, error=str(e))

    def _send_via_corp(self, chat_id: str, text: str) -> SendResult:
        """通过企业微信 API 发送"""
        token = self._get_corp_token()
        if not token:
            return SendResult(success=False, error="获取 token 失败")

        import httpx
        try:
            resp = httpx.post(
                f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}",
                json={
                    "touser": chat_id,
                    "msgtype": "text",
                    "agentid": self.agent_id,
                    "text": {"content": text},
                },
                timeout=10,
            )
            if resp.is_success:
                data = resp.json()
                if data.get("errcode") == 0:
                    return SendResult(success=True)
                return SendResult(success=False, error=data.get("errmsg", ""))
            return SendResult(success=False, error=resp.text)
        except Exception as e:
            return SendResult(success=False, error=str(e))

    def _get_corp_token(self) -> str:
        """获取企业微信 access_token"""
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
                data = resp.json()
                self._token = data.get("access_token", "")
        except Exception:
            pass
        return self._token

    def start(self, message_handler: Callable[[MessageEvent], None]):
        """启动（Webhook 模式，接收回调）"""
        self._handler = message_handler
        self._running = True
        logger.info("微信适配器已就绪 (corp_id=%s, agent_id=%s)", self.corp_id[:10], self.agent_id)

    def handle_webhook(self, body: dict) -> str:
        """处理微信回调消息"""
        text = ""
        if "text" in body:
            text = body["text"].get("content", "")
        elif "Content" in body:
            text = body["Content"]

        from_user = body.get("FromUserName", body.get("fromusername", ""))

        if not text:
            return "success"

        event = MessageEvent(
            type=MessageType.TEXT,
            text=text.strip(),
            chat_id=from_user,
            platform="wechat",
            raw=body,
        )

        if self._handler:
            self._handler(event)

        return "success"

    def stop(self):
        self._running = False


class WeChatPublicAdapter(PlatformAdapter):
    """微信公众号适配器（被动回复模式）"""

    def __init__(self, app_id: str, app_secret: str, token: str, encoding_aes_key: str = ""):
        self.app_id = app_id
        self.app_secret = app_secret
        self.token = token
        self.encoding_aes_key = encoding_aes_key
        self._handler: Callable | None = None
        self._running = False

    def send_text(self, chat_id: str, text: str) -> SendResult:
        """微信公众号通过客服接口发送消息"""
        from wechatpy import WeChatClient
        try:
            client = WeChatClient(self.app_id, self.app_secret)
            client.message.send_text(chat_id, text)
            return SendResult(success=True)
        except Exception as e:
            return SendResult(success=False, error=str(e))

    def start(self, message_handler: Callable[[MessageEvent], None]):
        self._handler = message_handler
        self._running = True
        logger.info("微信公众平台适配器已就绪")

    def handle_webhook(self, body: str, signature: str, timestamp: str, nonce: str) -> str:
        """处理微信服务器回调（XML 格式）"""
        from wechatpy import parse_message
        from wechatpy.utils import check_signature

        try:
            check_signature(self.token, signature, timestamp, nonce)
        except Exception:
            return "signature check failed"

        msg = parse_message(body)
        if msg and msg.type == "text":
            event = MessageEvent(
                type=MessageType.TEXT,
                text=msg.content,
                chat_id=msg.source,
                platform="wechat_mp",
            )
            if self._handler:
                self._handler(event)

        return "success"

    def stop(self):
        self._running = False
