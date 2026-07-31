"""
ClawHermes - ChannelRouter / SessionRouter 扩展测试

覆盖 router.py 中未被 test_channel.py / test_unit_extended.py 覆盖的分支：
- SessionRouter.resolve() 超时分支
- SessionRouter.touch() / remove()
- ChannelRouter.set_pairing_required() + 配对门控
- ChannelRouter._get_session_lock() 新建锁路径
- ChannelRouter._active_session getter/setter
- _on_message 中 session_creator 调用路径
- _on_message 中 COLLECT flush task 创建/取消
- _flush_collect_after_idle 异步路径
- _process_queue 完整流程（sync/async handler）
- route_message 显式 session_id / async handler / 无 handler
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

from clawhermes.channel.adapter import (
    ChannelManager,
    ChannelMessage,
    ChannelType,
    ChannelUser,
    RESTAdapter,
)
from clawhermes.channel.router import (
    ChannelRouter,
    QueuedMessage,
    QueueMode,
    SessionRouter,
)

# ============================================================
# SessionRouter 边界
# ============================================================


class TestSessionRouterExpired:
    def test_resolve_expired_returns_none(self):
        """resolve 在 mapping 已超时时应删除并返回 None"""
        sr = SessionRouter(idle_timeout_seconds=0)
        sr.create(ChannelType.REST, "user1", session_id="sess_x")
        # 等待超时
        time.sleep(0.01)
        result = sr.resolve(ChannelType.REST, "user1")
        assert result is None
        # 超时后 mapping 应被删除
        assert "rest:user1" not in sr._mappings

    def test_resolve_non_expired_returns_session(self):
        """resolve 在 mapping 未超时时应返回 session_id"""
        sr = SessionRouter(idle_timeout_seconds=3600)
        sr.create(ChannelType.REST, "user1", session_id="sess_x")
        result = sr.resolve(ChannelType.REST, "user1")
        assert result == "sess_x"

    def test_touch_updates_last_active(self):
        """touch 应更新 last_active 时间戳"""
        sr = SessionRouter(idle_timeout_seconds=3600)
        sr.create(ChannelType.REST, "user1", session_id="sess_x")
        original = sr._mappings["rest:user1"].last_active
        time.sleep(0.01)
        sr.touch(ChannelType.REST, "user1")
        assert sr._mappings["rest:user1"].last_active > original


# ============================================================
# ChannelRouter 配对门控
# ============================================================


class TestPairingGate:
    def test_set_pairing_required_changes_flag(self):
        """set_pairing_required 应更新 _pairing_required 标志"""
        router = ChannelRouter(channel_manager=MagicMock())
        assert router._pairing_required is False  # 默认 False
        router.set_pairing_required(True)
        assert router._pairing_required is True
        router.set_pairing_required(False)
        assert router._pairing_required is False

    def test_pairing_required_blocks_unpaired_user(self):
        """启用 pairing_required 时未配对用户的消息应被拒绝"""
        channel_manager = MagicMock()
        pairing_mgr = MagicMock()
        pairing_mgr.is_paired.return_value = False
        router = ChannelRouter(
            channel_manager=channel_manager,
            pairing_manager=pairing_mgr,
            pairing_required=True,
        )
        router._running = True
        router.set_agent_handler(lambda msg, session_id="": "ok")

        msg = ChannelMessage(
            message_id="m1",
            channel_type=ChannelType.FEISHU,
            user=ChannelUser(user_id="unpaired_user"),
            content="hello",
        )
        router._on_message(msg)
        # 队列应为空（消息被拒绝）
        assert router.get_queue_size() == 0

    def test_pairing_required_allows_paired_user(self):
        """启用 pairing_required 时已配对用户的消息应被放行"""
        channel_manager = MagicMock()
        pairing_mgr = MagicMock()
        pairing_mgr.is_paired.return_value = True
        router = ChannelRouter(
            channel_manager=channel_manager,
            pairing_manager=pairing_mgr,
            pairing_required=True,
        )
        router._running = True
        router.set_agent_handler(lambda msg, session_id="": "ok")

        msg = ChannelMessage(
            message_id="m1",
            channel_type=ChannelType.FEISHU,
            user=ChannelUser(user_id="paired_user"),
            content="hello",
        )
        router._on_message(msg)
        # 队列应有消息（被放行）
        assert router.get_queue_size() >= 1

    def test_pairing_required_skipped_for_cli_channel(self):
        """CLI 渠道应跳过配对检查"""
        channel_manager = MagicMock()
        pairing_mgr = MagicMock()
        pairing_mgr.is_paired.return_value = False
        router = ChannelRouter(
            channel_manager=channel_manager,
            pairing_manager=pairing_mgr,
            pairing_required=True,
        )
        router._running = True
        router.set_agent_handler(lambda msg, session_id="": "ok")

        msg = ChannelMessage(
            message_id="m1",
            channel_type=ChannelType.CLI,
            user=ChannelUser(user_id="cli_user"),
            content="hello",
        )
        router._on_message(msg)
        # CLI 应放行
        assert router.get_queue_size() >= 1

    def test_pairing_required_skipped_for_rest_channel(self):
        """REST 渠道应跳过配对检查"""
        channel_manager = MagicMock()
        pairing_mgr = MagicMock()
        pairing_mgr.is_paired.return_value = False
        router = ChannelRouter(
            channel_manager=channel_manager,
            pairing_manager=pairing_mgr,
            pairing_required=True,
        )
        router._running = True
        router.set_agent_handler(lambda msg, session_id="": "ok")

        msg = ChannelMessage(
            message_id="m1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="rest_user"),
            content="hello",
        )
        router._on_message(msg)
        assert router.get_queue_size() >= 1

    def test_pairing_required_no_manager_skipped(self):
        """启用 pairing_required 但 pairing_manager 为 None 时应放行"""
        channel_manager = MagicMock()
        router = ChannelRouter(
            channel_manager=channel_manager,
            pairing_manager=None,
            pairing_required=True,
        )
        router._running = True
        router.set_agent_handler(lambda msg, session_id="": "ok")

        msg = ChannelMessage(
            message_id="m1",
            channel_type=ChannelType.FEISHU,
            user=ChannelUser(user_id="any_user"),
            content="hello",
        )
        router._on_message(msg)
        assert router.get_queue_size() >= 1


# ============================================================
# _get_session_lock / _active_session
# ============================================================


class TestSessionLockAndActive:
    def test_get_session_lock_creates_new_lock(self):
        """_get_session_lock 在 session_id 不存在时应创建新锁"""
        router = ChannelRouter(channel_manager=MagicMock())
        assert "sess_new" not in router._session_locks
        lock1 = router._get_session_lock("sess_new")
        assert "sess_new" in router._session_locks
        assert lock1 is not None

        # 再次获取应返回同一个锁
        lock2 = router._get_session_lock("sess_new")
        assert lock2 is lock1

    def test_active_session_getter_returns_one_when_set(self):
        """_active_session getter 在有活跃 session 时返回其中一个"""
        router = ChannelRouter(channel_manager=MagicMock())
        assert router._active_session is None
        router._active_sessions.add("sess_a")
        router._active_sessions.add("sess_b")
        active = router._active_session
        assert active in {"sess_a", "sess_b"}

    def test_active_session_setter_string_adds_to_set(self):
        """_active_session setter 接收字符串时应加入活跃集合"""
        router = ChannelRouter(channel_manager=MagicMock())
        router._active_session = "sess_x"
        assert "sess_x" in router._active_sessions

    def test_active_session_setter_none_clears_set(self):
        """_active_session setter 接收 None 时应清空活跃集合"""
        router = ChannelRouter(channel_manager=MagicMock())
        router._active_sessions.add("sess_a")
        router._active_sessions.add("sess_b")
        router._active_session = None
        assert len(router._active_sessions) == 0

    def test_get_active_session_method(self):
        """get_active_session 公开方法应返回 _active_session"""
        router = ChannelRouter(channel_manager=MagicMock())
        assert router.get_active_session() is None
        router._active_sessions.add("sess_x")
        assert router.get_active_session() == "sess_x"


# ============================================================
# _on_message 中 session_creator 路径
# ============================================================


class TestOnMessageSessionCreator:
    def test_on_message_uses_session_creator_when_no_session(self):
        """_on_message 在无 session 时应调用 session_creator 获取 session_id（不写入 router）"""
        channel_manager = MagicMock()
        router = ChannelRouter(channel_manager=channel_manager)
        router._running = True
        router.set_agent_handler(lambda msg, session_id="": "ok")
        creator = MagicMock(return_value="sess_from_creator")
        router.set_session_creator(creator)

        msg = ChannelMessage(
            message_id="m1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="hello",
        )
        router._on_message(msg)
        # session_creator 应被调用一次
        creator.assert_called_once()
        # session 不在 active_sessions 中，走 else 分支，消息应入队
        assert router.get_queue_size() == 1


# ============================================================
# COLLECT flush task 异步路径
# ============================================================


class TestCollectFlushAsync:
    def test_flush_collect_after_idle_calls_process_queue(self):
        """_flush_collect_after_idle 在静默期后应 flush 并触发 _process_queue"""
        channel_manager = MagicMock()
        router = ChannelRouter(channel_manager=channel_manager)
        router._running = True
        router.set_agent_handler(lambda msg, session_id="": "ok")
        router._session_router.create(ChannelType.REST, "user1", session_id="sess_active")
        router._active_session = "sess_active"

        # 设置较短 idle 时间
        router._collect_idle_seconds = 0.05

        msg = ChannelMessage(
            message_id="c1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="collect msg",
            metadata={"chat_id": "user1", "queue_mode": "collect"},
        )

        # _on_message 必须在运行的事件循环内调用，loop.create_task 才能创建 flush task
        with patch.object(router, "_process_queue", new=AsyncMock()) as mock_pq:
            async def _run():
                router._on_message(msg)
                assert len(router._collect_buffer) == 1
                assert router._collect_flush_task is not None
                # 等待 idle 时间 + 余量，让 flush task 完成
                await asyncio.sleep(0.3)
                # 缓冲区应被 flush
                assert len(router._collect_buffer) == 0
                # 队列应有合并后的消息
                assert router.get_queue_size() == 1
                # _process_queue 应被触发
                mock_pq.assert_called()

            asyncio.run(_run())

    def test_flush_collect_after_idle_empty_buffer_no_op(self):
        """_flush_collect_after_idle 在缓冲区为空时应 no-op"""
        channel_manager = MagicMock()
        router = ChannelRouter(channel_manager=channel_manager)
        router._collect_idle_seconds = 0.05

        async def _run():
            # 缓冲区为空 → 直接 return
            await router._flush_collect_after_idle("sess_x")

        asyncio.run(_run())
        assert router.get_queue_size() == 0

    def test_flush_collect_buffer_empty_no_op(self):
        """_flush_collect_buffer 在缓冲区为空时应 no-op"""
        channel_manager = MagicMock()
        router = ChannelRouter(channel_manager=channel_manager)
        assert len(router._collect_buffer) == 0
        router._flush_collect_buffer("sess_x")
        assert router.get_queue_size() == 0

    def test_collect_multiple_messages_cancel_previous_flush_task(self):
        """连续 COLLECT 消息应取消前一个 flush task 并创建新 task"""
        channel_manager = MagicMock()
        router = ChannelRouter(channel_manager=channel_manager)
        router._running = True
        router.set_agent_handler(lambda msg, session_id="": "ok")
        router._session_router.create(ChannelType.REST, "user1", session_id="sess_active")
        router._active_session = "sess_active"
        router._collect_idle_seconds = 1.0  # 较长，避免中途触发

        msg1 = ChannelMessage(
            message_id="c1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="msg1",
            metadata={"chat_id": "user1", "queue_mode": "collect"},
        )
        msg2 = ChannelMessage(
            message_id="c2",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="msg2",
            metadata={"chat_id": "user1", "queue_mode": "collect"},
        )

        # _on_message 必须在运行的事件循环内调用，loop.create_task 才能创建 flush task
        async def _run():
            router._on_message(msg1)
            first_task = router._collect_flush_task
            assert first_task is not None

            router._on_message(msg2)
            second_task = router._collect_flush_task
            # 第二个 task 应是新的
            assert second_task is not None
            assert second_task is not first_task

            # 清理：取消未完成的 task
            if second_task is not None and not second_task.done():
                second_task.cancel()

        asyncio.run(_run())


# ============================================================
# _process_queue 完整流程
# ============================================================


class TestProcessQueue:
    def test_process_queue_with_sync_handler(self):
        """_process_queue 同步 handler 应正确处理并清空队列"""
        channel_manager = MagicMock()
        adapter = MagicMock()
        adapter.send_response = AsyncMock()
        channel_manager.get.return_value = adapter
        router = ChannelRouter(channel_manager=channel_manager)
        router.set_agent_handler(lambda msg, session_id="": f"reply:{msg}")

        msg = ChannelMessage(
            message_id="m1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="hello",
            metadata={"chat_id": "user1"},
        )
        router._queue.append(QueuedMessage(message=msg, mode=QueueMode.STEER))

        async def _run():
            await router._process_queue()

        asyncio.run(_run())
        # 队列应清空
        assert router.get_queue_size() == 0
        # adapter.send_response 应被调用
        adapter.send_response.assert_called_once()

    def test_process_queue_with_async_handler(self):
        """_process_queue 异步 handler 应被 await"""
        channel_manager = MagicMock()
        adapter = MagicMock()
        adapter.send_response = AsyncMock()
        channel_manager.get.return_value = adapter
        router = ChannelRouter(channel_manager=channel_manager)

        async def _async_handler(msg, session_id=""):
            return f"async_reply:{msg}"

        router.set_agent_handler(_async_handler)

        msg = ChannelMessage(
            message_id="m1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="hello",
            metadata={"chat_id": "user1"},
        )
        router._queue.append(QueuedMessage(message=msg, mode=QueueMode.STEER))

        async def _run():
            await router._process_queue()

        asyncio.run(_run())
        assert router.get_queue_size() == 0
        adapter.send_response.assert_called_once()

    def test_process_queue_handler_returns_none(self):
        """handler 返回 None 时 response.content 应为空字符串"""
        channel_manager = MagicMock()
        adapter = MagicMock()
        adapter.send_response = AsyncMock()
        channel_manager.get.return_value = adapter
        router = ChannelRouter(channel_manager=channel_manager)
        router.set_agent_handler(lambda msg, session_id="": None)

        msg = ChannelMessage(
            message_id="m1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="hello",
            metadata={"chat_id": "user1"},
        )
        router._queue.append(QueuedMessage(message=msg, mode=QueueMode.STEER))

        async def _run():
            await router._process_queue()

        asyncio.run(_run())
        # 验证 response.content 是 ""
        sent_response = adapter.send_response.call_args[0][0]
        assert sent_response.content == ""

    def test_process_queue_no_adapter_no_error(self):
        """adapter 不存在时不应抛异常"""
        channel_manager = MagicMock()
        channel_manager.get.return_value = None
        router = ChannelRouter(channel_manager=channel_manager)
        router.set_agent_handler(lambda msg, session_id="": "reply")

        msg = ChannelMessage(
            message_id="m1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="hello",
            metadata={"chat_id": "user1"},
        )
        router._queue.append(QueuedMessage(message=msg, mode=QueueMode.STEER))

        async def _run():
            await router._process_queue()

        # 不应抛异常
        asyncio.run(_run())
        assert router.get_queue_size() == 0

    def test_process_queue_handler_exception_no_crash(self):
        """handler 抛异常时应被捕获，不传播"""
        channel_manager = MagicMock()
        adapter = MagicMock()
        adapter.send_response = AsyncMock()
        channel_manager.get.return_value = adapter
        router = ChannelRouter(channel_manager=channel_manager)
        router.set_agent_handler(lambda msg, session_id="": (_ for _ in ()).throw(RuntimeError("boom")))

        msg = ChannelMessage(
            message_id="m1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="hello",
            metadata={"chat_id": "user1"},
        )
        router._queue.append(QueuedMessage(message=msg, mode=QueueMode.STEER))

        async def _run():
            await router._process_queue()

        # 不应抛异常
        asyncio.run(_run())
        # 异常时 send_response 不应被调用
        adapter.send_response.assert_not_called()

    def test_process_queue_empty_no_op(self):
        """队列为空时 _process_queue 应 no-op"""
        channel_manager = MagicMock()
        router = ChannelRouter(channel_manager=channel_manager)

        async def _run():
            await router._process_queue()

        asyncio.run(_run())
        assert router.get_queue_size() == 0

    def test_process_queue_no_session_creates_new(self):
        """_process_queue 中 session_id 为 None 时应创建新 session"""
        channel_manager = MagicMock()
        adapter = MagicMock()
        adapter.send_response = AsyncMock()
        channel_manager.get.return_value = adapter
        router = ChannelRouter(channel_manager=channel_manager)
        router.set_agent_handler(lambda msg, session_id="": "reply")

        msg = ChannelMessage(
            message_id="m1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="brand_new_user"),
            content="hello",
            metadata={"chat_id": "brand_new_user"},
        )
        router._queue.append(QueuedMessage(message=msg, mode=QueueMode.STEER))

        async def _run():
            await router._process_queue()

        asyncio.run(_run())
        # session 应被创建
        assert router._session_router.resolve(ChannelType.REST, "brand_new_user") is not None

    def test_on_message_not_running_drops_message(self):
        """router 未运行时 _on_message 应丢弃消息"""
        channel_manager = MagicMock()
        router = ChannelRouter(channel_manager=channel_manager)
        router._running = False  # 未运行
        router.set_agent_handler(lambda msg, session_id="": "ok")

        msg = ChannelMessage(
            message_id="m1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="hello",
        )
        router._on_message(msg)
        assert router.get_queue_size() == 0


# ============================================================
# route_message 扩展路径
# ============================================================


class TestRouteMessageExtended:
    def test_route_message_with_explicit_session_id(self):
        """route_message 传入显式 session_id 时应使用该 id 并注册"""
        mgr = ChannelManager()
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr)
        router.set_agent_handler(lambda msg, session_id="": f"ok:{session_id}")

        resp = asyncio.run(
            router.route_message(
                "hello",
                ChannelType.REST,
                user_id="user1",
                session_id="explicit_sess",
            )
        )
        assert resp == "ok:explicit_sess"
        # 显式 session_id 应被注册到 session_router
        assert router._session_router.resolve(ChannelType.REST, "user1") == "explicit_sess"

    def test_route_message_with_session_creator(self):
        """route_message 无显式 session_id 但有 session_creator 时应调用 creator"""
        mgr = ChannelManager()
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr)
        router.set_agent_handler(lambda msg, session_id="": f"ok:{session_id}")
        router.set_session_creator(lambda: "creator_sess")

        resp = asyncio.run(
            router.route_message("hello", ChannelType.REST, user_id="user_new")
        )
        assert resp == "ok:creator_sess"
        assert router._session_router.resolve(ChannelType.REST, "user_new") == "creator_sess"

    def test_route_message_with_chat_id(self):
        """route_message 传入 chat_id 时应使用 chat_id 作为 session key"""
        mgr = ChannelManager()
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr)
        router.set_agent_handler(lambda msg, session_id="": "ok")

        asyncio.run(
            router.route_message(
                "hello",
                ChannelType.REST,
                user_id="user1",
                chat_id="custom_chat",
            )
        )
        # chat_id 应被用作 session key
        assert router._session_router.resolve(ChannelType.REST, "custom_chat") is not None

    def test_route_message_with_async_handler(self):
        """route_message 异步 handler 应被 await"""
        mgr = ChannelManager()
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr)

        async def _async_handler(msg, session_id=""):
            return f"async:{msg}"

        router.set_agent_handler(_async_handler)

        resp = asyncio.run(
            router.route_message("hello", ChannelType.REST, user_id="user1")
        )
        assert resp == "async:hello"

    def test_route_message_no_handler_returns_empty(self):
        """route_message 无 handler 时应返回空字符串"""
        mgr = ChannelManager()
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr)
        # 不设置 handler
        resp = asyncio.run(
            router.route_message("hello", ChannelType.REST, user_id="user1")
        )
        assert resp == ""

    def test_route_message_existing_session_reused(self):
        """route_message 已有 session 时应复用"""
        mgr = ChannelManager()
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr)
        router.set_agent_handler(lambda msg, session_id="": f"ok:{session_id}")

        # 第一次创建 session
        resp1 = asyncio.run(
            router.route_message("hello", ChannelType.REST, user_id="user1")
        )
        # 第二次应复用
        resp2 = asyncio.run(
            router.route_message("world", ChannelType.REST, user_id="user1")
        )
        assert resp1 == resp2


# ============================================================
# 队列模式边界
# ============================================================


class TestQueueModesExtended:
    def test_steer_mode_active_session_appends_to_queue(self):
        """STEER 模式在 session 活跃时应 append 到队列"""
        channel_manager = MagicMock()
        router = ChannelRouter(channel_manager=channel_manager)
        router._running = True
        router.set_agent_handler(lambda msg, session_id="": "ok")
        router._session_router.create(ChannelType.REST, "user1", session_id="sess_active")
        router._active_session = "sess_active"

        msg = ChannelMessage(
            message_id="steer1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="steer msg",
            metadata={"chat_id": "user1", "queue_mode": "steer"},
        )
        router._on_message(msg)
        assert router.get_queue_size() >= 1

    def test_followup_mode_active_session_appends_to_queue(self):
        """FOLLOWUP 模式在 session 活跃时应 append 到队列"""
        channel_manager = MagicMock()
        router = ChannelRouter(channel_manager=channel_manager)
        router._running = True
        router.set_agent_handler(lambda msg, session_id="": "ok")
        router._session_router.create(ChannelType.REST, "user1", session_id="sess_active")
        router._active_session = "sess_active"

        msg = ChannelMessage(
            message_id="fu1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="followup msg",
            metadata={"chat_id": "user1", "queue_mode": "followup"},
        )
        router._on_message(msg)
        assert router.get_queue_size() >= 1

    def test_collect_mode_no_active_session_flushes_and_appends(self):
        """COLLECT 模式无活跃 session 但有缓冲时应 flush 后 append"""
        channel_manager = MagicMock()
        router = ChannelRouter(channel_manager=channel_manager)
        router._running = True
        router.set_agent_handler(lambda msg, session_id="": "ok")

        # 预填充 collect_buffer
        buffer_msg = ChannelMessage(
            message_id="buf1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="buffered",
            metadata={"chat_id": "user1"},
        )
        router._collect_buffer.append(buffer_msg)

        # 发送 COLLECT 消息（无活跃 session）
        msg = ChannelMessage(
            message_id="c1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="new collect",
            metadata={"chat_id": "user1", "queue_mode": "collect"},
        )
        router._on_message(msg)
        # 缓冲应被 flush
        assert len(router._collect_buffer) == 0
        # 队列应有合并消息 + 新消息
        assert router.get_queue_size() >= 1
