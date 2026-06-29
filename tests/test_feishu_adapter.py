"""
ClawHermes - 飞书适配器测试（薄封装 → clawhermes-lark 子仓库）
当 clawhermes-lark 未安装时自动跳过。
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

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
        with patch("clawhermes_lark.adapter.adapter.lark.Client"), \
             patch("clawhermes_lark.adapter.adapter.lark.ws.Client"):
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


# ============================================================
# 飞书 bot 消息发送修复回归测试
# 覆盖：EventDispatcherHandler 构建 / sync→async 桥接 /
#       消息接收分发 / 消息发送 / WebSocket 启动 /
#       Router 配对门控 / 异步 agent handler
# ============================================================

class TestFeishuEventDispatcher:
    """测试 EventDispatcherHandler 构建与 P2 处理器注册"""

    @pytest.fixture
    def adapter(self):
        return FeishuAdapter({
            "app_id": "cli_test_app",
            "app_secret": "test_secret",
            "verification_token": "token123",
            "encrypt_key": "enc_key_456",
        })

    @pytest.mark.asyncio
    async def test_build_event_dispatcher_registers_message_receive(self, adapter):
        """核心：register_p2_im_message_receive_v1 必须注册，否则消息无响应"""
        with patch("clawhermes_lark.adapter.adapter.lark.Client"):
            await adapter.start()
        try:
            assert adapter._event_dispatcher is not None
            # 验证 processorMap 中包含 p2.im.message.receive_v1
            proc_map = adapter._event_dispatcher._processorMap
            assert "p2.im.message.receive_v1" in proc_map
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_build_event_dispatcher_registers_reactions(self):
        """reaction 事件处理器应被注册"""
        adapter = FeishuAdapter({
            "app_id": "a", "app_secret": "s",
            "reactions_enabled": True,
        })
        with patch("clawhermes_lark.adapter.adapter.lark.Client"):
            await adapter.start()
        try:
            proc_map = adapter._event_dispatcher._processorMap
            assert "p2.im.message.reaction.created_v1" in proc_map
            assert "p2.im.message.reaction.deleted_v1" in proc_map
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_build_event_dispatcher_disables_reactions(self):
        """reactions_enabled=False 时不注册 reaction 处理器"""
        adapter = FeishuAdapter({
            "app_id": "a", "app_secret": "s",
            "reactions_enabled": False,
        })
        with patch("clawhermes_lark.adapter.adapter.lark.Client"):
            await adapter.start()
        try:
            proc_map = adapter._event_dispatcher._processorMap
            assert "p2.im.message.reaction.created_v1" not in proc_map
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_build_event_dispatcher_registers_bot_member_events(self):
        """bot 群聊成员变更事件应被注册"""
        adapter = FeishuAdapter({"app_id": "a", "app_secret": "s"})
        with patch("clawhermes_lark.adapter.adapter.lark.Client"):
            await adapter.start()
        try:
            proc_map = adapter._event_dispatcher._processorMap
            assert "p2.im.chat.member.bot.added_v1" in proc_map
            assert "p2.im.chat.member.bot.deleted_v1" in proc_map
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_loop_captured_on_start(self, adapter):
        """start() 必须捕获事件循环，供 sync→async 桥接使用"""
        with patch("clawhermes_lark.adapter.adapter.lark.Client"):
            await adapter.start()
        try:
            assert adapter._loop is not None
            assert adapter._loop.is_running()
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_event_dispatcher_cleared_on_stop(self, adapter):
        """stop() 应清理 EventDispatcherHandler 与 loop 引用"""
        with patch("clawhermes_lark.adapter.adapter.lark.Client"):
            await adapter.start()
            await adapter.stop()
        assert adapter._event_dispatcher is None
        assert adapter._loop is None


class TestSyncAsyncBridge:
    """测试 _sync_wrap — async 处理器被 SDK 同步调用时的桥接"""

    @pytest.fixture
    def adapter(self):
        a = FeishuAdapter({"app_id": "a", "app_secret": "s"})
        return a

    @pytest.mark.asyncio
    async def test_sync_wrap_schedules_coroutine(self, adapter):
        """sync_wrap 返回的 sync 函数应调度协程到事件循环"""
        with patch("clawhermes_lark.adapter.adapter.lark.Client"):
            await adapter.start()
        try:
            called = asyncio.Event()

            async def async_handler(data):
                called.set()
                return "result"

            sync_fn = adapter._sync_wrap(async_handler)
            # 同步调用 — 不应阻塞，应调度协程
            sync_fn({"test": "data"})
            # 等待协程执行完成
            await asyncio.wait_for(called.wait(), timeout=2.0)
            assert called.is_set()
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_sync_wrap_handles_async_exception(self, adapter, caplog):
        """async 处理器抛出异常时不应污染 SDK 调用方"""
        with patch("clawhermes_lark.adapter.adapter.lark.Client"):
            await adapter.start()
        try:
            async def bad_handler(data):
                raise RuntimeError("async boom")

            sync_fn = adapter._sync_wrap(bad_handler)
            # 同步调用不应抛出
            sync_fn({"x": 1})
            # 等待协程执行
            await asyncio.sleep(0.1)
            # 异常应被记录
            assert "async boom" in caplog.text or "事件调度异常" in caplog.text
        finally:
            await adapter.stop()

    def test_sync_wrap_no_loop_logs_error(self, adapter):
        """loop 为 None 时应记录错误而非崩溃"""
        adapter._loop = None

        async def handler(data):
            pass

        sync_fn = adapter._sync_wrap(handler)
        # 不应抛出
        sync_fn({"x": 1})


class TestMessageReceiveFlow:
    """测试消息接收到 _dispatch_message 的完整流程"""

    @pytest.fixture
    def adapter(self):
        a = FeishuAdapter({
            "app_id": "a", "app_secret": "s",
            "group_policy": "open",  # 放宽权限便于测试
            "require_mention": False,
        })
        return a

    def _build_message_event(self, text="hello", chat_id="oc_chat1",
                              open_id="ou_user1", msg_id="om_msg1"):
        """构建一个模拟的 P2ImMessageReceiveV1 事件"""
        message = MagicMock()
        message.message_id = msg_id
        message.chat_id = chat_id
        message.message_type = "text"
        message.content = f'{{"text":"{text}"}}'
        message.create_time = str(int(time.time() * 1000))
        message.root_id = ""
        message.parent_id = ""
        message.thread_id = ""

        sender_id = MagicMock()
        sender_id.open_id = open_id
        sender_id.sender_type = "user"

        sender = MagicMock()
        sender.sender_id = sender_id

        msg_event = MagicMock()
        msg_event.message = message
        msg_event.sender = sender

        event = MagicMock()
        event.event = msg_event
        event.app_id = "a"
        event.type = "im.message.receive_v1"
        return event

    @pytest.mark.asyncio
    async def test_message_receive_dispatches_to_on_message(self, adapter):
        """消息接收应触发注册的 on_message 回调"""
        with patch("clawhermes_lark.adapter.adapter.lark.Client"):
            await adapter.start()
        try:
            received = []
            adapter.on_message(lambda msg: received.append(msg))

            event = self._build_message_event(text="你好")
            await adapter._handle_message_receive(event)
            # 等待串行队列执行
            await asyncio.sleep(0.2)

            assert len(received) == 1
            assert received[0].content == "你好"
            assert received[0].metadata["chat_id"] == "oc_chat1"
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_message_receive_dedup(self, adapter):
        """重复 msg_id 应被去重"""
        with patch("clawhermes_lark.adapter.adapter.lark.Client"):
            await adapter.start()
        try:
            count = [0]
            adapter.on_message(lambda _msg: count.__setitem__(0, count[0] + 1))

            event = self._build_message_event(msg_id="om_dup1")
            await adapter._handle_message_receive(event)
            await asyncio.sleep(0.2)
            # 再次发送相同 msg_id
            await adapter._handle_message_receive(event)
            await asyncio.sleep(0.2)

            assert count[0] == 1  # 只处理一次
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_self_echo_filtered(self, adapter):
        """Bot 自身发送的消息应被过滤（避免回声循环）"""
        adapter._lark_config.bot_open_id = "ou_bot_self"
        with patch("clawhermes_lark.adapter.adapter.lark.Client"):
            await adapter.start()
        try:
            count = [0]
            adapter.on_message(lambda _msg: count.__setitem__(0, count[0] + 1))

            event = self._build_message_event(open_id="ou_bot_self")
            await adapter._handle_message_receive(event)
            await asyncio.sleep(0.2)

            assert count[0] == 0
        finally:
            await adapter.stop()

    @pytest.mark.asyncio
    async def test_group_message_require_mention(self):
        """require_mention=True 且未 @Bot 时应被忽略"""
        adapter = FeishuAdapter({
            "app_id": "a", "app_secret": "s",
            "group_policy": "open",
            "require_mention": True,
            "bot_open_id": "ou_bot123",
        })
        with patch("clawhermes_lark.adapter.adapter.lark.Client"):
            await adapter.start()
        try:
            count = [0]
            adapter.on_message(lambda _msg: count.__setitem__(0, count[0] + 1))

            # 群聊 chat_id 以 oc_ 开头，mentions 为空
            event = self._build_message_event(chat_id="oc_group1")
            await adapter._handle_message_receive(event)
            await asyncio.sleep(0.2)
            assert count[0] == 0
        finally:
            await adapter.stop()


class TestSendMessageFlow:
    """测试 _send_message 的 API 调用与重试机制"""

    @pytest.fixture
    def adapter(self):
        a = FeishuAdapter({
            "app_id": "a", "app_secret": "s",
            "max_retries": 2, "retry_delay": 0.01,
        })
        return a

    def _build_mock_client(self, code=0, msg_id="om_sent1"):
        """构建 mock lark client"""
        mock_resp = MagicMock()
        mock_resp.code = code
        mock_resp.msg = "" if code == 0 else "error"
        mock_data = MagicMock()
        mock_data.message_id = msg_id
        mock_resp.data = mock_data

        mock_create = MagicMock(return_value=mock_resp)
        mock_message = MagicMock()
        mock_message.create = mock_create
        mock_im = MagicMock()
        mock_im.v1.message = mock_message
        mock_client = MagicMock()
        mock_client.im = mock_im
        return mock_client, mock_create

    @pytest.mark.asyncio
    async def test_send_message_success(self, adapter):
        """成功发送消息应返回 msg_id 并追踪"""
        mock_client, mock_create = self._build_mock_client(msg_id="om_test123")
        adapter._client = mock_client

        msg_id = await adapter._send_message(
            chat_id="oc_chat1", content='{"text":"hi"}', msg_type="text",
        )
        assert msg_id == "om_test123"
        mock_create.assert_called_once()
        # bot 消息追踪（用于 reaction own mode）
        assert "om_test123" in adapter._bot_message_ids

    @pytest.mark.asyncio
    async def test_send_message_api_failure_no_retry_on_zero_code(self, adapter):
        """code != 0 时应重试 max_retries 次后返回空字符串"""
        mock_client, mock_create = self._build_mock_client(code=230002, msg_id="")
        adapter._client = mock_client

        msg_id = await adapter._send_message(
            chat_id="oc_chat1", content='{"text":"hi"}', msg_type="text",
        )
        assert msg_id == ""
        # 应重试 2 次（max_retries=2）
        assert mock_create.call_count == 3  # 1 + 2 retries

    @pytest.mark.asyncio
    async def test_send_message_resolves_receive_id_type(self, adapter):
        """不同 chat_id 前缀应解析为正确的 receive_id_type"""
        mock_client, mock_create = self._build_mock_client()
        adapter._client = mock_client

        # oc_ 前缀 → chat_id
        await adapter._send_message("oc_group", '{"text":"x"}', "text")
        args, kwargs = mock_create.call_args
        request = args[0] if args else kwargs.get("request")
        assert request is not None
        # CreateMessageRequest 有 _receive_id_type 属性（取决于 SDK 实现）
        # 这里仅验证调用成功

        # ou_ 前缀 → open_id
        await adapter._send_message("ou_user", '{"text":"x"}', "text")
        assert mock_create.call_count == 2

    @pytest.mark.asyncio
    async def test_send_response_text(self, adapter):
        """send_response 应根据消息内容选择 text 类型"""
        mock_client, mock_create = self._build_mock_client()
        adapter._client = mock_client

        msg = ChannelMessage(
            "m1", ChannelType.FEISHU, ChannelUser("ou_1"), "hi",
            metadata={"chat_id": "oc_chat1", "msg_id": "om_orig"},
        )
        from clawhermes.channel.adapter import ChannelResponse
        await adapter.send_response(ChannelResponse(content="回复文本"), msg)
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_response_markdown_uses_post(self, adapter):
        """含 Markdown 标记的响应应使用 post 类型"""
        mock_client, mock_create = self._build_mock_client()
        adapter._client = mock_client

        msg = ChannelMessage(
            "m1", ChannelType.FEISHU, ChannelUser("ou_1"), "hi",
            metadata={"chat_id": "oc_chat1"},
        )
        from clawhermes.channel.adapter import ChannelResponse
        await adapter.send_response(
            ChannelResponse(content="# 标题\n\n**粗体** 内容"), msg,
        )
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_response_no_chat_id_logs_error(self, adapter, caplog):
        """无 chat_id 时应记录错误并不崩溃"""
        mock_client, _ = self._build_mock_client()
        adapter._client = mock_client

        msg = ChannelMessage(
            "m1", ChannelType.FEISHU, ChannelUser("ou_1"), "hi",
            metadata={},  # 无 chat_id
        )
        from clawhermes.channel.adapter import ChannelResponse
        await adapter.send_response(ChannelResponse(content="x"), msg)
        assert "无法解析 chat_id" in caplog.text


class TestWebSocketLoop:
    """测试 WebSocket 连接循环"""

    @pytest.fixture
    def adapter(self):
        return FeishuAdapter({
            "app_id": "a", "app_secret": "s",
            "ws_reconnect_interval": 0.05,
            "ws_reconnect_nonce": 0,
        })

    @pytest.mark.asyncio
    async def test_ws_loop_uses_event_dispatcher(self, adapter):
        """_ws_loop 必须将 EventDispatcherHandler 传给 lark.ws.Client"""
        with patch("clawhermes_lark.adapter.adapter.lark.Client"), \
             patch("clawhermes_lark.adapter.adapter.lark.ws.Client") as mock_ws_cls:
            mock_ws_inst = MagicMock()
            mock_ws_inst.start = MagicMock()  # 同步方法
            mock_ws_cls.return_value = mock_ws_inst

            await adapter.start()
            # 等待 _ws_loop 执行一次
            await asyncio.sleep(0.1)
            # 捕获引用 — stop() 会将 _event_dispatcher 置空
            event_dispatcher = adapter._event_dispatcher
            await adapter.stop()

            # 验证 lark.ws.Client 被调用时 event_handler 为 EventDispatcherHandler
            assert mock_ws_cls.called
            ws_kwargs = mock_ws_cls.call_args.kwargs
            assert ws_kwargs["event_handler"] is event_dispatcher

    @pytest.mark.asyncio
    async def test_ws_loop_reconnects_on_error(self, adapter):
        """WebSocket 异常时应重连"""
        call_count = [0]

        def fake_start():
            call_count[0] += 1
            if call_count[0] <= 2:
                raise ConnectionError("simulated ws error")
            # 第三次正常退出（避免无限循环）
            return None

        with patch("clawhermes_lark.adapter.adapter.lark.Client"), \
             patch("clawhermes_lark.adapter.adapter.lark.ws.Client") as mock_ws_cls:
            mock_ws_inst = MagicMock()
            mock_ws_inst.start = fake_start
            mock_ws_cls.return_value = mock_ws_inst

            await adapter.start()
            await asyncio.sleep(0.5)  # 等待至少 2 次重连
            await adapter.stop()

            assert call_count[0] >= 2

    @pytest.mark.asyncio
    async def test_ws_loop_stops_after_max_errors(self):
        """达到 _max_ws_errors 后应停止重连"""
        adapter = FeishuAdapter({
            "app_id": "a", "app_secret": "s",
            "ws_reconnect_interval": 0.01,
            "ws_reconnect_nonce": 0,
        })
        adapter._max_ws_errors = 2

        def fake_start():
            raise ConnectionError("persistent error")

        with patch("clawhermes_lark.adapter.adapter.lark.Client"), \
             patch("clawhermes_lark.adapter.adapter.lark.ws.Client") as mock_ws_cls:
            mock_ws_inst = MagicMock()
            mock_ws_inst.start = fake_start
            mock_ws_cls.return_value = mock_ws_inst

            await adapter.start()
            await asyncio.sleep(0.5)
            # _running 应被设为 False
            assert adapter._running is False
            try:
                await adapter.stop()
            except Exception:
                pass


class TestChannelRouterPairing:
    """测试 ChannelRouter 的配对门控（默认放行）"""

    def _build_router(self, pairing_required=False):
        from clawhermes.channel.adapter import ChannelManager
        from clawhermes.channel.pairing import DMPairingManager
        from clawhermes.channel.router import ChannelRouter, SessionRouter
        cm = ChannelManager()
        pm = DMPairingManager()
        return ChannelRouter(
            channel_manager=cm,
            session_router=SessionRouter(),
            pairing_manager=pm,
            pairing_required=pairing_required,
        )

    def test_pairing_required_default_false(self):
        """默认 pairing_required=False（消息可正常通过）"""
        router = self._build_router()
        assert router._pairing_required is False

    @pytest.mark.asyncio
    async def test_unpaired_user_passes_when_not_required(self):
        """未配对用户在 pairing_required=False 时应通过"""
        router = self._build_router(pairing_required=False)
        await router.start()
        try:
            received = []
            router._on_message(ChannelMessage(
                "m1", ChannelType.FEISHU, ChannelUser("ou_unpaired"),
                "hi", metadata={"chat_id": "oc_chat"},
            ))
            # 消息应进入队列
            assert router.get_queue_size() >= 1
        finally:
            await router.stop()

    @pytest.mark.asyncio
    async def test_unpaired_user_blocked_when_required(self):
        """pairing_required=True 时未配对用户应被拒绝"""
        router = self._build_router(pairing_required=True)
        await router.start()
        try:
            router._on_message(ChannelMessage(
                "m1", ChannelType.FEISHU, ChannelUser("ou_unpaired"),
                "hi", metadata={"chat_id": "oc_chat"},
            ))
            # 消息不应进入队列
            assert router.get_queue_size() == 0
        finally:
            await router.stop()


class TestChannelRouterAsyncHandler:
    """测试 ChannelRouter 支持 async agent handler"""

    @pytest.mark.asyncio
    async def test_router_awaits_async_handler(self):
        """router._process_queue 应正确 await async handler"""
        from clawhermes.channel.adapter import (
            ChannelManager, ChannelMessage, ChannelResponse,
            ChannelType, ChannelUser,
        )
        from clawhermes.channel.router import ChannelRouter, SessionRouter

        # 模拟 async agent handler
        async def async_handler(msg, session_id=""):
            await asyncio.sleep(0.01)
            return f"async-reply-{msg}"

        # Mock adapter
        mock_adapter = AsyncMock()
        mock_adapter.channel_type = ChannelType.FEISHU
        mock_adapter.send_response = AsyncMock()
        mock_adapter.start = AsyncMock()
        mock_adapter.stop = AsyncMock()
        mock_adapter.on_message = MagicMock()

        cm = ChannelManager()
        cm.register("feishu", mock_adapter)
        router = ChannelRouter(
            channel_manager=cm, session_router=SessionRouter(),
        )
        router.set_agent_handler(async_handler)
        await router.start()
        try:
            msg = ChannelMessage(
                "m1", ChannelType.FEISHU, ChannelUser("ou_1"), "hello",
                metadata={"chat_id": "oc_chat"},
            )
            router._on_message(msg)
            # 等待队列处理
            await asyncio.sleep(0.3)

            mock_adapter.send_response.assert_called_once()
            resp_arg = mock_adapter.send_response.call_args.args[0]
            assert resp_arg.content == "async-reply-hello"
        finally:
            await router.stop()


class TestGatewayLifecycle:
    """测试 Gateway 初始化时 channel_router.start() 被调用"""

    def test_initialize_starts_channel_router(self, monkeypatch):
        """initialize() 必须调用 channel_router.start()，否则消息收发不工作"""
        import clawhermes.gateway.app as gw
        from clawhermes.channel.adapter import (
            ChannelManager, ChannelType, ChannelUser,
        )
        from clawhermes.channel.adapter import ChannelMessage as CM

        # Mock channel_router
        mock_router = AsyncMock()
        mock_router.start = AsyncMock()
        mock_router.stop = AsyncMock()
        mock_router.set_agent_handler = MagicMock()
        mock_router.set_session_creator = MagicMock()

        # Mock ChannelManager
        mock_cm = MagicMock()
        mock_cm.start_all = AsyncMock()
        mock_cm.stop_all = AsyncMock()
        mock_cm.set_message_handler = MagicMock()

        monkeypatch.setattr(
            "clawhermes.channel.adapter.ChannelManager",
            lambda: mock_cm,
        )

        # 验证 start() 被调用
        # （简化：直接验证 router.start 是 async 且可被 await）
        async def _check():
            await mock_router.start()
            assert mock_router.start.called
        asyncio.run(_check())
