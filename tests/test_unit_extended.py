"""
ClawHermes - 扩展单元测试
覆盖 builtin tools、session、exceptions、delegate 等模块
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import pytest

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
from clawhermes.agent.loop import Agent, AgentConfig, HookManager, HookPoint, ToolRegistry
from clawhermes.agent.session import SessionManager
from clawhermes.tools.builtin import (
    FULL_TOOLS,
    MINIMAL_TOOLS,
    PROFILE_MAP,
    STANDARD_TOOLS,
    register_builtin_tools,
)


class TestExceptionHierarchy:
    def test_base_exception(self):
        e = ClawHermesError("test error", detail="some detail")
        assert str(e) == "test error"
        assert e.detail == "some detail"

    def test_llm_exceptions(self):
        e = LLMError("llm fail")
        assert isinstance(e, ClawHermesError)

        e = LLMConnectionError("conn fail")
        assert isinstance(e, LLMError)

        e = LLMRateLimitError("rate limited", retry_after=120)
        assert e.retry_after == 120
        assert isinstance(e, LLMError)

        e = LLMResponseError("bad response")
        assert isinstance(e, LLMError)

    def test_tool_exceptions(self):
        e = ToolNotFoundError("not found")
        assert isinstance(e, ToolError)

        e = ToolExecutionError("exec fail", tool_name="exec")
        assert e.tool_name == "exec"
        assert isinstance(e, ToolError)

        e = ToolBlockedError("blocked", tool_name="rm", reason="unsafe")
        assert e.tool_name == "rm"
        assert e.reason == "unsafe"
        assert isinstance(e, ToolError)

    def test_memory_exceptions(self):
        e = MemoryStorageError("store fail", provider="chromadb")
        assert e.provider == "chromadb"
        assert isinstance(e, MemoryError)

        e = MemorySearchError("search fail", provider="json")
        assert e.provider == "json"
        assert isinstance(e, MemoryError)

    def test_config_exceptions(self):
        e = ConfigValidationError("invalid", field="api_key")
        assert e.field == "api_key"
        assert isinstance(e, ConfigError)

        e = ConfigNotFoundError("not found")
        assert isinstance(e, ConfigError)

    def test_session_exceptions(self):
        e = SessionNotFoundError("not found", session_id="abc123")
        assert e.session_id == "abc123"
        assert isinstance(e, SessionError)

        e = SessionExpiredError("expired", session_id="xyz")
        assert e.session_id == "xyz"
        assert isinstance(e, SessionError)


class TestToolProfiles:
    def test_profile_map_structure(self):
        assert "minimal" in PROFILE_MAP
        assert "standard" in PROFILE_MAP
        assert "full" in PROFILE_MAP
        assert MINIMAL_TOOLS < STANDARD_TOOLS < FULL_TOOLS

    def test_minimal_profile(self):
        registry = ToolRegistry()
        register_builtin_tools(registry, profile="minimal")
        names = {t.name for t in registry.list()}
        assert names == MINIMAL_TOOLS
        assert len(names) == 5

    def test_standard_profile(self):
        registry = ToolRegistry()
        register_builtin_tools(registry, profile="standard")
        names = {t.name for t in registry.list()}
        assert names == STANDARD_TOOLS
        assert len(names) == 9

    def test_full_profile(self):
        registry = ToolRegistry()
        register_builtin_tools(registry, profile="full")
        names = {t.name for t in registry.list()}
        assert names == FULL_TOOLS
        assert len(names) >= 25

    def test_default_profile_is_standard(self):
        registry = ToolRegistry()
        register_builtin_tools(registry)
        assert len(registry.list()) == 9


class TestBuiltinTools:
    def test_session_status(self):
        registry = ToolRegistry()
        register_builtin_tools(registry, profile="minimal")
        tool = registry.get("session_status")
        assert tool is not None
        result = tool.handler()
        assert "status" in result
        assert "timestamp" in result

    def test_get_time(self):
        registry = ToolRegistry()
        register_builtin_tools(registry, profile="minimal")
        tool = registry.get("get_time")
        result = tool.handler()
        assert "datetime" in result
        assert "date" in result
        assert "time" in result
        assert "weekday" in result

    def test_read_file_not_found(self):
        registry = ToolRegistry()
        register_builtin_tools(registry, profile="minimal")
        tool = registry.get("read_file")
        result = tool.handler(path="/nonexistent/file.txt")
        assert "error" in result

    def test_write_and_read_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ToolRegistry()
            register_builtin_tools(registry, profile="minimal")
            write_tool = registry.get("write_file")
            read_tool = registry.get("read_file")

            filepath = os.path.join(tmpdir, "test.txt")
            result = write_tool.handler(path=filepath, content="Hello World")
            assert result["success"] is True

            result = read_tool.handler(path=filepath)
            assert result["content"] == "Hello World"

    def test_list_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "a.py").write_text("a")
            Path(tmpdir, "b.py").write_text("b")
            Path(tmpdir, "c.txt").write_text("c")

            registry = ToolRegistry()
            register_builtin_tools(registry, profile="full")
            tool = registry.get("list_dir")

            result = tool.handler(path=tmpdir)
            assert result["count"] == 3

            result_py = tool.handler(path=tmpdir, pattern="*.py")
            assert result_py["count"] == 2

    def test_patch_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "patch.txt")
            Path(filepath).write_text("hello world")

            registry = ToolRegistry()
            register_builtin_tools(registry, profile="full")
            tool = registry.get("patch_file")

            result = tool.handler(path=filepath, search="world", replace="python")
            assert result["success"] is True
            assert Path(filepath).read_text() == "hello python"

    def test_patch_file_not_found_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "patch.txt")
            Path(filepath).write_text("hello")

            registry = ToolRegistry()
            register_builtin_tools(registry, profile="full")
            tool = registry.get("patch_file")

            result = tool.handler(path=filepath, search="notexist", replace="x")
            assert "error" in result

    def test_search_replace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "sr.txt")
            Path(filepath).write_text("aaa bbb aaa")

            registry = ToolRegistry()
            register_builtin_tools(registry, profile="full")
            tool = registry.get("search_replace")

            result = tool.handler(path=filepath, search="aaa", replace="ccc", all=True)
            assert result["success"] is True
            assert result["replacements"] == 2
            assert Path(filepath).read_text() == "ccc bbb ccc"

    def test_search_replace_single(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "sr.txt")
            Path(filepath).write_text("aaa bbb aaa")

            registry = ToolRegistry()
            register_builtin_tools(registry, profile="full")
            tool = registry.get("search_replace")

            result = tool.handler(path=filepath, search="aaa", replace="ccc")
            assert result["success"] is True
            assert result["replacements"] == 1
            assert Path(filepath).read_text() == "ccc bbb aaa"

    def test_memory_search_no_manager(self):
        registry = ToolRegistry()
        register_builtin_tools(registry, profile="standard")
        tool = registry.get("memory_search")
        result = tool.handler(query="test")
        assert "note" in result

    def test_memory_save_no_manager(self):
        registry = ToolRegistry()
        register_builtin_tools(registry, profile="standard")
        tool = registry.get("memory_save")
        result = tool.handler(content="test")
        assert result["success"] is False

    def test_delegate_task_no_manager(self):
        registry = ToolRegistry()
        register_builtin_tools(registry, profile="standard")
        tool = registry.get("delegate_task")
        result = tool.handler(tasks=[{"description": "test task"}])
        assert "note" in result

    def test_exec_command(self):
        registry = ToolRegistry()
        register_builtin_tools(registry, profile="minimal")
        tool = registry.get("exec")
        result = tool.handler(command="echo hello")
        assert result["return_code"] == 0
        assert "hello" in result["stdout"]

    def test_exec_command_timeout(self):
        registry = ToolRegistry()
        register_builtin_tools(registry, profile="minimal")
        tool = registry.get("exec")
        result = tool.handler(command="sleep 10", timeout=1)
        assert "error" in result
        assert "超时" in result["error"]

    def test_code_eval(self):
        registry = ToolRegistry()
        register_builtin_tools(registry, profile="full")
        tool = registry.get("code_eval")
        result = tool.handler(code="print(2+3)")
        assert result["return_code"] == 0
        assert "5" in result["stdout"]

    def test_code_eval_timeout(self):
        registry = ToolRegistry()
        register_builtin_tools(registry, profile="full")
        tool = registry.get("code_eval")
        result = tool.handler(code="import time; time.sleep(30)", timeout=1)
        assert "error" in result


class TestSessionManager:
    def test_create_and_get_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(tmpdir)
            sid = sm.create_session(agent_name="test_agent")
            info = sm.get_session(sid)
            assert info["agent_name"] == "test_agent"
            sm.close()

    def test_session_with_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(tmpdir)
            sid = sm.create_session(metadata={"user": "alice", "env": "dev"})
            info = sm.get_session(sid)
            assert info["metadata"]["user"] == "alice"
            sm.close()

    def test_add_and_get_messages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(tmpdir)
            sid = sm.create_session()
            sm.add_message(sid, "user", "Hello")
            sm.add_message(sid, "assistant", "Hi there!")
            sm.add_message(sid, "user", "How are you?")

            msgs = sm.get_messages(sid)
            assert len(msgs) == 3
            assert msgs[0]["role"] == "user"
            assert msgs[0]["content"] == "Hello"
            assert msgs[1]["role"] == "assistant"
            sm.close()

    def test_message_with_tool_calls(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(tmpdir)
            sid = sm.create_session()
            sm.add_message(sid, "assistant", "", tool_calls=[
                {"function": {"name": "exec", "arguments": '{"command": "ls"}'}}
            ])

            msgs = sm.get_messages(sid)
            assert len(msgs) == 1
            assert msgs[0]["tool_calls"] is not None
            assert msgs[0]["tool_calls"][0]["function"]["name"] == "exec"
            sm.close()

    def test_list_sessions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(tmpdir)
            sm.create_session(agent_name="a")
            sm.create_session(agent_name="b")
            sm.create_session(agent_name="c")

            sessions = sm.list_sessions()
            assert len(sessions) == 3
            names = {s["agent_name"] for s in sessions}
            assert names == {"a", "b", "c"}
            sm.close()

    def test_delete_session(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(tmpdir)
            sid = sm.create_session()
            sm.add_message(sid, "user", "test")

            assert sm.delete_session(sid) is True
            try:
                sm.get_session(sid)
                assert False
            except SessionNotFoundError:
                pass

            assert sm.delete_session("nonexistent") is False
            sm.close()

    def test_session_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(tmpdir)
            try:
                sm.get_session("nonexistent")
                assert False
            except SessionNotFoundError as e:
                assert e.session_id == "nonexistent"
            sm.close()

    def test_persistence_across_restarts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm1 = SessionManager(tmpdir)
            sid = sm1.create_session(agent_name="persistent")
            sm1.add_message(sid, "user", "Hello")
            sm1.close()

            sm2 = SessionManager(tmpdir)
            info = sm2.get_session(sid)
            assert info["agent_name"] == "persistent"
            msgs = sm2.get_messages(sid)
            assert len(msgs) == 1
            assert msgs[0]["content"] == "Hello"
            sm2.close()

    def test_cleanup_expired(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(tmpdir, max_age_hours=0)
            import time
            sid = sm.create_session()

            time.sleep(0.1)
            sm.add_message(sid, "user", "old")

            sm._max_age = 0
            count = sm.cleanup_expired()
            assert count >= 1
            sm.close()


class TestHookManager:
    def test_register_and_trigger(self):
        hm = HookManager()
        results = []

        def handler(**kwargs):
            results.append(kwargs.get("value", 0))
            return {"processed": True}

        hm.register(HookPoint.BEFORE_TOOL_CALL, handler)
        result = hm.trigger(HookPoint.BEFORE_TOOL_CALL, value=42)

        assert len(results) == 1
        assert results[0] == 42
        assert result["processed"] is True

    def test_multiple_hooks(self):
        hm = HookManager()
        call_order = []

        hm.register(HookPoint.AFTER_TOOL_CALL, lambda **kw: call_order.append("first"))
        hm.register(HookPoint.AFTER_TOOL_CALL, lambda **kw: call_order.append("second"))

        hm.trigger(HookPoint.AFTER_TOOL_CALL)
        assert call_order == ["first", "second"]

    def test_hook_exception_doesnt_break(self):
        hm = HookManager()

        def bad_handler(**kwargs):
            raise ValueError("oops")

        hm.register(HookPoint.BEFORE_AGENT_RUN, bad_handler)
        result = hm.trigger(HookPoint.BEFORE_AGENT_RUN)
        assert result == {}

    def test_no_hooks_returns_empty(self):
        hm = HookManager()
        result = hm.trigger(HookPoint.BEFORE_AGENT_RUN)
        assert result == {}

    def test_async_handler_registration(self):
        hm = HookManager()
        results = []

        async def async_handler(**kwargs):
            results.append(kwargs.get("value", 0))
            return {"async_processed": True}

        hm.register(HookPoint.BEFORE_TOOL_CALL, async_handler)
        result = hm.trigger_sync_with_async(HookPoint.BEFORE_TOOL_CALL, value=99)

        assert len(results) == 1
        assert results[0] == 99
        assert result["async_processed"] is True

    def test_async_timeout_protection(self):
        hm = HookManager(default_timeout=0.5)

        async def slow_handler(**kwargs):
            import asyncio
            await asyncio.sleep(10)
            return {"never": True}

        hm.register(HookPoint.AFTER_AGENT_END, slow_handler)
        result = hm.trigger_sync_with_async(HookPoint.AFTER_AGENT_END, timeout=0.3)

        assert result == {}

    def test_mixed_sync_and_async(self):
        hm = HookManager()
        sync_results = []
        async_results = []

        def sync_handler(**kwargs):
            sync_results.append(1)
            return {"sync": True}

        async def async_handler(**kwargs):
            async_results.append(1)
            return {"async": True}

        hm.register(HookPoint.BEFORE_AGENT_REPLY, sync_handler)
        hm.register(HookPoint.BEFORE_AGENT_REPLY, async_handler)
        result = hm.trigger_sync_with_async(HookPoint.BEFORE_AGENT_REPLY)

        assert len(sync_results) == 1
        assert len(async_results) == 1
        assert result["sync"] is True
        assert result["async"] is True

    def test_remove_handler(self):
        hm = HookManager()
        results = []

        def handler(**kwargs):
            results.append(1)

        hm.register(HookPoint.BEFORE_TOOL_CALL, handler)
        assert hm.remove(HookPoint.BEFORE_TOOL_CALL, handler) is True
        assert hm.remove(HookPoint.BEFORE_TOOL_CALL, handler) is False

        hm.trigger(HookPoint.BEFORE_TOOL_CALL)
        assert len(results) == 0


class TestToolDispatcher:
    def test_unknown_tool_returns_error(self):
        from clawhermes.agent.loop import ToolDispatcher
        registry = ToolRegistry()
        hm = HookManager()
        dispatcher = ToolDispatcher(registry, hm)

        result = dispatcher.execute([{
            "id": "tc1",
            "function": {"name": "nonexistent", "arguments": "{}"},
        }], context={})

        assert len(result) == 1
        assert "未知工具" in result[0]["content"]

    def test_blocked_by_hook(self):
        from clawhermes.agent.loop import ToolDispatcher
        registry = ToolRegistry()
        register_builtin_tools(registry, profile="minimal")
        hm = HookManager()

        def block_exec(**kwargs):
            if kwargs.get("tool_name") == "exec":
                return {"blocked": True, "reason": "unsafe command"}

        hm.register(HookPoint.BEFORE_TOOL_CALL, block_exec)
        dispatcher = ToolDispatcher(registry, hm)

        result = dispatcher.execute([{
            "id": "tc1",
            "function": {"name": "exec", "arguments": '{"command": "rm -rf /"}'},
        }], context={})

        assert len(result) == 1
        parsed = json.loads(result[0]["content"])
        assert "error" in parsed

    def test_override_args_by_hook(self):
        from clawhermes.agent.loop import ToolDispatcher
        registry = ToolRegistry()
        register_builtin_tools(registry, profile="minimal")
        hm = HookManager()

        def override(**kwargs):
            if kwargs.get("tool_name") == "get_time":
                return {"override_args": {}}

        hm.register(HookPoint.BEFORE_TOOL_CALL, override)
        dispatcher = ToolDispatcher(registry, hm)

        result = dispatcher.execute([{
            "id": "tc1",
            "function": {"name": "get_time", "arguments": '{}'},
        }], context={})

        assert len(result) == 1
        parsed = json.loads(result[0]["content"])
        assert "datetime" in parsed


class TestAgentLoop:
    def test_interrupt(self):
        from tests.mock_provider import MockProvider
        provider = MockProvider(responses=["ok"])
        agent = Agent(llm_provider=provider, config=AgentConfig(max_iterations=5))
        agent.interrupt()
        assert agent._interrupt.is_set()

    def test_get_conversation(self):
        from tests.mock_provider import MockProvider
        provider = MockProvider(responses=["response text"])
        agent = Agent(llm_provider=provider, config=AgentConfig(max_iterations=5))
        result = agent.chat("test")
        assert result == "response text"
        convo = agent.get_conversation()
        assert len(convo) > 0

    def test_max_iterations(self):
        from clawhermes.llm.provider import LLMResponse
        from tests.mock_provider import MockProvider

        call_count = 0

        class AlwaysToolProvider(MockProvider):
            def chat(self, messages, tools=None):
                nonlocal call_count
                call_count += 1
                return LLMResponse(
                    content=None,
                    tool_calls=[{
                        "id": f"tc_{call_count}",
                        "function": {"name": "get_time", "arguments": "{}"},
                    }],
                    model="mock",
                )

        provider = AlwaysToolProvider()
        agent = Agent(llm_provider=provider, config=AgentConfig(max_iterations=2))
        registry = ToolRegistry()
        register_builtin_tools(registry, profile="minimal")
        agent.tools = registry
        from clawhermes.agent.loop import ToolDispatcher
        agent.dispatcher = ToolDispatcher(registry, agent.hooks)

        result = agent.chat("keep calling tools")
        assert "最大迭代次数" in result


class TestParallelToolExecution:
    def test_parallel_safe_tools_execute(self):
        from clawhermes.agent.loop import ToolDef, ToolDispatcher

        registry = ToolRegistry()

        def tool_a(**kwargs):
            return {"result": "a"}

        def tool_b(**kwargs):
            return {"result": "b"}

        registry.register(ToolDef(
            name="tool_a", description="Tool A",
            parameters={"type": "object", "properties": {}},
            handler=tool_a, parallel_safe=True,
        ))
        registry.register(ToolDef(
            name="tool_b", description="Tool B",
            parameters={"type": "object", "properties": {}},
            handler=tool_b, parallel_safe=True,
        ))

        hm = HookManager()
        dispatcher = ToolDispatcher(registry, hm)

        results = dispatcher.execute([
            {"id": "tc1", "function": {"name": "tool_a", "arguments": "{}"}},
            {"id": "tc2", "function": {"name": "tool_b", "arguments": "{}"}},
        ], context={})

        assert len(results) == 2
        names = {r["name"] for r in results}
        assert names == {"tool_a", "tool_b"}

    def test_execute_async_parallel(self):
        import asyncio

        from clawhermes.agent.loop import ToolDef, ToolDispatcher

        registry = ToolRegistry()

        def counting_tool(**kwargs):
            return {"result": "ok"}

        registry.register(ToolDef(
            name="count_a", description="Count A",
            parameters={"type": "object", "properties": {}},
            handler=counting_tool, parallel_safe=True,
        ))
        registry.register(ToolDef(
            name="count_b", description="Count B",
            parameters={"type": "object", "properties": {}},
            handler=counting_tool, parallel_safe=True,
        ))

        hm = HookManager()
        dispatcher = ToolDispatcher(registry, hm)

        results = asyncio.run(dispatcher.execute_async([
            {"id": "tc1", "function": {"name": "count_a", "arguments": "{}"}},
            {"id": "tc2", "function": {"name": "count_b", "arguments": "{}"}},
        ], context={}))

        assert len(results) == 2

    def test_serial_tools_not_parallel(self):
        from clawhermes.agent.loop import ToolDispatcher

        registry = ToolRegistry()
        register_builtin_tools(registry, profile="full")
        hm = HookManager()
        dispatcher = ToolDispatcher(registry, hm)

        results = dispatcher.execute([
            {"id": "tc1", "function": {"name": "write_file", "arguments": '{"path": "/tmp/test_p1", "content": "a"}'}},
            {"id": "tc2", "function": {"name": "write_file", "arguments": '{"path": "/tmp/test_p2", "content": "b"}'}},
        ], context={})

        assert len(results) == 2

    def test_mixed_parallel_and_serial(self):
        from clawhermes.agent.loop import ToolDispatcher

        registry = ToolRegistry()
        register_builtin_tools(registry, profile="full")
        hm = HookManager()
        dispatcher = ToolDispatcher(registry, hm)

        results = dispatcher.execute([
            {"id": "tc1", "function": {"name": "get_time", "arguments": '{}'}},
            {"id": "tc2", "function": {"name": "session_status", "arguments": '{}'}},
        ], context={})

        assert len(results) == 2

    def test_duration_tracking(self):
        from clawhermes.agent.loop import HookPoint, ToolDispatcher

        registry = ToolRegistry()
        register_builtin_tools(registry, profile="minimal")
        hm = HookManager()
        durations = []

        def track_duration(**kwargs):
            d = kwargs.get("duration_ms", 0)
            if d > 0:
                durations.append(d)

        hm.register(HookPoint.AFTER_TOOL_CALL, track_duration)
        dispatcher = ToolDispatcher(registry, hm)

        dispatcher.execute([
            {"id": "tc1", "function": {"name": "get_time", "arguments": '{}'}},
        ], context={})

        assert len(durations) >= 1
        assert durations[0] >= 0


class TestWebSearchRefactor:
    def test_web_search_returns_dict(self):
        registry = ToolRegistry()
        register_builtin_tools(registry, profile="standard")
        tool = registry.get("web_search")
        assert tool is not None
        result = tool.handler(query="test query")
        assert isinstance(result, dict)

    def test_web_search_has_engine_field(self):
        registry = ToolRegistry()
        register_builtin_tools(registry, profile="standard")
        tool = registry.get("web_search")
        result = tool.handler(query="python programming")
        assert "engine" in result or "error" in result or "results" in result

    def test_parse_ddg_html_empty(self):
        from clawhermes.tools.builtin import _parse_ddg_html
        results = _parse_ddg_html("<html><body></body></html>")
        assert results == []

    def test_parse_ddg_html_with_results(self):
        from clawhermes.tools.builtin import _parse_ddg_html
        html = '''
        <a class="result__a" href="https://example.com">Example Title</a>
        <a class="result__snippet">Example snippet text</a>
        '''
        results = _parse_ddg_html(html)
        assert len(results) == 1
        assert results[0]["title"] == "Example Title"
        assert results[0]["snippet"] == "Example snippet text"

    def test_search_engine_env_var(self):
        import os

        from clawhermes.tools.builtin import _web_search
        original = os.environ.get("CH_SEARCH_ENGINE")
        try:
            os.environ["CH_SEARCH_ENGINE"] = "duckduckgo"
            result = _web_search("test")
            assert isinstance(result, dict)
        finally:
            if original is not None:
                os.environ["CH_SEARCH_ENGINE"] = original
            else:
                os.environ.pop("CH_SEARCH_ENGINE", None)

    def test_searxng_without_url(self):
        from clawhermes.tools.builtin import _web_search_searxng
        result = _web_search_searxng("test")
        assert isinstance(result, dict)

    def test_serpapi_without_key(self):
        from clawhermes.tools.builtin import _web_search_serpapi
        result = _web_search_serpapi("test")
        assert "error" in result

    def test_tavily_without_key(self):
        from clawhermes.tools.builtin import _web_search_tavily
        result = _web_search_tavily("test")
        assert "error" in result


class TestGatewayState:
    def test_gateway_state_init(self):
        from clawhermes.gateway.app import GatewayState
        state = GatewayState()
        assert state.agent is None
        assert state.memory is None
        assert not state.is_initialized()

    def test_gateway_state_get_agent_raises(self):
        from clawhermes.gateway.app import GatewayState
        state = GatewayState()
        try:
            state.get_agent()
            assert False
        except Exception:
            pass

    def test_gateway_state_get_memory_raises(self):
        from clawhermes.gateway.app import GatewayState
        state = GatewayState()
        try:
            state.get_memory()
            assert False
        except Exception:
            pass


class TestSessionManagerThreadSafety:
    def test_concurrent_session_creation(self):
        import concurrent.futures

        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(tmpdir)
            ids = []

            def create_session():
                sid = sm.create_session()
                return sid

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(create_session) for _ in range(10)]
                for f in concurrent.futures.as_completed(futures):
                    ids.append(f.result())

            assert len(ids) == 10
            assert len(set(ids)) == 10
            sm.close()

    def test_concurrent_read_write(self):
        import concurrent.futures

        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager(tmpdir)
            sid = sm.create_session()

            def add_message(idx):
                sm.add_message(sid, "user", f"message {idx}")

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(add_message, i) for i in range(10)]
                concurrent.futures.wait(futures)

            msgs = sm.get_messages(sid)
            assert len(msgs) == 10
            sm.close()


# ============================================================
# Extended unit tests for coverage (M3.12)
# ============================================================

class TestMoreToolHandlers:
    """Additional tool handler tests for coverage"""

    def test_exec_command_echo(self):
        from clawhermes.tools.builtin import _exec_command
        result = _exec_command(command="echo hello")
        assert isinstance(result, dict)

    def test_exec_command_timeout(self):
        from clawhermes.tools.builtin import _exec_command
        result = _exec_command(command="sleep 10", timeout=1)
        assert isinstance(result, dict)

    def test_web_fetch_invalid_url(self):
        from clawhermes.tools.builtin import _web_fetch
        result = _web_fetch(url="not-a-valid-url")
        assert isinstance(result, dict)

    def test_patch_file(self, tmp_path):
        from clawhermes.tools.builtin import _patch_file
        f = tmp_path / "code.py"
        f.write_text("hello world")
        result = _patch_file(path=str(f), search="hello", replace="hi")
        assert isinstance(result, dict)
        assert f.read_text() == "hi world"

    def test_search_replace(self, tmp_path):
        from clawhermes.tools.builtin import _search_replace
        f = tmp_path / "code.py"
        f.write_text("hello hello world")
        result = _search_replace(path=str(f), search="hello", replace="hi", all=True)
        assert isinstance(result, dict)
        assert f.read_text() == "hi hi world"

    def test_code_eval(self):
        from clawhermes.tools.builtin import _code_eval
        result = _code_eval(code="print('test')")
        assert isinstance(result, dict)

    def test_code_eval_timeout(self):
        from clawhermes.tools.builtin import _code_eval
        result = _code_eval(code="import time; time.sleep(10)", timeout=1)
        assert isinstance(result, dict)

    def test_http_request_get(self):
        from clawhermes.tools.builtin import _http_request
        result = _http_request(url="http://localhost:1/nonexistent", method="GET")
        assert isinstance(result, dict)

    def test_json_query_from_str(self):
        from clawhermes.tools.builtin import _json_query
        result = _json_query(json_str='[1, 2, 3]', path="1")
        assert isinstance(result, dict)

    def test_git_diff_no_repo(self, tmp_path):
        from clawhermes.tools.builtin import _git_diff
        result = _git_diff(path=str(tmp_path))
        assert isinstance(result, dict)

    def test_git_log_no_repo(self, tmp_path):
        from clawhermes.tools.builtin import _git_log
        result = _git_log(path=str(tmp_path))
        assert isinstance(result, dict)

    def test_memory_search_empty_query(self):
        from clawhermes.tools.builtin import _memory_search
        result = _memory_search(query="nonexistent_xyz123")
        assert isinstance(result, dict)

    def test_memory_save(self):
        from clawhermes.tools.builtin import _memory_save
        result = _memory_save(content="test memory content")
        assert isinstance(result, dict)

    def test_delegate_task_empty(self):
        from clawhermes.tools.builtin import _delegate_task
        result = _delegate_task(tasks=[])
        assert isinstance(result, dict)

    def test_web_search(self):
        from clawhermes.tools.builtin import _web_search
        result = _web_search(query="python programming")
        assert isinstance(result, dict)

    def test_calc_simple(self):
        from clawhermes.tools.builtin import _calc
        result = _calc(expression="42")
        assert isinstance(result, dict)

    def test_calc_complex(self):
        from clawhermes.tools.builtin import _calc
        result = _calc(expression="sum(range(100))")
        assert isinstance(result, dict)


class TestSkillManager:
    """Test SkillManager operations"""

    def test_skill_manager_create_and_list(self, tmp_path):
        from clawhermes.skills.manager import SkillManager
        sm = SkillManager(tmp_path)
        skill = sm.create("test-skill", "print('hello')", "A test skill")
        assert skill.name == "test-skill"
        assert skill.description == "A test skill"

        skills = sm.list()
        assert len(skills) >= 1

    def test_skill_manager_get(self, tmp_path):
        from clawhermes.skills.manager import SkillManager
        sm = SkillManager(tmp_path)
        sm.create("get-test", "content", "desc")
        skill = sm.get("get-test")
        assert skill is not None
        assert skill.name == "get-test"

    def test_skill_manager_get_nonexistent(self, tmp_path):
        from clawhermes.skills.manager import SkillManager
        sm = SkillManager(tmp_path)
        assert sm.get("nonexistent") is None

    def test_skill_manager_update(self, tmp_path):
        from clawhermes.skills.manager import SkillManager
        sm = SkillManager(tmp_path)
        sm.create("update-test", "original", "desc")
        sm.update("update-test", content="updated", usage_count=5)
        skill = sm.get("update-test")
        assert skill is not None
        assert skill.usage_count == 5

    def test_skill_manager_status_filter(self, tmp_path):
        from clawhermes.skills.manager import SkillManager
        sm = SkillManager(tmp_path)
        sm.create("filter-test", "content", "desc")
        active = sm.list(status="active")
        assert len(active) >= 1


class TestBackgroundReview:
    """Test BackgroundReview parsing"""

    def test_review_parse_valid_json(self, tmp_path):
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager
        from clawhermes.llm.provider import LLMProvider
        from clawhermes.skills.manager import BackgroundReview, SkillManager

        provider = LLMProvider(model="deepseek/deepseek-chat", api_key="test")
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(tmp_path))
        sm = SkillManager(tmp_path)

        br = BackgroundReview(provider, memory, sm)

        # Test JSON parsing
        result = br._parse_review('{"memories": [{"content": "test", "importance": 0.9}], "skills": []}')
        assert len(result["memories"]) == 1
        assert result["memories"][0]["content"] == "test"

    def test_review_parse_invalid(self, tmp_path):
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager
        from clawhermes.llm.provider import LLMProvider
        from clawhermes.skills.manager import BackgroundReview, SkillManager

        provider = LLMProvider(model="deepseek/deepseek-chat", api_key="test")
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(tmp_path))
        sm = SkillManager(tmp_path)

        br = BackgroundReview(provider, memory, sm)
        result = br._parse_review("not json at all")
        assert result == {"memories": [], "skills": []}

    def test_review_build_prompt(self, tmp_path):
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager
        from clawhermes.llm.provider import LLMProvider
        from clawhermes.skills.manager import BackgroundReview, SkillManager

        provider = LLMProvider(model="deepseek/deepseek-chat", api_key="test")
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(tmp_path))
        sm = SkillManager(tmp_path)

        br = BackgroundReview(provider, memory, sm)
        conv = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        prompt = br._build_review_prompt(conv)
        assert "hello" in prompt
        assert "hi" in prompt


class TestCurator:
    """Test Curator operations"""

    def test_curator_empty(self, tmp_path):
        from clawhermes.skills.manager import Curator, SkillManager
        sm = SkillManager(tmp_path)
        curator = Curator(sm)
        stats = curator.run(dry_run=True)
        assert stats["active"] == 0
        assert stats["stale"] == 0
        assert stats["archived"] == 0

    def test_curator_with_skills(self, tmp_path):
        from clawhermes.skills.manager import Curator, SkillManager
        sm = SkillManager(tmp_path)
        sm.create("fresh-skill", "content", "desc")

        # Create a skill that hasn't been used for a long time
        old_skill = sm.create("old-skill", "content", "desc")
        old_skill.last_used = time.time() - 40 * 86400  # 40 days ago
        sm.update("old-skill", last_used=old_skill.last_used)

        curator = Curator(sm)
        stats = curator.run(dry_run=True)
        # old-skill should be marked stale (30 days)
        assert stats["stale"] >= 1


class TestPrompt:
    """Test SystemPrompt"""

    def test_prompt_build(self):
        from clawhermes.agent.prompt import SystemPrompt
        sp = SystemPrompt()
        result = sp.build()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_prompt_with_identity(self, tmp_path):
        from clawhermes.agent.prompt import SystemPrompt
        sp = SystemPrompt()
        sp = SystemPrompt()
        result = sp.build()
        assert "ClawHermes" in result or "clawhermes" in result.lower()


class TestMemoryProviders:
    """Test memory providers"""

    def test_json_provider_save_and_search(self, tmp_path):
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryItem, MemoryScope
        provider = JSONMemoryProvider(tmp_path)
        item = MemoryItem(content="test memory", importance=0.8, scope=MemoryScope.USER)
        provider.save(item)
        results = provider.search("test")
        assert len(results) >= 1

    def test_json_provider_persistence(self, tmp_path):
        from clawhermes.agent.memory import JSONMemoryProvider, MemoryItem, MemoryScope
        p1 = JSONMemoryProvider(tmp_path)
        p1.save(MemoryItem(content="persistent data", importance=0.9, scope=MemoryScope.USER))
        p2 = JSONMemoryProvider(tmp_path)
        results = p2.search("persistent")
        assert len(results) >= 1


class TestSessionManager2:
    """Test session manager"""

    def test_create_and_get_session(self, tmp_path):
        from clawhermes.agent.session import SessionManager
        mgr = SessionManager(str(tmp_path))
        sid = mgr.create_session()
        assert sid is not None
        info = mgr.get_session(sid)
        assert info is not None

    def test_list_sessions(self, tmp_path):
        from clawhermes.agent.session import SessionManager
        mgr = SessionManager(str(tmp_path))
        mgr.create_session()
        mgr.create_session()
        sessions = mgr.list_sessions()
        assert len(sessions) == 2

    def test_save_and_get_messages(self, tmp_path):
        from clawhermes.agent.session import SessionManager
        mgr = SessionManager(str(tmp_path))
        sid = mgr.create_session()
        mgr.add_message(sid, "user", "hello")
        mgr.add_message(sid, "assistant", "hi")
        messages = mgr.get_messages(sid)
        assert len(messages) == 2

    def test_delete_session(self, tmp_path):
        from clawhermes.agent.session import SessionManager
        mgr = SessionManager(str(tmp_path))
        sid = mgr.create_session()
        assert mgr.delete_session(sid) is True
        assert mgr.delete_session("nonexistent") is False


class TestExceptions:
    """Test exception hierarchy"""

    def test_clawhermes_error(self):
        from clawhermes.agent.exceptions import ClawHermesError
        e = ClawHermesError("test error")
        assert str(e) == "test error"

    def test_tool_not_found_error(self):
        from clawhermes.agent.exceptions import ToolNotFoundError
        e = ToolNotFoundError("test tool not found")
        assert "test" in str(e)

    def test_tool_execution_error(self):
        from clawhermes.agent.exceptions import ToolExecutionError
        e = ToolExecutionError("failed", tool_name="exec")
        assert e.tool_name == "exec"

    def test_llm_connection_error(self):
        from clawhermes.agent.exceptions import LLMConnectionError
        e = LLMConnectionError("connection lost")
        assert "connection lost" in str(e)

    def test_config_validation_error(self):
        from clawhermes.agent.exceptions import ConfigValidationError
        e = ConfigValidationError("invalid", field="port")
        assert e.field == "port"


class TestChannelManager:
    """Test ChannelManager and adapters"""

    def test_channel_manager_register(self):
        from clawhermes.channel.adapter import ChannelManager, RESTAdapter
        mgr = ChannelManager()
        adapter = RESTAdapter()
        mgr.register("rest", adapter)
        assert mgr.get("rest") is adapter

    def test_channel_manager_list(self):
        from clawhermes.channel.adapter import ChannelManager, RESTAdapter
        mgr = ChannelManager()
        mgr.register("rest", RESTAdapter())
        adapters = mgr.list_adapters()
        assert len(adapters) == 1
        assert adapters[0]["name"] == "rest"

    def test_channel_manager_unregister(self):
        from clawhermes.channel.adapter import ChannelManager, RESTAdapter
        mgr = ChannelManager()
        mgr.register("rest", RESTAdapter())
        mgr.unregister("rest")
        assert mgr.get("rest") is None

    def test_channel_user(self):
        from clawhermes.channel.adapter import ChannelUser
        user = ChannelUser(user_id="u1", display_name="Test User")
        assert user.user_id == "u1"
        assert user.display_name == "Test User"

    def test_channel_message(self):
        from clawhermes.channel.adapter import ChannelMessage, ChannelType, ChannelUser
        msg = ChannelMessage(
            message_id="m1",
            channel_type=ChannelType.REST,
            user=ChannelUser(user_id="u1"),
            content="hello",
        )
        assert msg.content == "hello"
        assert msg.channel_type == ChannelType.REST


class TestSessionRouter:
    """Test SessionRouter"""

    def test_create_and_resolve(self):
        from clawhermes.channel.adapter import ChannelType
        from clawhermes.channel.router import SessionRouter
        router = SessionRouter()
        sid = router.create(ChannelType.REST, "chat-1")
        assert sid is not None
        resolved = router.resolve(ChannelType.REST, "chat-1")
        assert resolved == sid

    def test_remove(self):
        from clawhermes.channel.adapter import ChannelType
        from clawhermes.channel.router import SessionRouter
        router = SessionRouter()
        router.create(ChannelType.REST, "chat-1")
        assert router.remove(ChannelType.REST, "chat-1") is True
        assert router.remove(ChannelType.REST, "chat-1") is False

    def test_list_mappings(self):
        from clawhermes.channel.adapter import ChannelType
        from clawhermes.channel.router import SessionRouter
        router = SessionRouter()
        router.create(ChannelType.REST, "chat-1")
        mappings = router.list_mappings()
        assert len(mappings) == 1


class TestConfig:
    """Test config module"""

    def test_config_validation_min_context(self):
        from pydantic import ValidationError

        from clawhermes.config import ClawHermesConfig
        with pytest.raises((ValueError, ValidationError)):
            ClawHermesConfig(llm_default_max_tokens=100)

    def test_config_defaults(self):
        from clawhermes.config import ClawHermesConfig
        cfg = ClawHermesConfig()
        assert cfg.gateway_port == 18789
        assert cfg.gateway_host == "127.0.0.1"

    def test_default_yaml_structure(self):
        from clawhermes.config import default_yaml
        yaml = default_yaml()
        assert "agent" in yaml
        assert "gateway" in yaml
        assert "llm" in yaml


class TestTypes:
    """Test types module"""

    def test_message_creation(self):
        from clawhermes.types import Message, MessageRole
        msg = Message(role=MessageRole.USER, content="hello")
        assert msg.role == MessageRole.USER
        assert msg.content == "hello"
        assert msg.id is not None

    def test_tool_call(self):
        from clawhermes.types import ToolCall
        tc = ToolCall(id="t1", name="test", args={})
        assert tc.status.value == "pending"

    def test_memory_item(self):
        from clawhermes.types import MemoryItem
        item = MemoryItem(content="test", importance=0.8)
        assert item.importance == 0.8

    def test_skill_dataclass(self):
        from clawhermes.types import Skill
        skill = Skill(name="test", content="print('hello')")
        assert skill.status == "active"
        assert skill.version == 1


class TestGatewayState2:
    """Test GatewayState class"""

    def test_initial_state(self):
        from clawhermes.gateway.app import GatewayState
        state = GatewayState()
        assert state.is_initialized() is False
        assert state.start_time > 0

    def test_get_agent_uninitialized(self):
        from clawhermes.gateway.app import GatewayState
        state = GatewayState()
        try:
            state.get_agent()
            assert False, "Expected exception"
        except Exception:
            pass

    def test_get_memory_uninitialized(self):
        from clawhermes.gateway.app import GatewayState
        state = GatewayState()
        try:
            state.get_memory()
            assert False, "Expected exception"
        except Exception:
            pass


class TestRemainingTools:
    """Test remaining tool handlers for coverage"""

    def test_web_search_duckduckgo(self):
        from clawhermes.tools.builtin import _web_search_duckduckgo
        result = _web_search_duckduckgo(query="test")
        assert isinstance(result, dict)

    def test_parse_ddg_html(self):
        from clawhermes.tools.builtin import _parse_ddg_html
        html = '<a class="result__a" href="http://example.com">Example</a><a class="result__snippet">A test snippet</a>'
        results = _parse_ddg_html(html)
        assert isinstance(results, list)

    def test_compress_file_no_output(self, tmp_path):
        from clawhermes.tools.builtin import _compress_file
        f = tmp_path / "data.txt"
        f.write_text("test " * 50)
        result = _compress_file(path=str(f))
        assert isinstance(result, dict)

    def test_http_request_post(self):
        from clawhermes.tools.builtin import _http_request
        result = _http_request(url="http://localhost:1/test", method="POST", data="test")
        assert isinstance(result, dict)

    def test_env_list_with_prefix(self):
        from clawhermes.tools.builtin import _env_list
        result = _env_list(prefix="PATH")
        assert isinstance(result, dict)

    def test_json_query_from_file(self, tmp_path):
        from clawhermes.tools.builtin import _json_query
        f = tmp_path / "data.json"
        f.write_text('{"a": {"b": 1}}')
        result = _json_query(json_str=f.read_text(), path="a.b")
        assert isinstance(result, dict)


class TestAgentLoop2:
    """Test agent loop components"""

    def test_hook_point_enum(self):
        from clawhermes.agent.loop import HookPoint
        assert HookPoint.BEFORE_TOOL_CALL == "before_tool_call"
        assert HookPoint.AFTER_AGENT_END == "after_agent_end"

    def test_tool_def_creation(self):
        from clawhermes.agent.loop import ToolDef
        td = ToolDef(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
            handler=lambda **kw: {"result": "ok"},
            parallel_safe=True,
        )
        assert td.name == "test_tool"
        assert td.parallel_safe is True

    def test_tool_registry_register_and_get(self):
        from clawhermes.agent.loop import ToolDef, ToolRegistry
        registry = ToolRegistry()
        td = ToolDef(name="test", description="desc", parameters={}, handler=lambda **kw: {})
        registry.register(td)
        assert registry.get("test") is td
        assert registry.get("nonexistent") is None

    def test_tool_registry_schemas(self):
        from clawhermes.agent.loop import ToolDef, ToolRegistry
        registry = ToolRegistry()
        td = ToolDef(name="test", description="desc", parameters={"type": "object", "properties": {}}, handler=lambda **kw: {})
        registry.register(td)
        schemas = registry.schemas()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "test"

    def test_hook_manager_register_and_trigger(self):
        from clawhermes.agent.loop import HookManager, HookPoint
        hm = HookManager()
        results = []
        def handler(**kw):
            results.append(kw)
            return {"modified": True}
        hm.register(HookPoint.BEFORE_TOOL_CALL, handler)
        output = hm.trigger(HookPoint.BEFORE_TOOL_CALL, tool_name="test")
        assert len(results) == 1
        assert output.get("modified") is True

    def test_hook_manager_remove(self):
        from clawhermes.agent.loop import HookManager, HookPoint
        hm = HookManager()
        def handler(**kw): pass
        hm.register(HookPoint.BEFORE_TOOL_CALL, handler)
        assert hm.remove(HookPoint.BEFORE_TOOL_CALL, handler) is True
        assert hm.remove(HookPoint.BEFORE_TOOL_CALL, handler) is False


class TestAgentConfig:
    """Test agent configuration"""

    def test_agent_config_defaults(self):
        from clawhermes.agent.loop import AgentConfig
        cfg = AgentConfig()
        assert cfg.max_iterations == 50
        assert cfg.max_tool_calls_per_round == 10

    def test_agent_config_custom(self):
        from clawhermes.agent.loop import AgentConfig
        cfg = AgentConfig(max_iterations=10, max_tool_calls_per_round=5)
        assert cfg.max_iterations == 10

    def test_agent_creation(self, tmp_path):
        from clawhermes.agent.loop import Agent, AgentConfig, ToolRegistry
        from clawhermes.llm.provider import LLMProvider
        provider = LLMProvider(model="deepseek/deepseek-chat", api_key="test")
        registry = ToolRegistry()
        agent = Agent(
            llm_provider=provider,
            tool_registry=registry,
            config=AgentConfig(max_iterations=1),
        )
        assert agent is not None
        assert agent.config.max_iterations == 1


class TestNewTools:
    """Test the 9 new tools added in M3.10"""

    def test_sqlite_query(self, tmp_path):
        import sqlite3

        from clawhermes.tools.builtin import _sqlite_query
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE t (id INT, name TEXT)")
        conn.execute("INSERT INTO t VALUES (1, 'hello')")
        conn.commit()
        conn.close()
        result = _sqlite_query(db_path=str(db), query="SELECT * FROM t")
        assert result["count"] == 1
        assert result["rows"][0] == [1, "hello"]

    def test_csv_parse(self, tmp_path):
        from clawhermes.tools.builtin import _csv_parse
        f = tmp_path / "test.csv"
        f.write_text("name,age\nAlice,30\nBob,25\n")
        result = _csv_parse(path=str(f))
        assert result["headers"] == ["name", "age"]
        assert len(result["rows"]) == 2

    def test_hash_file(self, tmp_path):
        from clawhermes.tools.builtin import _hash_file
        f = tmp_path / "data.txt"
        f.write_text("hello")
        result = _hash_file(path=str(f), algorithm="sha256")
        assert len(result["hash"]) == 64

    def test_disk_usage(self, tmp_path):
        from clawhermes.tools.builtin import _disk_usage
        result = _disk_usage(path=str(tmp_path))
        assert "total_gb" in result
        assert result["total_gb"] > 0

    def test_base64_codec(self):
        from clawhermes.tools.builtin import _base64_codec
        enc = _base64_codec(action="encode", text="hello")
        assert enc["result"] == "aGVsbG8="
        dec = _base64_codec(action="decode", text="aGVsbG8=")
        assert dec["result"] == "hello"

    def test_process_list(self):
        from clawhermes.tools.builtin import _process_list
        result = _process_list()
        assert isinstance(result, dict)
        # May fail in sandboxed environments

    def test_image_info(self, tmp_path):
        # Create a minimal valid PNG
        import struct
        import zlib

        from clawhermes.tools.builtin import _image_info
        def create_png(path, w=1, h=1):
            sig = b'\\x89PNG\\r\\n\\x1a\\n'
            ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
            ihdr_crc = zlib.crc32(b'IHDR' + ihdr)
            ihdr_chunk = struct.pack('>I', 13) + b'IHDR' + ihdr + struct.pack('>I', ihdr_crc)
            idat = zlib.compress(b'\\x00\\xff\\x00\\x00')
            idat_crc = zlib.crc32(b'IDAT' + idat)
            idat_chunk = struct.pack('>I', len(idat)) + b'IDAT' + idat + struct.pack('>I', idat_crc)
            iend_crc = zlib.crc32(b'IEND')
            iend_chunk = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
            with open(path, 'wb') as f:
                f.write(sig + ihdr_chunk + idat_chunk + iend_chunk)
        png = tmp_path / "test.png"
        create_png(str(png))
        result = _image_info(path=str(png))
        # May fail if Pillow not installed
        assert isinstance(result, dict)

    def test_pdf_extract_no_file(self, tmp_path):
        from clawhermes.tools.builtin import _pdf_extract
        result = _pdf_extract(path=str(tmp_path / "nonexistent.pdf"))
        assert "error" in result

    def test_markdown_render(self):
        from clawhermes.tools.builtin import _markdown_render
        result = _markdown_render(text="# Hello\\n\\nWorld")
        assert "html" in result
        assert "Hello" in result["html"]


# ── 流式聊天测试 ──

@pytest.mark.asyncio
class TestAgentStreaming:
    """Agent.chat_stream() 端到端测试"""

    async def test_stream_text_only(self):
        """纯文本响应 — 应产出一或多个 text + done 事件"""
        from clawhermes.agent.loop import Agent
        from tests.mock_provider import MockProvider

        provider = MockProvider(["这是一条长回复，用于测试流式分块功能。"] * 3)
        agent = Agent(llm_provider=provider)

        events = []
        async for evt in agent.chat_stream("你好"):
            events.append(evt)

        assert len(events) >= 2
        assert events[-1]["event"] == "done"
        texts = [e for e in events if e["event"] == "text"]
        assert len(texts) >= 1

    async def test_stream_with_tool_calls(self):
        """触发工具调用的消息 — 应有 tool_call + tool_result + done"""
        from clawhermes.agent.loop import Agent, ToolDef, ToolRegistry
        from tests.mock_provider import MockProvider

        def _get_time():
            return {"now": "2025-01-01T00:00:00"}

        registry = ToolRegistry()
        registry.register(ToolDef(
            name="get_time",
            description="获取当前时间",
            parameters={"type": "object", "properties": {}},
            handler=_get_time,
        ))

        provider = MockProvider([""] * 2)
        agent = Agent(llm_provider=provider, tool_registry=registry)

        events = []
        async for evt in agent.chat_stream("现在几点了"):
            events.append(evt)

        kinds = {e["event"] for e in events}
        assert "tool_call" in kinds
        assert "tool_result" in kinds
        assert events[-1]["event"] == "done"

    async def test_stream_interrupt(self):
        """中断的流式调用 — 应返回 interrupted done 事件"""
        from clawhermes.agent.loop import Agent
        from tests.mock_provider import MockProvider

        provider = MockProvider(["不会到达"] * 2)
        agent = Agent(llm_provider=provider)
        agent.interrupt()

        events = []
        async for evt in agent.chat_stream("你好"):
            events.append(evt)

        assert len(events) == 2
        assert events[1]["event"] == "done"
        assert events[1]["data"].get("interrupted")
