"""ClawHermes Gateway - DM pairing routes (/dm/pair)"""
from __future__ import annotations

import os
import time

from fastapi import APIRouter, HTTPException

import clawhermes.gateway.app as _gw
from clawhermes.agent.exceptions import ClawHermesError

router = APIRouter()


# ════════════════════════════════════════════════════════
# DM 配对安全 (M3.6d)
# ════════════════════════════════════════════════════════


def _require_admin(admin_key: str):
    """管理员权限校验（通过 ADMIN_KEY 环境变量）"""
    _admin = os.getenv("ADMIN_KEY", "")
    if not _admin:
        raise HTTPException(501, "ADMIN_KEY 未配置")
    if admin_key != _admin:
        raise HTTPException(403, "需要管理员权限")


@router.post("/dm/pair/generate")
def dm_pair_generate(user_id: str, platform: str, device_family: str = "", admin_key: str = ""):
    """管理员生成 DM 配对码"""
    _require_admin(admin_key)
    if _gw._state.pairing_manager is None:
        raise HTTPException(500, "Pairing Manager 未初始化")
    try:
        req = _gw._state.pairing_manager.generate_code(user_id, platform, device_family)
        return {
            "code": req.code,
            "challenge": req.challenge,
            "user_id": req.user_id,
            "platform": req.platform,
            "expires_in": int(req.expires_at - time.time()),
        }
    except Exception as e:
        raise HTTPException(400, f"生成配对码失败: {e}")


@router.post("/dm/pair/verify")
def dm_pair_verify(code: str, response: str, user_id: str | None = None):
    """用户提交配对码 + 挑战响应进行验证"""
    if _gw._state.pairing_manager is None:
        raise HTTPException(500, "Pairing Manager 未初始化")
    try:
        req = _gw._state.pairing_manager.verify_code(code, response, user_id)
        return {
            "status": req.status.value,
            "user_id": req.user_id,
            "platform": req.platform,
        }
    except ClawHermesError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/dm/pair/status")
def dm_pair_status(user_id: str):
    """查询配对状态"""
    if _gw._state.pairing_manager is None:
        raise HTTPException(500, "Pairing Manager 未初始化")
    result = _gw._state.pairing_manager.get_pairing_status(user_id)
    if result is None:
        raise HTTPException(404, f"未找到配对状态: {user_id}")
    return result


@router.get("/dm/pair/list")
def dm_pair_list(admin_key: str = ""):
    """列出全部已配对用户和 pending 配对请求"""
    _require_admin(admin_key)
    if _gw._state.pairing_manager is None:
        raise HTTPException(500, "Pairing Manager 未初始化")
    return {
        "paired": _gw._state.pairing_manager.list_paired_users(),
        "pending": _gw._state.pairing_manager.list_pending_requests(),
    }


@router.delete("/dm/pair/{user_id}")
async def dm_pair_revoke(user_id: str, admin_key: str = ""):
    """撤销配对"""
    _require_admin(admin_key)
    if _gw._state.pairing_manager is None:
        raise HTTPException(500, "Pairing Manager 未初始化")
    if _gw._state.pairing_manager.revoke_pairing(user_id):
        return {"status": "ok", "user_id": user_id}
    raise HTTPException(404, f"配对用户未找到: {user_id}")
