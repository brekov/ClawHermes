"""
MCP 客户端与注册中心测试。

覆盖重点：
- ``_make_handler`` 返回 async handler，使异步分派路径真正调用 ``client.call_tool``；
- 同步分派路径（``_execute_single_tool``）经 ``_run_maybe_async`` 也能正确执行 async handler；
- ``MCPRegistry`` 的增删改查与生命周期；
- ``MCPClient`` 的连接、工具列举/调用、断连。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from clawhermes.agent.loop import (
    HookManager,
    ToolDef,
    ToolDispatcher,
    ToolRegistry,
)
from clawhermes.mcp.client import MCPClient, MCPRegistry, MCPServerSpec

# ---------------------------------------------------------------------------
# 测试辅助：构造一个已连接的假 MCPClient
# ---------------------------------------------------------------------------

def _make_fake_client(
    *,
    connected: bool = True,
    tools: list[dict] | None = None,
    call_result: Any = None,
    call_raises: Exception | None = None,
) -> MagicMock:
    """构造一个行为可控的 MCPClient 替身（不触发真实 IO）。"""
    client = MagicMock()
    client.is_connected = connected
    client.connect = AsyncMock(return_value={"server": "fake"})
    client.list_tools = AsyncMock(return_value=tools or [])
    if call_raises is not None:
        client.call_tool = AsyncMock(side_effect=call_raises)
    else:
        client.call_tool = AsyncMock(return_value=call_result if call_result is not None else {"ok": True})
    client.disconnect = AsyncMock(return_value=None)
    return client


# ---------------------------------------------------------------------------
# _make_handler：async handler 行为
# ---------------------------------------------------------------------------

class TestMakeHandler:
    """验证 _make_handler 返回的 async handler 在异步与同步路径下都真正执行。"""

    @pytest.mark.asyncio
    async def test_async_handler_calls_call_tool_with_kwargs(self):
        registry = MCPRegistry(ToolRegistry())
        fake_client = _make_fake_client(call_result={"echo": "hi"})
        registry._clients["srv"] = fake_client

        handler = registry._make_handler("srv", "echo")
        # 关键：handler 必须是协程函数，否则异步分派路径会走 run_in_executor
        assert asyncio.iscoroutinefunction(handler)

        result = await handler(query="hello", limit=3)
        fake_client.call_tool.assert_awaited_once_with("echo", {"query": "hello", "limit": 3})
        assert result == {"result": {"echo": "hi"}}

    @pytest.mark.asyncio
    async def test_async_handler_returns_error_when_server_missing(self):
        registry = MCPRegistry(ToolRegistry())
        handler = registry._make_handler("missing", "echo")

        result = await handler(x=1)
        assert result == {"error": "MCP server not connected: missing"}

    @pytest.mark.asyncio
    async def test_async_handler_catches_exception(self):
        registry = MCPRegistry(ToolRegistry())
        fake_client = _make_fake_client(call_raises=RuntimeError("boom"))
        registry._clients["srv"] = fake_client

        handler = registry._make_handler("srv", "echo")
        result = await handler()
        assert result == {"error": "boom"}


# ---------------------------------------------------------------------------
# _make_handler 经 ToolDispatcher 异步分派路径（回归核心场景）
# ---------------------------------------------------------------------------

class TestAsyncDispatchPath:
    """经 ToolDispatcher.execute_async 验证：async handler 被 await 而非返回占位。"""

    @pytest.mark.asyncio
    async def test_execute_async_awaits_async_handler(self):
        registry = MCPRegistry(ToolRegistry())
        fake_client = _make_fake_client(call_result={"value": 42})
        registry._clients["srv"] = fake_client

        # 注册一个 MCP 工具到 ToolRegistry（模拟 add_server 的注册动作）
        handler = registry._make_handler("srv", "compute")
        tool_registry = registry._tool_registry
        tool_registry.register(ToolDef(
            name="mcp_srv_compute",
            description="[MCP] compute",
            parameters={"type": "object", "properties": {}},
            handler=handler,
            group="mcp.srv",
        ))

        dispatcher = ToolDispatcher(tool_registry, HookManager())
        results = await dispatcher.execute_async([{
            "id": "tc1",
            "function": {"name": "mcp_srv_compute", "arguments": '{"n": 6}'},
        }], context={})

        assert len(results) == 1
        parsed = json.loads(results[0]["content"])
        # 修复前：占位 {"info": "..."}；修复后：真正结果 {"result": {"value": 42}}
        assert parsed == {"result": {"value": 42}}
        fake_client.call_tool.assert_awaited_once_with("compute", {"n": 6})


# ---------------------------------------------------------------------------
# _make_handler 经 ToolDispatcher 同步分派路径（不能破坏现有 /chat）
# ---------------------------------------------------------------------------

class TestSyncDispatchPath:
    """经 ToolDispatcher.execute（同步）验证：async handler 也能执行，不返回未 await 的协程。"""

    def test_execute_sync_runs_async_handler_no_running_loop(self):
        registry = MCPRegistry(ToolRegistry())
        fake_client = _make_fake_client(call_result={"v": 1})
        registry._clients["srv"] = fake_client

        handler = registry._make_handler("srv", "compute")
        tool_registry = registry._tool_registry
        tool_registry.register(ToolDef(
            name="mcp_srv_compute",
            description="[MCP] compute",
            parameters={"type": "object", "properties": {}},
            handler=handler,
            group="mcp.srv",
        ))

        dispatcher = ToolDispatcher(tool_registry, HookManager())
        results = dispatcher.execute([{
            "id": "tc1",
            "function": {"name": "mcp_srv_compute", "arguments": '{"n": 1}'},
        }], context={})

        assert len(results) == 1
        parsed = json.loads(results[0]["content"])
        assert parsed == {"result": {"v": 1}}

    def test_execute_sync_sync_handler_still_works(self):
        """普通同步 handler 不应受 _run_maybe_async 影响。"""
        registry = ToolRegistry()
        registry.register(ToolDef(
            name="sync_only",
            description="sync",
            parameters={"type": "object", "properties": {}},
            handler=lambda **kw: {"sync": True},
            group="core",
        ))
        dispatcher = ToolDispatcher(registry, HookManager())
        results = dispatcher.execute([{
            "id": "tc1",
            "function": {"name": "sync_only", "arguments": "{}"},
        }], context={})
        assert json.loads(results[0]["content"]) == {"sync": True}


# ---------------------------------------------------------------------------
# MCPRegistry 生命周期
# ---------------------------------------------------------------------------

class TestMCPRegistry:
    @pytest.mark.asyncio
    async def test_add_server_registers_tools(self, monkeypatch):
        """add_server 连接后应发现工具并注册到 ToolRegistry。"""
        registry = MCPRegistry(ToolRegistry())
        fake_client = _make_fake_client(tools=[
            {"name": "search", "description": "search things", "inputSchema": {"type": "object"}},
            {"name": "fetch", "description": "fetch things"},
        ])
        monkeypatch.setattr(
            "clawhermes.mcp.client.MCPClient",
            lambda spec: fake_client,
        )

        registered = await registry.add_server(MCPServerSpec(name="srv", transport="http", url="http://x"))
        assert registered == ["mcp_srv_search", "mcp_srv_fetch"]
        # 工具确实注册进 ToolRegistry
        assert registry._tool_registry.get("mcp_srv_search") is not None
        assert registry._tool_registry.get("mcp_srv_fetch") is not None
        assert registry.get_server_tools("srv") == ["mcp_srv_search", "mcp_srv_fetch"]

    @pytest.mark.asyncio
    async def test_add_server_duplicate_raises(self):
        registry = MCPRegistry(ToolRegistry())
        registry._clients["srv"] = _make_fake_client()
        with pytest.raises(ValueError, match="already registered"):
            await registry.add_server(MCPServerSpec(name="srv", transport="http", url="http://x"))

    @pytest.mark.asyncio
    async def test_add_server_connect_failure_propagates(self, monkeypatch):
        registry = MCPRegistry(ToolRegistry())
        fake_client = _make_fake_client()
        fake_client.connect = AsyncMock(side_effect=RuntimeError("conn refused"))
        monkeypatch.setattr("clawhermes.mcp.client.MCPClient", lambda spec: fake_client)
        with pytest.raises(RuntimeError, match="conn refused"):
            await registry.add_server(MCPServerSpec(name="srv", transport="http", url="http://x"))
        # 连接失败不应残留 client
        assert "srv" not in registry._clients

    @pytest.mark.asyncio
    async def test_remove_server(self):
        registry = MCPRegistry(ToolRegistry())
        registry._clients["srv"] = _make_fake_client()
        registry._server_tools["srv"] = ["mcp_srv_x"]

        ok = await registry.remove_server("srv")
        assert ok is True
        assert "srv" not in registry._clients
        assert registry.get_server_tools("srv") == []
        # 不存在的 server 返回 False
        assert await registry.remove_server("nope") is False

    @pytest.mark.asyncio
    async def test_disconnect_all(self):
        registry = MCPRegistry(ToolRegistry())
        c1 = _make_fake_client()
        c2 = _make_fake_client()
        registry._clients["a"] = c1
        registry._clients["b"] = c2

        await registry.disconnect_all()
        c1.disconnect.assert_awaited_once()
        c2.disconnect.assert_awaited_once()
        assert registry._clients == {}

    def test_list_servers(self):
        registry = MCPRegistry(ToolRegistry())
        registry._clients["a"] = _make_fake_client(connected=True)
        registry._clients["b"] = _make_fake_client(connected=False)
        registry._server_tools["a"] = ["mcp_a_x"]

        servers = registry.list_servers()
        names = {s["name"] for s in servers}
        assert names == {"a", "b"}
        a = next(s for s in servers if s["name"] == "a")
        assert a["connected"] is True
        assert a["tools"] == ["mcp_a_x"]


# ---------------------------------------------------------------------------
# MCPClient：transport 无关的协议行为（用假的 _call）
# ---------------------------------------------------------------------------

class TestMCPClient:
    @pytest.mark.asyncio
    async def test_call_tool_and_list_tools(self, monkeypatch):
        client = MCPClient(MCPServerSpec(name="s", transport="stdio", command="echo"))
        client._call = AsyncMock(side_effect=[
            {"tools": [{"name": "t1"}, {"name": "t2"}]},  # list_tools
            {"content": "result"},                          # call_tool
        ])

        tools = await client.list_tools()
        assert [t["name"] for t in tools] == ["t1", "t2"]

        res = await client.call_tool("t1", {"x": 1})
        assert res == {"content": "result"}
        # 第二次 _call 应以 tools/call + 正确参数调用
        client._call.assert_awaited_with("tools/call", {"name": "t1", "arguments": {"x": 1}})

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected_is_noop(self):
        client = MCPClient(MCPServerSpec(name="s", transport="stdio", command="echo"))
        # 未连接，disconnect 不应抛错
        await client.disconnect()
        assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect_closes_process_and_session(self):
        client = MCPClient(MCPServerSpec(name="s", transport="stdio", command="echo"))
        proc = MagicMock()
        proc.stdin.close = MagicMock()
        proc.wait = AsyncMock()
        client._process = proc
        client._connected = True

        session = MagicMock()
        session.aclose = AsyncMock()
        client._session = session

        await client.disconnect()
        proc.stdin.close.assert_called_once()
        proc.wait.assert_awaited_once()
        session.aclose.assert_awaited_once()
        assert client.is_connected is False

    def test_unknown_transport_raises(self):
        import asyncio as _asyncio
        client = MCPClient(MCPServerSpec(name="s", transport="bogus", command="x"))
        with pytest.raises(ValueError, match="Unknown transport"):
            _asyncio.run(client.connect())


# ---------------------------------------------------------------------------
# MCPClient：stdio transport（mock 子进程）
# ---------------------------------------------------------------------------

class _FakeStream:
    """模拟 asyncio subprocess 的 stdin/stdout 流。"""

    def __init__(self, responses: list[bytes]):
        self._responses = list(responses)
        self.written = bytearray()

    def write(self, data: bytes) -> None:
        self.written.extend(data)

    async def drain(self) -> None:
        return None

    async def readline(self) -> bytes:
        if self._responses:
            return self._responses.pop(0)
        return b"{}\n"

    def close(self) -> None:
        pass


class _FakeProcess:
    def __init__(self, responses: list[bytes]):
        self.stdin = _FakeStream([])
        self.stdout = _FakeStream(responses)
        self.stderr = _FakeStream([])
        self._waited = False

    async def wait(self) -> int:
        self._waited = True
        return 0


class TestMCPStdioTransport:
    @pytest.mark.asyncio
    async def test_connect_stdio_handshake(self, monkeypatch):
        """stdio connect 应完成 initialize 握手并标记已连接。"""
        client = MCPClient(MCPServerSpec(name="s", transport="stdio", command="fake-server"))
        fake_proc = _FakeProcess([b'{"jsonrpc":"2.0","id":1,"result":{"server":"v1"}}\n'])

        async def _fake_exec(*args, **kwargs):
            assert args[0] == "fake-server"
            return fake_proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

        result = await client.connect()
        assert result == {"server": "v1"}
        assert client.is_connected is True
        # 二次 connect 应直接返回缓存，不再 spawn
        again = await client.connect()
        assert again == {"server": "v1"}

    @pytest.mark.asyncio
    async def test_connect_stdio_no_command_raises(self):
        client = MCPClient(MCPServerSpec(name="s", transport="stdio", command=None, args=[]))
        with pytest.raises(ValueError, match="stdio transport requires command"):
            await client.connect()

    @pytest.mark.asyncio
    async def test_stdio_send_request_roundtrip(self, monkeypatch):
        """tools/list 与 tools/call 经 stdio 的 JSON-RPC 往返。"""
        client = MCPClient(MCPServerSpec(name="s", transport="stdio", command="srv"))
        fake_proc = _FakeProcess([
            b'{"jsonrpc":"2.0","id":1,"result":{"server":"v1"}}\n',   # initialize
            b'{"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"t"}]}}\n',  # tools/list
            b'{"jsonrpc":"2.0","id":3,"result":{"output":"done"}}\n',         # tools/call
        ])

        async def _fake_exec(*args, **kwargs):
            return fake_proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
        await client.connect()

        tools = await client.list_tools()
        assert tools == [{"name": "t"}]

        res = await client.call_tool("t", {"a": 1})
        assert res == {"output": "done"}

        # 校验写入的请求体包含正确 method
        written = fake_proc.stdin.written.decode()
        assert '"method": "tools/list"' in written
        assert '"method": "tools/call"' in written

    @pytest.mark.asyncio
    async def test_stdio_request_error_raises(self, monkeypatch):
        """JSON-RPC error 响应应抛 RuntimeError。"""
        client = MCPClient(MCPServerSpec(name="s", transport="stdio", command="srv"))
        fake_proc = _FakeProcess([
            b'{"jsonrpc":"2.0","id":1,"result":{}}\n',          # initialize
            b'{"jsonrpc":"2.0","id":2,"error":{"message":"nope"}}\n',  # tools/list error
        ])

        async def _fake_exec(*args, **kwargs):
            return fake_proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
        await client.connect()
        with pytest.raises(RuntimeError, match="MCP error"):
            await client.list_tools()

    @pytest.mark.asyncio
    async def test_stdio_request_when_not_connected_raises(self):
        client = MCPClient(MCPServerSpec(name="s", transport="stdio", command="srv"))
        with pytest.raises(RuntimeError, match="stdio not connected"):
            await client.list_tools()


# ---------------------------------------------------------------------------
# MCPClient：http transport（mock httpx）
# ---------------------------------------------------------------------------

class _FakeHttpResponse:
    def __init__(self, payload: dict, status: int = 200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


class _FakeHttpSession:
    """模拟 httpx.AsyncClient。"""

    def __init__(self, responses: list[dict]):
        self._responses = list(responses)
        self.posts: list[dict] = []
        self.closed = False

    async def post(self, path: str, json: dict):
        self.posts.append(json)
        return _FakeHttpResponse(self._responses.pop(0))

    async def aclose(self):
        self.closed = True


class TestMCPHttpTransport:
    @pytest.mark.asyncio
    async def test_connect_http_handshake(self, monkeypatch):
        client = MCPClient(MCPServerSpec(name="s", transport="http", url="http://srv", headers={"X": "1"}))
        fake_session = _FakeHttpSession([{"jsonrpc": "2.0", "id": 1, "result": {"name": "srv"}}])

        # 让 httpx.AsyncClient 返回我们的替身
        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: fake_session)

        result = await client.connect()
        assert result == {"name": "srv"}
        assert client.is_connected is True
        # initialize 请求被发送
        assert fake_session.posts[0]["method"] == "initialize"

    @pytest.mark.asyncio
    async def test_http_call_and_list(self, monkeypatch):
        client = MCPClient(MCPServerSpec(name="s", transport="http", url="http://srv"))
        fake_session = _FakeHttpSession([
            {"jsonrpc": "2.0", "id": 1, "result": {}},                       # initialize
            {"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "t"}]}},  # tools/list
            {"jsonrpc": "2.0", "id": 3, "result": {"ok": True}},             # tools/call
        ])

        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: fake_session)

        await client.connect()
        tools = await client.list_tools()
        assert tools == [{"name": "t"}]
        res = await client.call_tool("t", {"x": 9})
        assert res == {"ok": True}
        # tools/call 请求参数正确
        call_post = fake_session.posts[-1]
        assert call_post["method"] == "tools/call"
        assert call_post["params"] == {"name": "t", "arguments": {"x": 9}}

    @pytest.mark.asyncio
    async def test_http_error_response_raises(self, monkeypatch):
        client = MCPClient(MCPServerSpec(name="s", transport="http", url="http://srv"))
        fake_session = _FakeHttpSession([
            {"jsonrpc": "2.0", "id": 1, "result": {}},                       # initialize
            {"jsonrpc": "2.0", "id": 2, "error": {"message": "denied"}},    # tools/list error
        ])

        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: fake_session)

        await client.connect()
        with pytest.raises(RuntimeError, match="MCP error"):
            await client.list_tools()

    @pytest.mark.asyncio
    async def test_http_request_when_not_connected_raises(self):
        client = MCPClient(MCPServerSpec(name="s", transport="http", url="http://srv"))
        with pytest.raises(RuntimeError, match="http not connected"):
            await client.list_tools()

    @pytest.mark.asyncio
    async def test_http_disconnect_closes_session(self, monkeypatch):
        client = MCPClient(MCPServerSpec(name="s", transport="http", url="http://srv"))
        fake_session = _FakeHttpSession([{"jsonrpc": "2.0", "id": 1, "result": {}}])

        import httpx
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: fake_session)

        await client.connect()
        await client.disconnect()
        assert fake_session.closed is True
        assert client.is_connected is False
