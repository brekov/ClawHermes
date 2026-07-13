"""ClawHermes Gateway - Session routes (/sessions, /sessions/{id})"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

import clawhermes.gateway.app as _gw
from clawhermes.agent.exceptions import SessionNotFoundError

router = APIRouter()


@router.get("/sessions")
def list_sessions(limit: int = 50):
    if _gw._state.session_mgr is None:
        return {"sessions": [], "count": 0}
    sessions = _gw._state.session_mgr.list_sessions(limit=limit)
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    if _gw._state.session_mgr is None:
        raise HTTPException(500, "Session 管理器未初始化")
    try:
        info = _gw._state.session_mgr.get_session(session_id)
        messages = _gw._state.session_mgr.get_messages(session_id)
        return {"session": info, "messages": messages}
    except SessionNotFoundError as e:
        raise HTTPException(404, str(e))


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    if _gw._state.session_mgr is None:
        raise HTTPException(500, "Session 管理器未初始化")
    if _gw._state.session_mgr.delete_session(session_id):
        return {"status": "ok"}
    raise HTTPException(404, f"会话不存在: {session_id}")
