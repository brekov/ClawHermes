"""ClawHermes Gateway - Misc routes (/init, /health, /tools, /memory, /skills, /curator)"""
from __future__ import annotations

import os
import time

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import clawhermes.gateway.app as _gw
from clawhermes.agent.exceptions import ClawHermesError

router = APIRouter()


class InitRequest(BaseModel):
    api_key: str | None = None
    model: str = "deepseek/deepseek-chat"
    base_url: str | None = None
    max_iterations: int = 50
    profile: str = "standard"


@router.post("/init")
async def initialize(req: InitRequest):
    try:
        api_key = req.api_key or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise HTTPException(400, "请设置 api_key")
        base_url = req.base_url or os.getenv("DEEPSEEK_BASE_URL")
        await _gw._state.initialize(
            api_key=api_key,
            model=req.model,
            base_url=base_url,
            max_iterations=req.max_iterations,
            profile=req.profile,
        )
        assert _gw._state.agent is not None  # noqa: S101  mypy 类型收窄
        return {
            "status": "ok",
            "model": req.model,
            "tools": len(_gw._state.agent.tools.list()),
            "profile": req.profile,
        }
    except ClawHermesError as e:
        raise HTTPException(500, f"初始化失败: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"初始化失败: {e}")


@router.get("/health")
def health():
    info = {
        "status": "ok",
        "initialized": _gw._state.is_initialized(),
        "uptime": round(time.time() - _gw._state.start_time, 1),
    }
    if _gw._state.agent:
        info["model"] = _gw._state.agent.llm.model if hasattr(_gw._state.agent, 'llm') else "unknown"
        info["tools"] = len(_gw._state.agent.tools.list())
    if _gw._state.scheduler:
        info["cron_jobs"] = _gw._state.scheduler.job_count
    if _gw._state.channel_router:
        info["queue_size"] = _gw._state.channel_router.get_queue_size()
        info["active_session"] = _gw._state.channel_router.get_active_session()
    return info


@router.get("/tools")
def list_tools():
    agent = _gw._state.get_agent()
    return {"tools": agent.tools.schemas()}


@router.post("/memory/save")
def save_memory(content: str = Query(...), importance: float = 0.5, scope: str = "user"):
    from clawhermes.types import MemoryScope
    memory = _gw._state.get_memory()
    try:
        ms = MemoryScope(scope)
    except ValueError:
        ms = MemoryScope.USER
    memory.save(content=content, importance=importance, scope=ms)
    return {"status": "ok"}


@router.get("/memory/search")
def search_memory(query: str = Query(...)):
    memory = _gw._state.get_memory()
    results = memory.search(query)
    return {"results": [{"content": r.content, "importance": r.importance} for r in results]}


@router.get("/skills")
def list_skills(status: str | None = None):
    sm = _gw._state.get_skill_manager()
    return {"skills": [{"name": s.name, "description": s.description,
                        "category": s.category, "status": s.status,
                        "usage_count": s.usage_count} for s in sm.list(status)]}


@router.post("/skills/create")
def create_skill(name: str = Query(...), content: str = Query(...), description: str = ""):
    sm = _gw._state.get_skill_manager()
    skill = sm.create(name, content, description)
    return {"status": "ok", "name": skill.name}


@router.post("/curator/run")
def run_curator(dry_run: bool = False):
    from clawhermes.skills.manager import Curator
    curator = Curator(_gw._state.get_skill_manager())
    stats = curator.run(dry_run=dry_run)
    return {"status": "ok", "stats": stats}
