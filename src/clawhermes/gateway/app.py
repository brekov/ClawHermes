"""
ClawHermes - Gateway HTTP API
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from clawhermes.agent.loop import Agent, AgentConfig, ToolRegistry, HookManager, HookPoint
from clawhermes.agent.memory import MemoryManager, JSONMemoryProvider
from clawhermes.llm.provider import LLMProvider
from clawhermes.tools.builtin import register_builtin_tools

logger = logging.getLogger(__name__)

_agent: Agent | None = None
_memory: MemoryManager | None = None
_skill_manager = None
_sessions: dict[str, list[dict]] = {}
_start_time = time.time()


def _get_data_dir() -> str:
    return os.getenv("CH_DATA_DIR", os.path.expanduser("~/.clawhermes"))


def _auto_init():
    global _agent, _memory, _skill_manager
    if _agent is not None:
        return
    api_key = os.getenv("CH_GW_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return
    model = os.getenv("CH_GW_MODEL", "deepseek/deepseek-chat")
    try:
        data_dir = _get_data_dir()
        provider = LLMProvider(model=model, api_key=api_key)
        registry = ToolRegistry()
        register_builtin_tools(registry)
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(Path(data_dir)))
        try:
            from clawhermes.storage.chroma_memory import ChromaMemoryProvider
            memory.add_provider(ChromaMemoryProvider(Path(data_dir)))
        except Exception:
            pass
        _memory = memory

        from clawhermes.skills.manager import SkillManager, BackgroundReview, Curator
        sm = SkillManager(Path(data_dir) / "skills")
        _skill_manager = sm

        _agent = Agent(llm_provider=provider, tool_registry=registry,
                       config=AgentConfig(max_iterations=50),
                       memory_manager=memory, skill_manager=sm)

        reviewer = BackgroundReview(provider, memory, sm)
        def _on_end(**kw):
            convo = _agent.get_conversation() if _agent else []
            if convo:
                threading.Thread(target=reviewer.apply, args=(convo,), daemon=True).start()
        _agent.hooks.register(HookPoint.AFTER_AGENT_END, _on_end)

        curator = Curator(sm)
        def _curator_loop():
            while True:
                time.sleep(3600)
                try:
                    curator.run()
                except Exception:
                    pass
        threading.Thread(target=_curator_loop, daemon=True).start()

        logger.info("Agent 初始化完成: %s (%d tools)", model, len(registry.list()))
    except Exception as e:
        logger.error("Auto-init failed: %s", e)


def get_agent() -> Agent:
    if _agent is None:
        raise RuntimeError("Agent 未初始化")
    return _agent


def get_memory() -> MemoryManager:
    if _memory is None:
        raise RuntimeError("Memory 未初始化")
    return _memory


def get_skill_manager():
    from clawhermes.skills.manager import SkillManager
    return _skill_manager or SkillManager(Path(_get_data_dir()) / "skills")


class InitRequest(BaseModel):
    api_key: str | None = None
    model: str = "deepseek/deepseek-chat"
    base_url: str | None = None
    max_iterations: int = 50


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    model: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ClawHermes Gateway 启动")
    _auto_init()
    yield
    logger.info("ClawHermes Gateway 关闭")


app = FastAPI(title="ClawHermes Gateway", version="0.9.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.post("/init")
def initialize(req: InitRequest):
    global _agent, _memory, _skill_manager
    try:
        api_key = req.api_key or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise HTTPException(400, "请设置 api_key")
        data_dir = _get_data_dir()
        provider = LLMProvider(model=req.model, api_key=api_key,
                               base_url=req.base_url or os.getenv("DEEPSEEK_BASE_URL"))
        registry = ToolRegistry()
        register_builtin_tools(registry)
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(Path(data_dir)))
        try:
            from clawhermes.storage.chroma_memory import ChromaMemoryProvider
            memory.add_provider(ChromaMemoryProvider(Path(data_dir)))
        except Exception:
            pass
        _memory = memory

        from clawhermes.skills.manager import SkillManager, BackgroundReview, Curator
        sm = SkillManager(Path(data_dir) / "skills")
        _skill_manager = sm
        _agent = Agent(llm_provider=provider, tool_registry=registry,
                       config=AgentConfig(max_iterations=req.max_iterations),
                       memory_manager=memory, skill_manager=sm)
        reviewer = BackgroundReview(provider, memory, sm)
        def _on_end(**kw):
            convo = _agent.get_conversation() if _agent else []
            if convo:
                threading.Thread(target=reviewer.apply, args=(convo,), daemon=True).start()
        _agent.hooks.register(HookPoint.AFTER_AGENT_END, _on_end)
        curator = Curator(sm)
        def _loop():
            while True:
                time.sleep(3600)
                try:
                    curator.run()
                except Exception:
                    pass
        threading.Thread(target=_loop, daemon=True).start()
        return {"status": "ok", "model": req.model, "tools": len(registry.list())}
    except Exception as e:
        raise HTTPException(500, f"初始化失败: {e}")


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    agent = get_agent()
    sid = req.session_id or f"session_{uuid.uuid4().hex[:8]}"
    if sid not in _sessions:
        _sessions[sid] = []
    try:
        resp = agent.chat(req.message, session_id=sid)
        _sessions[sid].append({"role": "user", "content": req.message})
        _sessions[sid].append({"role": "assistant", "content": resp})
        return ChatResponse(response=resp, session_id=sid, model=agent.llm.model)
    except Exception as e:
        raise HTTPException(500, f"对话失败: {e}")


@app.get("/health")
def health():
    try:
        a = get_agent()
        tools = len(a.tools.list())
    except Exception:
        tools = 0
    return {"status": "ok", "version": "0.9.0", "uptime_seconds": int(time.time() - _start_time), "tools": tools}


@app.get("/tools")
def list_tools():
    agent = get_agent()
    return {"tools": [{"name": t.name, "description": t.description} for t in agent.tools.list()]}


@app.post("/memory/save")
def save_memory(content: str = Query(...), importance: float = 0.5):
    from clawhermes.types import MemoryScope
    get_memory().save(content, MemoryScope.USER, importance)
    return {"status": "ok"}


@app.get("/memory/search")
def search_memory(query: str = Query(...)):
    results = get_memory().search(query)
    return {"results": [{"content": r.content, "importance": r.importance} for r in results]}


@app.get("/skills")
def list_skills(status: str | None = None):
    sm = get_skill_manager()
    return {"skills": [{"name": s.name, "description": s.description,
                        "category": s.category, "status": s.status,
                        "usage_count": s.usage_count} for s in sm.list(status)]}


@app.post("/skills/create")
def create_skill(name: str = Query(...), content: str = Query(...), description: str = ""):
    sm = get_skill_manager()
    skill = sm.create(name, content, description)
    return {"status": "ok", "name": skill.name}


@app.post("/curator/run")
def run_curator(dry_run: bool = False):
    from clawhermes.skills.manager import Curator
    curator = Curator(get_skill_manager())
    stats = curator.run(dry_run=dry_run)
    return {"status": "ok", "stats": stats}


@app.get("/sessions")
def list_sessions():
    return {"sessions": list(_sessions.keys()), "count": len(_sessions)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("CH_GATEWAY_PORT", "18789")))
