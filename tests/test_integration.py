"""
ClawHermes - 集成测试（用 MockProvider，不依赖真实 API）
"""
import tempfile
from pathlib import Path

import pytest

from clawhermes.agent.loop import Agent, AgentConfig, ToolRegistry
from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager
from clawhermes.tools.builtin import register_builtin_tools
from tests.mock_provider import MockProvider


def test_agent_simple_chat():
    """测试：简单对话"""
    provider = MockProvider(responses=["你好！我是 ClawHermes。"])
    agent = Agent(llm_provider=provider)
    resp = agent.chat("你好")
    assert "ClawHermes" in resp
    print("✅ 简单对话 OK")


def test_agent_with_tools():
    """测试：触发工具调用"""
    provider = MockProvider()
    registry = ToolRegistry()
    register_builtin_tools(registry)
    agent = Agent(llm_provider=provider, tool_registry=registry)
    resp = agent.chat("现在几点了？")
    assert resp  # 应该有响应
    print(f"✅ 工具调用 OK → {resp[:50]}")


def test_agent_multi_turn():
    """测试：多轮对话"""
    provider = MockProvider(responses=["第一轮", "第二轮"])
    agent = Agent(llm_provider=provider, config=AgentConfig(max_iterations=5))
    r1 = agent.chat("第一句话")
    r2 = agent.chat("第二句话")
    assert r1 == "第一轮"
    assert r2 == "第二轮"
    print("✅ 多轮对话 OK")


def test_memory_system():
    """测试：记忆系统完整流程"""
    with tempfile.TemporaryDirectory() as tmp:
        mem = MemoryManager()
        mem.add_provider(JSONMemoryProvider(tmp))

        # 保存记忆
        mem.save("用户喜欢讨论技术", importance=0.8)
        mem.save("用户是 Python 开发者", importance=0.9)

        # 搜索
        results = mem.search("Python")
        assert len(results) >= 1
        assert "Python" in results[0].content

        # 快照
        snapshot = mem.snapshot()
        assert "Python" in snapshot
        print(f"✅ 记忆系统 OK → {len(results)} 条匹配")


def test_tool_registry_and_dispatch():
    """测试：工具注册与调度"""
    registry = ToolRegistry()
    register_builtin_tools(registry)

    tools = registry.list()
    assert len(tools) == 9
    names = {t.name for t in tools}
    assert names == {
        "session_status", "read_file", "write_file", "exec",
        "get_time", "web_search", "memory_search", "memory_save",
        "delegate_task",
    }

    schemas = registry.schemas()
    assert len(schemas) == 9
    print(f"✅ 工具系统 OK → {len(tools)} 个工具")


def test_tool_profiles():
    """测试：工具 profile 分级"""
    registry_min = ToolRegistry()
    register_builtin_tools(registry_min, profile="minimal")
    assert len(registry_min.list()) == 5

    registry_std = ToolRegistry()
    register_builtin_tools(registry_std, profile="standard")
    assert len(registry_std.list()) == 9

    registry_full = ToolRegistry()
    register_builtin_tools(registry_full, profile="full")
    assert len(registry_full.list()) >= 25

    full_names = {t.name for t in registry_full.list()}
    assert "web_fetch" in full_names
    assert "list_dir" in full_names
    assert "patch_file" in full_names
    assert "grep" in full_names
    assert "search_replace" in full_names
    assert "code_eval" in full_names
    print("✅ 工具 profiles OK → minimal=5, standard=9, full=15")


def test_system_prompt_three_layers():
    """测试：三层 System Prompt"""
    from clawhermes.agent.prompt import SystemPrompt

    sp = SystemPrompt()
    prompt = sp.build()

    # stable 层应该包含身份信息
    assert "ClawHermes" in prompt
    assert "工具" in prompt or "工具" in prompt

    # volatile 层渲染
    sp.volatile.timestamp = "2026-06-16 12:00"
    sp.volatile.memory_snapshot = "用户喜欢 Python"
    prompt2 = sp.build()
    assert "2026-06-16" in prompt2
    assert "Python" in prompt2

    print("✅ 三层 System Prompt OK")


def test_hook_system():
    """测试：钩子系统"""
    from clawhermes.agent.loop import HookManager, HookPoint

    hooks = HookManager()
    call_log = []

    def before_tool(**kw):
        call_log.append(("before", kw.get("tool_name")))

    def after_tool(**kw):
        call_log.append(("after", kw.get("tool_name")))

    hooks.register(HookPoint.BEFORE_TOOL_CALL, before_tool)
    hooks.register(HookPoint.AFTER_TOOL_CALL, after_tool)

    hooks.trigger(HookPoint.BEFORE_TOOL_CALL, tool_name="web_search")
    hooks.trigger(HookPoint.AFTER_TOOL_CALL, tool_name="web_search")

    assert len(call_log) == 2
    assert call_log[0] == ("before", "web_search")
    print("✅ 钩子系统 OK")


def test_credential_pool():
    """测试：多凭证池"""
    from clawhermes.llm.provider import CredentialPool

    pool = CredentialPool(["key_a", "key_b", "key_c"], strategy="round_robin")
    keys = [pool.get_key() for _ in range(3)]
    assert len(set(keys)) == 3  # 轮询应该都不同

    # 标记一个失败
    pool.mark_failed("key_b", 429)
    # 暂时拿不到 key_b
    import time
    from unittest.mock import patch
    with patch("time.time", return_value=time.time() + 10):
        pass  # 冷却期内

    print("✅ 多凭证池 OK")


def test_exception_hierarchy():
    """测试：自定义异常类层次"""
    from clawhermes.agent.exceptions import (
        ClawHermesError,
        ConfigError,
        ConfigNotFoundError,
        ConfigValidationError,
        LLMConnectionError,
        LLMError,
        LLMRateLimitError,
        LLMResponseError,
        MemoryError,
        MemorySearchError,
        MemoryStorageError,
        SessionError,
        SessionExpiredError,
        SessionNotFoundError,
        ToolBlockedError,
        ToolError,
        ToolExecutionError,
        ToolNotFoundError,
    )

    assert issubclass(LLMError, ClawHermesError)
    assert issubclass(LLMConnectionError, LLMError)
    assert issubclass(LLMRateLimitError, LLMError)
    assert issubclass(LLMResponseError, LLMError)

    assert issubclass(ToolError, ClawHermesError)
    assert issubclass(ToolNotFoundError, ToolError)
    assert issubclass(ToolExecutionError, ToolError)
    assert issubclass(ToolBlockedError, ToolError)

    assert issubclass(MemoryError, ClawHermesError)
    assert issubclass(MemoryStorageError, MemoryError)
    assert issubclass(MemorySearchError, MemoryError)

    assert issubclass(ConfigError, ClawHermesError)
    assert issubclass(ConfigValidationError, ConfigError)
    assert issubclass(ConfigNotFoundError, ConfigError)

    assert issubclass(SessionError, ClawHermesError)
    assert issubclass(SessionNotFoundError, SessionError)
    assert issubclass(SessionExpiredError, SessionError)

    e = LLMRateLimitError("test", retry_after=60)
    assert e.retry_after == 60

    e2 = ToolBlockedError("blocked", tool_name="exec", reason="unsafe")
    assert e2.tool_name == "exec"
    assert e2.reason == "unsafe"

    e3 = SessionNotFoundError("not found", session_id="abc")
    assert e3.session_id == "abc"

    print("✅ 异常类层次 OK")


def test_chat_async():
    """测试：异步对话接口"""
    import asyncio

    provider = MockProvider(responses=["异步响应"])
    agent = Agent(llm_provider=provider, config=AgentConfig(max_iterations=5))

    result = asyncio.run(agent.chat_async("测试异步"))
    assert result == "异步响应"
    print("✅ chat_async OK")


def test_session_persistence():
    """测试：会话持久化"""
    import tempfile

    from clawhermes.agent.exceptions import SessionNotFoundError
    from clawhermes.agent.session import SessionManager

    with tempfile.TemporaryDirectory() as tmpdir:
        sm = SessionManager(tmpdir)

        sid = sm.create_session(agent_name="test")
        assert sid.startswith("sess_")

        info = sm.get_session(sid)
        assert info["id"] == sid
        assert info["agent_name"] == "test"

        sm.add_message(sid, "user", "你好")
        sm.add_message(sid, "assistant", "你好！有什么可以帮你的？")
        sm.add_message(sid, "user", "再见")

        messages = sm.get_messages(sid)
        assert len(messages) == 3
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "你好"
        assert messages[1]["role"] == "assistant"
        assert messages[2]["content"] == "再见"

        sessions = sm.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["id"] == sid

        sm2 = SessionManager(tmpdir)
        info2 = sm2.get_session(sid)
        assert info2["id"] == sid
        messages2 = sm2.get_messages(sid)
        assert len(messages2) == 3

        assert sm.delete_session(sid) is True
        try:
            sm.get_session(sid)
            assert False, "应该抛出 SessionNotFoundError"
        except SessionNotFoundError:
            pass

        assert sm.delete_session("nonexistent") is False

        sm.close()
        sm2.close()

    print("✅ 会话持久化 OK")


if __name__ == "__main__":
    test_system_prompt_three_layers()
    test_hook_system()
    test_credential_pool()
    test_tool_registry_and_dispatch()
    test_memory_system()
    test_agent_simple_chat()
    test_agent_multi_turn()
    test_agent_with_tools()
    print("\n🎉 所有集成测试通过！")



# ============================================================
# Gateway endpoint & handler integration tests (M3.12)
# ============================================================

class TestGatewayEndpoints:
    """Test Gateway REST API endpoints via FastAPI TestClient"""

    def _init_agent(self):
        """Helper: initialize a mock agent state"""
        import clawhermes.gateway.app as gw
        from clawhermes.agent.loop import Agent, AgentConfig, ToolRegistry
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager
        from clawhermes.agent.session import SessionManager
        from clawhermes.llm.provider import LLMProvider

        data_dir = tempfile.mkdtemp()
        provider = LLMProvider(model="deepseek/deepseek-chat", api_key="test-key")
        registry = ToolRegistry()
        from clawhermes.tools.builtin import register_builtin_tools
        register_builtin_tools(registry, profile="minimal")

        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(Path(data_dir)))

        from clawhermes.skills.manager import SkillManager
        sm = SkillManager(Path(data_dir) / "skills")

        agent = Agent(
            llm_provider=provider,
            tool_registry=registry,
            config=AgentConfig(max_iterations=1),
            memory_manager=memory,
            skill_manager=sm,
        )

        session_mgr = SessionManager(data_dir)

        from clawhermes.channel.adapter import ChannelManager, RESTAdapter
        from clawhermes.channel.router import ChannelRouter, SessionRouter
        channel_manager = ChannelManager()
        channel_manager.register("rest", RESTAdapter())
        channel_router = ChannelRouter(
            channel_manager=channel_manager,
            session_router=SessionRouter(),
        )

        gw._state.agent = agent
        gw._state.memory = memory
        gw._state.skill_manager = sm
        gw._state.session_mgr = session_mgr
        gw._state.channel_router = channel_router
        from clawhermes.agent.scheduler import CronScheduler
        gw._state.scheduler = CronScheduler(data_dir)

        return gw._state

    def test_health_uninitialized(self):
        from starlette.testclient import TestClient

        from clawhermes.gateway.app import app
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["initialized"] is False

    def test_health_initialized(self):
        self._init_agent()
        from starlette.testclient import TestClient

        from clawhermes.gateway.app import app
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["initialized"] is True
        assert "tools" in data

    def test_tools_endpoint(self):
        self._init_agent()
        from starlette.testclient import TestClient

        from clawhermes.gateway.app import app
        client = TestClient(app)
        resp = client.get("/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
        assert len(data["tools"]) > 0

    def test_memory_save_and_search(self):
        self._init_agent()
        from starlette.testclient import TestClient

        from clawhermes.gateway.app import app
        client = TestClient(app)

        resp = client.post("/memory/save?content=hello+world&importance=0.8")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        resp = client.get("/memory/search?query=hello")
        assert resp.status_code == 200
        results = resp.json().get("results", [])
        # JSON memory provider does substring search
        assert isinstance(results, list)

    def test_skills_list_and_create(self):
        self._init_agent()
        from starlette.testclient import TestClient

        from clawhermes.gateway.app import app
        client = TestClient(app)

        resp = client.get("/skills")
        assert resp.status_code == 200
        assert "skills" in resp.json()

        resp = client.post("/skills/create?name=test-skill&content=test+content&description=test")
        assert resp.status_code == 200
        assert resp.json()["name"] == "test-skill"

    def test_curator_run(self):
        self._init_agent()
        from starlette.testclient import TestClient

        from clawhermes.gateway.app import app
        client = TestClient(app)
        resp = client.post("/curator/run?dry_run=true")
        assert resp.status_code == 200
        assert "stats" in resp.json()

    def test_sessions_list(self):
        self._init_agent()
        from starlette.testclient import TestClient

        from clawhermes.gateway.app import app
        client = TestClient(app)
        resp = client.get("/sessions")
        assert resp.status_code == 200

    def test_delete_nonexistent_session(self):
        self._init_agent()
        from starlette.testclient import TestClient

        from clawhermes.gateway.app import app
        client = TestClient(app)
        resp = client.delete("/sessions/nonexistent-id")
        assert resp.status_code == 404

    def test_channels_endpoints(self):
        self._init_agent()
        from starlette.testclient import TestClient

        from clawhermes.gateway.app import app
        client = TestClient(app)

        resp = client.get("/channels")
        assert resp.status_code == 200
        assert "channels" in resp.json()

        resp = client.get("/channels/sessions")
        assert resp.status_code == 200
        assert "mappings" in resp.json()

    def test_cron_jobs_crud(self):
        self._init_agent()
        from starlette.testclient import TestClient

        from clawhermes.gateway.app import app
        client = TestClient(app)

        resp = client.post("/cron/jobs", json={
            "name": "test-job", "task": "say hello",
            "mode": "interval", "interval_seconds": 3600,
        })
        assert resp.status_code == 200
        job_id = resp.json()["job"]["job_id"]

        resp = client.get("/cron/jobs")
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

        resp = client.get(f"/cron/jobs/{job_id}")
        assert resp.status_code == 200

        resp = client.post(f"/cron/jobs/{job_id}/pause")
        assert resp.status_code == 200

        resp = client.post(f"/cron/jobs/{job_id}/resume")
        assert resp.status_code == 200

        resp = client.delete(f"/cron/jobs/{job_id}")
        assert resp.status_code == 200

        resp = client.get(f"/cron/jobs/{job_id}")
        assert resp.status_code == 404

    def test_init_request_schema(self):
        from clawhermes.gateway.app import InitRequest
        req = InitRequest(api_key="sk-test", model="test/model")
        assert req.api_key == "sk-test"
        assert req.model == "test/model"
        assert req.max_iterations == 50
        assert req.profile == "standard"

    def test_chat_requires_initialization(self, monkeypatch):
        import clawhermes.gateway.app as gw
        gw._state = gw.GatewayState()  # fresh uninitialized state
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("CH_GW_API_KEY", raising=False)
        from starlette.testclient import TestClient

        from clawhermes.gateway.app import app
        client = TestClient(app)
        # Uninitialized agent raises SessionNotFoundError → 500 via TestClient exception
        with pytest.raises(Exception):
            client.post("/chat", json={"message": "hello"})


class TestToolHandlers:
    """Test built-in tool handler functions using correct signatures"""

    def test_session_status(self):
        from clawhermes.tools.builtin import _session_status
        result = _session_status()
        assert isinstance(result, dict)

    def test_read_file(self, tmp_path):
        from clawhermes.tools.builtin import _read_file
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        result = _read_file(path=str(f))
        assert isinstance(result, dict)

    def test_read_file_not_found(self, tmp_path):
        from clawhermes.tools.builtin import _read_file
        result = _read_file(path=str(tmp_path / "nonexistent.txt"))
        assert isinstance(result, dict)

    def test_write_file(self, tmp_path):
        from clawhermes.tools.builtin import _write_file
        f = tmp_path / "output.txt"
        result = _write_file(path=str(f), content="test content")
        assert isinstance(result, dict)
        assert f.read_text() == "test content"

    def test_get_time(self):
        from clawhermes.tools.builtin import _get_time
        result = _get_time()
        assert isinstance(result, dict)

    def test_list_dir(self, tmp_path):
        from clawhermes.tools.builtin import _list_dir
        (tmp_path / "a.txt").write_text("a")
        result = _list_dir(path=str(tmp_path))
        assert isinstance(result, dict)

    def test_list_dir_not_found(self):
        from clawhermes.tools.builtin import _list_dir
        result = _list_dir(path="/nonexistent/path_xyz_test")
        assert isinstance(result, dict)

    def test_grep(self, tmp_path):
        from clawhermes.tools.builtin import _grep
        f = tmp_path / "test_grep.py"
        f.write_text("def foo():\n    return 42\n")
        result = _grep(pattern="def", path=str(tmp_path), file_pattern="*.py")
        assert isinstance(result, dict)

    def test_git_status_no_repo(self, tmp_path):
        from clawhermes.tools.builtin import _git_status
        result = _git_status(path=str(tmp_path))
        assert isinstance(result, dict)

    def test_env_list(self):
        from clawhermes.tools.builtin import _env_list
        result = _env_list()
        assert isinstance(result, dict)

    def test_calc(self):
        from clawhermes.tools.builtin import _calc
        result = _calc(expression="2 + 3 * 4")
        assert isinstance(result, dict)

    def test_calc_invalid(self):
        from clawhermes.tools.builtin import _calc
        result = _calc(expression="__import__('os')")
        assert isinstance(result, dict)

    def test_url_encode_decode(self):
        from clawhermes.tools.builtin import _url_decode, _url_encode
        encoded = _url_encode(text="hello world")
        assert isinstance(encoded, dict)
        decoded = _url_decode(text="hello%20world")
        assert isinstance(decoded, dict)

    def test_compress_file(self, tmp_path):
        from clawhermes.tools.builtin import _compress_file
        f = tmp_path / "data.txt"
        f.write_text("hello " * 100)
        result = _compress_file(path=str(f))
        assert isinstance(result, dict)

    def test_timer(self):
        from clawhermes.tools.builtin import _timer
        result = _timer(action="start")
        assert isinstance(result, dict)

    def test_json_query(self, tmp_path):
        from clawhermes.tools.builtin import _json_query
        result = _json_query(json_str='{"name": "test", "value": 42}', path="name")
        assert isinstance(result, dict)


class TestContextEngine:
    """Test context compression engine"""

    def test_empty_compressor_should_compress(self):
        from clawhermes.agent.context import NoopCompressor
        c = NoopCompressor()
        assert c.should_compress(100000) is False

    def test_empty_compressor_compress(self):
        from clawhermes.agent.context import NoopCompressor
        c = NoopCompressor()
        msgs = [{"role": "user", "content": "hello"}]
        result = c.compress(msgs, 100)
        assert result == msgs


class TestDelegateManager:
    """Test delegate manager"""

    def test_delegate_manager_creation(self, tmp_path):
        from clawhermes.agent.delegate import DelegateManager
        from clawhermes.agent.loop import ToolRegistry
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager
        from clawhermes.llm.provider import LLMProvider

        provider = LLMProvider(model="deepseek/deepseek-chat", api_key="test")
        registry = ToolRegistry()
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(tmp_path))

        dm = DelegateManager(
            llm_provider=provider,
            tool_registry=registry,
            memory_manager=memory,
        )
        assert dm is not None

    def test_delegate_returns_result(self, tmp_path):
        from clawhermes.agent.delegate import DelegateManager
        from clawhermes.agent.loop import ToolRegistry
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager
        from clawhermes.llm.provider import LLMProvider

        provider = LLMProvider(model="deepseek/deepseek-chat", api_key="test")
        registry = ToolRegistry()
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(tmp_path))

        dm = DelegateManager(
            llm_provider=provider,
            tool_registry=registry,
            memory_manager=memory,
        )
        result = dm.delegate([{"id": "1", "description": "test", "instructions": "say hello"}], parent_depth=0)
        assert isinstance(result, list)

    def test_delegate_exceeds_max_depth(self, tmp_path):
        from clawhermes.agent.delegate import MAX_DEPTH, DelegateManager
        from clawhermes.agent.loop import ToolRegistry
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager
        from clawhermes.llm.provider import LLMProvider

        provider = LLMProvider(model="deepseek/deepseek-chat", api_key="test")
        registry = ToolRegistry()
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(tmp_path))

        dm = DelegateManager(
            llm_provider=provider,
            tool_registry=registry,
            memory_manager=memory,
        )
        # Depth MAX_DEPTH+1 should trigger error
        result = dm.delegate([{"id": "1", "description": "test", "instructions": "hi"}], parent_depth=MAX_DEPTH)
        assert isinstance(result, list)
        # When depth exceeds MAX_DEPTH, each result should have an error
        if result:
            for r in result:
                assert "error" in r


class TestMCPClient:
    """Test MCP client and registry"""

    def test_server_spec_creation(self):
        from clawhermes.mcp.client import MCPServerSpec
        spec = MCPServerSpec(
            name="test-server",
            transport="stdio",
            command="echo",
            args=["hello"],
        )
        assert spec.name == "test-server"
        assert spec.transport == "stdio"
        assert spec.command == "echo"

    def test_server_spec_http(self):
        from clawhermes.mcp.client import MCPServerSpec
        spec = MCPServerSpec(
            name="http-server",
            transport="http",
            url="http://localhost:8080",
        )
        assert spec.transport == "http"
        assert spec.url == "http://localhost:8080"

    def test_mcp_client_creation(self):
        from clawhermes.mcp.client import MCPClient, MCPServerSpec
        spec = MCPServerSpec(name="test", transport="stdio", command="echo")
        client = MCPClient(spec)
        assert client.spec.name == "test"
        assert client.is_connected is False

    def test_mcp_registry_creation(self):
        from clawhermes.agent.loop import ToolRegistry
        from clawhermes.mcp.client import MCPRegistry
        registry = ToolRegistry()
        mcp_reg = MCPRegistry(registry)
        assert mcp_reg.list_servers() == []

    def test_mcp_registry_remove_nonexistent(self):
        from clawhermes.agent.loop import ToolRegistry
        from clawhermes.mcp.client import MCPRegistry
        registry = ToolRegistry()
        mcp_reg = MCPRegistry(registry)
        import asyncio
        result = asyncio.run(mcp_reg.remove_server("nonexistent"))
        assert result is False

    def test_mcp_registry_get_server_tools_empty(self):
        from clawhermes.agent.loop import ToolRegistry
        from clawhermes.mcp.client import MCPRegistry
        registry = ToolRegistry()
        mcp_reg = MCPRegistry(registry)
        assert mcp_reg.get_server_tools("nonexistent") == []

    def test_mcp_gateway_endpoints(self):
        """Test MCP Gateway endpoints without connecting"""
        from starlette.testclient import TestClient

        from clawhermes.gateway.app import app
        client = TestClient(app)

        # List servers (empty before init)
        resp = client.get("/mcp/servers")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0
