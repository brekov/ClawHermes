"""
ClawHermes - Gateway HTTP API
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
from clawhermes.channel.adapter import ChannelManager, ChannelType, RESTAdapter
from clawhermes.channel.adapters.feishu import FeishuAdapter
from clawhermes.channel.config import build_adapter_config
from clawhermes.channel.adapters.wechat import WeChatAdapter, WeComAdapter
from clawhermes.channel.router import ChannelRouter, SessionRouter
from clawhermes.llm.provider import LLMProvider
from clawhermes.tools.builtin import register_builtin_tools

logger = logging.getLogger(__name__)


class GatewayState:
    def __init__(self):
        self.agent: Agent | None = None
        self.memory: MemoryManager | None = None
        self.skill_manager = None
        self.delegate_manager: DelegateManager | None = None
        self.session_mgr: SessionManager | None = None
        self.scheduler: CronScheduler | None = None
        self.channel_router: ChannelRouter | None = None
        self.feishu_adapter: Any = None  # FeishuAdapter | None
        self.start_time = time.time()
        self.wechat_adapter: Any = None  # WeChatAdapter | None
        self.wecom_adapter: Any = None  # WeComAdapter | None
        self._bg_tasks: set[asyncio.Task] = set()
        self._mcp_registry = None

    def is_initialized(self) -> bool:
        return self.agent is not None

    def get_agent(self) -> Agent:
        if self.agent is None:
            raise SessionNotFoundError("Agent 未初始化")
        return self.agent

    def get_memory(self) -> MemoryManager:
        if self.memory is None:
            raise SessionNotFoundError("Memory 未初始化")
        return self.memory

    def get_skill_manager(self):
        from clawhermes.skills.manager import SkillManager
        return self.skill_manager or SkillManager(Path(_get_data_dir()) / "skills")

    async def initialize(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        max_iterations: int = 50,
        profile: str = "standard",
    ):
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

        # BackgroundReview：fire-and-forget，用 asyncio.to_thread 避免阻塞事件循环
        reviewer = BackgroundReview(provider, memory, sm)
        def _on_end(**kw):
            convo = agent.get_conversation()
            if convo:
                task = asyncio.create_task(
                    asyncio.to_thread(reviewer.apply, convo),
                    name="background_review",
                )
                self._bg_tasks.add(task)
                task.add_done_callback(self._bg_tasks.discard)
        agent.hooks.register(HookPoint.AFTER_AGENT_END, _on_end)

        # Curator：每小时运行，纯 asyncio 循环
        curator = Curator(sm)
        async def _curator_loop():
            while True:
                await asyncio.sleep(3600)
                try:
                    curator.run()
                except Exception:
                    pass
        curator_task = asyncio.create_task(_curator_loop(), name="curator_loop")
        self._bg_tasks.add(curator_task)
        curator_task.add_done_callback(self._bg_tasks.discard)

        # Scheduler：asyncio 原生
        scheduler = CronScheduler(data_dir)
        scheduler.set_executor(lambda task, sid: agent.chat(task, session_id=sid))
        await scheduler.start()

        channel_manager = ChannelManager()
        rest_adapter = RESTAdapter()
        channel_manager.register("rest", rest_adapter)

        # ── 渠道初始化（YAML 配置为单一来源）──
        # .env → ${VAR} 插值 → channels/<name>.yaml → build_adapter_config
        # 详见 docs/architecture.md "渠道配置格式"

        # WeChat/WeCom Adapter（需安装 clawhermes-weixin）
        if WeChatAdapter is not None:
            wx_cfg = build_adapter_config("wechat")
            wx_session_key = wx_cfg.get("session_key", "")
            wx_bot_key = wx_cfg.get("bot_key", "")
            if wx_session_key:
                self.wechat_adapter = WeChatAdapter({"session_key": wx_session_key})
                channel_manager.register("wechat", self.wechat_adapter)
                logger.info("WeChat Adapter 已启用（iLink 长轮询）")
            if wx_bot_key:
                self.wecom_adapter = WeComAdapter({"bot_key": wx_bot_key})
                channel_manager.register("wecom", self.wecom_adapter)
                logger.info("WeCom Adapter 已启用（Webhook 模式）")

        # Feishu Adapter（需安装 clawhermes-lark）
        if FeishuAdapter is not None:
            fa_cfg = build_adapter_config("feishu")
            if fa_cfg.get("app_id") and fa_cfg.get("app_secret"):
                adapter_cfg = {
                    "app_id": fa_cfg["app_id"],
                    "app_secret": fa_cfg["app_secret"],
                    "verification_token": fa_cfg.get("verification_token", ""),
                    "encrypt_key": fa_cfg.get("encrypt_key", ""),
                    "domain": fa_cfg.get("domain", "feishu"),
                    "connection_mode": fa_cfg.get("connection_mode", "websocket"),
                    "bot_open_id": fa_cfg.get("bot_open_id", ""),
                    "bot_user_id": fa_cfg.get("bot_user_id", ""),
                    "bot_name": fa_cfg.get("bot_name", ""),
                    "group_policy": fa_cfg.get("group_policy", "allowlist"),
                    "allowed_group_users": fa_cfg.get("allowed_group_users", []),
                    "admins": fa_cfg.get("admins", []),
                    "allow_bots": fa_cfg.get("allow_bots", "none"),
                    "require_mention": _to_bool(fa_cfg.get("require_mention", True)),
                    "webhook_host": fa_cfg.get("webhook_host", "0.0.0.0"),
                    "webhook_port": int(fa_cfg.get("webhook_port", 8080)),
                    "webhook_path": fa_cfg.get("webhook_path", "/feishu/webhook"),
                    "ws_reconnect_nonce": int(fa_cfg.get("ws_reconnect_nonce", 30)),
                    "ws_reconnect_interval": int(fa_cfg.get("ws_reconnect_interval", 120)),
                    "ws_ping_interval": fa_cfg.get("ws_ping_interval"),
                    "ws_ping_timeout": fa_cfg.get("ws_ping_timeout"),
                    "log_level": int(fa_cfg.get("log_level", 20)),
                    "max_retries": int(fa_cfg.get("max_retries", 3)),
                    "retry_delay": float(fa_cfg.get("retry_delay", 1.0)),
                    "dedup_cache_size": int(fa_cfg.get("dedup_cache_size", 1024)),
                    "reactions_enabled": _to_bool(fa_cfg.get("reactions_enabled", True)),
                }
                self.feishu_adapter = FeishuAdapter(adapter_cfg)
                channel_manager.register("feishu", self.feishu_adapter)
                logger.info("Feishu Adapter 已启用（clawhermes-lark）")
        session_router = SessionRouter()
        channel_router = ChannelRouter(
            channel_manager=channel_manager,
            session_router=session_router,
        )
        channel_router.set_agent_handler(lambda msg, session_id="": agent.chat(msg, session_id=session_id))
        channel_router.set_session_creator(lambda: session_mgr.create_session())

        self.agent = agent
        self.memory = memory
        self.skill_manager = sm
        self.delegate_manager = delegate_mgr
        self.session_mgr = session_mgr
        self.scheduler = scheduler
        self.channel_router = channel_router

        logger.info("Agent 初始化完成: %s (%d tools, profile=%s)", model, len(registry.list()), profile)

    async def shutdown(self):
        """优雅关闭所有后台任务"""
        if self.scheduler:
            await self.scheduler.stop()
        for task in self._bg_tasks:
            if not task.done():
                task.cancel()
        if self._bg_tasks:
            await asyncio.gather(*self._bg_tasks, return_exceptions=True)
        self._bg_tasks.clear()


_state = GatewayState()


def _get_data_dir() -> str:
    return os.getenv("CH_DATA_DIR", os.path.expanduser("~/.clawhermes"))


async def _auto_init():
    if _state.is_initialized():
        return
    api_key = os.getenv("CH_GW_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return
    model = os.getenv("CH_GW_MODEL", "deepseek/deepseek-chat")
    profile = os.getenv("CH_TOOLS_PROFILE", "standard")
    try:
        await _state.initialize(api_key=api_key, model=model, profile=profile)
    except ClawHermesError as e:
        logger.error("Auto-init failed: %s", e)
    except Exception as e:
        logger.error("Auto-init failed: %s", e)


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
    await _auto_init()
    yield
    logger.info("ClawHermes Gateway 关闭")
    await _state.shutdown()


app = FastAPI(title="ClawHermes Gateway", version="0.14.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.post("/init")
async def initialize(req: InitRequest):
    try:
        api_key = req.api_key or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise HTTPException(400, "请设置 api_key")
        base_url = req.base_url or os.getenv("DEEPSEEK_BASE_URL")
        await _state.initialize(
            api_key=api_key,
            model=req.model,
            base_url=base_url,
            max_iterations=req.max_iterations,
            profile=req.profile,
        )
        assert _state.agent is not None
        return {
            "status": "ok",
            "model": req.model,
            "tools": len(_state.agent.tools.list()),
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
    agent = _state.get_agent()
    if _state.session_mgr is None:
        raise HTTPException(500, "Session 管理器未初始化")

    if req.session_id:
        try:
            _state.session_mgr.get_session(req.session_id)
        except SessionNotFoundError:
            raise HTTPException(404, f"会话不存在: {req.session_id}")
        sid = req.session_id
    else:
        sid = _state.session_mgr.create_session()

    try:
        if _state.channel_router:
            response = _state.channel_router.route_message(
                content=req.message,
                channel_type=ChannelType.REST,
                user_id="rest_user",
                session_id=sid,
            )
        else:
            response = agent.chat(req.message, session_id=sid)

        model_name = agent.llm.model if hasattr(agent, 'llm') else "unknown"
        return ChatResponse(response=response, session_id=sid, model=model_name)
    except LLMRateLimitError as e:
        retry = getattr(e, 'retry_after', 60)
        raise HTTPException(429, f"LLM 速率限制，{retry}秒后重试", headers={"Retry-After": str(retry)})
    except LLMConnectionError as e:
        raise HTTPException(502, f"LLM 连接失败: {e}")
    except LLMError as e:
        raise HTTPException(500, f"LLM 调用失败: {e}")
    except ClawHermesError as e:
        raise HTTPException(500, f"Agent 错误: {e}")
    except Exception as e:
        logger.exception("Unexpected error in chat")
        raise HTTPException(500, f"内部错误: {e}")


@app.get("/health")
def health():
    info = {
        "status": "ok",
        "initialized": _state.is_initialized(),
        "uptime": round(time.time() - _state.start_time, 1),
    }
    if _state.agent:
        info["model"] = _state.agent.llm.model if hasattr(_state.agent, 'llm') else "unknown"
        info["tools"] = len(_state.agent.tools.list())
    if _state.scheduler:
        info["cron_jobs"] = _state.scheduler.job_count
    if _state.channel_router:
        info["queue_size"] = _state.channel_router.get_queue_size()
        info["active_session"] = _state.channel_router.get_active_session()
    return info


@app.get("/tools")
def list_tools():
    agent = _state.get_agent()
    return {"tools": agent.tools.schemas()}


@app.post("/memory/save")
def save_memory(content: str = Query(...), importance: float = 0.5, scope: str = "user"):
    from clawhermes.types import MemoryScope
    memory = _state.get_memory()
    try:
        ms = MemoryScope(scope)
    except ValueError:
        ms = MemoryScope.USER
    memory.save(content=content, importance=importance, scope=ms)
    return {"status": "ok"}


@app.get("/memory/search")
def search_memory(query: str = Query(...)):
    memory = _state.get_memory()
    results = memory.search(query)
    return {"results": [{"content": r.content, "importance": r.importance} for r in results]}


@app.get("/skills")
def list_skills(status: str | None = None):
    sm = _state.get_skill_manager()
    return {"skills": [{"name": s.name, "description": s.description,
                        "category": s.category, "status": s.status,
                        "usage_count": s.usage_count} for s in sm.list(status)]}


@app.post("/skills/create")
def create_skill(name: str = Query(...), content: str = Query(...), description: str = ""):
    sm = _state.get_skill_manager()
    skill = sm.create(name, content, description)
    return {"status": "ok", "name": skill.name}


@app.post("/curator/run")
def run_curator(dry_run: bool = False):
    from clawhermes.skills.manager import Curator
    curator = Curator(_state.get_skill_manager())
    stats = curator.run(dry_run=dry_run)
    return {"status": "ok", "stats": stats}


@app.get("/sessions")
def list_sessions(limit: int = 50):
    if _state.session_mgr is None:
        return {"sessions": [], "count": 0}
    sessions = _state.session_mgr.list_sessions(limit=limit)
    return {"sessions": sessions, "count": len(sessions)}


@app.get("/sessions/{session_id}")
def get_session(session_id: str):
    if _state.session_mgr is None:
        raise HTTPException(500, "Session 管理器未初始化")
    try:
        info = _state.session_mgr.get_session(session_id)
        messages = _state.session_mgr.get_messages(session_id)
        return {"session": info, "messages": messages}
    except SessionNotFoundError as e:
        raise HTTPException(404, str(e))


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    if _state.session_mgr is None:
        raise HTTPException(500, "Session 管理器未初始化")
    if _state.session_mgr.delete_session(session_id):
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
    if _state.scheduler is None:
        raise HTTPException(500, "调度器未初始化")
    try:
        mode = ScheduleMode(req.mode)
        if mode == ScheduleMode.CRON:
            spec = ScheduleSpec.cron(req.minute, req.hour, req.day_of_week)
        elif mode == ScheduleMode.ONESHOT:
            spec = ScheduleSpec.oneshot(delay_seconds=req.delay_seconds)
        else:
            spec = ScheduleSpec.interval(req.interval_seconds)
        job = _state.scheduler.create_job(req.name, req.task, spec, session_id=req.session_id)
        return {"status": "ok", "job": job.to_dict()}
    except ValueError as e:
        raise HTTPException(400, f"无效的调度模式: {e}")


@app.get("/cron/jobs")
def list_cron_jobs(status: str | None = None):
    if _state.scheduler is None:
        return {"jobs": [], "count": 0}
    jobs = _state.scheduler.list_jobs(status=status)
    return {"jobs": [j.to_dict() for j in jobs], "count": len(jobs)}


@app.get("/cron/jobs/{job_id}")
def get_cron_job(job_id: str):
    if _state.scheduler is None:
        raise HTTPException(500, "调度器未初始化")
    job = _state.scheduler.get_job(job_id)
    if job is None:
        raise HTTPException(404, f"任务不存在: {job_id}")
    return {"job": job.to_dict()}


@app.delete("/cron/jobs/{job_id}")
def delete_cron_job(job_id: str):
    if _state.scheduler is None:
        raise HTTPException(500, "调度器未初始化")
    if _state.scheduler.delete_job(job_id):
        return {"status": "ok"}
    raise HTTPException(404, f"任务不存在: {job_id}")


@app.post("/cron/jobs/{job_id}/pause")
def pause_cron_job(job_id: str):
    if _state.scheduler is None:
        raise HTTPException(500, "调度器未初始化")
    if _state.scheduler.pause_job(job_id):
        return {"status": "ok"}
    raise HTTPException(400, f"无法暂停任务: {job_id}")


@app.post("/cron/jobs/{job_id}/resume")
def resume_cron_job(job_id: str):
    if _state.scheduler is None:
        raise HTTPException(500, "调度器未初始化")
    if _state.scheduler.resume_job(job_id):
        return {"status": "ok"}
    raise HTTPException(400, f"无法恢复任务: {job_id}")


@app.get("/channels")
def list_channels():
    if _state.channel_router is None:
        return {"channels": [], "count": 0}
    return {"channels": _state.channel_router.list_channels()}


@app.get("/channels/sessions")
def list_channel_sessions():
    if _state.channel_router is None:
        return {"mappings": [], "count": 0}
    return {"mappings": _state.channel_router.session_router.list_mappings()}



@app.api_route("/wechat/webhook", methods=["POST"])
async def wechat_webhook(request: Request):
    """个人微信 Webhook 端点（兼容 iLink 回调）"""
    if _state.wechat_adapter is None:
        raise HTTPException(501, "WeChat Adapter 未启用")
    body = await request.json()
    result = await _state.wechat_adapter.handle_webhook(body)
    return result


@app.api_route("/wecom/webhook", methods=["POST"])
async def wecom_webhook(request: Request):
    """企业微信 Webhook 端点"""
    if _state.wecom_adapter is None:
        raise HTTPException(501, "WeCom Adapter 未启用")
    body = await request.json()
    result = await _state.wecom_adapter.handle_webhook(body)
    return result


if __name__ == "__main__":
    import uvicorn


def _to_bool(val: Any) -> bool:
    """将各种类型转换为 bool"""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return bool(val)

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("CH_GATEWAY_PORT", "18789")))


# ============================================================
# Feishu Webhook（飞书消息事件回调）
# ============================================================

@app.api_route("/feishu/webhook", methods=["POST"])
async def feishu_webhook(request: Request):
    """飞书事件回调端点（需启用 clawhermes-lark）"""
    if _state.feishu_adapter is None:
        raise HTTPException(503, "Feishu Adapter 未启用")
    body = await request.json()
    result = await _state.feishu_adapter.handle_webhook(body)
    return JSONResponse(content=result)


# ============================================================
# MCP (Model Context Protocol) 集成端点 (M3.7)
# ============================================================

class MCPAddRequest(BaseModel):
    name: str
    transport: str = "stdio"
    command: str | None = None
    args: list[str] = []
    url: str | None = None


@app.post("/mcp/servers")
async def add_mcp_server(req: MCPAddRequest):
    """添加 MCP Server 并自动注册其工具"""
    if _state.agent is None:
        raise HTTPException(400, "请先初始化 Agent (/init)")

    from clawhermes.mcp.client import MCPRegistry, MCPServerSpec

    if not hasattr(_state, '_mcp_registry') or _state._mcp_registry is None:
        _state._mcp_registry = MCPRegistry(_state.agent.tools)

    spec = MCPServerSpec(
        name=req.name,
        transport=req.transport,
        command=req.command,
        args=req.args,
        url=req.url,
    )
    try:
        tools = await _state._mcp_registry.add_server(spec)
        return {"status": "ok", "server": req.name, "tools": tools, "count": len(tools)}
    except Exception as e:
        raise HTTPException(500, f"MCP Server 连接失败: {e}")


@app.get("/mcp/servers")
def list_mcp_servers():
    """列出所有 MCP Server"""
    if not hasattr(_state, '_mcp_registry') or _state._mcp_registry is None:
        return {"servers": [], "count": 0}
    return {"servers": _state._mcp_registry.list_servers(), "count": len(_state._mcp_registry.list_servers())}


@app.delete("/mcp/servers/{name}")
async def remove_mcp_server(name: str):
    """移除 MCP Server"""
    if not hasattr(_state, '_mcp_registry') or _state._mcp_registry is None:
        raise HTTPException(404, "无 MCP Server")
    if await _state._mcp_registry.remove_server(name):
        return {"status": "ok"}
    raise HTTPException(404, f"MCP Server 未找到: {name}")
