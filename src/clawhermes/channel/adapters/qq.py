"""
ClawHermes — QQ 渠道适配器入口

薄封装，实际实现位于 clawhermes-qq 子仓库。
pip install clawhermes-qq 后自动可用。

支持 QQ Bot API：
  - WebSocket 长连接事件订阅
  - HTTP API 消息发送（文本/Markdown）
  - 私聊（C2C）+ 群聊 @机器人
"""
from __future__ import annotations

try:
    from clawhermes_qq import (
        QQAdapter,
        QQConfig,
        QQEventType,
        create_qq_adapter,
    )
except ImportError:
    QQAdapter = None
    QQConfig = None
    QQEventType = None

    def create_qq_adapter(*args, **kwargs):
        raise ImportError("clawhermes-qq 未安装，请运行: pip install clawhermes-qq")


__all__ = [
    "QQAdapter",
    "QQConfig",
    "QQEventType",
    "create_qq_adapter",
]
