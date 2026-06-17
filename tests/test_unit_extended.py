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
        from clawhermes.agent.loop import ToolDispatcher, ToolDef

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
        from clawhermes.agent.loop import ToolDispatcher, ToolDef

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
        from clawhermes.agent.loop import ToolDispatcher, HookPoint

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
