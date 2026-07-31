"""ClawHermes - Profile 隔离 API / Chat / ChannelRouter 测试

覆盖 PR5b：
- TestProfileAPI: /profiles 端点（创建/列表/详情/删除/绑定）
- TestChatWithProfile: /chat?profile_id=xxx 通过 profile_manager 解析 Agent
- TestChannelRouterProfile: ChannelRouter 按 profile_id 分发消息
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.testclient import TestClient

import clawhermes.gateway.app as gw
from clawhermes.channel.adapter import (
    ChannelManager,
    ChannelMessage,
    ChannelType,
    ChannelUser,
)
from clawhermes.channel.router import ChannelRouter, QueuedMessage, QueueMode
from clawhermes.gateway.app import GatewayState, app
from clawhermes.profile.config import ProfileConfig
from clawhermes.profile.context import ProfileContext
from clawhermes.profile.manager import ProfileManager

# ============================================================
# 通用夹具
# ============================================================


@pytest.fixture
def fresh_state(monkeypatch):
    """每个测试前重置 _state，并设置独立的 CH_DATA_DIR"""
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("CH_DATA_DIR", tmp)
    old_state = gw._state
    gw._state = GatewayState()
    yield gw._state
    for task in gw._state._bg_tasks:
        if not task.done():
            task.cancel()
    gw._state = old_state


def _make_mock_agent(chat_return: str = "default-reply", model: str = "test/model"):
    """构造一个 mock Agent，``chat`` 同步返回 chat_return"""
    agent = MagicMock()
    agent.chat = MagicMock(return_value=chat_return)
    agent.llm = MagicMock(model=model)
    return agent


def _make_profile_context(
    profile_id: str, agent: MagicMock, data_dir: Path
) -> ProfileContext:
    """构造已初始化的 ProfileContext（attach mock agent）"""
    ctx = ProfileContext(
        profile_id=profile_id,
        data_dir=data_dir / profile_id,
        config=ProfileConfig.default(),
    )
    ctx.attach_components(agent=agent)
    return ctx


# ============================================================
# TestProfileAPI — /profiles 端点
# ============================================================


class TestProfileAPI:
    """覆盖 /profiles 创建/列表/详情/删除/绑定端点"""

    def test_create_profile_success(self, fresh_state, tmp_path):
        """POST /profiles 创建新 profile 返回 200 + 配置"""
        from clawhermes.profile.config import ProfileConfig as PCfg

        pm = ProfileManager(tmp_path)
        asyncio.run(pm.initialize())
        fresh_state.profile_manager = pm

        client = TestClient(app)
        resp = client.post("/profiles", json={
            "profile_id": "research",
            "llm_provider": "openai",
            "llm_model": "gpt-4o",
            "tools_profile": "full",
        })
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["profile_id"] == "research"
        assert data["status"] == "created"
        assert data["config"]["llm_provider"] == "openai"
        assert data["config"]["llm_model"] == "gpt-4o"
        assert data["config"]["tools_profile"] == "full"
        # 验证默认值已写入（default ProfileConfig 字段）
        assert data["config"]["memory_backend"] == PCfg.default().memory_backend

        asyncio.run(pm.shutdown_all())

    def test_create_profile_default_values(self, fresh_state, tmp_path):
        """POST /profiles 仅传 profile_id 时使用 ProfileConfig.default()"""
        pm = ProfileManager(tmp_path)
        asyncio.run(pm.initialize())
        fresh_state.profile_manager = pm

        client = TestClient(app)
        resp = client.post("/profiles", json={"profile_id": "plain"})
        assert resp.status_code == 200
        cfg = resp.json()["config"]
        assert cfg["llm_provider"] == "deepseek"
        assert cfg["llm_model"] == "deepseek/deepseek-chat"
        assert cfg["tools_profile"] == "standard"

        asyncio.run(pm.shutdown_all())

    def test_create_profile_invalid_id_returns_400(self, fresh_state, tmp_path):
        """POST /profiles 非法 profile_id 返回 400"""
        pm = ProfileManager(tmp_path)
        asyncio.run(pm.initialize())
        fresh_state.profile_manager = pm

        client = TestClient(app)
        resp = client.post("/profiles", json={"profile_id": "bad.name"})
        assert resp.status_code == 400
        assert "无效的 profile_id" in resp.json()["detail"]

        asyncio.run(pm.shutdown_all())

    def test_create_profile_duplicate_returns_400(self, fresh_state, tmp_path):
        """POST /profiles 已存在的 profile_id 返回 400"""
        pm = ProfileManager(tmp_path)
        asyncio.run(pm.initialize())
        fresh_state.profile_manager = pm

        client = TestClient(app)
        # default 由 initialize 创建
        resp = client.post("/profiles", json={"profile_id": "default"})
        assert resp.status_code == 400
        assert "Profile 已存在" in resp.json()["detail"]

        asyncio.run(pm.shutdown_all())

    def test_create_profile_when_no_manager_returns_503(self, fresh_state):
        """profile_manager 未初始化时所有 /profiles 操作返回 503"""
        assert fresh_state.profile_manager is None
        client = TestClient(app)
        resp = client.post("/profiles", json={"profile_id": "x"})
        assert resp.status_code == 503

    def test_list_profiles(self, fresh_state, tmp_path):
        """GET /profiles 返回所有 profile 列表"""
        pm = ProfileManager(tmp_path)
        asyncio.run(pm.initialize())
        asyncio.run(pm.create_profile("alpha"))
        asyncio.run(pm.create_profile("beta"))
        fresh_state.profile_manager = pm

        client = TestClient(app)
        resp = client.get("/profiles")
        assert resp.status_code == 200
        data = resp.json()
        ids = [p["profile_id"] for p in data["profiles"]]
        assert ids == ["alpha", "beta", "default"]
        assert data["count"] == 3

        asyncio.run(pm.shutdown_all())

    def test_get_profile_detail(self, fresh_state, tmp_path):
        """GET /profiles/{id} 返回 profile 详情"""
        pm = ProfileManager(tmp_path)
        asyncio.run(pm.initialize())
        asyncio.run(
            pm.create_profile(
                "research",
                config=ProfileConfig(llm_model="gpt-4o", tools_profile="full"),
            )
        )
        fresh_state.profile_manager = pm

        client = TestClient(app)
        resp = client.get("/profiles/research")
        assert resp.status_code == 200
        data = resp.json()
        assert data["profile_id"] == "research"
        assert data["config"]["llm_model"] == "gpt-4o"
        assert data["initialized"] is True

        asyncio.run(pm.shutdown_all())

    def test_get_profile_not_found_returns_404(self, fresh_state, tmp_path):
        """GET /profiles/{id} 不存在时返回 404"""
        pm = ProfileManager(tmp_path)
        asyncio.run(pm.initialize())
        fresh_state.profile_manager = pm

        client = TestClient(app)
        resp = client.get("/profiles/nonexistent")
        assert resp.status_code == 404

        asyncio.run(pm.shutdown_all())

    def test_delete_profile_success(self, fresh_state, tmp_path):
        """DELETE /profiles/{id} 删除非 default profile 返回 200"""
        pm = ProfileManager(tmp_path)
        asyncio.run(pm.initialize())
        asyncio.run(pm.create_profile("to-delete"))
        fresh_state.profile_manager = pm

        client = TestClient(app)
        resp = client.delete("/profiles/to-delete")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"
        assert data["profile_id"] == "to-delete"

        asyncio.run(pm.shutdown_all())

    def test_delete_profile_not_found_returns_404(self, fresh_state, tmp_path):
        """DELETE /profiles/{id} 不存在时返回 404"""
        pm = ProfileManager(tmp_path)
        asyncio.run(pm.initialize())
        fresh_state.profile_manager = pm

        client = TestClient(app)
        resp = client.delete("/profiles/nonexistent")
        assert resp.status_code == 404

        asyncio.run(pm.shutdown_all())

    def test_delete_default_returns_400(self, fresh_state, tmp_path):
        """DELETE /profiles/default 返回 400"""
        pm = ProfileManager(tmp_path)
        asyncio.run(pm.initialize())
        fresh_state.profile_manager = pm

        client = TestClient(app)
        resp = client.delete("/profiles/default")
        assert resp.status_code == 400
        assert "不能删除 default" in resp.json()["detail"]

        asyncio.run(pm.shutdown_all())

    def test_bind_profile_success(self, fresh_state, tmp_path):
        """POST /profiles/bind 绑定 user_id → profile_id 返回 200"""
        pm = ProfileManager(tmp_path)
        asyncio.run(pm.initialize())
        asyncio.run(pm.create_profile("research"))
        fresh_state.profile_manager = pm

        client = TestClient(app)
        resp = client.post("/profiles/bind", json={
            "user_id": "user1",
            "profile_id": "research",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "bound"
        assert data["user_id"] == "user1"
        assert data["profile_id"] == "research"
        # 绑定应已生效
        assert pm.get_user_binding("user1") == "research"

        asyncio.run(pm.shutdown_all())

    def test_bind_profile_unknown_returns_404(self, fresh_state, tmp_path):
        """POST /profiles/bind 绑定到不存在的 profile 返回 404"""
        pm = ProfileManager(tmp_path)
        asyncio.run(pm.initialize())
        fresh_state.profile_manager = pm

        client = TestClient(app)
        resp = client.post("/profiles/bind", json={
            "user_id": "user1",
            "profile_id": "nonexistent",
        })
        assert resp.status_code == 404

        asyncio.run(pm.shutdown_all())

    def test_bind_profile_empty_user_id_returns_400(self, fresh_state, tmp_path):
        """POST /profiles/bind 空 user_id 返回 400"""
        pm = ProfileManager(tmp_path)
        asyncio.run(pm.initialize())
        fresh_state.profile_manager = pm

        client = TestClient(app)
        resp = client.post("/profiles/bind", json={
            "user_id": "",
            "profile_id": "default",
        })
        assert resp.status_code == 400

        asyncio.run(pm.shutdown_all())


# ============================================================
# TestChatWithProfile — /chat?profile_id=xxx
# ============================================================


def _setup_chat_state(state: GatewayState):
    """设置已初始化的 state（绕过 initialize()）"""
    from clawhermes.agent.loop import Agent, AgentConfig, ToolRegistry
    from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager
    from clawhermes.agent.session import SessionManager
    from clawhermes.channel.adapter import ChannelManager, RESTAdapter
    from clawhermes.channel.router import ChannelRouter, SessionRouter
    from clawhermes.llm.provider import LLMProvider
    from clawhermes.skills.manager import SkillManager
    from clawhermes.tools.builtin import register_builtin_tools

    data_dir = tempfile.mkdtemp()
    provider = LLMProvider(model="test/model", api_key="test-key")
    registry = ToolRegistry()
    register_builtin_tools(registry, profile="minimal")
    memory = MemoryManager()
    memory.add_provider(JSONMemoryProvider(Path(data_dir)))
    sm = SkillManager(Path(data_dir) / "skills")
    agent = Agent(
        llm_provider=provider,
        tool_registry=registry,
        config=AgentConfig(max_iterations=1),
        memory_manager=memory,
        skill_manager=sm,
    )
    session_mgr = SessionManager(data_dir)
    channel_manager = ChannelManager()
    channel_manager.register("rest", RESTAdapter())
    channel_router = ChannelRouter(
        channel_manager=channel_manager,
        session_router=SessionRouter(),
    )
    state.agent = agent
    state.memory = memory
    state.skill_manager = sm
    state.session_mgr = session_mgr
    state.channel_router = channel_router
    return state


class TestChatWithProfile:
    """覆盖 /chat?profile_id=xxx 通过 profile_manager 解析 Agent 的逻辑"""

    def test_chat_without_profile_id_uses_state_agent(self, fresh_state):
        """无 profile_id 时保持原行为：用 _state.agent"""
        _setup_chat_state(fresh_state)
        fresh_state.profile_manager = MagicMock()
        fresh_state.channel_router.route_message = AsyncMock(return_value="默认回复")

        client = TestClient(app)
        resp = client.post("/chat", json={"message": "hi"})
        assert resp.status_code == 200
        assert resp.json()["response"] == "默认回复"
        # profile_manager.resolve_profile 不应被调用
        fresh_state.profile_manager.resolve_profile.assert_not_called()

    def test_chat_with_profile_id_resolves_via_profile_manager(self, fresh_state, tmp_path):
        """profile_id 非空时通过 profile_manager 解析对应 Agent"""
        _setup_chat_state(fresh_state)

        # 构造已初始化的 ProfileManager，含 research profile（mock agent）
        research_agent = _make_mock_agent(chat_return="research-reply", model="research/model")
        pm = ProfileManager(tmp_path)
        asyncio.run(pm.initialize())
        asyncio.run(pm.create_profile("research"))
        # 替换 research profile 的 agent
        pm.get_profile("research").attach_components(agent=research_agent)
        fresh_state.profile_manager = pm

        # route_message mock 避免实际 LLM 调用 — 重点验证 chat 端点不会因 profile_id 报错
        fresh_state.channel_router.route_message = AsyncMock(return_value="research-reply")

        client = TestClient(app)
        resp = client.post("/chat?profile_id=research", json={"message": "hi"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["response"] == "research-reply"
        # route_message 调用时应携带 profile_id metadata
        call_kwargs = fresh_state.channel_router.route_message.call_args.kwargs
        assert call_kwargs["metadata"]["profile_id"] == "research"

        asyncio.run(pm.shutdown_all())

    def test_chat_with_nonexistent_profile_id_returns_404(self, fresh_state, tmp_path):
        """profile_id 不存在时返回 404"""
        _setup_chat_state(fresh_state)

        pm = ProfileManager(tmp_path)
        asyncio.run(pm.initialize())
        fresh_state.profile_manager = pm

        client = TestClient(app)
        resp = client.post("/chat?profile_id=nonexistent", json={"message": "hi"})
        assert resp.status_code == 404

        asyncio.run(pm.shutdown_all())

    def test_chat_with_profile_id_no_manager_falls_back(self, fresh_state):
        """profile_id 非空但 profile_manager 为 None 时回退到 _state.agent"""
        _setup_chat_state(fresh_state)
        assert fresh_state.profile_manager is None
        fresh_state.channel_router.route_message = AsyncMock(return_value="回退回复")

        client = TestClient(app)
        resp = client.post("/chat?profile_id=any", json={"message": "hi"})
        assert resp.status_code == 200
        assert resp.json()["response"] == "回退回复"


# ============================================================
# TestChannelRouterProfile — ChannelRouter 按 profile 分发
# ============================================================


class TestChannelRouterProfile:
    """覆盖 ChannelRouter.set_profile_manager + _resolve_agent + route/_process_queue 分发"""

    def test_set_profile_manager(self):
        """set_profile_manager 应注入 _profile_manager 字段"""
        router = ChannelRouter(channel_manager=MagicMock())
        assert router._profile_manager is None

        pm = MagicMock()
        router.set_profile_manager(pm)
        assert router._profile_manager is pm

    def test_resolve_agent_no_manager_returns_none(self):
        """_profile_manager 未设置时 _resolve_agent 返回 None"""
        router = ChannelRouter(channel_manager=MagicMock())
        assert router._resolve_agent("user1", None) is None
        assert router._resolve_agent("user1", "research") is None

    def test_resolve_agent_with_explicit_profile_id(self):
        """explicit_id 优先于 user_id binding"""
        pm = MagicMock()
        ctx = MagicMock()
        ctx.agent = "agent_for_research"
        pm.resolve_profile.return_value = ctx

        router = ChannelRouter(channel_manager=MagicMock())
        router.set_profile_manager(pm)

        agent = router._resolve_agent("user1", "research")
        assert agent == "agent_for_research"
        pm.resolve_profile.assert_called_once_with("user1", "research")

    def test_resolve_agent_returns_none_on_keyerror(self):
        """explicit_id 指定但不存在时返回 None（回退到 _agent_handler）"""
        pm = MagicMock()
        pm.resolve_profile.side_effect = KeyError("not found")

        router = ChannelRouter(channel_manager=MagicMock())
        router.set_profile_manager(pm)

        agent = router._resolve_agent("user1", "nonexistent")
        assert agent is None

    def test_route_message_uses_profile_agent(self):
        """route_message 在 metadata.profile_id 指定时应调用对应 Agent.chat"""
        pm = MagicMock()
        ctx = MagicMock()
        profile_agent = MagicMock()
        profile_agent.chat = MagicMock(return_value="profile-reply")
        ctx.agent = profile_agent
        pm.resolve_profile.return_value = ctx

        mgr = ChannelManager()
        from clawhermes.channel.adapter import RESTAdapter
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr)
        router.set_profile_manager(pm)

        # 普通默认 handler 不应被调用
        fallback = MagicMock(return_value="fallback")
        router.set_agent_handler(fallback)

        resp = asyncio.run(
            router.route_message(
                "hello",
                ChannelType.REST,
                user_id="user1",
                metadata={"profile_id": "research"},
            )
        )
        assert resp == "profile-reply"
        profile_agent.chat.assert_called_once()
        # 校验调用参数：content + session_id（session_id 由 router 创建）
        call_args = profile_agent.chat.call_args
        assert call_args.args[0] == "hello"
        assert "session_id" in call_args.kwargs
        fallback.assert_not_called()

    def test_route_message_falls_back_when_profile_not_found(self):
        """profile_id 不存在时应回退到 _agent_handler"""
        pm = MagicMock()
        pm.resolve_profile.side_effect = KeyError("not found")

        mgr = ChannelManager()
        from clawhermes.channel.adapter import RESTAdapter
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr)
        router.set_profile_manager(pm)
        router.set_agent_handler(lambda msg, session_id="": "fallback-reply")

        resp = asyncio.run(
            router.route_message(
                "hello",
                ChannelType.REST,
                user_id="user1",
                metadata={"profile_id": "nonexistent"},
            )
        )
        assert resp == "fallback-reply"

    def test_route_message_no_profile_id_uses_default_profile_agent(self):
        """metadata 无 profile_id 时通过 profile_manager 解析到 default profile 的 agent

        profile_manager 已注入时，所有消息都走 resolve_profile 路径（默认 profile 优先于 _agent_handler）。
        """
        pm = MagicMock()
        ctx = MagicMock()
        profile_agent = MagicMock()
        profile_agent.chat = MagicMock(return_value="default-profile-reply")
        ctx.agent = profile_agent
        pm.resolve_profile.return_value = ctx

        mgr = ChannelManager()
        from clawhermes.channel.adapter import RESTAdapter
        mgr.register("rest", RESTAdapter())
        router = ChannelRouter(channel_manager=mgr)
        router.set_profile_manager(pm)
        router.set_agent_handler(lambda msg, session_id="": "fallback-reply")

        # 不传 profile_id metadata
        resp = asyncio.run(
            router.route_message(
                "hello",
                ChannelType.REST,
                user_id="user1",
            )
        )
        # 默认 profile_id 为 None，仍会调用 resolve_profile(user1, None) 解析到 default profile
        # 默认 profile 的 agent 优先于 _agent_handler
        assert resp == "default-profile-reply"

    def test_process_queue_uses_profile_agent(self):
        """_process_queue 在 metadata.profile_id 指定时应调用对应 Agent.chat"""
        pm = MagicMock()
        ctx = MagicMock()
        profile_agent = MagicMock()
        profile_agent.chat = MagicMock(return_value="profile-queue-reply")
        ctx.agent = profile_agent
        pm.resolve_profile.return_value = ctx

        channel_manager = MagicMock()
        adapter = MagicMock()
        adapter.send_response = AsyncMock()
        channel_manager.get.return_value = adapter
        router = ChannelRouter(channel_manager=channel_manager)
        router.set_profile_manager(pm)
        # 默认 handler 不应被调用
        router.set_agent_handler(MagicMock(return_value="should-not-call"))

        msg = ChannelMessage(
            message_id="m1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="hello",
            metadata={"chat_id": "user1", "profile_id": "research"},
        )
        router._queue.append(QueuedMessage(message=msg, mode=QueueMode.STEER))

        asyncio.run(router._process_queue())

        profile_agent.chat.assert_called_once()
        adapter.send_response.assert_called_once()
        sent_response = adapter.send_response.call_args[0][0]
        assert sent_response.content == "profile-queue-reply"

    def test_process_queue_falls_back_when_profile_not_found(self):
        """_process_queue 在 profile_id 解析失败时应回退到 _agent_handler"""
        pm = MagicMock()
        pm.resolve_profile.side_effect = KeyError("not found")

        channel_manager = MagicMock()
        adapter = MagicMock()
        adapter.send_response = AsyncMock()
        channel_manager.get.return_value = adapter
        router = ChannelRouter(channel_manager=channel_manager)
        router.set_profile_manager(pm)
        router.set_agent_handler(lambda msg, session_id="": "fallback-reply")

        msg = ChannelMessage(
            message_id="m1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="hello",
            metadata={"chat_id": "user1", "profile_id": "nonexistent"},
        )
        router._queue.append(QueuedMessage(message=msg, mode=QueueMode.STEER))

        asyncio.run(router._process_queue())

        adapter.send_response.assert_called_once()
        sent_response = adapter.send_response.call_args[0][0]
        assert sent_response.content == "fallback-reply"

    def test_backward_compat_no_profile_manager_uses_agent_handler(self):
        """未注入 profile_manager 时 _process_queue 行为不变（仍走 _agent_handler）"""
        channel_manager = MagicMock()
        adapter = MagicMock()
        adapter.send_response = AsyncMock()
        channel_manager.get.return_value = adapter
        router = ChannelRouter(channel_manager=channel_manager)
        # 不调用 set_profile_manager
        router.set_agent_handler(lambda msg, session_id="": "no-pm-reply")

        msg = ChannelMessage(
            message_id="m1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="user1"),
            content="hello",
            metadata={"chat_id": "user1", "profile_id": "ignored-when-no-pm"},
        )
        router._queue.append(QueuedMessage(message=msg, mode=QueueMode.STEER))

        asyncio.run(router._process_queue())

        adapter.send_response.assert_called_once()
        sent_response = adapter.send_response.call_args[0][0]
        assert sent_response.content == "no-pm-reply"


# ============================================================
# TestCLIProfileCommands — CLI 命令注册与基本可用性
# ============================================================


class TestCLIProfileCommands:
    """覆盖 CLI profile 子命令组注册（仅校验入口，不执行实际 ProfileManager 初始化）"""

    def test_profile_command_registered_in_main(self):
        """main 命令组应包含 profile 子命令"""
        from click.testing import CliRunner

        from clawhermes.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "profile" in result.output

    def test_profile_subcommands_help(self):
        """profile 子命令组应暴露 create/list/delete/bind 子命令"""
        from click.testing import CliRunner

        from clawhermes.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["profile", "--help"])
        assert result.exit_code == 0
        assert "create" in result.output
        assert "list" in result.output
        assert "delete" in result.output
        assert "bind" in result.output

    def test_profile_create_help_options(self):
        """profile create --help 应展示 --llm / --model / --tools 选项"""
        from click.testing import CliRunner

        from clawhermes.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["profile", "create", "--help"])
        assert result.exit_code == 0
        assert "--llm" in result.output
        assert "--model" in result.output
        assert "--tools" in result.output
