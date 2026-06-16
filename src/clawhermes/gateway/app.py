"""
ClawHermes - Gateway 消息网关（FastAPI 常驻服务）
集成 ChromaDB 向量检索、技能系统、Background Review、Curator、多渠道
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

# === 全局实例 ===
_agent: Agent | None = None
_memory: MemoryManager | None = None
_skill_manager = None
_reviewer = None
_curator = None
_gateway_manager = None
_sessions: dict[str, list[dict]] = {}
_start_time = time.time()


def _get_data_dir() -> str:
    return os.getenv("CH_DATA_DIR", os.path.expanduser("~/.clawhermes"))


def _start_bridge():
    """启动 Node SDK 长连接（收消息用）"""
    try:
        from clawhermes.gateway.bridge import get_bridge
        bridge = get_bridge()
        if bridge.start():
            logger.info("📡 Bridge 长连接已启动")
            # 注册消息接收回调
            def on_message(msg):
                logger.info("收到消息: %s", msg.get("text", "")[:50])
            bridge.on_message(on_message)
    except Exception as e:
        logger.warning("Bridge 启动失败（不影响基础功能）: %s", e)


def _auto_start_channels():
    """从 channels/*.yaml 配置自动启动渠道"""
    from clawhermes.gateway.channels import (
        GatewayManager, TelegramAdapter,
    )
    from clawhermes.gateway.platforms.feishu import FeishuAdapter
    from clawhermes.gateway.platforms.wechat import WeChatAdapter
    from clawhermes.gateway.platforms.wechat_corp import WeChatCorpAdapter
    from clawhermes.gateway.platforms.qq import QQAdapter
    from clawhermes.gateway.setup import load_channels

    channels = load_channels()
    if not channels:
        logger.info("无渠道配置，跳过（运行 clawhermes gateway setup 配置）")
        return

    gm = _get_gateway_manager()

    for name, cfg in channels.items():
        try:
            if name == "feishu":
                app_id = cfg.get("app_id")
                secret = cfg.get("app_secret")
                if app_id and secret:
                    gm.register("feishu", FeishuAdapter(app_id, secret))

            elif name == "wechat":
                bot_token = cfg.get("bot_token")
                if bot_token:
                    gm.register("wechat", WeChatAdapter(bot_token=bot_token))
                else:
                    corp_id = cfg.get("corp_id")
                    corp_secret = cfg.get("corp_secret")
                    agent_id = cfg.get("agent_id", 0)
                    if corp_id and corp_secret and agent_id:
                        gm.register("wechat", WeChatAdapter(corp_id, corp_secret, int(agent_id)))

            elif name == "wechat_corp":
                bot_token = cfg.get("bot_token")
                if bot_token:
                    gm.register("wechat_corp", WeChatCorpAdapter(bot_token=bot_token))

            elif name == "qq":
                ws_url = cfg.get("ws_url", "ws://127.0.0.1:6700")
                token = cfg.get("token", "")
                gm.register("qq", QQAdapter(ws_url, token))

            elif name == "telegram":
                token = cfg.get("token")
                if token:
                    gm.register("telegram", TelegramAdapter(token))

            logger.info("📡 渠道已配置: %s", name)
        except Exception as e:
            logger.warning("渠道 %s 配置失败: %s", name, e)

    gm.start_all()
    logger.info("✅ 所有渠道已启动")


def _auto_init():
    """从环境变量自动初始化（含 ChromaDB + Skills + Review + Curator）"""
    global _agent, _memory, _skill_manager, _reviewer, _curator

    if _agent is not None:
        return
    api_key = os.getenv("CH_GW_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return
    model = os.getenv("CH_GW_MODEL", "deepseek/deepseek-chat")

    try:
        data_dir = _get_data_dir()
        provider = LLMProvider(model=model, api_key=api_key)

        # 工具
        registry = ToolRegistry()
        register_builtin_tools(registry)

        # 记忆系统（JSON + ChromaDB 双存储）
        memory = MemoryManager()
        memory.add_provider(JSONMemoryProvider(Path(data_dir)))
        try:
            from clawhermes.storage.chroma_memory import ChromaMemoryProvider
            chroma = ChromaMemoryProvider(Path(data_dir))
            memory.add_provider(chroma)
            logger.info("ChromaDB 向量记忆已加载")
        except Exception as e:
            logger.warning("ChromaDB 加载失败，使用 JSON 后备: %s", e)
        _memory = memory

        # 技能系统
        from clawhermes.skills.manager import SkillManager, BackgroundReview, Curator
        skills_dir = Path(data_dir) / "skills"
        skill_manager = SkillManager(skills_dir)

        # Agent（注入 memory + skills）
        agent_cfg = AgentConfig(max_iterations=50)
        _agent = Agent(
            llm_provider=provider,
            tool_registry=registry,
            config=agent_cfg,
            memory_manager=memory,
            skill_manager=skill_manager,
        )
        _skill_manager = skill_manager

        # Background Review（注册到 after_agent_end 钩子）
        reviewer = BackgroundReview(provider, memory, skill_manager)

        def _on_agent_end(**kw):
            try:
                convo = _agent.get_conversation() if _agent else []
                if convo:
                    threading.Thread(target=reviewer.apply, args=(convo,), daemon=True).start()
            except Exception as e:
                logger.warning("Background review trigger failed: %s", e)

        _agent.hooks.register(HookPoint.AFTER_AGENT_END, _on_agent_end)
        _reviewer = reviewer

        # Curator（后台线程）
        curator = Curator(skill_manager)
        _curator = curator

        def _curator_loop():
            while True:
                time.sleep(3600)  # 每小时检查一次
                try:
                    stats = curator.run()
                    if stats.get("archived", 0) > 0 or stats.get("stale", 0) > 0:
                        logger.info("Curator 维护完成: %s", stats)
                except Exception as e:
                    logger.warning("Curator 运行失败: %s", e)

        threading.Thread(target=_curator_loop, daemon=True).start()

        logger.info("✅ Agent 初始化完成: %s (%d tools, skills: %d)",
                     model, len(registry.list()), len(skill_manager.list()))

        # 自动启动已配置的渠道
        _auto_start_channels()

    except Exception as e:
        logger.error("Auto-init failed: %s", e)


def get_agent() -> Agent:
    if _agent is None:
        raise RuntimeError("Agent 未初始化，请先 POST /init 或设置环境变量")
    return _agent


def get_memory() -> MemoryManager:
    if _memory is None:
        raise RuntimeError("Memory 未初始化")
    return _memory


def get_skill_manager():
    if _skill_manager is None:
        from clawhermes.skills.manager import SkillManager
        return SkillManager(Path(_get_data_dir()) / "skills")
    return _skill_manager


def get_reviewer():
    return _reviewer


# === Pydantic Schemas ===

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


# === App ===

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 ClawHermes Gateway 启动")
    _auto_init()
    yield
    logger.info("👋 ClawHermes Gateway 关闭")


app = FastAPI(title="ClawHermes Gateway", version="0.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


# ====== Agent API ======

@app.post("/init")
def initialize(req: InitRequest):
    global _agent, _memory, _skill_manager, _reviewer, _curator
    try:
        api_key = req.api_key or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise HTTPException(400, "请在请求中提供 api_key 或设置 DEEPSEEK_API_KEY")

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
        _reviewer = reviewer

        def _on_end(**kw):
            convo = _agent.get_conversation() if _agent else []
            if convo:
                threading.Thread(target=reviewer.apply, args=(convo,), daemon=True).start()
        _agent.hooks.register(HookPoint.AFTER_AGENT_END, _on_end)

        curator = Curator(sm)
        _curator = curator

        def _curator_loop():
            while True:
                time.sleep(3600)
                try:
                    curator.run()
                except Exception:
                    pass
        threading.Thread(target=_curator_loop, daemon=True).start()

        return {"status": "ok", "model": req.model, "tools": len(registry.list()),
                "skills": len(sm.list()), "chroma": True}

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


# ====== Health ======

@app.get("/health")
def health():
    try:
        a = get_agent()
        tools = len(a.tools.list())
        skills = len(_skill_manager.list()) if _skill_manager else 0
    except Exception:
        tools, skills = 0, 0
    return {
        "status": "ok",
        "version": "0.3.0",
        "uptime_seconds": int(time.time() - _start_time),
        "tools": tools,
        "skills": skills,
        "sessions": len(_sessions),
    }


# ====== Tools ======

@app.get("/tools")
def list_tools():
    agent = get_agent()
    return {"tools": [{"name": t.name, "description": t.description,
                       "parallel_safe": t.parallel_safe} for t in agent.tools.list()]}


# ====== Memory ======

@app.post("/memory/save")
def save_memory(content: str = Query(...), importance: float = 0.5):
    from clawhermes.types import MemoryScope
    get_memory().save(content, MemoryScope.USER, importance)
    return {"status": "ok"}


@app.get("/memory/search")
def search_memory(query: str = Query(...)):
    results = get_memory().search(query)
    return {"results": [{"content": r.content, "importance": r.importance} for r in results]}


# ====== Skills ======

@app.get("/skills")
def list_skills(status: str | None = None):
    sm = get_skill_manager()
    return {"skills": [{"name": s.name, "description": s.description,
                        "category": s.category, "status": s.status,
                        "usage_count": s.usage_count}
                       for s in sm.list(status)]}


@app.post("/skills/create")
def create_skill(name: str = Query(...), content: str = Query(...),
                 description: str = ""):
    sm = get_skill_manager()
    skill = sm.create(name, content, description)
    return {"status": "ok", "name": skill.name}


# ====== Curator ======

@app.post("/curator/run")
def run_curator(dry_run: bool = False):
    global _curator
    if _curator is None:
        from clawhermes.skills.manager import Curator
        _curator = Curator(get_skill_manager())
    stats = _curator.run(dry_run=dry_run)
    return {"status": "ok", "stats": stats}


# ====== Sessions ======

@app.get("/sessions")
def list_sessions():
    return {"sessions": list(_sessions.keys()), "count": len(_sessions)}


# ====== Channels ======

_gateway_manager: "GatewayManager" | None = None


def _agent_callback(text: str, chat_id: str) -> str:
    try:
        return get_agent().chat(text, session_id=f"ch:{chat_id}")
    except Exception as e:
        return f"处理失败: {e}"


def _get_gateway_manager():
    global _gateway_manager
    if _gateway_manager is None:
        from clawhermes.gateway.channels import GatewayManager
        _gateway_manager = GatewayManager(_agent_callback)
    return _gateway_manager


# ====== 飞书 ======

@app.post("/channels/feishu/start")
def start_feishu(app_id: str = Query(...), app_secret: str = Query(...)):
    """启动飞书 Bot（WebSocket 长连接）"""
    from clawhermes.gateway.platforms.feishu import FeishuAdapter
    gm = _get_gateway_manager()
    gm.register("feishu", FeishuAdapter(app_id, app_secret))
    gm.start_all()
    return {"status": "ok", "channel": "feishu"}


@app.post("/channels/feishu/start-from-env")
def start_feishu_from_env():
    """从环境变量启动飞书"""
    app_id = os.getenv("FEISHU_APP_ID") or os.getenv("LARK_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET") or os.getenv("LARK_APP_SECRET")
    if not app_id or not app_secret:
        raise HTTPException(400, "请在环境变量中设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
    return start_feishu(app_id=app_id, app_secret=app_secret)


# ====== 微信 ======

@app.post("/channels/wechat/start")
def start_wechat(corp_id: str = Query(...), corp_secret: str = Query(...),
                 agent_id: int = Query(...)):
    """启动企业微信 Bot"""
    from clawhermes.gateway.platforms.wechat import WeChatAdapter
    from clawhermes.gateway.platforms.wechat_corp import WeChatCorpAdapter
    gm = _get_gateway_manager()
    gm.register("wechat", WeChatAdapter(corp_id, corp_secret, agent_id))
    gm.start_all()
    return {"status": "ok", "channel": "wechat"}


@app.post("/channels/wechat/public/start")
def start_wechat_public(app_id: str = Query(...), app_secret: str = Query(...),
                        token: str = Query(...), encoding_aes_key: str = ""):
    """启动微信公众号"""
    from clawhermes.gateway.platforms.wechat import WeChatPublicAdapter
    gm = _get_gateway_manager()
    gm.register("wechat_mp", WeChatPublicAdapter(app_id, app_secret, token, encoding_aes_key))
    gm.start_all()
    return {"status": "ok", "channel": "wechat_mp"}


@app.post("/channels/wechat/callback")
def wechat_callback(body: dict):
    """微信回调入口"""
    from clawhermes.gateway.platforms.wechat import WeChatAdapter
    from clawhermes.gateway.platforms.wechat_corp import WeChatCorpAdapter
    gm = _get_gateway_manager()
    adapter = gm._adapters.get("wechat")
    if isinstance(adapter, WeChatAdapter):
        return adapter.handle_webhook(body)
    return {"error": "微信适配器未启动"}


# ====== QQ ======

@app.post("/channels/qq/start")
def start_qq(ws_url: str = Query("ws://127.0.0.1:6700"), token: str = ""):
    """启动 QQ Bot（OneBot/go-cqhttp 协议）"""
    from clawhermes.gateway.platforms.qq import QQAdapter
    gm = _get_gateway_manager()
    gm.register("qq", QQAdapter(ws_url, token))
    gm.start_all()
    return {"status": "ok", "channel": "qq", "ws_url": ws_url}


# ====== Telegram ======

@app.post("/channels/telegram/start")
def start_telegram(token: str = Query(...)):
    """启动 Telegram Bot"""
    from clawhermes.gateway.channels import TelegramAdapter
    gm = _get_gateway_manager()
    gm.register("telegram", TelegramAdapter(token))
    gm.start_all()
    return {"status": "ok", "channel": "telegram"}



@app.post("/channels/bridge/start")
def start_bridge():
    """启动 Node SDK 兼容层（微信/飞书官方 SDK）"""
    from clawhermes.gateway.bridge import get_bridge
    bridge = get_bridge()
    health = bridge.health()
    if health.get("status") == "ok":
        return {"status": "ok", "message": "Bridge 已在运行"}
    ok = bridge.start()
    if ok:
        return {"status": "ok", "message": "Bridge 已启动"}
    return {"status": "error", "message": "Bridge 启动失败（需要 Node.js + npm install）"}



# ====== 统一管理 ======

@app.get("/channels")
def list_channels():
    """查看已启动的渠道"""
    gm = _get_gateway_manager()
    return {"channels": list(gm._adapters.keys()), "count": len(gm._adapters)}


@app.post("/channels/webhook/receive")
def webhook_receive(platform: str = Query(...), chat_id: str = Query(...),
                    text: str = Query(...)):
    """Webhook 接收消息"""
    from clawhermes.gateway.channels import WebhookAdapter
    gm = _get_gateway_manager()
    adapter = WebhookAdapter()
    gm.register(platform, adapter)
    adapter.receive(platform, chat_id, text)
    return {"status": "ok", "message": f"已收到来自 {platform} 的消息"}


# ====== Direct Run ======

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("CH_GATEWAY_PORT", "18789")))
