"""
ClawHermes - 飞书适配器测试（薄封装 → clawhermes-lark 子仓库）
当 clawhermes-lark 未安装时自动跳过。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from clawhermes.channel.adapter import ChannelMessage, ChannelType, ChannelUser
from clawhermes.channel.adapters.feishu import (
    FeishuAdapter,
    create_feishu_adapter,
)

pytestmark = pytest.mark.skipif(
    FeishuAdapter is None,
    reason="clawhermes-lark 未安装（pip install clawhermes-lark）",
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
        adapter = FeishuAdapter({})
        await adapter.start()
        assert adapter.is_running is False

    @pytest.mark.asyncio
    async def test_stop_cleanup(self, adapter):
        with patch("clawhermes_lark.adapter.lark.Client"):
            await adapter.start()
            await adapter.stop()
            assert adapter.is_running is False

    @pytest.mark.asyncio
    async def test_send_response(self, adapter):
        from clawhermes.channel.adapter import ChannelResponse

        # send_response 调用 asyncio.to_thread(client.im.v1.message.create, req)
        # asyncio.to_thread 以普通 callable 调用（不 await），所以用 MagicMock
        mock_resp = MagicMock()
        mock_resp.code = 0
        mock_msg = MagicMock()
        mock_msg.message_id = "msg-test-1"
        mock_resp.data = mock_msg

        mock_create = MagicMock(return_value=mock_resp)
        mock_message = MagicMock()
        mock_message.create = mock_create
        mock_im = MagicMock()
        mock_im.v1.message = mock_message
        mock_client = MagicMock()
        mock_client.im = mock_im
        adapter._client = mock_client

        msg = ChannelMessage("m1", ChannelType.FEISHU, ChannelUser("ou1"), "hi",
                            metadata={"chat_id": "oc_test"})
        await adapter.send_response(ChannelResponse(content="ok"), msg)
        mock_create.assert_called_once()

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
