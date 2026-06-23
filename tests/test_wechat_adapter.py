"""
ClawHermes — 微信适配器测试（薄封装 → clawhermes-weixin 子仓库）
当 clawhermes-weixin 未安装时自动跳过。
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from clawhermes.channel.adapter import ChannelMessage, ChannelResponse, ChannelType, ChannelUser
from clawhermes.channel.adapters.wechat import (
    WeChatAdapter,
    WeComAdapter,
    create_wechat_adapter,
    create_wecom_adapter,
)

pytestmark = pytest.mark.skipif(
    WeChatAdapter is None,
    reason="clawhermes-weixin 未安装（pip install -e ./clawhermes-weixin）",
)


class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super().__call__(*args, **kwargs)


class TestWeChatAdapter:
    @pytest.fixture
    def adapter(self):
        return WeChatAdapter({"session_key": "test-key"})

    @pytest.mark.asyncio
    async def test_start_without_session_key(self):
        adapter = WeChatAdapter({})
        await adapter.start()
        assert adapter.is_running is False

    @pytest.mark.asyncio
    async def test_start_with_key(self, adapter):
        await adapter.start()
        assert adapter.is_running is True
        await adapter.stop()

    @pytest.mark.asyncio
    async def test_stop_cleanup(self, adapter):
        adapter._running = True
        await adapter.stop()
        assert adapter.is_running is False

    @pytest.mark.asyncio
    async def test_send_response(self, adapter):
        mock_client = MagicMock()
        mock_client.send_message = AsyncMock(return_value={"ret": 0})
        adapter._client = mock_client
        msg = ChannelMessage("m1", ChannelType.WECHAT, ChannelUser("u1"), "hi",
                             metadata={"from_uin": "123"})
        await adapter.send_response(ChannelResponse(content="reply"), msg)
        mock_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_error_handling(self, adapter, caplog):
        def _bad(_msg):
            raise RuntimeError("x")
        adapter.on_message(_bad)
        adapter._dispatch_message(ChannelMessage("e", ChannelType.WECHAT, ChannelUser("u"), "x"))
        assert "Channel message handler error" in caplog.text


class TestWeComAdapter:
    @pytest.fixture
    def adapter(self):
        return WeComAdapter({"bot_key": "test-bot-key"})

    @pytest.mark.asyncio
    async def test_start_without_key(self):
        adapter = WeComAdapter({})
        await adapter.start()
        assert adapter.is_running is False

    @pytest.mark.asyncio
    async def test_start_with_key(self, adapter):
        await adapter.start()
        assert adapter.is_running is True
        await adapter.stop()

    @pytest.mark.asyncio
    async def test_send_response(self, adapter):
        from unittest.mock import patch
        mock_session = AsyncMock()
        mock_session.post = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        with patch("aiohttp.ClientSession", return_value=mock_session):
            msg = ChannelMessage("m1", ChannelType.WECHAT, ChannelUser("u1"), "hi")
            await adapter.send_response(ChannelResponse(content="reply"), msg)
            mock_session.post.assert_called_once()


class TestFactory:
    def test_create_wechat(self):
        a = create_wechat_adapter(session_key="k")
        assert a.channel_type == ChannelType.WECHAT

    def test_create_wecom(self):
        a = create_wecom_adapter(bot_key="k")
        assert a.channel_type == ChannelType.WECHAT
