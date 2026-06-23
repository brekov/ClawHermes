"""
ClawHermes — 飞书渠道适配器入口

薄封装，实际实现位于 clawhermes-lark 子仓库。
pip install clawhermes-lark 后自动可用。
"""
from __future__ import annotations

try:
    from clawhermes_lark import (
        LarkAdapter as FeishuAdapter,
    )
    from clawhermes_lark import (
        LarkConfig as FeishuConfig,
    )
    from clawhermes_lark import (
        LarkEventType as FeishuEventType,
    )
    from clawhermes_lark import (
        create_lark_adapter as create_feishu_adapter,
    )
except ImportError:
    FeishuAdapter = None
    FeishuConfig = None
    FeishuEventType = None

    def create_feishu_adapter(*args, **kwargs):
        raise ImportError("clawhermes-lark 未安装，请运行: pip install clawhermes-lark")


__all__ = [
    "FeishuAdapter",
    "FeishuConfig",
    "FeishuEventType",
    "create_feishu_adapter",
]
