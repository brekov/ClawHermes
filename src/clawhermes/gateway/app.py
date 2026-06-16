"""
ClawHermes - Gateway 消息网关（FastAPI 常驻服务）
提供 REST API + 健康检查 + 会话管理
"""
from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from clawhermes.agent.loop import Agent, AgentConfig, ToolRegistry
from clawhermes.agent.memory import MemoryManager, JSONMemoryProvider
from clawhermes.llm.provider import LLMProvider
from clawhermes.tools.builtin import register_builtin_tools

logger = logging.getLogger(__name__)

# === 全局 Agent 实例 ===
_agent: Agent | None = None
_memory: MemoryManager | None = None
_sessions: dict[str, list[dict]] = {}


def _auto_init():
    """从环境变量自动初始化"""
    global _agent, _memory
    if _agent is not None:
        return
    api_key = os.getenv("CH_GW_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return
    model = os.getenv("CH_GW_MODEL", "deepseek/deepseek-chat")
    try:
        provider = LLMProvider(model=model, api_key=api_key)
        registry = ToolRegistry()
        register_builtin_tools(registry)
        data_dir = os.getenv("CH_DATA_DIR", os.path.expanduser("~/.clawhermes"))
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(data_dir))
        _memory = memory
        _agent = Agent(llm_provider=provider, tool_registry=registry, config=AgentConfig(max_iterations=50))
        logger.info("Agent auto-initialized: %s (%d tools)", model, len(registry.list()))
    except Exception as e:
        logger.warning("Auto-init skipped: %s", e)


def get_agent() -> Agent:
    global _agent
    if _agent is None:
        raise RuntimeError("Agent 未初始化，请先调用 POST /init")
    return _agent


def get_memory() -> MemoryManager:
    global _memory
    if _memory is None:
        raise RuntimeError("Memory 未初始化")
    return _memory


# === Pydantic Schemas ===

class InitRequest(BaseModel):
    api_key: str | None = None
    model: str = "deepseek/deepseek-chat"
    base_url: str | None = None
    max_iterations: int = 50


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    stream: bool = False


class ChatResponse(BaseModel):
    response: str
    session_id: str
    model: str
    usage: dict | None = None


class StatusResponse(BaseModel):
    status: str
    agent: str = "ClawHermes"
    version: str = "0.2.1"
    uptime: str = ""
    tools: int = 0
    sessions: int = 0
    memory_items: int = 0


# === App 生命周期 ===

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭"""
    logger.info("🚀 ClawHermes Gateway 启动")
    _auto_init()
    yield
    logger.info("👋 ClawHermes Gateway 关闭")


app = FastAPI(
    title="ClawHermes Gateway",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === API 端点 ===

@app.post("/init", summary="初始化 Agent")
def initialize(req: InitRequest):
    """配置 LLM Provider 并初始化 Agent"""
    global _agent, _memory

    try:
        api_key = req.api_key or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise HTTPException(400, "请在请求中提供 api_key 或设置 DEEPSEEK_API_KEY 环境变量")

        # LLM Provider
        provider = LLMProvider(
            model=req.model,
            api_key=api_key,
            base_url=req.base_url or os.getenv("DEEPSEEK_BASE_URL"),
        )

        # 工具注册
        registry = ToolRegistry()
        register_builtin_tools(registry)

        # 记忆系统
        data_dir = os.getenv("CH_DATA_DIR", os.path.expanduser("~/.clawhermes"))
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(data_dir))
        _memory = memory

        # Agent
        _agent = Agent(
            llm_provider=provider,
            tool_registry=registry,
            config=AgentConfig(max_iterations=req.max_iterations),
        )

        return {"status": "ok", "model": req.model, "tools": len(registry.list())}

    except Exception as e:
        raise HTTPException(500, f"初始化失败: {e}")


@app.post("/chat", summary="对话")
def chat(req: ChatRequest) -> ChatResponse:
    """发送消息并获取回复"""
    agent = get_agent()
    sid = req.session_id or f"session_{uuid.uuid4().hex[:8]}"

    if sid not in _sessions:
        _sessions[sid] = []

    try:
        resp = agent.chat(req.message, session_id=sid)
        _sessions[sid].append({"role": "user", "content": req.message})
        _sessions[sid].append({"role": "assistant", "content": resp})

        return ChatResponse(
            response=resp,
            session_id=sid,
            model=agent.llm.model,
        )
    except Exception as e:
        raise HTTPException(500, f"对话失败: {e}")


@app.get("/health", summary="健康检查")
def health() -> StatusResponse:
    """服务健康状态"""
    try:
        a = get_agent()
        tools = len(a.tools.list())
    except Exception:
        tools = 0

    return StatusResponse(
        status="ok",
        tools=tools,
        sessions=len(_sessions),
        memory_items=0,
    )


@app.get("/tools", summary="工具列表")
def list_tools():
    """列出所有已注册工具"""
    try:
        agent = get_agent()
        return {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "parallel_safe": t.parallel_safe,
                }
                for t in agent.tools.list()
            ]
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/memory/save", summary="保存记忆")
def save_memory(content: str, importance: float = 0.5):
    """保存一条记忆"""
    mem = get_memory()
    from clawhermes.types import MemoryScope
    mem.save(content, MemoryScope.USER, importance)
    return {"status": "ok"}


@app.get("/memory/search", summary="搜索记忆")
def search_memory(query: str):
    """搜索记忆"""
    mem = get_memory()
    results = mem.search(query)
    return {"results": [{"content": r.content, "importance": r.importance} for r in results]}


@app.get("/sessions", summary="会话列表")
def list_sessions():
    """列出当前活跃会话"""
    return {"sessions": list(_sessions.keys()), "count": len(_sessions)}


# === 直接启动 ===
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=18789)
