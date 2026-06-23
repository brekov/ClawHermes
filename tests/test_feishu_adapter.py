"""
ClawHermes - 飞书适配器测试（基于 lark-oapi）
覆盖：FeishuAdapter 生命周期 / Webhook / 消息发送 / 用户信息
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from clawhermes.channel.adapter import ChannelMessage, ChannelType, ChannelUser
from clawhermes.channel.adapters.feishu import (
    FeishuAdapter,
    create_feishu_adapter,
)

# ---------------------------------------------------------------------------
# FeishuAdapter
# ---------------------------------------------------------------------------

class TestFeishuAdapter:
    @pytest.fixture
    def adapter(self):
        return FeishuAdapter({
            "app_id": "test-app-id",
            "app_secret": "test-secret",
        })

    @pytest.mark.asyncio
    async def test_start_initializes_lark_client(self, adapter):
        """start 应初始化 lark.Client 并启动 WS 循环"""
        with patch("clawhermes.channel.adapters.feishu.lark.Client") as mock_lark:
            mock_client = MagicMock()
            mock_lark.builder.return_value.app_id.return_value \
                .app_secret.return_value.domain.return_value \
                .build.return_value = mock_client

            await adapter.start()
            assert adapter._client is not None

            await adapter.stop()

    @pytest.mark.asyncio
    async def test_start_skip_without_credentials(self):
        """无凭证时跳过启动"""
        adapter = FeishuAdapter({})
        await adapter.start()
        assert adapter._client is None
        assert adapter.is_running is False

    @pytest.mark.asyncio
    async def test_stop_cancels_ws(self, adapter):
        with patch("clawhermes.channel.adapters.feishu.lark.Client"):
            await adapter.start()
            assert adapter.is_running
            await adapter.stop()
            assert adapter.is_running is False

    @pytest.mark.asyncio
    async def test_send_response_uses_lark_builder(self, adapter):
        """send_response 应使用 lark-oapi Builder 模式发送消息"""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.success.return_value = True
        mock_client.arequest = AsyncMock(return_value=mock_resp)
        adapter._client = mock_client

        msg = ChannelMessage(
            message_id="msg-1",
            channel_type=ChannelType.FEISHU,
            user=ChannelUser(user_id="ou_abc"),
            content="你好",
        )
        await adapter.send_response(msg.to_response("回复内容"), msg)
        mock_client.arequest.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_response_no_client(self, adapter):
        """无 client 时不发送"""
        msg = ChannelMessage(
            message_id="msg-1",
            channel_type=ChannelType.FEISHU,
            user=ChannelUser(user_id="ou_abc"),
            content="hi",
        )
        await adapter.send_response(msg.to_response("x"), msg)
        # No error, just no-op

    @pytest.mark.asyncio
    async def test_send_response_no_open_id(self, adapter):
        """无 open_id 时不发送"""
        adapter._client = MagicMock()
        msg = ChannelMessage(
            message_id="msg-1",
            channel_type=ChannelType.FEISHU,
            user=ChannelUser(user_id=""),
            content="hi",
        )
        await adapter.send_response(msg.to_response("x"), msg)
        adapter._client.arequest.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_user_info(self, adapter):
        """get_user_info 应正确获取飞书用户"""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.success.return_value = True
        mock_user = MagicMock()
        mock_user.name = "张三"
        mock_user.avatar = {"avatar_240": "https://x.com/1.jpg"}
        mock_user.email = "zhang@example.com"
        mock_resp.data.user = mock_user
        mock_client.arequest = AsyncMock(return_value=mock_resp)
        adapter._client = mock_client

        user = await adapter.get_user_info("ou_123")
        assert user is not None
        assert user.display_name == "张三"

    @pytest.mark.asyncio
    async def test_get_user_info_no_client(self, adapter):
        user = await adapter.get_user_info("ou_123")
        assert user is None

    # ---- Webhook 事件处理 ----

    @pytest.mark.asyncio
    async def test_handle_url_verification(self, adapter):
        result = await adapter.handle_webhook({
            "type": "url_verification",
            "challenge": "abc123",
        })
        assert result["challenge"] == "abc123"

    @pytest.mark.asyncio
    async def test_handle_webhook_other_event(self, adapter):
        result = await adapter.handle_webhook({
            "type": "other",
        })
        assert result == {}

    # ---- 消息分发 ----

    @pytest.mark.asyncio
    async def test_dispatch_message_error_handling(self, adapter, caplog):
        """handler 内部异常不应导致崩溃"""
        def _bad_handler(_msg):
            raise RuntimeError("boom")
        adapter.on_message(_bad_handler)
        adapter._dispatch_message(ChannelMessage(
            message_id="err",
            channel_type=ChannelType.FEISHU,
            user=ChannelUser(user_id="u1"),
            content="x",
        ))
        assert "Channel message handler error" in caplog.text


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

class TestCreateFeishuAdapter:
    def test_create_factory(self):
        adapter = create_feishu_adapter(
            app_id="factory-app",
            app_secret="factory-secret",
        )
        assert adapter is not None
        assert adapter.channel_type == ChannelType.FEISHU
        assert adapter._feishu_config.app_id == "factory-app"


# ---------------------------------------------------------------------------
# AsyncMock helper (Python < 3.12 compat)
# ---------------------------------------------------------------------------

class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super().__call__(*args, **kwargs)
