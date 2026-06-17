"""
ClawHermes - Channel Adapter SDK 测试
"""
from __future__ import annotations

import asyncio

from clawhermes.channel.adapter import (
    ChannelConnectionError,
    ChannelError,
    ChannelManager,
    ChannelMessage,
    ChannelMessageError,
    ChannelResponse,
    ChannelType,
    ChannelUser,
    CLIAdapter,
    RESTAdapter,
    WebSocketAdapter,
)


class TestChannelTypes:
    def test_channel_type_values(self):
        assert ChannelType.CLI == "cli"
        assert ChannelType.REST == "rest"
        assert ChannelType.WEBSOCKET == "websocket"
        assert ChannelType.SLACK == "slack"
        assert ChannelType.DISCORD == "discord"
        assert ChannelType.FEISHU == "feishu"
        assert ChannelType.CUSTOM == "custom"

    def test_channel_exceptions(self):
        assert issubclass(ChannelConnectionError, ChannelError)
        assert issubclass(ChannelMessageError, ChannelError)
        from clawhermes.agent.exceptions import ClawHermesError
        assert issubclass(ChannelError, ClawHermesError)


class TestChannelUser:
    def test_create_user(self):
        user = ChannelUser(user_id="u1", display_name="Alice")
        assert user.user_id == "u1"
        assert user.display_name == "Alice"
        assert user.metadata == {}

    def test_user_with_metadata(self):
        user = ChannelUser(user_id="u2", metadata={"role": "admin"})
        assert user.metadata["role"] == "admin"


class TestChannelMessage:
    def test_create_message(self):
        user = ChannelUser(user_id="u1")
        msg = ChannelMessage(
            message_id="m1",
            channel_type=ChannelType.CLI,
            user=user,
            content="Hello",
        )
        assert msg.message_id == "m1"
        assert msg.content == "Hello"
        assert msg.session_id == ""
        assert msg.reply_to is None

    def test_message_with_session(self):
        user = ChannelUser(user_id="u1")
        msg = ChannelMessage(
            message_id="m2",
            channel_type=ChannelType.REST,
            user=user,
            content="Test",
            session_id="sess_abc",
        )
        assert msg.session_id == "sess_abc"


class TestChannelResponse:
    def test_create_response(self):
        resp = ChannelResponse(content="Hi there!", session_id="s1")
        assert resp.content == "Hi there!"
        assert resp.session_id == "s1"


class TestCLIAdapter:
    def test_create(self):
        adapter = CLIAdapter()
        assert adapter.channel_type == ChannelType.CLI
        assert not adapter.is_running

    def test_start_stop(self):
        adapter = CLIAdapter()
        asyncio.run(adapter.start())
        assert adapter.is_running
        asyncio.run(adapter.stop())
        assert not adapter.is_running

    def test_receive_message(self):
        received = []

        adapter = CLIAdapter()
        adapter.on_message(lambda msg: received.append(msg))
        asyncio.run(adapter.start())

        msg = adapter.receive_message("Hello CLI", session_id="s1")
        assert msg.content == "Hello CLI"
        assert msg.channel_type == ChannelType.CLI
        assert len(received) == 1

        asyncio.run(adapter.stop())

    def test_get_user_info(self):
        adapter = CLIAdapter()
        user = asyncio.run(adapter.get_user_info("cli_user"))
        assert user is not None
        assert user.display_name == "CLI User"


class TestRESTAdapter:
    def test_create(self):
        adapter = RESTAdapter()
        assert adapter.channel_type == ChannelType.REST

    def test_start_stop(self):
        adapter = RESTAdapter()
        asyncio.run(adapter.start())
        assert adapter.is_running
        asyncio.run(adapter.stop())
        assert not adapter.is_running

    def test_get_user_info(self):
        adapter = RESTAdapter()
        user = asyncio.run(adapter.get_user_info("rest_user_1"))
        assert user is not None
        assert user.user_id == "rest_user_1"


class TestWebSocketAdapter:
    def test_create(self):
        adapter = WebSocketAdapter()
        assert adapter.channel_type == ChannelType.WEBSOCKET

    def test_start_stop(self):
        adapter = WebSocketAdapter()
        asyncio.run(adapter.start())
        assert adapter.is_running
        asyncio.run(adapter.stop())
        assert not adapter.is_running

    def test_register_connection(self):
        adapter = WebSocketAdapter()
        asyncio.run(adapter.start())

        class FakeWS:
            async def send(self, data):
                pass

        adapter.register_connection("user1", FakeWS())
        assert "user1" in adapter._connections

        adapter.unregister_connection("user1")
        assert "user1" not in adapter._connections

        asyncio.run(adapter.stop())

    def test_receive_message(self):
        received = []
        adapter = WebSocketAdapter()
        adapter.on_message(lambda msg: received.append(msg))
        asyncio.run(adapter.start())

        msg = adapter.receive_message("Hello WS", user_id="user1")
        assert msg.content == "Hello WS"
        assert msg.channel_type == ChannelType.WEBSOCKET
        assert len(received) == 1

        asyncio.run(adapter.stop())


class TestChannelManager:
    def test_register_and_list(self):
        mgr = ChannelManager()
        cli = CLIAdapter()
        rest = RESTAdapter()

        mgr.register("cli", cli)
        mgr.register("api", rest)

        adapters = mgr.list_adapters()
        assert len(adapters) == 2
        names = {a["name"] for a in adapters}
        assert names == {"cli", "api"}

    def test_unregister(self):
        mgr = ChannelManager()
        mgr.register("cli", CLIAdapter())
        mgr.unregister("cli")
        assert mgr.get("cli") is None

    def test_get_adapter(self):
        mgr = ChannelManager()
        cli = CLIAdapter()
        mgr.register("cli", cli)
        assert mgr.get("cli") is cli
        assert mgr.get("nonexistent") is None

    def test_set_message_handler(self):
        mgr = ChannelManager()
        received = []

        cli = CLIAdapter()
        ws = WebSocketAdapter()
        mgr.register("cli", cli)
        mgr.register("ws", ws)

        mgr.set_message_handler(lambda msg: received.append(msg))

        asyncio.run(mgr.start_all())
        cli.receive_message("from CLI")
        ws.receive_message("from WS", user_id="u1")

        assert len(received) == 2

        asyncio.run(mgr.stop_all())

    def test_start_stop_all(self):
        mgr = ChannelManager()
        mgr.register("cli", CLIAdapter())
        mgr.register("rest", RESTAdapter())

        asyncio.run(mgr.start_all())
        assert mgr.get("cli").is_running
        assert mgr.get("rest").is_running

        asyncio.run(mgr.stop_all())
        assert not mgr.get("cli").is_running
        assert not mgr.get("rest").is_running
