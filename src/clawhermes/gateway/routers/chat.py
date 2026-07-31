"""ClawHermes Gateway - Chat routes (/chat, /chat/stream)"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import clawhermes.gateway.app as _gw
from clawhermes.agent.exceptions import (
    ClawHermesError,
    LLMConnectionError,
    LLMError,
    LLMRateLimitError,
    SessionNotFoundError,
)
from clawhermes.channel.adapter import ChannelType

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    model: str


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, profile_id: str | None = None):
    # PR5b: profile_id 查询参数 — 指定时通过 profile_manager 解析对应 Agent
    # 未指定（None）或 profile_manager 未初始化时保持原有行为（用 _state.agent）
    pm = _gw._state.profile_manager
    if profile_id and pm is not None:
        try:
            ctx = pm.resolve_profile(None, profile_id)
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        agent = ctx.agent or _gw._state.get_agent()
    else:
        agent = _gw._state.get_agent()

    if _gw._state.session_mgr is None:
        raise HTTPException(500, "Session 管理器未初始化")

    if req.session_id:
        try:
            _gw._state.session_mgr.get_session(req.session_id)
        except SessionNotFoundError:
            raise HTTPException(404, f"会话不存在: {req.session_id}")
        sid = req.session_id
    else:
        sid = _gw._state.session_mgr.create_session()

    try:
        if _gw._state.channel_router:
            response = await _gw._state.channel_router.route_message(
                content=req.message,
                channel_type=ChannelType.REST,
                user_id="rest_user",
                session_id=sid,
                metadata={"profile_id": profile_id} if profile_id else None,
            )
        else:
            response = await asyncio.to_thread(agent.chat, req.message, session_id=sid)

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


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """流式聊天 — SSE (text/event-stream) 端点。

    使用 Agent.chat_stream() 生成 SSE 事件流：text | tool_call | tool_result | error | done。
    """
    agent = _gw._state.get_agent()
    if _gw._state.session_mgr is None:
        raise HTTPException(500, "Session 管理器未初始化")

    if req.session_id:
        try:
            _gw._state.session_mgr.get_session(req.session_id)
        except SessionNotFoundError:
            raise HTTPException(404, f"会话不存在: {req.session_id}")
        sid = req.session_id
    else:
        sid = _gw._state.session_mgr.create_session()

    import json as _json

    async def _event_stream():
        try:
            async for event in agent.chat_stream(req.message, session_id=sid):
                event_name = event.get("event", "message")
                event_data = event.get("data", "")
                if not isinstance(event_data, str):
                    event_data = _json.dumps(event_data, ensure_ascii=False)
                yield f"event: {event_name}\ndata: {event_data}\n\n"
        except LLMRateLimitError as e:
            retry = getattr(e, 'retry_after', 60)
            yield f"event: error\ndata: LLM 速率限制，{retry}秒后重试\n\n"
        except LLMConnectionError as e:
            yield f"event: error\ndata: LLM 连接失败: {e}\n\n"
        except LLMError as e:
            yield f"event: error\ndata: LLM 调用失败: {e}\n\n"
        except ClawHermesError as e:
            yield f"event: error\ndata: Agent 错误: {e}\n\n"
        except Exception as e:
            logger.exception("Unexpected error in chat/stream")
            yield f"event: error\ndata: 内部错误: {e}\n\n"

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
