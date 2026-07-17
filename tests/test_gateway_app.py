"""
ClawHermes - Gateway app 模块测试

覆盖 /init、/chat、/chat/stream 端点、网关密钥中间件、CORS、
_auto_init、_to_bool、webhook、DM 配对、MCP 等端点。
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

import clawhermes.gateway.app as gw
from clawhermes.gateway.app import (
    ChatRequest,
    ChatResponse,
    CronJobRequest,
    GatewayState,
    InitRequest,
    MCPAddRequest,
    _to_bool,
    app,
)


@pytest.fixture
def fresh_state(monkeypatch):
    """每个测试前重置 _state，并设置独立的 CH_DATA_DIR"""
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("CH_DATA_DIR", tmp)
    old_state = gw._state
    gw._state = GatewayState()
    yield gw._state
    # 清理后台任务
    for task in gw._state._bg_tasks:
        if not task.done():
            task.cancel()
    gw._state = old_state


def _setup_initialized_state(state: GatewayState):
    """设置已初始化的 state（绕过 initialize() 的重依赖）"""
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
    from clawhermes.agent.scheduler import CronScheduler
    scheduler = CronScheduler(data_dir)

    state.agent = agent
    state.memory = memory
    state.skill_manager = sm
    state.session_mgr = session_mgr
    state.channel_router = channel_router
    state.scheduler = scheduler
    return state


# ============================================================
# GatewayState 测试
# ============================================================

class TestGatewayState:
    def test_initial_state(self):
        state = GatewayState()
        assert state.agent is None
        assert state.memory is None
        assert state.session_mgr is None
        assert state.scheduler is None
        assert state.channel_router is None
        assert state.is_initialized() is False
        assert state.start_time > 0

    def test_get_agent_raises_when_uninitialized(self):
        state = GatewayState()
        with pytest.raises(Exception):
            state.get_agent()

    def test_get_memory_raises_when_uninitialized(self):
        state = GatewayState()
        with pytest.raises(Exception):
            state.get_memory()

    def test_get_skill_manager_returns_default_when_unset(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CH_DATA_DIR", str(tmp_path))
        state = GatewayState()
        sm = state.get_skill_manager()
        assert sm is not None

    def test_get_skill_manager_returns_existing(self):
        state = GatewayState()
        mock_sm = MagicMock()
        state.skill_manager = mock_sm
        assert state.get_skill_manager() is mock_sm


# ============================================================
# _to_bool 测试
# ============================================================

class TestToBool:
    def test_true_bool(self):
        assert _to_bool(True) is True

    def test_false_bool(self):
        assert _to_bool(False) is False

    def test_true_string(self):
        assert _to_bool("true") is True
        assert _to_bool("True") is True
        assert _to_bool("1") is True
        assert _to_bool("yes") is True

    def test_false_string(self):
        assert _to_bool("false") is False
        assert _to_bool("0") is False
        assert _to_bool("no") is False

    def test_int(self):
        assert _to_bool(1) is True
        assert _to_bool(0) is False

    def test_none(self):
        assert _to_bool(None) is False


# ============================================================
# /init 端点测试
# ============================================================

class TestInitEndpoint:
    def test_init_no_api_key(self, fresh_state, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        client = TestClient(app)
        resp = client.post("/init", json={"model": "test/model"})
        assert resp.status_code == 400
        assert "api_key" in resp.json()["detail"]

    def test_init_with_api_key_in_body(self, fresh_state, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

        async def fake_init(self, **kwargs):
            self.agent = MagicMock()
            self.agent.tools.list.return_value = []

        with patch.object(GatewayState, "initialize", fake_init):
            client = TestClient(app)
            resp = client.post("/init", json={"api_key": "sk-test", "model": "test/model"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["model"] == "test/model"

    def test_init_uses_env_api_key(self, fresh_state, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")

        async def fake_init(self, **kwargs):
            self.agent = MagicMock()
            self.agent.tools.list.return_value = []

        with patch.object(GatewayState, "initialize", fake_init):
            client = TestClient(app)
            resp = client.post("/init", json={"model": "test/model"})
        assert resp.status_code == 200

    def test_init_uses_env_base_url(self, fresh_state, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://env.api.com")

        captured = {}

        async def fake_init(self, **kwargs):
            captured.update(kwargs)
            self.agent = MagicMock()
            self.agent.tools.list.return_value = []

        with patch.object(GatewayState, "initialize", fake_init):
            client = TestClient(app)
            resp = client.post("/init", json={"api_key": "sk-test", "model": "m"})
        assert resp.status_code == 200
        assert captured["base_url"] == "https://env.api.com"

    def test_init_clawhermes_error(self, fresh_state, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        from clawhermes.agent.exceptions import ClawHermesError

        async def fake_init(self, **kwargs):
            raise ClawHermesError("init failed")

        with patch.object(GatewayState, "initialize", fake_init):
            client = TestClient(app)
            resp = client.post("/init", json={"api_key": "sk-test", "model": "m"})
        assert resp.status_code == 500
        assert "初始化失败" in resp.json()["detail"]

    def test_init_generic_error(self, fresh_state, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

        async def fake_init(self, **kwargs):
            raise RuntimeError("boom")

        with patch.object(GatewayState, "initialize", fake_init):
            client = TestClient(app)
            resp = client.post("/init", json={"api_key": "sk-test", "model": "m"})
        assert resp.status_code == 500

    def test_init_request_schema_defaults(self):
        req = InitRequest()
        assert req.api_key is None
        assert req.model == "deepseek/deepseek-chat"
        assert req.base_url is None
        assert req.max_iterations == 50
        assert req.profile == "standard"


# ============================================================
# /chat 端点测试
# ============================================================

class TestChatEndpoint:
    def test_chat_uninitialized(self, fresh_state):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/chat", json={"message": "hello"})
        assert resp.status_code == 500

    def test_chat_no_session_mgr(self, fresh_state):
        _setup_initialized_state(fresh_state)
        fresh_state.session_mgr = None
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/chat", json={"message": "hello"})
        assert resp.status_code == 500

    def test_chat_creates_new_session(self, fresh_state):
        state = _setup_initialized_state(fresh_state)
        # Mock route_message to avoid actual agent execution
        state.channel_router.route_message = AsyncMock(return_value="回复内容")
        client = TestClient(app)
        resp = client.post("/chat", json={"message": "你好"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "回复内容"
        assert data["session_id"]
        assert data["model"] == "test/model"

    def test_chat_with_existing_session(self, fresh_state):
        state = _setup_initialized_state(fresh_state)
        sid = state.session_mgr.create_session()
        state.channel_router.route_message = AsyncMock(return_value="ok")
        client = TestClient(app)
        resp = client.post("/chat", json={"message": "hi", "session_id": sid})
        assert resp.status_code == 200
        assert resp.json()["session_id"] == sid

    def test_chat_with_nonexistent_session(self, fresh_state):
        _setup_initialized_state(fresh_state)
        client = TestClient(app)
        resp = client.post("/chat", json={"message": "hi", "session_id": "sess_nonexistent"})
        assert resp.status_code == 404

    def test_chat_without_router_uses_agent(self, fresh_state):
        state = _setup_initialized_state(fresh_state)
        state.channel_router = None
        # Mock agent.chat to avoid LLM call
        state.agent.chat = MagicMock(return_value="直接回复")
        client = TestClient(app)
        resp = client.post("/chat", json={"message": "hello"})
        assert resp.status_code == 200
        assert resp.json()["response"] == "直接回复"

    def test_chat_rate_limit_error(self, fresh_state):
        state = _setup_initialized_state(fresh_state)
        from clawhermes.agent.exceptions import LLMRateLimitError
        state.channel_router.route_message = AsyncMock(
            side_effect=LLMRateLimitError("rl", retry_after=30)
        )
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/chat", json={"message": "hi"})
        assert resp.status_code == 429

    def test_chat_connection_error(self, fresh_state):
        state = _setup_initialized_state(fresh_state)
        from clawhermes.agent.exceptions import LLMConnectionError
        state.channel_router.route_message = AsyncMock(
            side_effect=LLMConnectionError("conn")
        )
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/chat", json={"message": "hi"})
        assert resp.status_code == 502

    def test_chat_llm_error(self, fresh_state):
        state = _setup_initialized_state(fresh_state)
        from clawhermes.agent.exceptions import LLMError
        state.channel_router.route_message = AsyncMock(side_effect=LLMError("fail"))
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/chat", json={"message": "hi"})
        assert resp.status_code == 500

    def test_chat_clawhermes_error(self, fresh_state):
        state = _setup_initialized_state(fresh_state)
        from clawhermes.agent.exceptions import ClawHermesError
        state.channel_router.route_message = AsyncMock(
            side_effect=ClawHermesError("agent err")
        )
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/chat", json={"message": "hi"})
        assert resp.status_code == 500

    def test_chat_generic_error(self, fresh_state):
        state = _setup_initialized_state(fresh_state)
        state.channel_router.route_message = AsyncMock(
            side_effect=RuntimeError("unexpected")
        )
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/chat", json={"message": "hi"})
        assert resp.status_code == 500

    def test_chat_request_schema(self):
        req = ChatRequest(message="hi")
        assert req.message == "hi"
        assert req.session_id is None

    def test_chat_response_schema(self):
        resp = ChatResponse(response="ok", session_id="s1", model="m")
        assert resp.response == "ok"
        assert resp.session_id == "s1"
        assert resp.model == "m"


# ============================================================
# /chat/stream 端点测试
# ============================================================

class TestChatStreamEndpoint:
    def test_stream_uninitialized(self, fresh_state):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/chat/stream", json={"message": "hi"})
        assert resp.status_code == 500

    def test_stream_no_session_mgr(self, fresh_state):
        _setup_initialized_state(fresh_state)
        fresh_state.session_mgr = None
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/chat/stream", json={"message": "hi"})
        assert resp.status_code == 500

    def test_stream_success(self, fresh_state):
        state = _setup_initialized_state(fresh_state)

        async def fake_stream(msg, session_id=""):
            yield {"event": "text", "data": "流式内容"}
            yield {"event": "done", "data": {}}

        state.agent.chat_stream = fake_stream
        client = TestClient(app)
        resp = client.post("/chat/stream", json={"message": "hi"})
        assert resp.status_code == 200
        body = resp.text
        assert "text" in body
        assert "流式内容" in body
        assert "done" in body

    def test_stream_with_nonexistent_session(self, fresh_state):
        _setup_initialized_state(fresh_state)
        client = TestClient(app)
        resp = client.post("/chat/stream", json={"message": "hi", "session_id": "nope"})
        assert resp.status_code == 404

    def test_stream_error_events(self, fresh_state):
        state = _setup_initialized_state(fresh_state)
        from clawhermes.agent.exceptions import LLMError

        async def fake_stream(msg, session_id=""):
            raise LLMError("stream fail")
            yield  # noqa: F841

        state.agent.chat_stream = fake_stream
        client = TestClient(app)
        resp = client.post("/chat/stream", json={"message": "hi"})
        assert resp.status_code == 200
        assert "error" in resp.text
        assert "LLM 调用失败" in resp.text

    def test_stream_rate_limit_error(self, fresh_state):
        state = _setup_initialized_state(fresh_state)
        from clawhermes.agent.exceptions import LLMRateLimitError

        async def fake_stream(msg, session_id=""):
            raise LLMRateLimitError("rl", retry_after=30)
            yield  # noqa: F841

        state.agent.chat_stream = fake_stream
        client = TestClient(app)
        resp = client.post("/chat/stream", json={"message": "hi"})
        assert resp.status_code == 200
        assert "速率限制" in resp.text

    def test_stream_generic_error(self, fresh_state):
        state = _setup_initialized_state(fresh_state)

        async def fake_stream(msg, session_id=""):
            raise RuntimeError("oops")
            yield  # noqa: F841

        state.agent.chat_stream = fake_stream
        client = TestClient(app)
        resp = client.post("/chat/stream", json={"message": "hi"})
        assert resp.status_code == 200
        assert "内部错误" in resp.text

    def test_stream_non_str_data(self, fresh_state):
        state = _setup_initialized_state(fresh_state)

        async def fake_stream(msg, session_id=""):
            yield {"event": "tool_call", "data": {"name": "get_time"}}
            yield {"event": "done", "data": {}}

        state.agent.chat_stream = fake_stream
        client = TestClient(app)
        resp = client.post("/chat/stream", json={"message": "几点了"})
        assert resp.status_code == 200
        assert "get_time" in resp.text


# ============================================================
# 网关密钥中间件测试
# ============================================================

class TestGatewaySecretMiddleware:
    def test_no_secret_allows_all(self, fresh_state):
        with patch("clawhermes.gateway.app._gateway_secret", ""):
            client = TestClient(app)
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_secret_blocks_without_header(self, fresh_state):
        with patch("clawhermes.gateway.app._gateway_secret", "my-secret"):
            client = TestClient(app)
            resp = client.get("/health")
            # /health is exempted
            assert resp.status_code == 200

            resp2 = client.get("/tools")
            assert resp2.status_code == 401

    def test_secret_blocks_wrong_header(self, fresh_state):
        with patch("clawhermes.gateway.app._gateway_secret", "my-secret"):
            client = TestClient(app)
            resp = client.get("/tools", headers={"X-Gateway-Secret": "wrong"})
            assert resp.status_code == 401

    def test_secret_allows_with_correct_header(self, fresh_state):
        _setup_initialized_state(fresh_state)
        with patch("clawhermes.gateway.app._gateway_secret", "my-secret"):
            client = TestClient(app)
            resp = client.get("/tools", headers={"X-Gateway-Secret": "my-secret"})
            assert resp.status_code == 200

    def test_health_exempt_from_secret(self, fresh_state):
        with patch("clawhermes.gateway.app._gateway_secret", "my-secret"):
            client = TestClient(app)
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"


# ============================================================
# _auto_init 测试
# ============================================================

class TestAutoInit:
    @pytest.mark.asyncio
    async def test_auto_init_skips_when_already_initialized(self, fresh_state):
        fresh_state.agent = MagicMock()
        # Should not call initialize
        with patch.object(GatewayState, "initialize", AsyncMock()) as mock_init:
            await gw._auto_init()
        mock_init.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_init_no_api_key(self, fresh_state, monkeypatch):
        monkeypatch.delenv("CH_GW_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        with patch.object(GatewayState, "initialize", AsyncMock()) as mock_init:
            await gw._auto_init()
        mock_init.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_init_with_api_key(self, fresh_state, monkeypatch):
        monkeypatch.setenv("CH_GW_API_KEY", "gw-key")
        with patch.object(GatewayState, "initialize", AsyncMock()) as mock_init:
            await gw._auto_init()
        mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_init_clawhermes_error(self, fresh_state, monkeypatch):
        monkeypatch.setenv("CH_GW_API_KEY", "gw-key")
        from clawhermes.agent.exceptions import ClawHermesError
        with patch.object(GatewayState, "initialize", AsyncMock(side_effect=ClawHermesError("e"))):
            # Should not raise
            await gw._auto_init()

    @pytest.mark.asyncio
    async def test_auto_init_generic_error(self, fresh_state, monkeypatch):
        monkeypatch.setenv("CH_GW_API_KEY", "gw-key")
        with patch.object(GatewayState, "initialize", AsyncMock(side_effect=RuntimeError("e"))):
            # Should not raise
            await gw._auto_init()


# ============================================================
# Session 端点测试
# ============================================================

class TestSessionEndpoints:
    def test_get_session_uninitialized(self, fresh_state):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/sessions/xyz")
        assert resp.status_code == 500

    def test_get_session_not_found(self, fresh_state):
        _setup_initialized_state(fresh_state)
        client = TestClient(app)
        resp = client.get("/sessions/nonexistent")
        assert resp.status_code == 404

    def test_get_session_success(self, fresh_state):
        state = _setup_initialized_state(fresh_state)
        sid = state.session_mgr.create_session()
        state.session_mgr.add_message(sid, "user", "hi")
        client = TestClient(app)
        resp = client.get(f"/sessions/{sid}")
        assert resp.status_code == 200
        data = resp.json()
        assert "session" in data
        assert "messages" in data

    def test_delete_session_uninitialized(self, fresh_state):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.delete("/sessions/xyz")
        assert resp.status_code == 500

    def test_delete_session_not_found(self, fresh_state):
        _setup_initialized_state(fresh_state)
        client = TestClient(app)
        resp = client.delete("/sessions/nonexistent")
        assert resp.status_code == 404

    def test_delete_session_success(self, fresh_state):
        state = _setup_initialized_state(fresh_state)
        sid = state.session_mgr.create_session()
        client = TestClient(app)
        resp = client.delete(f"/sessions/{sid}")
        assert resp.status_code == 200

    def test_list_sessions_uninitialized(self, fresh_state):
        client = TestClient(app)
        resp = client.get("/sessions")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


# ============================================================
# Health 端点测试
# ============================================================

class TestHealthEndpoint:
    def test_health_uninitialized(self, fresh_state):
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["initialized"] is False
        assert "uptime" in data

    def test_health_initialized(self, fresh_state):
        _setup_initialized_state(fresh_state)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["initialized"] is True
        assert "model" in data
        assert "tools" in data
        assert "cron_jobs" in data


# ============================================================
# Memory 端点测试
# ============================================================

class TestMemoryEndpoints:
    def test_save_invalid_scope_falls_back_to_user(self, fresh_state):
        _setup_initialized_state(fresh_state)
        client = TestClient(app)
        resp = client.post("/memory/save?content=test&scope=invalid_scope")
        assert resp.status_code == 200

    def test_save_with_valid_scope(self, fresh_state):
        _setup_initialized_state(fresh_state)
        client = TestClient(app)
        resp = client.post("/memory/save?content=data&scope=agent")
        assert resp.status_code == 200

    def test_search_uninitialized(self, fresh_state):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/memory/search?query=test")
        assert resp.status_code == 500


# ============================================================
# Webhook 端点测试
# ============================================================

class TestWebhookEndpoints:
    def test_wechat_webhook_no_adapter(self, fresh_state):
        fresh_state.wechat_adapter = None
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/wechat/webhook", json={})
        assert resp.status_code == 501

    def test_wechat_webhook_with_adapter(self, fresh_state):
        fresh_state.wechat_adapter = MagicMock()
        fresh_state.wechat_adapter.handle_webhook = AsyncMock(return_value={"ok": True})
        client = TestClient(app)
        resp = client.post("/wechat/webhook", json={"msg": "hi"})
        assert resp.status_code == 200

    def test_wecom_webhook_no_adapter(self, fresh_state):
        fresh_state.wecom_adapter = None
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/wecom/webhook", json={})
        assert resp.status_code == 501

    def test_wecom_webhook_with_adapter(self, fresh_state):
        fresh_state.wecom_adapter = MagicMock()
        fresh_state.wecom_adapter.handle_webhook = AsyncMock(return_value={"ok": True})
        client = TestClient(app)
        resp = client.post("/wecom/webhook", json={})
        assert resp.status_code == 200

    def test_feishu_webhook_no_adapter(self, fresh_state):
        fresh_state.feishu_adapter = None
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/feishu/webhook", json={})
        assert resp.status_code == 503

    def test_feishu_webhook_with_adapter(self, fresh_state):
        fresh_state.feishu_adapter = MagicMock()
        fresh_state.feishu_adapter.handle_webhook = AsyncMock(return_value={"ok": True})
        client = TestClient(app)
        resp = client.post("/feishu/webhook", json={})
        assert resp.status_code == 200

    def test_qq_webhook_no_adapter(self, fresh_state):
        fresh_state.qq_adapter = None
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/qq/webhook", json={})
        assert resp.status_code == 503

    def test_qq_webhook_with_adapter(self, fresh_state):
        fresh_state.qq_adapter = MagicMock()
        fresh_state.qq_adapter.handle_webhook = AsyncMock(return_value={"ok": True})
        client = TestClient(app)
        resp = client.post("/qq/webhook", json={})
        assert resp.status_code == 200


# ============================================================
# DM 配对端点测试
# ============================================================

class TestDMPairingEndpoints:
    def test_generate_no_admin_key(self, fresh_state, monkeypatch):
        monkeypatch.delenv("ADMIN_KEY", raising=False)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/dm/pair/generate?user_id=u1&platform=feishu")
        assert resp.status_code == 501

    def test_generate_wrong_admin_key(self, fresh_state, monkeypatch):
        monkeypatch.setenv("ADMIN_KEY", "correct")
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/dm/pair/generate?user_id=u1&platform=feishu&admin_key=wrong")
        assert resp.status_code == 403

    def test_generate_no_pairing_manager(self, fresh_state, monkeypatch):
        monkeypatch.setenv("ADMIN_KEY", "correct")
        fresh_state.pairing_manager = None
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/dm/pair/generate?user_id=u1&platform=feishu&admin_key=correct")
        assert resp.status_code == 500

    def test_generate_success(self, fresh_state, monkeypatch):
        monkeypatch.setenv("ADMIN_KEY", "correct")
        import time
        mock_req = MagicMock()
        mock_req.code = "PAIR123"
        mock_req.challenge = "chal"
        mock_req.user_id = "u1"
        mock_req.platform = "feishu"
        mock_req.expires_at = time.time() + 300
        fresh_state.pairing_manager = MagicMock()
        fresh_state.pairing_manager.generate_code = MagicMock(return_value=mock_req)
        client = TestClient(app)
        resp = client.post("/dm/pair/generate?user_id=u1&platform=feishu&admin_key=correct")
        assert resp.status_code == 200
        assert resp.json()["code"] == "PAIR123"

    def test_verify_no_pairing_manager(self, fresh_state):
        fresh_state.pairing_manager = None
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/dm/pair/verify?code=c&response=r&user_id=u1")
        assert resp.status_code == 500

    def test_status_no_pairing_manager(self, fresh_state):
        fresh_state.pairing_manager = None
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/dm/pair/status?user_id=u1")
        assert resp.status_code == 500

    def test_status_not_found(self, fresh_state):
        fresh_state.pairing_manager = MagicMock()
        fresh_state.pairing_manager.get_pairing_status = MagicMock(return_value=None)
        client = TestClient(app)
        resp = client.get("/dm/pair/status?user_id=ghost")
        assert resp.status_code == 404

    def test_list_no_admin_key(self, fresh_state, monkeypatch):
        monkeypatch.delenv("ADMIN_KEY", raising=False)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/dm/pair/list")
        assert resp.status_code == 501

    def test_list_success(self, fresh_state, monkeypatch):
        monkeypatch.setenv("ADMIN_KEY", "k")
        fresh_state.pairing_manager = MagicMock()
        fresh_state.pairing_manager.list_paired_users = MagicMock(return_value=[])
        fresh_state.pairing_manager.list_pending_requests = MagicMock(return_value=[])
        client = TestClient(app)
        resp = client.get("/dm/pair/list?admin_key=k")
        assert resp.status_code == 200
        assert "paired" in resp.json()

    def test_revoke_no_admin_key(self, fresh_state, monkeypatch):
        monkeypatch.delenv("ADMIN_KEY", raising=False)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.delete("/dm/pair/u1")
        assert resp.status_code == 501

    def test_revoke_not_found(self, fresh_state, monkeypatch):
        monkeypatch.setenv("ADMIN_KEY", "k")
        fresh_state.pairing_manager = MagicMock()
        fresh_state.pairing_manager.revoke_pairing = MagicMock(return_value=False)
        client = TestClient(app)
        resp = client.delete("/dm/pair/u1?admin_key=k")
        assert resp.status_code == 404

    def test_revoke_success(self, fresh_state, monkeypatch):
        monkeypatch.setenv("ADMIN_KEY", "k")
        fresh_state.pairing_manager = MagicMock()
        fresh_state.pairing_manager.revoke_pairing = MagicMock(return_value=True)
        client = TestClient(app)
        resp = client.delete("/dm/pair/u1?admin_key=k")
        assert resp.status_code == 200


# ============================================================
# MCP 端点测试
# ============================================================

class TestMCPEndpoints:
    def test_list_empty(self, fresh_state):
        client = TestClient(app)
        resp = client.get("/mcp/servers")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_add_without_init(self, fresh_state):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/mcp/servers", json={"name": "test", "transport": "stdio", "command": "echo"})
        assert resp.status_code == 400

    def test_add_with_init(self, fresh_state):
        _setup_initialized_state(fresh_state)
        mock_registry = MagicMock()
        mock_registry.add_server = AsyncMock(return_value=["tool1", "tool2"])
        fresh_state._mcp_registry = mock_registry
        client = TestClient(app)
        resp = client.post("/mcp/servers", json={"name": "s1", "transport": "stdio", "command": "echo"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    def test_add_error(self, fresh_state):
        _setup_initialized_state(fresh_state)
        mock_registry = MagicMock()
        mock_registry.add_server = AsyncMock(side_effect=RuntimeError("conn fail"))
        fresh_state._mcp_registry = mock_registry
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/mcp/servers", json={"name": "s1", "transport": "stdio", "command": "echo"})
        assert resp.status_code == 500

    def test_list_with_registry(self, fresh_state):
        fresh_state._mcp_registry = MagicMock()
        fresh_state._mcp_registry.list_servers = MagicMock(return_value=[{"name": "s1"}])
        client = TestClient(app)
        resp = client.get("/mcp/servers")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_remove_no_registry(self, fresh_state):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.delete("/mcp/servers/ghost")
        assert resp.status_code == 404

    def test_remove_not_found(self, fresh_state):
        fresh_state._mcp_registry = MagicMock()
        fresh_state._mcp_registry.remove_server = AsyncMock(return_value=False)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.delete("/mcp/servers/ghost")
        assert resp.status_code == 404

    def test_remove_success(self, fresh_state):
        fresh_state._mcp_registry = MagicMock()
        fresh_state._mcp_registry.remove_server = AsyncMock(return_value=True)
        client = TestClient(app)
        resp = client.delete("/mcp/servers/s1")
        assert resp.status_code == 200

    def test_mcp_add_request_schema(self):
        req = MCPAddRequest(name="test", transport="http", url="http://localhost")
        assert req.name == "test"
        assert req.transport == "http"
        assert req.url == "http://localhost"
        assert req.args == []


# ============================================================
# Cron Job 端点测试（补充）
# ============================================================

class TestCronJobEndpoints:
    def test_create_cron_mode(self, fresh_state):
        _setup_initialized_state(fresh_state)
        client = TestClient(app)
        resp = client.post("/cron/jobs", json={
            "name": "cron-job", "task": "task",
            "mode": "cron", "minute": "0", "hour": "*",
        })
        assert resp.status_code == 200

    def test_create_oneshot_mode(self, fresh_state):
        _setup_initialized_state(fresh_state)
        client = TestClient(app)
        resp = client.post("/cron/jobs", json={
            "name": "oneshot-job", "task": "task",
            "mode": "oneshot", "delay_seconds": 10,
        })
        assert resp.status_code == 200

    def test_create_invalid_mode(self, fresh_state):
        _setup_initialized_state(fresh_state)
        client = TestClient(app)
        resp = client.post("/cron/jobs", json={
            "name": "bad", "task": "task", "mode": "invalid",
        })
        assert resp.status_code == 400

    def test_list_no_scheduler(self, fresh_state):
        fresh_state.scheduler = None
        client = TestClient(app)
        resp = client.get("/cron/jobs")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_get_no_scheduler(self, fresh_state):
        fresh_state.scheduler = None
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/cron/jobs/xyz")
        assert resp.status_code == 500

    def test_delete_no_scheduler(self, fresh_state):
        fresh_state.scheduler = None
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.delete("/cron/jobs/xyz")
        assert resp.status_code == 500

    def test_pause_no_scheduler(self, fresh_state):
        fresh_state.scheduler = None
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/cron/jobs/xyz/pause")
        assert resp.status_code == 500

    def test_resume_no_scheduler(self, fresh_state):
        fresh_state.scheduler = None
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/cron/jobs/xyz/resume")
        assert resp.status_code == 500

    def test_cron_job_request_schema(self):
        req = CronJobRequest(name="n", task="t")
        assert req.mode == "interval"
        assert req.interval_seconds == 3600


# ============================================================
# Channels 端点测试
# ============================================================

class TestChannelsEndpoints:
    def test_list_no_router(self, fresh_state):
        fresh_state.channel_router = None
        client = TestClient(app)
        resp = client.get("/channels")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_list_sessions_no_router(self, fresh_state):
        fresh_state.channel_router = None
        client = TestClient(app)
        resp = client.get("/channels/sessions")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


# ============================================================
# GatewayState.initialize 集成测试
# ============================================================

class TestGatewayStateInitialize:
    @pytest.mark.asyncio
    async def test_initialize_success(self, fresh_state, monkeypatch):
        """测试 initialize 完整流程（mock 重依赖）"""
        monkeypatch.setenv("CH_DATA_DIR", tempfile.mkdtemp())

        # Mock build_adapter_config 返回空配置（跳过 feishu/wechat/qq adapter 创建）
        with patch("clawhermes.gateway.app.build_adapter_config", return_value={}), \
                patch("clawhermes.gateway.app.CronScheduler") as mock_scheduler_cls, \
                patch("clawhermes.gateway.app.ChannelRouter") as mock_router_cls:
            mock_sched = MagicMock()
            mock_sched.start = AsyncMock()
            mock_sched.stop = AsyncMock()
            mock_sched.job_count = 0
            mock_scheduler_cls.return_value = mock_sched

            mock_router = MagicMock()
            mock_router.start = AsyncMock()
            mock_router.stop = AsyncMock()
            mock_router.get_queue_size = MagicMock(return_value=0)
            mock_router.get_active_session = MagicMock(return_value=None)
            mock_router.list_channels = MagicMock(return_value=[])
            mock_router.session_router = MagicMock()
            mock_router.session_router.list_mappings = MagicMock(return_value=[])
            mock_router_cls.return_value = mock_router

            await fresh_state.initialize(
                api_key="test-key",
                model="test/model",
                profile="minimal",
            )

        assert fresh_state.agent is not None
        assert fresh_state.memory is not None
        assert fresh_state.session_mgr is not None
        assert fresh_state.is_initialized() is True

        # 清理后台任务
        await fresh_state.shutdown()

    @pytest.mark.asyncio
    async def test_initialize_chroma_unavailable(self, fresh_state, monkeypatch):
        """ChromaDB 不可用时走 except 分支"""
        monkeypatch.setenv("CH_DATA_DIR", tempfile.mkdtemp())

        with patch("clawhermes.gateway.app.build_adapter_config", return_value={}), \
                patch("clawhermes.gateway.app.CronScheduler") as mock_scheduler_cls, \
                patch("clawhermes.gateway.app.ChannelRouter") as mock_router_cls, \
                patch("clawhermes.storage.chroma_memory.ChromaMemoryProvider",
                      side_effect=ImportError("no chroma")):
            mock_sched = MagicMock()
            mock_sched.start = AsyncMock()
            mock_sched.stop = AsyncMock()
            mock_sched.job_count = 0
            mock_scheduler_cls.return_value = mock_sched

            mock_router = MagicMock()
            mock_router.start = AsyncMock()
            mock_router.stop = AsyncMock()
            mock_router.get_queue_size = MagicMock(return_value=0)
            mock_router.get_active_session = MagicMock(return_value=None)
            mock_router.list_channels = MagicMock(return_value=[])
            mock_router.session_router = MagicMock()
            mock_router.session_router.list_mappings = MagicMock(return_value=[])
            mock_router_cls.return_value = mock_router

            await fresh_state.initialize(
                api_key="test-key",
                model="test/model",
                profile="minimal",
            )

        assert fresh_state.is_initialized() is True
        await fresh_state.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown(self, fresh_state):
        """测试 shutdown 清理"""
        fresh_state.scheduler = MagicMock()
        fresh_state.scheduler.stop = AsyncMock()
        fresh_state.channel_router = MagicMock()
        fresh_state.channel_router.stop = AsyncMock()
        await fresh_state.shutdown()
        fresh_state.scheduler.stop.assert_called_once()
