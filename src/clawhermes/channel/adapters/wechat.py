"""
ClawHermes — 微信渠道适配器入口

薄封装，实际实现位于 clawhermes-weixin 子仓库。
pip install -e ./clawhermes-weixin 后自动可用。
支持个人微信（iLink Bot API）和企业微信（Webhook）。
"""
from __future__ import annotations

try:
    from clawhermes_weixin import (
        WeChatAdapter,
        WeComAdapter,
        create_wechat_adapter,
        create_wecom_adapter,
    )
except ImportError:
    WeChatAdapter = None
    WeComAdapter = None

    def create_wechat_adapter(*args, **kwargs):
        raise ImportError("clawhermes-weixin 未安装，请运行: pip install -e ./clawhermes-weixin")

    def create_wecom_adapter(*args, **kwargs):
        raise ImportError("clawhermes-weixin 未安装，请运行: pip install -e ./clawhermes-weixin")


__all__ = [
    "WeChatAdapter",
    "WeComAdapter",
    "create_wechat_adapter",
    "create_wecom_adapter",
]
