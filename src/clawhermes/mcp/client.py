"""
ClawHermes - MCP 客户端
实现 MCP (Model Context Protocol) JSON-RPC 2.0 客户端
支持 stdio 子进程和 HTTP 两种传输方式
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MCPServerSpec:
    """MCP Server 配置描述"""
    name: str
    transport: str = "stdio"          # "stdio" | "http"
    command: str | None = None         # stdio: 可执行文件
    args: list[str] = field(default_factory=list)  # stdio: 命令行参数
    env: dict[str, str] | None = None  # stdio: 环境变量
    url: str | None = None             # http: URL
    headers: dict[str, str] | None = None  # http: 请求头


class MCPClient:
    """
    MCP 协议客户端

    支持两种传输方式：
    - stdio: 启动子进程，通过 stdin/stdout 通信
    - http: 通过 HTTP POST 发送 JSON-RPC 请求
    """

    def __init__(self, spec: MCPServerSpec):
        self.spec = spec
        self._process: asyncio.subprocess.Process | None = None
        self._session: Any = None  # httpx.AsyncClient for http mode
        self._server_info: dict = {}
        self._connected = False
        self._request_id = 0

    async def connect(self) -> dict[str, Any]:
        """连接 MCP Server 并完成初始化握手"""
        if self._connected:
            return self._server_info

        if self.spec.transport == "stdio":
            return await self._connect_stdio()
        elif self.spec.transport == "http":
            return await self._connect_http()
        else:
            raise ValueError(f"Unknown transport: {self.spec.transport}")

    async def _connect_stdio(self) -> dict[str, Any]:
        """通过 stdio 连接 MCP Server"""
        cmd = [self.spec.command] if self.spec.command else []
        cmd.extend(self.spec.args)

        if not cmd:
            raise ValueError("stdio transport requires command")

        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.spec.env,
        )
        # 初始化握手
        init_result = await self._send_request_stdio("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "clawhermes", "version": "0.14.0"},
        })
        self._server_info = init_result
        self._connected = True
        logger.info("MCP stdio connected: %s (%s)", self.spec.name, cmd)
        return init_result

    async def _connect_http(self) -> dict[str, Any]:
        """通过 HTTP 连接 MCP Server"""
        try:
            import httpx
        except ImportError:
            raise ImportError("httpx is required for HTTP MCP transport")

        self._session = httpx.AsyncClient(
            base_url=self.spec.url or "",
            headers=self.spec.headers or {},
            timeout=30.0,
        )
        init_result = await self._send_request_http("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "clawhermes", "version": "0.14.0"},
        })
        self._server_info = init_result
        self._connected = True
        logger.info("MCP http connected: %s (%s)", self.spec.name, self.spec.url)
        return init_result

    async def disconnect(self) -> None:
        """断开 MCP Server 连接"""
        if not self._connected:
            return
        try:
            if self._process:
                self._process.stdin.close()  # type: ignore
                await self._process.wait()
                self._process = None
            if self._session:
                await self._session.aclose()
                self._session = None
        except Exception as e:
            logger.warning("Error disconnecting MCP: %s", e)
        self._connected = False
        logger.info("MCP disconnected: %s", self.spec.name)

    async def list_tools(self) -> list[dict[str, Any]]:
        """列出 MCP Server 提供的所有工具"""
        result = await self._call("tools/list", {})
        tools: list[dict[str, Any]] = result.get("tools", [])
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """调用 MCP 工具"""
        return await self._call("tools/call", {"name": name, "arguments": arguments})

    async def _call(self, method: str, params: dict) -> dict[str, Any]:
        """发送 JSON-RPC 请求"""
        if self.spec.transport == "stdio":
            return await self._send_request_stdio(method, params)
        return await self._send_request_http(method, params)

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _send_request_stdio(self, method: str, params: dict) -> dict[str, Any]:
        """通过 stdio 发送 JSON-RPC 请求"""
        if not self._process or not self._process.stdin or not self._process.stdout:
            raise RuntimeError("MCP stdio not connected")

        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params,
        }
        payload = json.dumps(request, ensure_ascii=False) + "\n"
        self._process.stdin.write(payload.encode())
        await self._process.stdin.drain()

        # 读取响应
        line = await asyncio.wait_for(
            self._process.stdout.readline(),
            timeout=30.0,
        )
        response = json.loads(line.decode())

        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")
        result: dict[str, Any] = response.get("result", {})
        return result

    async def _send_request_http(self, method: str, params: dict) -> dict[str, Any]:
        """通过 HTTP 发送 JSON-RPC 请求"""
        if not self._session:
            raise RuntimeError("MCP http not connected")

        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params,
        }
        resp = await self._session.post("/", json=request)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"MCP error: {data['error']}")
        result: dict[str, Any] = data.get("result", {})
        return result

    @property
    def is_connected(self) -> bool:
        return self._connected


class MCPRegistry:
    """
    MCP 工具注册中心

    管理多个 MCP Server 连接，将外部工具自动注册到 ClawHermes 的 ToolRegistry
    """

    def __init__(self, tool_registry):
        """
        :param tool_registry: clawhermes.agent.loop.ToolRegistry 实例
        """
        from clawhermes.agent.loop import ToolDef
        self._tool_registry = tool_registry
        self._ToolDef = ToolDef
        self._clients: dict[str, MCPClient] = {}
        self._server_tools: dict[str, list[str]] = {}  # server_name → [tool_name, ...]

    async def add_server(self, spec: MCPServerSpec) -> list[str]:
        """
        添加并连接一个 MCP Server，自动发现并注册其工具

        :return: 注册的工具名称列表
        """
        if spec.name in self._clients:
            raise ValueError(f"MCP server already registered: {spec.name}")

        client = MCPClient(spec)
        try:
            await client.connect()
        except Exception as e:
            logger.error("Failed to connect MCP server '%s': %s", spec.name, e)
            raise

        self._clients[spec.name] = client

        # 发现并注册工具
        tools = await client.list_tools()
        registered = []
        for tool in tools:
            tool_name = f"mcp_{spec.name}_{tool['name']}"
            tool_def = self._ToolDef(
                name=tool_name,
                description=f"[MCP:{spec.name}] {tool.get('description', '')}",
                parameters=tool.get("inputSchema", {"type": "object", "properties": {}}),
                handler=self._make_handler(spec.name, tool["name"]),
                group=f"mcp.{spec.name}",
            )
            self._tool_registry.register(tool_def)
            registered.append(tool_name)

        self._server_tools[spec.name] = registered
        logger.info(
            "MCP server '%s' registered with %d tools: %s",
            spec.name, len(registered), registered,
        )
        return registered

    async def remove_server(self, name: str) -> bool:
        """移除 MCP Server 并注销其工具"""
        if name not in self._clients:
            return False

        client = self._clients.pop(name)
        await client.disconnect()

        # 工具注册表中不直接支持注销，但可以从 MCP 工具列表中移除
        self._server_tools.pop(name, None)
        logger.info("MCP server removed: %s", name)
        return True

    def _make_handler(self, server_name: str, tool_name: str):
        """为 MCP 工具创建 async handler。

        返回协程函数，使得异步工具分派路径（ToolDispatcher._execute_single_tool_async）
        经 ``asyncio.iscoroutinefunction`` 判定为真后直接 ``await`` 调用，
        从而真正执行 ``client.call_tool``，而非返回占位结果。

        同步分派路径（_execute_single_tool）在无事件循环时仍可借助
        ``asyncio.run`` 正常执行。
        """
        async def handler(**kwargs) -> dict:
            client = self._clients.get(server_name)
            if not client:
                return {"error": f"MCP server not connected: {server_name}"}
            try:
                result = await client.call_tool(tool_name, kwargs)
                return {"result": result}
            except Exception as e:
                return {"error": str(e)}

        return handler

    async def disconnect_all(self) -> None:
        """断开所有 MCP Server 连接"""
        for name in list(self._clients.keys()):
            await self.remove_server(name)

    def get_server_tools(self, name: str) -> list[str]:
        """获取某个 MCP Server 注册的工具列表"""
        return self._server_tools.get(name, [])

    def list_servers(self) -> list[dict]:
        """列出所有 MCP Server"""
        return [
            {"name": name, "connected": client.is_connected, "tools": self._server_tools.get(name, [])}
            for name, client in self._clients.items()
        ]
