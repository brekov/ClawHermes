"""ClawHermes Gateway - Profile 管理 routes (/profiles)

提供 Profile 创建/列表/详情/删除/绑定 API，所有操作透传到
``GatewayState.profile_manager``。当 ``profile_manager`` 未初始化时返回 503。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import clawhermes.gateway.app as _gw
from clawhermes.profile.config import ProfileConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profiles", tags=["profiles"])


# ============================================================
# 请求 / 响应模型
# ============================================================


class CreateProfileRequest(BaseModel):
    """创建 Profile 请求体"""

    profile_id: str
    llm_provider: str | None = None
    llm_model: str | None = None
    tools_profile: str | None = None


class BindProfileRequest(BaseModel):
    """绑定 user_id → profile_id 请求体"""

    user_id: str
    profile_id: str


# ============================================================
# 辅助函数
# ============================================================


def _require_profile_manager():
    """获取 profile_manager，未初始化时抛 503。"""
    pm = _gw._state.profile_manager
    if pm is None:
        raise HTTPException(503, "Profile 管理器未初始化")
    return pm


def _build_config(req: CreateProfileRequest) -> ProfileConfig:
    """根据请求体构造 ProfileConfig（仅设置非空字段，其余用默认值）"""
    cfg = ProfileConfig.default()
    if req.llm_provider is not None:
        cfg.llm_provider = req.llm_provider
    if req.llm_model is not None:
        cfg.llm_model = req.llm_model
    if req.tools_profile is not None:
        cfg.tools_profile = req.tools_profile
    return cfg


# ============================================================
# 端点
# ============================================================


@router.post("")
async def create_profile(req: CreateProfileRequest):
    """创建新 Profile"""
    pm = _require_profile_manager()
    cfg = _build_config(req)
    try:
        ctx = await pm.create_profile(req.profile_id, config=cfg)
    except ValueError as e:
        # 非法 profile_id 或与现有 profile 冲突
        raise HTTPException(400, str(e)) from e
    except KeyError as e:
        raise HTTPException(409, str(e)) from e

    return {
        "profile_id": ctx.profile_id,
        "status": "created",
        "config": ctx.config.to_dict(),
    }


@router.get("")
def list_profiles():
    """列出所有 Profile"""
    pm = _require_profile_manager()
    items = pm.list_profiles()
    return {"profiles": items, "count": len(items)}


@router.get("/{profile_id}")
def get_profile(profile_id: str):
    """获取 Profile 详情"""
    pm = _require_profile_manager()
    try:
        ctx = pm.get_profile(profile_id)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e

    return {
        "profile_id": ctx.profile_id,
        "data_dir": str(ctx.data_dir),
        "config": ctx.config.to_dict(),
        "initialized": ctx.is_initialized,
    }


@router.delete("/{profile_id}")
async def delete_profile(profile_id: str):
    """删除 Profile（不能删除 default）"""
    pm = _require_profile_manager()
    try:
        deleted = await pm.delete_profile(profile_id)
    except ValueError as e:
        # 尝试删除 default profile
        raise HTTPException(400, str(e)) from e

    if not deleted:
        raise HTTPException(404, f"Profile 不存在: {profile_id}")

    return {"status": "deleted", "profile_id": profile_id}


@router.post("/bind")
def bind_profile(req: BindProfileRequest):
    """绑定 user_id → profile_id"""
    pm = _require_profile_manager()
    try:
        pm.bind_user(req.user_id, req.profile_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except KeyError as e:
        raise HTTPException(404, str(e)) from e

    return {"status": "bound", "user_id": req.user_id, "profile_id": req.profile_id}
