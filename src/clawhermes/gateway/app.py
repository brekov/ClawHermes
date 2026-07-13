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

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from clawhermes.agent.delegate import DelegateManager
from clawhermes.agent.exceptions import (
    ClawHermesError,
    SessionNotFoundError,
)
from clawhermes.agent.loop import Agent, AgentConfig, HookPoint, ToolRegistry
from clawhermes.agent.memory import JSONMemoryProvider, MemoryManager
from clawhermes.agent.scheduler import CronScheduler
from clawhermes.agent.session import SessionManager
from clawhermes.channel.adapter import ChannelManager, RESTAdapter
from clawhermes.channel.adapters.feishu import FeishuAdapter
from clawhermes.channel.adapters.qq import QQAdapter
from clawhermes.channel.adapters.wechat import WeChatAdapter, WeComAdapter
from clawhermes.channel.config import build_adapter_config
from clawhermes.channel.pairing import DMPairingManager
from clawhermes.channel.router import ChannelRouter, SessionRouter
from clawhermes.config import get_data_dir, load_env
from clawhermes.gateway.routers.channels import router as channels_router
from clawhermes.gateway.routers.chat import ChatRequest, ChatResponse
from clawhermes.gateway.routers.chat import router as chat_router
from clawhermes.gateway.routers.cron import CronJobRequest
from clawhermes.gateway.routers.cron import router as cron_router
from clawhermes.gateway.routers.dm import router as dm_router
from clawhermes.gateway.routers.mcp import MCPAddRequest
from clawhermes.gateway.routers.mcp import router as mcp_router
from clawhermes.gateway.routers.misc import InitRequest
from clawhermes.gateway.routers.misc import router as misc_router
from clawhermes.gateway.routers.sessions import router as sessions_router
from clawhermes.llm.provider import LLMProvider
from clawhermes.tools.builtin import register_builtin_tools

# 加载 $CH_DATA_DIR/.env → os.environ（不覆盖已存在的环境变量）
load_env()


logger = logging.getLogger(__name__)

# 确保渠道适配器诊断日志可见（默认 root logger 为 WARNING 会压住 INFO 日志）
logging.getLogger("clawhermes.lark").setLevel(logging.INFO)
logging.getLogger("clawhermes.channel").setLevel(logging.INFO)

# 请求/响应模型由各 routers/ 模块定义，在此重新导出以保持
# `from clawhermes.gateway.app import ChatRequest, ...` 向后兼容（被测试使用）。
__all__ = [
    "ChatRequest",
    "ChatResponse",
    "CronJobRequest",
    "GatewayState",
    "InitRequest",
    "MCPAddRequest",
    "app",
]


class GatewayState:
    def __init__(self):
        self.agent: Agent | None = None
        self.memory: MemoryManager | None = None
        self.skill_manager = None
        self.delegate_manager: DelegateManager | None = None
        self.session_mgr: SessionManager | None = None
        self.scheduler: CronScheduler | None = None
        self.channel_router: ChannelRouter | None = None
        self.pairing_manager: DMPairingManager | None = None
        self.feishu_adapter: Any = None  # FeishuAdapter | None
        self.start_time = time.time()
        self.wechat_adapter: Any = None  # WeChatAdapter | None
        self.wecom_adapter: Any = None  # WeComAdapter | None
        self.qq_adapter: Any = None  # QQAdapter | None
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
        return self.skill_manager or SkillManager(get_data_dir() / "skills")

    async def initialize(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        max_iterations: int = 50,
        profile: str = "standard",
    ):
        data_dir = get_data_dir()
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
            session_mgr=session_mgr,
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

        # QQ Adapter（需安装 clawhermes-qq）
        if QQAdapter is not None:
            qq_cfg = build_adapter_config("qq")
            if qq_cfg.get("app_id") and qq_cfg.get("token"):
                self.qq_adapter = QQAdapter({
                    "app_id": qq_cfg["app_id"],
                    "token": qq_cfg["token"],
                    "secret": qq_cfg.get("secret", ""),
                    "sandbox": _to_bool(qq_cfg.get("sandbox", True)),
                })
                channel_manager.register("qq", self.qq_adapter)
                logger.info("QQ Adapter 已启用（clawhermes-qq）")
        session_router = SessionRouter()
        pairing_manager = DMPairingManager(db_path=Path(data_dir) / "pairing_state.json")
        channel_router = ChannelRouter(
            channel_manager=channel_manager,
            session_router=session_router,
            pairing_manager=pairing_manager,
        )
        # agent.chat 是同步阻塞调用（内部调用 LLM），必须用 asyncio.to_thread 包装
        # 否则会在 router._process_queue 中阻塞事件循环，导致 WebSocket ping 超时断连
        async def _agent_handler(msg: str, session_id: str = "") -> str:
            return await asyncio.to_thread(agent.chat, msg, session_id=session_id)
        channel_router.set_agent_handler(_agent_handler)
        channel_router.set_session_creator(lambda: session_mgr.create_session())

        # 关键：启动 channel_router — 否则适配器不会 start()，_on_message 也不会被注册
        # 这会直接导致飞书消息收发完全无响应
        await channel_router.start()

        self.agent = agent
        self.memory = memory
        self.skill_manager = sm
        self.delegate_manager = delegate_mgr
        self.session_mgr = session_mgr
        self.scheduler = scheduler
        self.channel_router = channel_router
        self.pairing_manager = pairing_manager

        logger.info("Agent 初始化完成: %s (%d tools, profile=%s)", model, len(registry.list()), profile)

    async def shutdown(self):
        """优雅关闭所有后台任务"""
        if self.scheduler:
            await self.scheduler.stop()
        if self.channel_router:
            try:
                await self.channel_router.stop()
            except Exception as e:
                logger.error("Channel router stop failed: %s", e)
        for task in self._bg_tasks:
            if not task.done():
                task.cancel()
        if self._bg_tasks:
            await asyncio.gather(*self._bg_tasks, return_exceptions=True)
        self._bg_tasks.clear()


_state = GatewayState()


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ClawHermes Gateway 启动")
    await _auto_init()
    yield
    logger.info("ClawHermes Gateway 关闭")
    await _state.shutdown()


_cors_origins = [o.strip() for o in os.getenv("CH_CORS_ORIGINS", "*").split(",") if o.strip()]
_gateway_secret = os.getenv("CH_GATEWAY_SECRET", "")
app = FastAPI(title="ClawHermes Gateway", version="0.15.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=(_cors_origins != ["*"]),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _gateway_secret_middleware(request: Request, call_next):
    """网关密钥校验：配置了 CH_GATEWAY_SECRET 时，除 /health 外所有请求需携带 X-Gateway-Secret 头"""
    if _gateway_secret and request.url.path != "/health":
        if request.headers.get("X-Gateway-Secret") != _gateway_secret:
            return JSONResponse(status_code=401, content={"detail": "网关密钥无效或缺失"})
    return await call_next(request)


# ============================================================
# 路由注册 — 端点按功能分组到 routers/ 模块
# ============================================================
app.include_router(misc_router)
app.include_router(chat_router)
app.include_router(sessions_router)
app.include_router(cron_router)
app.include_router(channels_router)
app.include_router(mcp_router)
app.include_router(dm_router)


if __name__ == "__main__":
    import argparse

    import uvicorn  # noqa: F401

    parser = argparse.ArgumentParser(description="ClawHermes Gateway")
    parser.add_argument("--host", default=os.environ.get("CH_GATEWAY_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("CH_GATEWAY_PORT", "18789")))
    args = parser.parse_args()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


def _to_bool(val: Any) -> bool:
    """将各种类型转换为 bool"""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return bool(val)
