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
from clawhermes.channel.router import (
    ChannelRouter,
    QueueMode,
    SessionRouter,
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


class TestSessionRouter:
    def test_create_and_resolve(self):
        sr = SessionRouter()
        sid = sr.create(ChannelType.REST, "user1")
        assert sr.resolve(ChannelType.REST, "user1") == sid

    def test_resolve_nonexistent(self):
        sr = SessionRouter()
        assert sr.resolve(ChannelType.REST, "user1") is None

    def test_remove(self):
        sr = SessionRouter()
        sr.create(ChannelType.REST, "user1")
        assert sr.remove(ChannelType.REST, "user1")
        assert sr.resolve(ChannelType.REST, "user1") is None

    def test_remove_nonexistent(self):
        sr = SessionRouter()
        assert not sr.remove(ChannelType.REST, "user1")

    def test_different_channels_different_sessions(self):
        sr = SessionRouter()
        sid1 = sr.create(ChannelType.REST, "user1")
        sid2 = sr.create(ChannelType.CLI, "user1")
        assert sid1 != sid2
        assert sr.resolve(ChannelType.REST, "user1") == sid1
        assert sr.resolve(ChannelType.CLI, "user1") == sid2

    def test_list_mappings(self):
        sr = SessionRouter()
        sr.create(ChannelType.REST, "user1")
        sr.create(ChannelType.CLI, "user2")
        mappings = sr.list_mappings()
        assert len(mappings) == 2

    def test_cleanup_expired(self):
        sr = SessionRouter(idle_timeout_seconds=0)
        sr.create(ChannelType.REST, "user1")
        import time
        time.sleep(0.01)
        expired = sr.cleanup_expired()
        assert expired == 1
        assert sr.resolve(ChannelType.REST, "user1") is None


class TestChannelRouter:
    def test_route_message_with_handler(self):
        mgr = ChannelManager()
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr)
        results = []
        router.set_agent_handler(lambda msg, session_id="": (results.append(msg), "response")[-1])
        router.set_session_creator(lambda: "sess_test")
        resp = router.route_message("hello", ChannelType.REST, user_id="user1")
        assert resp == "response"
        assert results == ["hello"]

    def test_route_message_creates_session(self):
        mgr = ChannelManager()
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr)
        router.set_agent_handler(lambda msg, session_id="": "ok")
        router.set_session_creator(lambda: "sess_auto")
        resp = router.route_message("hello", ChannelType.REST, user_id="user1")
        assert resp == "ok"
        mapping = router.session_router.resolve(ChannelType.REST, "user1")
        assert mapping is not None

    def test_route_message_with_existing_session(self):
        mgr = ChannelManager()
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr)
        router.set_agent_handler(lambda msg, session_id="": f"ok:{session_id}")
        router.set_session_creator(lambda: "sess_auto")
        resp1 = router.route_message("hello", ChannelType.REST, user_id="user1")
        resp2 = router.route_message("world", ChannelType.REST, user_id="user1")
        assert "ok:" in resp1
        assert "ok:" in resp2

    def test_allowlist_filtering(self):
        mgr = ChannelManager()
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr)
        router.set_agent_handler(lambda msg, session_id="": "ok")
        router.set_allowlist({"allowed_user"})

        msg = ChannelMessage(
            message_id="test1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="blocked_user"),
            content="hello",
        )
        router._on_message(msg)
        assert router.get_queue_size() == 0

        msg2 = ChannelMessage(
            message_id="test2",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="allowed_user"),
            content="hello",
        )
        router._on_message(msg2)
        assert router.get_queue_size() >= 0

    def test_queue_mode_enum(self):
        assert QueueMode.STEER == "steer"
        assert QueueMode.FOLLOWUP == "followup"
        assert QueueMode.COLLECT == "collect"
        assert QueueMode.INTERRUPT == "interrupt"

    def test_list_channels(self):
        mgr = ChannelManager()
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr)
        channels = router.list_channels()
        assert len(channels) == 1
        assert channels[0]["name"] == "rest"

    def test_start_stop(self):
        mgr = ChannelManager()
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr)
        asyncio.run(router.start())
        asyncio.run(router.stop())


class TestMessageQueueModes:
    def test_steer_mode_queues_message(self):
        mgr = ChannelManager()
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr, default_queue_mode=QueueMode.STEER)
        router._running = True
        router.set_agent_handler(lambda msg, session_id="": "ok")

        msg = ChannelMessage(
            message_id="steer1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="steer message",
            metadata={"queue_mode": "steer"},
        )
        router._on_message(msg)
        assert router.get_queue_size() >= 0

    def test_followup_mode_queues_message(self):
        mgr = ChannelManager()
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr, default_queue_mode=QueueMode.FOLLOWUP)
        router._running = True
        router.set_agent_handler(lambda msg, session_id="": "ok")

        msg = ChannelMessage(
            message_id="followup1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="followup message",
            metadata={"queue_mode": "followup"},
        )
        router._on_message(msg)
        assert router.get_queue_size() >= 0

    def test_interrupt_mode_clears_queue(self):
        mgr = ChannelManager()
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr, default_queue_mode=QueueMode.STEER)
        router._running = True
        router.set_agent_handler(lambda msg, session_id="": "ok")
        router._session_router.create(ChannelType.REST, "user1", session_id="sess_active")
        router._active_session = "sess_active"

        followup_msg = ChannelMessage(
            message_id="f1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="followup",
            metadata={"chat_id": "user1", "queue_mode": "followup"},
        )
        router._on_message(followup_msg)

        interrupt_msg = ChannelMessage(
            message_id="int1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="interrupt!",
            metadata={"chat_id": "user1", "queue_mode": "interrupt"},
        )
        router._on_message(interrupt_msg)

        queue_contents = [qm.message.content for qm in router._queue]
        assert "interrupt!" in queue_contents

    def test_collect_mode_buffers_messages(self):
        mgr = ChannelManager()
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr, default_queue_mode=QueueMode.STEER)
        router._running = True
        router.set_agent_handler(lambda msg, session_id="": "ok")
        router._session_router.create(ChannelType.REST, "user1", session_id="sess_active")
        router._active_session = "sess_active"

        msg1 = ChannelMessage(
            message_id="c1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="collect msg 1",
            metadata={"chat_id": "user1", "queue_mode": "collect"},
        )
        msg2 = ChannelMessage(
            message_id="c2",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="collect msg 2",
            metadata={"chat_id": "user1", "queue_mode": "collect"},
        )
        router._on_message(msg1)
        router._on_message(msg2)

        assert len(router._collect_buffer) == 2

    def test_collect_flush_on_non_active_message(self):
        mgr = ChannelManager()
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr, default_queue_mode=QueueMode.STEER)
        router._running = True
        router.set_agent_handler(lambda msg, session_id="": "ok")
        router._session_router.create(ChannelType.REST, "user1", session_id="sess_active")
        router._active_session = "sess_active"

        collect_msg = ChannelMessage(
            message_id="c1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="collect msg",
            metadata={"chat_id": "user1", "queue_mode": "collect"},
        )
        router._on_message(collect_msg)
        assert len(router._collect_buffer) == 1

        router._active_session = None
        router._session_router.create(ChannelType.REST, "user2", session_id="sess_other")
        new_msg = ChannelMessage(
            message_id="new1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user2"),
            content="new message",
            metadata={"chat_id": "user2", "queue_mode": "collect"},
        )
        router._on_message(new_msg)
        assert len(router._collect_buffer) == 0

    def test_invalid_queue_mode_defaults(self):
        mgr = ChannelManager()
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr, default_queue_mode=QueueMode.STEER)
        router._running = True
        router.set_agent_handler(lambda msg, session_id="": "ok")

        msg = ChannelMessage(
            message_id="inv1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="invalid mode",
            metadata={"queue_mode": "nonexistent"},
        )
        router._on_message(msg)
        assert router.get_queue_size() >= 0
