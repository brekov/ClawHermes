"""
ClawHermes - 飞书适配器测试（薄封装 → clawhermes-lark 子仓库）
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from clawhermes.channel.adapter import ChannelMessage, ChannelType, ChannelUser
from clawhermes.channel.adapters.feishu import (
    FeishuAdapter,
    create_feishu_adapter,
)


class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super().__call__(*args, **kwargs)


class TestFeishuAdapter:
    @pytest.fixture
    def adapter(self):
        return FeishuAdapter({
            "app_id": "test-app",
            "app_secret": "test-secret",
        })

    @pytest.mark.asyncio
    async def test_start_skip_without_credentials(self):
        """无凭证时跳过启动"""
        adapter = FeishuAdapter({})
        await adapter.start()
        assert adapter.is_running is False

    @pytest.mark.asyncio
    async def test_stop_cleanup(self, adapter):
        """stop 应清理资源"""
        with patch("clawhermes_lark.adapter.lark.Client"):
            await adapter.start()
            await adapter.stop()
            assert adapter.is_running is False

    @pytest.mark.asyncio
    async def test_send_response(self, adapter):
        """通过 lark-oapi Builder 发送消息"""
        from clawhermes.channel.adapter import ChannelResponse

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.success.return_value = True
        mock_client.arequest = AsyncMock(return_value=mock_resp)
        adapter._client = mock_client

        msg = ChannelMessage("m1", ChannelType.FEISHU, ChannelUser("ou1"), "hi")
        await adapter.send_response(ChannelResponse(content="ok"), msg)
        mock_client.arequest.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_webhook_url_verification(self, adapter):
        result = await adapter.handle_webhook({"type": "url_verification", "challenge": "c"})
        assert result["challenge"] == "c"

    @pytest.mark.asyncio
    async def test_dispatch_error_handling(self, adapter, caplog):
        def _bad(_msg):
            raise RuntimeError("x")
        adapter.on_message(_bad)
        adapter._dispatch_message(ChannelMessage("e", ChannelType.FEISHU, ChannelUser("u"), "x"))
        assert "Channel message handler error" in caplog.text


class TestCreateFeishuAdapter:
    def test_factory(self):
        a = create_feishu_adapter(app_id="fa", app_secret="fs")
        assert a.channel_type == ChannelType.FEISHU
