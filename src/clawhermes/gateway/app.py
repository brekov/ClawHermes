"""
ClawHermes - Gateway HTTP API
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from clawhermes import __version__
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
        # M14: _auto_init 失败时记录错误，/health 返回 degraded
        self._init_error: str | None = None

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
                except Exception as e:
                    logger.warning("Curator run failed: %s", e)
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
        # C1 完善：关闭 DelegateManager 线程池，避免进程退出前仍持有工作线程
        if self.delegate_manager:
            try:
                self.delegate_manager.shutdown(wait=True)
            except Exception as e:
                logger.error("Delegate manager shutdown failed: %s", e)
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
        _state._init_error = None
    except ClawHermesError as e:
        _state._init_error = str(e)
        logger.error("Auto-init failed: %s", e)
    except Exception as e:
        _state._init_error = str(e)
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


def _validate_gateway_security(host: str, secret: str) -> None:
    """fail-fast: 公网监听（0.0.0.0 / ::）必须配置网关密钥，否则拒绝启动。

    防止用户在公网暴露无鉴权的 Gateway。在 __main__ 启动 uvicorn 前调用。
    """
    if not secret and host in ("0.0.0.0", "::"):
        logger.error(
            "CH_GATEWAY_SECRET 未配置且监听地址为 %s，拒绝启动（公网暴露无鉴权）", host
        )
        sys.exit(1)


def _validate_cors_config(allow_origins: list[str], allow_credentials: bool) -> None:
    """fail-fast: CORS 凭证与通配源互斥（浏览器规范禁止此组合）。

    allow_credentials=True 且 allow_origins=['*'] 会被浏览器拒绝，
    启动时直接报错而非运行时静默失效。
    """
    if allow_credentials and allow_origins == ["*"]:
        logger.error(
            "CORS 配置冲突：allow_credentials=True 与 allow_origins=['*'] 互斥，拒绝启动"
        )
        sys.exit(1)


# CORS 配置：通配源时禁用 credentials（浏览器规范），并 fail-fast 校验互斥
_cors_allow_credentials = _cors_origins != ["*"]
_validate_cors_config(_cors_origins, _cors_allow_credentials)

app = FastAPI(title="ClawHermes Gateway", version=__version__, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# M14: 初始化守卫白名单 — /health（degraded 返回）和 /init（手动初始化入口）不受 503 阻断
_INIT_GUARD_EXEMPT_PATHS = frozenset({"/health", "/init", "/docs", "/openapi.json", "/redoc"})


@app.middleware("http")
async def _init_guard_middleware(request: Request, call_next):
    """初始化守卫：_auto_init 失败后非白名单端点返回 503，/health 返回 degraded 状态。

    仅在 _init_error 被设置（auto-init 明确失败）时阻断，而非所有"未初始化"场景。
    正常的未初始化场景（如未配置 API key）由各端点自行处理错误。
    放在 _gateway_secret_middleware 之前定义（内层），使密钥校验先执行（外层）。
    """
    path = request.url.path
    if path == "/health":
        if _state._init_error:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "degraded",
                    "error": _state._init_error,
                    "initialized": False,
                    "uptime": round(time.time() - _state.start_time, 1),
                },
            )
        return await call_next(request)
    if _state._init_error and path not in _INIT_GUARD_EXEMPT_PATHS:
        return JSONResponse(
            status_code=503,
            content={
                "detail": f"Gateway 初始化失败: {_state._init_error}",
                "status": "degraded",
            },
        )
    return await call_next(request)


@app.middleware("http")
async def _gateway_secret_middleware(request: Request, call_next):
    """网关密钥校验：配置了 CH_GATEWAY_SECRET 时，除 /health 外所有请求需携带 X-Gateway-Secret 头。

    使用 hmac.compare_digest 进行恒定时间比较，避免计时侧信道攻击。
    """
    if _gateway_secret and request.url.path != "/health":
        received = request.headers.get("X-Gateway-Secret", "")
        if not hmac.compare_digest(received, _gateway_secret):
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

    # fail-fast: 公网监听必须配置 secret，防止无鉴权暴露
    _validate_gateway_security(args.host, _gateway_secret)

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


def _to_bool(val: Any) -> bool:
    """将各种类型转换为 bool"""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return bool(val)
