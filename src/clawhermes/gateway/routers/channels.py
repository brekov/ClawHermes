"""ClawHermes Gateway - Channel & webhook routes (/channels, /channels/sessions, webhooks)"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

import clawhermes.gateway.app as _gw

router = APIRouter()


@router.get("/channels")
def list_channels():
    if _gw._state.channel_router is None:
        return {"channels": [], "count": 0}
    return {"channels": _gw._state.channel_router.list_channels()}


@router.get("/channels/sessions")
def list_channel_sessions():
    if _gw._state.channel_router is None:
        return {"mappings": [], "count": 0}
    return {"mappings": _gw._state.channel_router.session_router.list_mappings()}


@router.api_route("/wechat/webhook", methods=["POST"])
async def wechat_webhook(request: Request):
    """个人微信 Webhook 端点（兼容 iLink 回调）"""
    if _gw._state.wechat_adapter is None:
        raise HTTPException(501, "WeChat Adapter 未启用")
    body = await request.json()
    result = await _gw._state.wechat_adapter.handle_webhook(body)
    return result


@router.api_route("/wecom/webhook", methods=["POST"])
async def wecom_webhook(request: Request):
    """企业微信 Webhook 端点"""
    if _gw._state.wecom_adapter is None:
        raise HTTPException(501, "WeCom Adapter 未启用")
    body = await request.json()
    result = await _gw._state.wecom_adapter.handle_webhook(body)
    return result


# ============================================================
# Feishu Webhook（飞书消息事件回调）
# ============================================================

@router.api_route("/feishu/webhook", methods=["POST"])
async def feishu_webhook(request: Request):
    """飞书事件回调端点（需启用 clawhermes-lark）"""
    if _gw._state.feishu_adapter is None:
        raise HTTPException(503, "Feishu Adapter 未启用")
    body = await request.json()
    result = await _gw._state.feishu_adapter.handle_webhook(body)
    return JSONResponse(content=result)


# ============================================================
# QQ Webhook（QQ Bot 事件回调）
# ============================================================

@router.api_route("/qq/webhook", methods=["POST"])
async def qq_webhook(request: Request):
    """QQ Bot 事件回调端点（需启用 clawhermes-qq）"""
    if _gw._state.qq_adapter is None:
        raise HTTPException(503, "QQ Adapter 未启用")
    body = await request.json()
    result = await _gw._state.qq_adapter.handle_webhook(body)
    return JSONResponse(content=result)
