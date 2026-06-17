"""
ClawHermes - Gateway HTTP API
"""
from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from clawhermes.agent.delegate import DelegateManager
from clawhermes.agent.exceptions import (
    ClawHermesError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    SessionNotFoundError,
)
from clawhermes.agent.loop import Agent, AgentConfig, HookPoint, ToolRegistry
from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager
from clawhermes.agent.scheduler import CronScheduler, ScheduleMode, ScheduleSpec
from clawhermes.agent.session import SessionManager
from clawhermes.llm.provider import LLMProvider
from clawhermes.tools.builtin import register_builtin_tools

logger = logging.getLogger(__name__)

_agent: Agent | None = None
_memory: MemoryManager | None = None
_skill_manager = None
_delegate_manager: DelegateManager | None = None
_session_mgr: SessionManager | None = None
_scheduler: CronScheduler | None = None
_start_time = time.time()


def _get_data_dir() -> str:
    return os.getenv("CH_DATA_DIR", os.path.expanduser("~/.clawhermes"))


def _create_agent_components(
    api_key: str,
    model: str,
    base_url: str | None = None,
    max_iterations: int = 50,
    profile: str = "standard",
) -> tuple[Agent, MemoryManager, object, DelegateManager, SessionManager, CronScheduler]:
    data_dir = _get_data_dir()
    provider = LLMProvider(model=model, api_key=api_key, base_url=base_url)
    registry = ToolRegistry()
    register_builtin_tools(registry, profile=profile)

    memory = MemoryManager()
    memory.add_provider(JSONMemoryProvider(Path(data_dir)))
    try:
        from clawhermes.storage.chroma_memory import ChromaMemoryProvider
        memory.add_provider(ChromaMemoryProvider(Path(data_dir)))
    except Exception:
        logger.info("ChromaDB 不可用，使用 JSON 记忆存储")

    from clawhermes.skills.manager import BackgroundReview, Curator, SkillManager
    sm = SkillManager(Path(data_dir) / "skills")

    delegate_mgr = DelegateManager(
        llm_provider=provider,
        tool_registry=registry,
        memory_manager=memory,
        skill_manager=sm,
    )

    session_mgr = SessionManager(data_dir)

    agent = Agent(
        llm_provider=provider,
        tool_registry=registry,
        config=AgentConfig(max_iterations=max_iterations),
        memory_manager=memory,
        skill_manager=sm,
        delegate_manager=delegate_mgr,
    )

    reviewer = BackgroundReview(provider, memory, sm)
    def _on_end(**kw):
        convo = agent.get_conversation()
        if convo:
            threading.Thread(target=reviewer.apply, args=(convo,), daemon=True).start()
    agent.hooks.register(HookPoint.AFTER_AGENT_END, _on_end)

    curator = Curator(sm)
    def _curator_loop():
        while True:
            time.sleep(3600)
            try:
                curator.run()
            except Exception:
                pass
    threading.Thread(target=_curator_loop, daemon=True).start()

    scheduler = CronScheduler(data_dir)

    logger.info("Agent 初始化完成: %s (%d tools, profile=%s)", model, len(registry.list()), profile)
    return agent, memory, sm, delegate_mgr, session_mgr, scheduler


def _auto_init():
    global _agent, _memory, _skill_manager, _delegate_manager, _session_mgr, _scheduler
    if _agent is not None:
        return
    api_key = os.getenv("CH_GW_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return
    model = os.getenv("CH_GW_MODEL", "deepseek/deepseek-chat")
    profile = os.getenv("CH_TOOLS_PROFILE", "standard")
    try:
        _agent, _memory, _skill_manager, _delegate_manager, _session_mgr, _scheduler = _create_agent_components(
            api_key=api_key, model=model, profile=profile,
        )
        if _agent is None or _scheduler is None:
            return
        _scheduler.set_executor(lambda task, sid: _agent.chat(task, session_id=sid))
        _scheduler.start()
    except ClawHermesError as e:
        logger.error("Auto-init failed: %s", e)
    except Exception as e:
        logger.error("Auto-init failed: %s", e)


def get_agent() -> Agent:
    if _agent is None:
        raise SessionNotFoundError("Agent 未初始化")
    return _agent


def get_memory() -> MemoryManager:
    if _memory is None:
        raise SessionNotFoundError("Memory 未初始化")
    return _memory


def get_skill_manager():
    from clawhermes.skills.manager import SkillManager
    return _skill_manager or SkillManager(Path(_get_data_dir()) / "skills")


class InitRequest(BaseModel):
    api_key: str | None = None
    model: str = "deepseek/deepseek-chat"
    base_url: str | None = None
    max_iterations: int = 50
    profile: str = "standard"


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


app = FastAPI(title="ClawHermes Gateway", version="0.11.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.post("/init")
def initialize(req: InitRequest):
    global _agent, _memory, _skill_manager, _delegate_manager, _session_mgr, _scheduler
    try:
        api_key = req.api_key or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise HTTPException(400, "请设置 api_key")
        base_url = req.base_url or os.getenv("DEEPSEEK_BASE_URL")
        _agent, _memory, _skill_manager, _delegate_manager, _session_mgr, _scheduler = _create_agent_components(
            api_key=api_key,
            model=req.model,
            base_url=base_url,
            max_iterations=req.max_iterations,
            profile=req.profile,
        )
        assert _agent is not None
        assert _scheduler is not None
        _scheduler.set_executor(lambda task, sid: _agent.chat(task, session_id=sid))
        _scheduler.start()
        return {
            "status": "ok",
            "model": req.model,
            "tools": len(_agent.tools.list()),
            "profile": req.profile,
        }
    except ClawHermesError as e:
        raise HTTPException(500, f"初始化失败: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"初始化失败: {e}")


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    agent = get_agent()
    if _session_mgr is None:
        raise HTTPException(500, "Session 管理器未初始化")

    if req.session_id:
        try:
            _session_mgr.get_session(req.session_id)
        except SessionNotFoundError:
            pass
        sid = req.session_id
    else:
        sid = _session_mgr.create_session()

    try:
        _session_mgr.add_message(sid, "user", req.message)
        resp = agent.chat(req.message, session_id=sid)
        _session_mgr.add_message(sid, "assistant", resp)
        return ChatResponse(response=resp, session_id=sid, model=agent.llm.model)
    except LLMRateLimitError as e:
        raise HTTPException(429, f"速率限制: {e}")
    except LLMConnectionError as e:
        raise HTTPException(502, f"LLM 连接失败: {e}")
    except LLMError as e:
        raise HTTPException(500, f"LLM 错误: {e}")
    except ClawHermesError as e:
        raise HTTPException(500, f"对话失败: {e}")
    except Exception as e:
        raise HTTPException(500, f"对话失败: {e}")


@app.get("/health")
def health():
    try:
        a = get_agent()
        tools = len(a.tools.list())
    except Exception:
        tools = 0
    return {
        "status": "ok",
        "version": "0.11.0",
        "uptime_seconds": int(time.time() - _start_time),
        "tools": tools,
    }


@app.get("/tools")
def list_tools():
    agent = get_agent()
    return {"tools": [
        {
            "name": t.name,
            "description": t.description,
            "parallel_safe": t.parallel_safe,
            "group": t.group,
        }
        for t in agent.tools.list()
    ]}


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
def list_sessions(limit: int = 50):
    if _session_mgr is None:
        return {"sessions": [], "count": 0}
    sessions = _session_mgr.list_sessions(limit=limit)
    return {"sessions": sessions, "count": len(sessions)}


@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    if _session_mgr is None:
        raise HTTPException(500, "Session 管理器未初始化")
    try:
        info = _session_mgr.get_session(session_id)
        messages = _session_mgr.get_messages(session_id)
        return {"session": info, "messages": messages}
    except SessionNotFoundError as e:
        raise HTTPException(404, str(e))


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    if _session_mgr is None:
        raise HTTPException(500, "Session 管理器未初始化")
    if _session_mgr.delete_session(session_id):
        return {"status": "ok"}
    raise HTTPException(404, f"会话不存在: {session_id}")


class CronJobRequest(BaseModel):
    name: str
    task: str
    mode: str = "interval"
    interval_seconds: int = 3600
    minute: str = "*"
    hour: str = "*"
    day_of_week: str = "*"
    delay_seconds: int = 0
    session_id: str = ""


@app.post("/cron/jobs")
def create_cron_job(req: CronJobRequest):
    if _scheduler is None:
        raise HTTPException(500, "调度器未初始化")
    try:
        mode = ScheduleMode(req.mode)
        if mode == ScheduleMode.CRON:
            spec = ScheduleSpec.cron(req.minute, req.hour, req.day_of_week)
        elif mode == ScheduleMode.ONESHOT:
            spec = ScheduleSpec.oneshot(delay_seconds=req.delay_seconds)
        else:
            spec = ScheduleSpec.interval(req.interval_seconds)
        job = _scheduler.create_job(req.name, req.task, spec, session_id=req.session_id)
        return {"status": "ok", "job": job.to_dict()}
    except ValueError as e:
        raise HTTPException(400, f"无效的调度模式: {e}")


@app.get("/cron/jobs")
def list_cron_jobs(status: str | None = None):
    if _scheduler is None:
        return {"jobs": [], "count": 0}
    jobs = _scheduler.list_jobs(status=status)
    return {"jobs": [j.to_dict() for j in jobs], "count": len(jobs)}


@app.get("/cron/jobs/{job_id}")
def get_cron_job(job_id: str):
    if _scheduler is None:
        raise HTTPException(500, "调度器未初始化")
    job = _scheduler.get_job(job_id)
    if job is None:
        raise HTTPException(404, f"任务不存在: {job_id}")
    return {"job": job.to_dict()}


@app.delete("/cron/jobs/{job_id}")
def delete_cron_job(job_id: str):
    if _scheduler is None:
        raise HTTPException(500, "调度器未初始化")
    if _scheduler.delete_job(job_id):
        return {"status": "ok"}
    raise HTTPException(404, f"任务不存在: {job_id}")


@app.post("/cron/jobs/{job_id}/pause")
def pause_cron_job(job_id: str):
    if _scheduler is None:
        raise HTTPException(500, "调度器未初始化")
    if _scheduler.pause_job(job_id):
        return {"status": "ok"}
    raise HTTPException(400, f"无法暂停任务: {job_id}")


@app.post("/cron/jobs/{job_id}/resume")
def resume_cron_job(job_id: str):
    if _scheduler is None:
        raise HTTPException(500, "调度器未初始化")
    if _scheduler.resume_job(job_id):
        return {"status": "ok"}
    raise HTTPException(400, f"无法恢复任务: {job_id}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("CH_GATEWAY_PORT", "18789")))
