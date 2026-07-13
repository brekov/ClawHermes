"""ClawHermes Gateway - MCP routes (/mcp/servers)"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import clawhermes.gateway.app as _gw

router = APIRouter()


class MCPAddRequest(BaseModel):
    name: str
    transport: str = "stdio"
    command: str | None = None
    args: list[str] = []
    url: str | None = None


@router.post("/mcp/servers")
async def add_mcp_server(req: MCPAddRequest):
    """添加 MCP Server 并自动注册其工具"""
    if _gw._state.agent is None:
        raise HTTPException(400, "请先初始化 Agent (/init)")

    from clawhermes.mcp.client import MCPRegistry, MCPServerSpec

    if not hasattr(_gw._state, '_mcp_registry') or _gw._state._mcp_registry is None:
        _gw._state._mcp_registry = MCPRegistry(_gw._state.agent.tools)

    spec = MCPServerSpec(
        name=req.name,
        transport=req.transport,
        command=req.command,
        args=req.args,
        url=req.url,
    )
    try:
        tools = await _gw._state._mcp_registry.add_server(spec)
        return {"status": "ok", "server": req.name, "tools": tools, "count": len(tools)}
    except Exception as e:
        raise HTTPException(500, f"MCP Server 连接失败: {e}")


@router.get("/mcp/servers")
def list_mcp_servers():
    """列出所有 MCP Server"""
    if not hasattr(_gw._state, '_mcp_registry') or _gw._state._mcp_registry is None:
        return {"servers": [], "count": 0}
    return {"servers": _gw._state._mcp_registry.list_servers(), "count": len(_gw._state._mcp_registry.list_servers())}


@router.delete("/mcp/servers/{name}")
async def remove_mcp_server(name: str):
    """移除 MCP Server"""
    if not hasattr(_gw._state, '_mcp_registry') or _gw._state._mcp_registry is None:
        raise HTTPException(404, "无 MCP Server")
    if await _gw._state._mcp_registry.remove_server(name):
        return {"status": "ok"}
    raise HTTPException(404, f"MCP Server 未找到: {name}")
